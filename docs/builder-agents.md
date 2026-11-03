# Builder agents and shared LangChain infrastructure

[`builder-agents/`](../builder-agents/) contains five narrowly scoped agents and one shared implementation layer. Each agent owns only two files:

```text
<agent-name>/
├── agent.py          Inline prompt functions and create_workflow().
└── output-schema.py  JSON Schema for the structured result.
```

The shared runtime, model adapter, and process lifecycle are documented in [Runtime architecture](runtime.md). Backend consumers are documented in [API Builder backend](api-builder-backend.md).

## Design principles

- Agent code proposes structured data or bounded source changes; it does not deploy resources.
- Prompts remain inline in the function that uses them.
- `PromptChain` orders steps; Deep Agents owns each model/tool loop.
- Every prompt step receives a fresh graph with isolated `StateBackend` state.
- `ToolStrategy` turns the JSON Schema into the structured-output tool contract.
- Responses are validated once by `validate_agent_response()` and trusted downstream.
- Application tools must be explicitly registered and injected; the default agents use none.
- Agent files are loaded only through the allowlist in `runtime/registry.py`.

## Agent inventory

| Registry name | Workflow | Output contract | Primary consumer |
| --- | --- | --- | --- |
| `entity-builder` | Draft, then review | `EntityDefinition` | Entity configuration generation |
| `search-builder` | Propose, then review with a type-constrained schema | `SearchConfiguration` | Search proposal endpoint |
| `rbac-builder` | Draft, then review | `RbacProposal` | RBAC generation service |
| `infrastructure-builder` | Propose, then review | `InfrastructureProposal` | Infrastructure planning endpoint |
| `api-implementation-builder` | One implementation step | `ApiImplementation` | Explicit project Build workflow |

## Agent execution pattern

A normal two-step agent is a pair of ordinary Python functions:

```python
def draft(context: dict, previous: dict | None, runtime: AgentRuntime) -> dict:
    return runtime.run("Draft the requested result. Return Result only.", context)


def review(context: dict, previous: dict, runtime: AgentRuntime) -> dict:
    return runtime.run(
        "Review the draft against the request. Return corrected Result only.",
        {"context": context, "draft": previous},
    )


def create_workflow() -> PromptChain:
    return PromptChain(draft, review)
```

The first step's `previous` value is `None`. Every later step receives the prior validated result. A review is a second model judgment, not proof of business correctness; backend services still enforce domain invariants before persistence.

## `entity-builder`

Files:

- [`agent.py`](../builder-agents/entity-builder/agent.py)
- [`output-schema.py`](../builder-agents/entity-builder/output-schema.py)

### Purpose

Generates a complete replacement definition for one existing entity while preserving the entity ID and valid existing details. It is the only agent with a conventional draft/review workflow where separate prompt functions have distinct responsibilities.

### Input context

The project-scoped flow builds context containing:

- `entity_id`;
- the user's description/prompt;
- the current entity and saved definition;
- `existing_entities`, used to constrain relationship targets.

The legacy entity endpoint provides a similar context around the older `Entity` models.

### Workflow

1. `draft_definition()` asks for a complete set of attributes and outgoing relationships.
2. `review_definition()` checks the draft against the original request, fixes duplicate names/types/directions, and preserves the original entity ID.

The prompt requires useful inferred attributes, schema-approved types/cardinalities, existing target IDs only, and no SQL, source code, or Markdown.

### Output contract

`EntityDefinition` contains:

- `entity_id`: positive integer;
- `attributes`: 1–100 named attributes with `data_type`, `nullable`, and description;
- `relationships`: up to 100 outgoing relationships with target ID and cardinality.

Allowed data types are `string`, `text`, `integer`, `float`, `decimal`, `boolean`, `date`, `datetime`, `uuid`, and `json`. Allowed relationship types are `one_to_one`, `one_to_many`, `many_to_one`, and `many_to_many`.

### Backend safeguards

After schema validation, `configuration_service.generate_validated_definition()` rejects duplicate attribute names, mismatched entity IDs, and relationships to entities outside the current project. It then applies optimistic revision locking before saving.

## `search-builder`

Files:

- [`agent.py`](../builder-agents/search-builder/agent.py)
- [`output-schema.py`](../builder-agents/search-builder/output-schema.py)

### Purpose

Produces reviewable route configuration for one of four search modes without provisioning a store, indexing data, or claiming a live integration.

### Supported modes

| Request type | Ranking | Embedding value |
| --- | --- | --- |
| `embedding` | `none` | Required object |
| `semantic` | `vector` | Required object |
| `regular` | `lexical` | `null` |
| `hybrid` | `rrf` | Required object |

### Workflow and dynamic schema

`configure_search()` runs twice: the second invocation receives the first proposal as `draft`. Before each run it deep-copies the default schema and narrows the contract based on `context["type"]`:

```python
schema = deepcopy(runtime.output_schema)
schema["properties"]["ranking"] = {"const": ranking_for_type}

if context["type"] == "regular":
    schema["properties"]["embedding"] = {"type": "null"}
else:
    schema["properties"]["embedding"] = embedding_object_schema
```

This makes invalid combinations impossible to accept as structured output rather than relying only on prompt wording.

### Output contract

`SearchConfiguration` records summary, source, fields, optional embedding model/dimensions/chunking, ranking, request/response descriptions, implementation steps, and unresolved requirements. The prompt also calls for bounded results, tenant/access filtering before retrieval, idempotent indexing, and no sensitive text in logs.

## `rbac-builder`

Files:

- [`agent.py`](../builder-agents/rbac-builder/agent.py)
- [`output-schema.py`](../builder-agents/rbac-builder/output-schema.py)

### Purpose

Proposes explicit role-to-route grants for the supplied route catalog. It does not modify authentication settings, create AWS groups, or enforce authorization at runtime.

### Workflow

1. `draft_permissions()` creates roles, explicit grants, notes, questions, and allow/deny examples.
2. `review_permissions()` removes unknown roles/routes, public-route grants, duplicate groups, and broad or ambiguous privileges.

The prompt forbids wildcard routes, implicit admin behavior, role inheritance, and grants for public routes.

### Output contract

`RbacProposal` contains:

- up to 20 roles with lowercase IDs, group names, descriptions, and `create_group` flags;
- up to 500 unique `{role, route}` grants;
- notes and unresolved questions;
- up to 50 allow/deny cases.

### Backend safeguards

`validation.validate_rbac_semantics()` checks unique role IDs and groups, canonical unique route shapes, valid role/route references, no grants on public routes, and valid test-case references. `rbac_service.generate_configuration()` keeps identity and routes fixed while merging the unsaved proposal.

## `infrastructure-builder`

Files:

- [`agent.py`](../builder-agents/infrastructure-builder/agent.py)
- [`output-schema.py`](../builder-agents/infrastructure-builder/output-schema.py)

### Purpose

Creates a minimal, explicitly undeployed AWS serverless recommendation from project entities, caching policy, environment, and free-form requirements.

### Workflow

`propose_infrastructure()` runs twice. On the first call `draft` is `None`; on the second it receives the first proposal for review and correction.

The baseline architecture in the prompt is:

- CloudFront with a private S3 origin and OAC for static assets;
- API Gateway HTTP API;
- Cognito JWT authorization;
- one entity-prefixed Lambda per saved entity;
- DynamoDB on-demand;
- least-privilege per-function IAM, logging, alarms, and environment isolation.

SQS, SNS, and Redis are optional booleans that must be justified. The prompt also recognizes that API Gateway response caching requires a REST API rather than the default HTTP API.

### Output contract

`InfrastructureProposal` contains a summary, `{sqs, sns, redis}` decisions, 1–12 recommendations, and up to 12 unresolved requirements. It contains no executable infrastructure code, credentials, AWS identifiers, or invented costs.

## `api-implementation-builder`

Files:

- [`agent.py`](../builder-agents/api-implementation-builder/agent.py)
- [`output-schema.py`](../builder-agents/api-implementation-builder/output-schema.py)

### Purpose

Implements reviewed entity and endpoint configuration inside the existing generated container API. Unlike the proposal agents, it returns source code—but only during an explicit Build operation.

### Input and workflow

`project_build_service.run_project_check()` supplies:

- the complete saved configuration snapshot;
- the existing trusted source for record service, validation, models, routing, tests, app setup, telemetry, and observability documentation.

`implement_api()` is a one-step workflow. Its prompt requires complete replacement source for only:

- `services/record_service.py`;
- `validation.py`.

It must preserve public signatures, metadata-driven CRUD/sell behavior, SQLite transaction safety, validation, logging, tests, and the supplied OpenTelemetry runtime. It must not implement infrastructure, external authentication, dependencies, or other integrations.

### Output contract and execution safety

`ApiImplementation` has exactly two bounded strings: `record_service` and `validation`. The backend compiles all generated Python and runs agent-written source only in a disposable Docker image with:

- no network;
- read-only filesystem;
- all capabilities dropped;
- `no-new-privileges`;
- CPU and memory limits;
- bounded temporary filesystems;
- a test command and timeout.

The previously persisted build remains unchanged if the generated implementation fails.

## The `shared/` folder

[`builder-agents/shared/`](../builder-agents/shared/) is imported as the top-level `shared` package. It owns reusable implementation that must not be copied into individual agents.

### `agent_builder.py`

`AgentBuilder` receives a LangChain-compatible model and an optional trusted tool registry. `build()` validates the prompt/schema, resolves configured tools, constructs fresh middleware, and creates a Deep Agents graph:

```python
harness = create_deep_agent(
    name=settings.name,
    model=self.model,
    system_prompt=prompt,
    tools=tools,
    backend=StateBackend(),
    middleware=[TodoListMiddleware()] if settings.planning else [],
    response_format=ToolStrategy(schema=deepcopy(schema), handle_errors=False),
)
return harness.with_config(
    recursion_limit=settings.recursion_limit,
    run_name=settings.name,
)
```

`handle_errors=False` lets structured-output errors propagate to the runner instead of hiding them in an unbounded model retry.

### `agent_response_validator.py`

This module centralizes JSON Schema boundary validation:

- `validate_agent_response()` validates and returns the original decoded value;
- `validate_agent_assets()` requires a non-empty prompt and valid object schema with `title` and `description`;
- `validate_agent_tools()` resolves unique tool names, rejects missing registrations, and prevents a tool from shadowing the structured output tool name.

Downstream code should trust validated results rather than adding repeated manual type guards.

### `configuration.py`

`AgentSettings` is a frozen Pydantic model with these fields:

| Field | Default | Constraint |
| --- | --- | --- |
| `name` | `builder-agent` | 1–100 characters |
| `model_name` | `None` | non-empty when supplied |
| `planning` | `true` | strict boolean |
| `recursion_limit` | `20` | 2–100 |
| `tools` | empty tuple | unique trusted names |

`load_agent_settings()` applies defaults, optional JSON, environment overrides, then explicit Python overrides. Unknown fields are rejected.

### `logging_service.py`

Provides one correlated, line-oriented JSON application log without serializing requests, prompts, model responses, credentials, or exception messages.

Key pieces:

- `configure_logging()` atomically reserves a daily run file or joins a trusted parent file;
- `LogStep` records start/completion/failure and duration while preserving exceptions;
- `log_function` traces synchronous function boundaries;
- `worker_environment()` carries log-file and correlation metadata to the child process;
- `configure_worker()` restores that metadata in the runner;
- request hooks add `X-Request-ID` and clear context after each Flask request.

Only fields in `ALLOWED_FIELDS` reach log records. Failure stacks contain file/function/line locations but no local values or error message text.

### `telemetry_service.py`

Implements project-configurable OpenTelemetry HTTP tracing without mutating the global tracer provider.

Important pieces:

- validated resource attributes and parent-based ratio sampling;
- local OTLP/HTTP exporter with environment credentials and proxies disabled;
- a bounded cache of providers keyed by immutable configuration;
- Flask request start/finish/teardown hooks;
- route templates instead of raw URLs, bodies, headers, or query strings;
- `X-Trace-ID` response correlation;
- a real test export that reports collector acceptance.

### `__init__.py`

Marks the reusable package and documents its responsibility. Public imports currently use the concrete shared modules directly.

## Configuration files

Optional deployment settings live under [`.codex/config/agents/`](../.codex/config/agents/). Current JSON files exist for `entity-builder`, `rbac-builder`, and `api-implementation-builder`; search and infrastructure agents use `AgentSettings` defaults plus environment overrides.

Configuration affects graph construction only. It does not contain prompts, schemas, provider credentials, or arbitrary Python paths.

## Adding a new agent

Use the existing convention:

```text
builder-agents/example-builder/
├── agent.py
└── output-schema.py
```

Then:

1. Define short inline prompt functions with `(context, previous, runtime)`.
2. Return `PromptChain(first_step, ...)` from `create_workflow()`.
3. Define a strict object schema with `title`, `description`, required fields, bounded collections/strings, and `additionalProperties: false` where appropriate.
4. Register the agent in `runtime/registry.py` with a distinct environment prefix.
5. Add a settings JSON only when the defaults are insufficient.
6. Add tests for workflow order, valid output, invalid structured output, fresh state, and downstream domain invariants.

Do not create a per-agent `utils/` folder, separate prompt file, agent base class, auto-discovery mechanism, or second LangChain agent loop.

## Verification

Relevant tests:

- [`test_agent_workflows.py`](../api-builder-backend/tests/test_agent_workflows.py)
- [`test_agent_configuration.py`](../api-builder-backend/tests/test_agent_configuration.py)
- [`test_agent_response_validation.py`](../api-builder-backend/tests/test_agent_response_validation.py)
- [`test_entities.py`](../api-builder-backend/tests/test_entities.py)
- [`test_search_configuration.py`](../api-builder-backend/tests/test_search_configuration.py)
- [`test_rbac.py`](../api-builder-backend/tests/test_rbac.py)
- [`test_infrastructure_plan.py`](../api-builder-backend/tests/test_infrastructure_plan.py)
- [`test_project_actions.py`](../api-builder-backend/tests/test_project_actions.py)

Run:

```bash
.venv/bin/python -m pytest api-builder-backend/tests -q
```
