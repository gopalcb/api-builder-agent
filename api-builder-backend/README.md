# Entity API

Flask and SQLAlchemy store entity definitions, generated attributes and directed
relationships. Generation runs a LangChain agent inside the Deep Agents harness,
using a custom chat model backed by the official `openai-codex` Python SDK and
your existing ChatGPT Codex sign-in. Requires Python 3.11+ (tested with 3.14).

From the project root (the environment and requirements are shared):

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
codex login status
.venv/bin/python api-builder-backend/app.py
```

The API binds `127.0.0.1:5000`. If needed, run `codex login` privately first.
The SDK inherits the same user's Codex home/login; no API key is required.
The sibling `builder-agents/`, `runtime/`, `workflows/` and `.codex/config/agents/`
directories must remain available.

```bash
curl -X POST http://127.0.0.1:5000/create-entity \
  -H 'Content-Type: application/json' \
  -d '{"name":"Customer","description":"A buyer"}'

curl -X POST http://127.0.0.1:5000/create-entity \
  -H 'Content-Type: application/json' \
  -d '{"name":"Order","description":"A customer purchase"}'

# Substitute the IDs returned above; these examples assume a new database.
curl -X POST http://127.0.0.1:5000/generate-entity-attributes \
  -H 'Content-Type: application/json' \
  -d '{"entity_id":2,"prompt":"Add a required decimal total and a many_to_one customer relationship to Customer entity 1."}'

curl http://127.0.0.1:5000/entities/2
```

All routes also exist under `/api` for the Angular proxy. Responses wrap the
persisted definition in `{"entity": ...}` and include `id`, `name`, `description`,
`revision`, `attributes`, and `relationships`. Creation returns 201; generation
and reads return 200. Errors use `{"error":"..."}`: 400 invalid payload, 404 missing
entity, 409 duplicate name or stale generation, 502 invalid/failed generation,
504 timeout, 500 database failure. Malformed JSON returns 400, wrong content type
415, and requests larger than 64 KiB return 413.

Payload validation currently checks only that the request is a JSON object and
returns it unchanged. Field/type/length/unknown-field checks and trimming were
removed for now. Required fields are still consumed by routes/services, and
existing database constraints remain. Generated output still follows the agent
JSON schema; extra semantic identity/name/target checks were removed.

Regeneration replaces attributes and outgoing relationships for one entity;
failed generation preserves the previous definition. Create relationship targets
first. These are metadata records, not dynamically created SQL tables. There are
no migration or deployment authentication facilities yet; use this as a local API.

Configuration (environment variables):

| Variable | Default | Purpose |
| --- | --- | --- |
| `DATABASE_URL` | `sqlite:///entities.db` | SQLite lives at `instance/entities.db`; other SQLAlchemy databases require their driver. |
| `ENTITY_AGENT_TIMEOUT` | `120` | Worker deadline in seconds; timed-out worker group is terminated. |
| `ENTITY_AGENT_MODEL` | Codex configured default | Optional account-accessible model override. |
| `ENTITY_AGENT_CONFIG` | `.codex/config/agents/entity-builder.json` | Optional trusted settings-file override. |
| `ENTITY_AGENT_RECURSION_LIMIT` | `20` | Per-prompt graph bound from 2–100; timeout covers the whole workflow. |
| `CODEX_HOME` | Codex default | Inherited login/configuration directory; do not place credentials in the repo. |

Tests from the project root (no model calls):
`.venv/bin/python -m pytest -q api-builder-backend/tests`.
Opt-in live integration check: `.venv/bin/python api-builder-backend/live_smoke.py` (uses your signed-in
Codex account and a disposable database). This makes real model calls and is
separate from the SDK-mocked workflow tests.
Tables are initialized on startup. Use migrations before evolving a persistent
deployed schema. Start the server under the same account that is signed into Codex.

