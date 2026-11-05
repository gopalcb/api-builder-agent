# API Builder Agent: from an entity model to a tested local API

API Builder Agent is a local-first workbench for designing and building APIs. An Angular workspace keeps entities, endpoints, access settings, documents, and build activity together. A Flask backend saves those decisions and calls small, focused builder agents.

The useful unit of work is a project: a saved API design that can move through review, implementation, testing, and export.

[Project repository](https://github.com/gopalcb/api-builder-agent) · [Watch the demo](https://1drv.ms/v/c/cb8c3cac74469fbc/IQCO688UzI0LQq7YokJ2XspGARNya53c8egrHBySqUNORAc?e=oECXIF)

## 1. Start with a small product API

Imagine a product service with a name, price, and stock count. Define the entity, review its generated attributes, and save the operations it needs.

```text
Product entity
  name + price + stock
          |
          v
Reviewed endpoint configuration
  list / get / create / update / delete / sell
          |
          v
Explicit Build
  implement -> test -> archive
          |
          v
Run locally or download the ZIP
```

The saved entity definition is metadata. It does not immediately create a new database table in the builder. The generated container template stores entity records as JSON documents in SQLite, using the saved attributes for validation.

The template also includes a `sell` operation. It checks the requested quantity and available stock inside a transaction, then updates the record. This makes the example more useful than a collection of empty route stubs.

## 2. Keep design state outside the conversation

The Angular UI sends requests to the Flask backend under `/api`. Project-scoped requests identify their project with `X-Project-ID`; SQLAlchemy models hold the configuration and revisions.

```text
Angular project workspace
          |
          | /api + X-Project-ID
          v
Flask routes and services <----> SQLite project state
          |
          +--> bounded agent worker
          |
          +--> build checks and ZIP artifacts
```

For example, entity generation reads the current revision and definition before asking the agent for changes. Persistence uses that revision to avoid overwriting a newer edit. Build artifacts have a separate fingerprint: if the configuration or starter source changes, the user must build again before downloading or publishing the artifact.

This gives a long model call a clear relationship to the project state it was asked to change.

## 3. Give each agent one job

The trusted runtime registry contains five builders:

- **Entity builder:** drafts and reviews attributes and directed relationships.
- **Search builder:** proposes embedding, semantic, lexical, or hybrid search configuration.
- **RBAC builder:** proposes roles, explicit grants, and allow/deny examples.
- **Infrastructure builder:** recommends an AWS serverless design.
- **API implementation builder:** returns reviewed record-service and validation source for the container build.

Each agent has an `agent.py` workflow and an `output-schema.py` contract. The entity workflow shows the pattern:

```python
def create_workflow() -> PromptChain:
    return PromptChain(draft_definition, review_definition)
```

The first step drafts a complete definition. The second receives the original context and the draft, checks requirements, and returns the complete corrected definition. `PromptChain` passes copies between steps; it does not require a shared, persistent conversation.

## 4. Separate model decisions from tool execution

The shared runtime constructs a fresh Deep Agents graph for each prompt step. It uses LangChain's model interface, `StateBackend` for in-memory graph storage, and `ToolStrategy` for structured output. `AgentRuntime` validates the resulting response against the selected schema.

```text
Registered agent
      |
      v
PromptChain: draft -> review
      |
      v
AgentRuntime -> fresh Deep Agents graph
                         |
                         v
                   CodexChatModel
                         |
                         v
                   openai-codex SDK
                         |
                         v
               Structured model decision
                         |
                         v
              Harness tool execution
                         |
                         v
              Schema-validated result
```

`CodexChatModel` adapts the signed-in Codex account to LangChain messages. Its SDK session uses an ephemeral, read-only workspace with approvals denied. The adapter translates model-requested tool calls; the harness executes them. The model session is not given responsibility for arbitrary repository edits.

The worker process has a timeout and process-group cleanup. The graph has its own recursion limit. These bounds address different failure modes: elapsed time and runaway graph steps.

## 5. Turn the reviewed design into an artifact

An explicit Build starts from the container template and the saved project snapshot. For projects with entities, the implementation builder supplies the record-service and validation source. The build service checks Python syntax and JSON, then tests agent-written source in a disposable Docker container with networking disabled, a read-only filesystem, and resource limits.

```text
Saved project + container template
                |
                v
Implementation builder
  record_service.py + validation.py
                |
                v
Syntax and container runtime checks
                |
                v
Configuration fingerprint still matches?
        yes -> save ZIP
         no -> reject stale build
```

The resulting bundle includes the application, Docker configuration, project snapshot, OpenAPI document, and saved project documents. The generated service runs on `127.0.0.1:8080` when started through its Compose configuration. The builder backend itself uses port `5000`.

## 6. Know what the local build actually enables

The container supports configured operations and local mock authentication. `/auth/token` issues a short-lived test bearer token for authenticated endpoints. It is not a production OAuth or Cognito deployment.

Search, RBAC, and caching proposals remain configuration snapshots in this build. Saving them does not install a vector store, attach an authorizer, or activate Redis. The infrastructure builder's recommendation is separate from the container artifact; the container build does not deploy AWS resources.

The workspace also includes document editing, load testing, activity logs, and OpenTelemetry configuration. Their purpose is to keep delivery and inspection close to the design, while leaving the actual runtime checks visible.

## Explore the implementation

The article describes source behavior reviewed on 2026-11-05. It does not claim a fresh live Codex run or a production deployment.

- [Project build service](../api-builder-backend/services/project_build_service.py): snapshots, implementation, tests, fingerprints, and archives.
- [Entity workflow](../builder-agents/entity-builder/agent.py): the draft/review chain.
- [Shared graph builder](../builder-agents/shared/agent_builder.py): graph construction and structured output.
- [Runtime and Codex adapter](runtime.md): worker execution and model integration.
- [Builder agents guide](builder-agents.md): the registered builders and shared modules.
- [Backend guide](api-builder-backend.md): HTTP contracts, persistence, and project services.
- [Container template](../builder-resources/templates/container-api/README.md): local startup and mock-token usage.