SDK reference: [Official Codex SDK documentation](https://developers.openai.com/codex/sdk/).
Harness: [Deep Agents create_deep_agent](https://reference.langchain.com/python/deepagents/graph/create_deep_agent).

Agent generation uses a draft -> review prompt chain. Each step runs a fresh
Deep Agents graph with the shared `AgentBuilder` and `AgentRuntime`; the backend
starts `runtime/runner.py entity-builder`. Both prompts share the process deadline.
The entity folder contains only `agent.py` and `output-schema.py`. The backend
loads that same output contract before persistence.

Settings precedence is defaults < optional JSON < environment < programmatic
overrides. `.env` files are not loaded automatically. The previous `prompt_file`
and `output_schema_file` settings are removed; prompts and schemas live in code.

See [Agent workflows](../workflows/README.md) for adding agents, prompt steps,
model/tool injection and later routing or parallel workflows. The HTTP worker
accepts only registered agents and no caller-defined tools.

## Entities screen persistence

The screen saves through `POST /api/entities` with `{"name":"Customer"}` and
loads through `GET /api/entities`. POST returns `{"entity":{"id":1,"name":"Customer"}}`
(201); GET returns `{"entities":[...]}` (200). The default SQLite file is
`instance/entities.db` at the workspace root. Startup creates the `entities` table
with exactly `id INTEGER PRIMARY KEY` and a required, unique `name` (SQLite
NOCASE). No definition text is stored. The route reads name unchanged from the
JSON object and ignores other catalog fields. Non-object payloads return 400,
duplicate names return 409, and database errors return 500.

This screen catalog is independent of the existing richer generation tables;
its IDs must not be passed to the generation routes as generation entity IDs.
Start the backend on port 5000 alongside `npm start` in `api-builder-ui` so the
Angular proxy can reach it. Existing rows survive application restarts.

## Search configuration proposals

`POST /api/generate-search-configuration` accepts `type` (`embedding`, `semantic`,
`regular`, `hybrid`), a static `/route/path` and a 1–4000 character `prompt`.
It returns `{ "configuration": ... }` after the registered `search-builder`
draft/review chain. The backend adds available entity names as context, not as
proof of an indexed data source. Schema enforcement runs once per model response
in AgentRuntime. Output is descriptive metadata; it is never executed or deployed.
The UI retains configurations only in memory until reload. Duplicate paths are
checked within search drafts; reconciliation with other route drafts is a future
deployment responsibility.

Uses the existing Codex sign-in. `SEARCH_AGENT_TIMEOUT` defaults to 180 seconds;
`SEARCH_AGENT_MODEL`, `SEARCH_AGENT_CONFIG` and `SEARCH_AGENT_RECURSION_LIMIT`
use the shared settings loader. No provider keys or new dependencies are required.
Errors: 400 invalid intent, 502 generation/runtime failure, 504 worker timeout.
Timeout terminates the worker process group; UI inputs and previous configuration
remain available for retry.

## RBAC configuration

`services/rbac_service.py` manages one local workspace's reviewed RBAC snapshot in
`rbac_configuration`, with revision-based conflict protection. `/api/rbac` supports
GET and PUT; `/api/rbac/generate`, `/preview`, and `/export` accept POST. The same
routes are available without `/api`. Writes take `{revision, configuration}`;
generation adds `prompt`, preview adds `roles` and the exact method/path `route` key,
and export takes only `revision`. The new table is created on backend startup.

The RBAC screen imports session Routing and saved Cognito drafts. Resolve all
HTTP methods, add or generate roles, select explicit grants, and save before export.
Saved snapshots survive reload; unsaved edits survive in-app navigation only.
Unlinked saved snapshots and changes to imported source drafts are identified.
New routes receive no implicit grants. Public routes are not constrained by RBAC.

The registered `rbac-builder` runs draft/review through the existing Codex-backed
runtime and shared worker. `RBAC_AGENT_TIMEOUT` defaults to 120 seconds;
`RBAC_AGENT_MODEL`, `RBAC_AGENT_CONFIG` and `RBAC_AGENT_RECURSION_LIMIT` use the
shared configuration conventions. Proposals never replace saved configuration
until an explicit save. Invalid output, timeouts and revision conflicts preserve it.

Exports contain `rbac-config.yaml`, `cloudformation.yaml`, `schema.json`,
`policies.cedar`, and an integration README. Python compiles policies from the
validated matrix; it does not execute model-generated YAML or code. CloudFormation
uses Cognito and Verified Permissions with a STRICT Cedar schema, client validation
and group mapping. Blank pool/client IDs become required deployment parameters.
Only groups explicitly marked new are provisioned. User membership is managed
separately. Limits: 100 routes, 20 roles, 500 grants, 4000 prompt characters and the
existing 64 KiB request-body limit.

**Configuration/export is not deployment or enforcement.** Preview is a matrix
lookup, not a live AWS decision. Follow the exported README to attach an authorizer
to a generated API and prevent backend bypass. No tenant/row ownership or builder
admin authorization is added. Keep this builder backend local until its own
management endpoints have authentication and administration authorization.

Checks: `.venv/bin/python -m pytest -q api-builder-backend/tests` from the root;
`.venv/bin/cfn-lint <export-directory>/cloudformation.yaml` validates export structure.
Live AWS policy evaluation and deployment require separate integration verification.

## Active projects

`GET /api/projects` returns `projects` (id, name, summary) and `default_project_id`.
`POST /api/projects` accepts a required name (1–100 trimmed characters) and summary
(1–4000). Names are case-insensitively unique. Default is created once at startup;
legacy UI entity names and RBAC snapshot are copied into its scoped tables without
deleting the old records. The legacy definition-generation model remains separate.

All UI `/api/entities`, `/api/rbac` and `/api/generate-search-configuration`
requests require `X-Project-ID` identifying an existing project. Entity names and
RBAC revisions are isolated per project, and search generation receives only that
project's entity names. Missing/unknown IDs return 400. This selects local workspace
context; it is not user/tenant authorization. Standalone legacy entity-generation
endpoints are unchanged. Projects do not yet add persistence to routing/auth/search
drafts; those retain per-project session state in the UI.

### Project documents

`GET /api/project-documents` lists generated Markdown for `X-Project-ID`.
`GET /api/project-documents/<id>` returns content, revision and etag.
`PUT` at the same URL accepts `{content, revision, etag}` (48 KB content limit),
persists an edit in `ProjectDocument`, and rejects stale writes with 409.
The source is the saved project overview/entity catalog and, when present,
RBAC/caching snapshots. It does not read legacy unscoped entity schemas or
in-memory routing drafts. Edits override the generated text without changing
configuration. There is no external document upload or LLM generation in this flow.
The Angular Docs page reuses the existing telemetry list and Markdown editor.

### Project lifecycle and artifacts

- `PUT /api/projects/<id>` updates name/summary. `DELETE` hides a project through `ProjectArchive`; original metadata remains for administrative recovery. Restore by removing its archive row after explicit operator intent. Archived names stay reserved.
- `POST /api/projects/<id>/test` checks the saved snapshot, starter Python/JSON syntax and the trusted starter health handler.
- `POST /api/projects/<id>/build` runs those checks and stores a ZIP in `ProjectBuild`. This is a starter/configuration bundle, not generated CRUD or a deployed application. CDK dependencies/synthesis/deployment remain separate.
- `GET /api/projects/<id>/download` returns a current build; stale/missing builds return409. `GET .../openapi` describes the actual starter endpoint. Swagger UI assets are bundled locally through Angular.
- `POST /api/projects/<id>/github` accepts owner (optional), name, token and create (boolean). Create makes a private repository; otherwise an existing initialized repository is required. Generated paths update on its default branch, unrelated files remain, and refs never force-update. GitHub branch protection may reject the push. Credentials live only in the request; only repository destination is stored. After uncertain network errors inspect GitHub before retrying.

GitHub contract: https://docs.github.com/en/rest/repos/repos and https://docs.github.com/en/rest/git/trees. Swagger installation/configuration: https://swagger.io/docs/open-source-tools/swagger-ui/usage/installation/ and https://swagger.io/docs/open-source-tools/swagger-ui/usage/configuration/ (checked2026-11-02).

## Temporary anonymous users

Opening the builder loads `/api/projects`, which assigns a random unused ID from
`user-1000` through `user-9999` and stores it in the `user_id` cookie for one year.
The cookie is HttpOnly, SameSite=Lax, and Secure on HTTPS. No ID is rendered in
the UI. `users` contains `id`, `username` (the same ID), `email` and `password`;
the latter two stay empty. No authentication endpoints are added. The frontend
currently enables its existing no-login mode in `app.config.ts`.

Each visitor gets a separate Default project. `project.user_id` owns every
workspace, and names are unique per owner. Project lists, edits, archives,
configuration, builds, downloads and repository actions check the cookie owner.
Catalog responses disable shared caching. Reuse cookies when calling the API
from scripts (for example curl's cookie jar options).

Restart the backend to load these changes. On startup, the old SQLite project
table is migrated while preserving project IDs and related records. Previously
shared projects are assigned to a separate anonymous owner; they are not claimed
by the first visitor. Recovering those projects requires an explicit local owner
reassignment. Non-SQLite legacy schemas require a manual migration.

This is temporary identification, not authentication: the plain four-digit ID
can be replaced by a client. Clearing or losing the cookie starts a new identity;
there is no account recovery or cross-device login. The ID space holds 9000 users;
allocation returns 503 when full, while existing cookies continue working.
Legacy standalone entity-generation routes retain their existing local behavior;
they are not the project configuration APIs.

## Local connection settings

Settings, beside the project's dropdown, chooses the backend connection for this
browser. Default mode uses the site's existing `/api` proxy. Direct mode is
available only on localhost and connects to the selected port using the same
hostname and protocol as the site. Start that backend first, for example:

```bash
PORT=5001 .venv/bin/python api-builder-backend/app.py
```

Test connection calls `/api/health`, checks database availability and verifies the
API Builder service marker without creating a user. Save and reload tests before
persisting the preference, then reloads Projects. Invalid/unreachable settings do
not replace the saved connection. Reset defaults changes only the popup's draft.
A different database can have a different catalog; unsaved page drafts are lost
on apply. The popup changes the connection, not the running server's bind port.

The backend permits credentialed browser requests only from the same loopback
hostname and HTTP(S) scheme on another port. Preflights do not create users or
perform project actions; remote cross-origin requests are rejected. Requests via
a deployed same-origin reverse proxy must preserve the original Host/scheme.


## Local product API workflow

Anonymous users are persisted in `users` and identified by the HttpOnly `user_id`
cookie. The browser stores only the active project ID in localStorage. This is a
localhost workspace identity, not production authentication.

Create a project and Product entity. Enter a definition (id UUID, name string,
price decimal, stock integer), then Generate configuration. The existing Codex
agent generates/reviews attributes and saves them under that project's entity.
Endpoints persist automatically on add/edit/remove. Choose Product and Sell to
add POST /product/sell; its quantity request decrements stock atomically.

Test and Build verify the container application, then Download project provides
Dockerfile, compose.yaml, application code, schemas and tests. Run
`docker compose up --build -d` in the downloaded directory. It listens on
http://127.0.0.1:8080 and keeps SQLite data in a named Docker volume.
POST /auth/token returns a local mock bearer token. Swagger can execute the local
API after Authorize; remote browser origins are rejected. Production auth and
cloud infrastructure generation are excluded. Search/RBAC/cache proposals are
not implemented runtime policies; unsupported endpoint operations block Build.

Verified sample: `generated-artifacts/product-e2e/`. Run its tests with
`docker compose exec api python -m unittest discover -s tests`.

## Application logs

The builder and agent workers write JSON lines to root `logs/log-yyyy-mm-dd-N`
(no extension). N starts at 1 each local calendar day and increments atomically
for each new application process. Workers spawned by the builder join its current
file; independent CLI agents allocate their own run. A long-running process keeps
its startup file. Record timestamps are UTC.

INFO records include request/function start and completion, workflow draft/review,
model calls, validation, rendering, tests, archive and persistence. ERROR records
include failed functions and HTTP 4xx/5xx results. `trace_id`, `span_id`,
`parent_span_id`, `pid`, durations and safe stack locations support flow analysis.
Responses expose `X-Request-ID`, matching `trace_id`. Filter a run with
`rg '<request-id>' logs/log-yyyy-mm-dd-N`.

The shared implementation is `builder-agents/shared/logging_service.py`; backend
services import `services/logger_service.py`. Generated bundles embed the same
implementation as `services/logger_service.py`, use project-local `logs/`, and
bind it to `/app/logs` in Docker. Arguments, return values, request bodies, query
values, prompts, model responses, cookies, tokens and raw exception messages are
not logged. Logs are ignored by Git and excluded from Docker contexts/artifacts.
There is no automatic retention deletion or mid-run rotation.

## Real local load testing

The Load testing page calls project-owned `GET /api/load-testing` to restore the saved configuration, current run and most recent report. `POST /api/load-testing` starts a background Docker run and returns 202; the UI polls the GET endpoint. Both require the existing anonymous cookie and `X-Project-ID`. A file lock prevents concurrent runs for one project, including across backend processes. Interrupted runs are marked on the next read and their named container is cleaned up.

Start Docker and deploy the generated API with local mock authentication enabled. Use its local origin, such as `http://127.0.0.1:8080`. The runner maps loopback to `host.docker.internal` inside Docker; this was verified on Docker Desktop for Mac. Native Linux needs a target reachable through Docker's host gateway. UI and backend ports 4200/5000 are rejected. The pinned runner is `locustio/locust:2.47.0` ([official Docker usage](https://docs.locust.io/en/stable/running-in-docker.html)); first run may download the image.

The current scenario tests saved GET list endpoints. Enter `Test all read endpoints` or exact paths such as `GET /product/list`. Unsupported endpoints, mutations and unrecognized freeform scenarios fail validation. Generated local bearer tokens remain in runner memory. Limits are 100 concurrent users, 100 users/second and 3,600 seconds. Duration includes ramp-up. A passed report means nonzero requests, every selected endpoint exercised, no request/contract failures and a successful runner exit; it is not a performance SLO certification.

Files are project-specific:

```text
generated-artifacts/load-testing/project-<id>/
  configuration.json
  locustfile.py               # only rewritten when content changes or missing
  run.json
  last-report.json           # latest finished run, including failed runs
  runs/<run-id>/
    locustfile.py             # immutable scenario snapshot for this run
    report.json
    results_stats.csv
    results_failures.csv
    results_exceptions.csv
    runner.log
```

JSON reports contain UTC start/completion timestamps, submitted configuration, endpoint metrics, percentile data, code fingerprint/reuse state and result status. The UI displays local time. JSON writes are atomic; previous reports remain visible while a new run executes. Load settings and target URL do not regenerate unchanged code. The template and selected endpoint contracts determine code content. Authentication/setup failures with no measurements are reported as failed, never as a zero-latency success. Root structured logs trace generation, execution and persistence; runner output stays beside each report. No report retention policy is applied automatically.

## Local observability

From the workspace root run `docker compose -f compose.observability.yaml up -d`.
Open More → Observability & Tracing, enable tracing and save the active project's
settings. Send test trace verifies OTLP acceptance. View the returned trace ID at
http://127.0.0.1:16686. Subsequent selected-project API requests use the saved
policy without restarting the builder; disabled is the default. Existing JSON
logs correlate to real request trace IDs. Traces exclude payloads/headers/query
values. Jaeger data is in memory, not durable. No metrics or log export is enabled.
Generated builds carry the same runtime and saved policy; see OBSERVABILITY.md
inside the ZIP for Compose endpoints and port conflict handling.

## Entity review, live logs and explicit implementation

Generate configuration invokes the entity draft/review workflow only. Its prompt receives the current saved attributes/relationships, so a follow-up request can update the schema. It does not invoke the implementation agent or create a build. Attribute Edit/Delete saves a revised configuration through `PUT /api/entity-configurations/<id>` with `{revision, attributes}`. The server validates the shared entity schema and duplicate names, preserves relationships and prompt, and rejects stale revisions with 409. Changing a schema invalidates previous build downloads.

Generation POST optionally accepts a UUID `run_id`. The UI polls `GET /api/entity-configurations/<id>/logs/<run_id>?cursor=0`, carrying the selected project header. The backend checks entity ownership and returns safe timestamp/level/function/event/step/duration/error-type fields from the existing structured log. Generation metadata under `instance/entity-generations/<project>/<entity>/<run>.json` records file offset/status; operational events remain in the normal `logs/log-yyyy-mm-dd-N` file. Worker processes inherit generation/project/entity correlation. Prompts, response payloads, credentials and model reasoning are not exposed by this endpoint. The UI keeps at most 200 events per entity while the page is open, and performs a final fetch even if another entity starts generating.

Build on a configured project invokes registered `api-implementation-builder` through the shared AgentRuntime/PromptChain and existing Codex authentication. It receives the saved configuration and existing API source, and returns complete `services/record_service.py` and `validation.py`. Authentication, routers, database scaffolding, logger, dependencies, Docker files and tests remain from the trusted template. No infrastructure code is generated. The implementation source is syntax-checked without execution, then tested inside a disposable Docker image/container with no network, read-only root, no host bind mounts, dropped capabilities and temporary writable test/log directories. Only a successful tested artifact is persisted. A configuration change during implementation rejects the stale result; a failed implementation preserves the previous build. Empty projects retain their starter-build behavior because there is no entity implementation to generate.

The model deadline defaults to 300 seconds (`IMPLEMENTATION_AGENT_TIMEOUT` Flask config), with separate bounded container build/test deadlines. The UI allows up to ten minutes for Build and displays the implementation/Docker-check stage. Input source/configuration fingerprints determine readiness, while the ZIP contains the actual agent-produced files. Test does not start the implementation agent.
