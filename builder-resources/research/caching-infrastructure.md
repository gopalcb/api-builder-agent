# Caching and infrastructure: agent-driven workflow

Research date: 2026-11-02. Recommendation: humans supply intent and review changes; agents propose typed plans; deterministic backend code renders approved templates and runs validation. Keep generation separate from deployment. This document proposes future backend endpoints; none are implemented by the navigation previews.

## GB Systems reuse inspection

Inspected local source under `/Users/gopalcbala/Desktop/WORK_N_PROJECTS/gb-systems/softrobots-systems/aws-infrastructure/cdk/`:

| Existing module | Finding | Reuse decision |
| --- | --- | --- |
| data_stack.py / DocumentDataStack | CfnInclude of ../document-data.yaml, retaining logical IDs | Useful migration/adoption pattern; not a standalone table/bucket library |
| identity_stack.py / PortalIdentityStack | CfnInclude of ../auth.yaml | Useful existing-identity ownership pattern; do not clone existing pools/domains |
| edge_stack.py / PortalEdgeStack | CfnInclude of ../portal-edge.yaml and telemetry-specific origin/identity parameters | Useful in-place CloudFront migration pattern; not portable as-is |
| telemetry_stack.py / TelemetryStack | L2 private encrypted S3 and Lambda DockerImageFunction; project runtime integration | Reuse design ideas, not project application assets/permissions/constants |
| requirements.txt | aws-cdk-lib 2.273.0 and constructs 10.5.0 | Starter pins these existing versions; synthesis tests verify used APIs |

Also located CDK directories in `gb-systems/markdown-file-sharing-network-across-agents/aws-infrastructure/cdk` and `gb-systems/gb-portfolio-aws`; these were not audited module by module. No reusable general-purpose module was established from the inspected subset. This is not a claim that none exists elsewhere. Original sources were not modified or copied into the starter.

AWS offers a maintained [Lambda-to-DynamoDB Solutions Construct](https://docs.aws.amazon.com/solutions/latest/constructs/aws_lambda_dynamodb.html). Prefer ordinary CDK L2 constructs initially: they fit the Python project and keep generated grants and resource relationships visible. Consider Solutions Constructs for combinations that match requirements exactly; validate their defaults and version compatibility first.

## Caching choices

| Layer | Recommended use | Rules for the builder |
| --- | --- | --- |
| Browser / HTTP headers | Static versioned assets; deliberate public read routes | Explicit Cache-Control; private data defaults to no-store |
| CloudFront | S3 assets and separately reviewed public API reads | minTTL=0; include all response-varying query/header/cookie inputs; versioned asset URLs preferred |
| API Gateway REST cache | Existing REST API requiring managed stage/method response caching | Paid managed cache; explicit cache keys/TTL/invalidation and encryption; not an HTTP API setting |
| Lambda process memory | Disposable immutable metadata | Per-execution-environment optimization only; never durable/shared state or an authorization source |
| DynamoDB cache table | Low-frequency reusable computations where persistent storage is acceptable | Enforce expires_at in application reads; TTL deletion is asynchronous, not an expiry guarantee |
| ElastiCache Serverless | Measured repeated low-latency reads requiring a shared cache | Separate optional module after workload/cost/connectivity/auth review; never silently add VPC/network dependencies |

[API Gateway comparison](https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-vs-rest.html) confirms REST response caching and its absence from HTTP APIs. The starter uses HTTP API for a small JWT-protected Lambda route and deliberately has no API response cache. [CloudFront cache policy documentation](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/cache-key-understand-cache-policy.html) warns that a positive minimum TTL overrides no-store/private headers; hence zero minimum TTL. Forwarding credentials alone does not establish safe cache isolation.

[DynamoDB TTL documentation](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/TTL.html) is the operational reference for eventual expiry cleanup; recheck before implementing a cache adapter. [ElastiCache documentation](https://docs.aws.amazon.com/AmazonElastiCache/latest/dg/WhatIs.html) describes serverless options; region, engine and connection support must be verified for the chosen deployment. No node-based cache or ECS is included.

For each policy store route ID/method, source revision, layer, public/private classification, TTL and stale window, response-varying inputs, tenant partition, invalidation events and rationale. Reject shared caching for authenticated/private routes in the initial release. Do not treat a token in a key as sufficient revocation handling. Authorization decision caching has its own expiry/revocation semantics and is not response caching.

Mutation invalidation should be an idempotent event after a committed write, using an outbox or DynamoDB Streams where applicable. Prefer entity-versioned keys; define bounded stale behavior, retry/DLQ, stampede control, jitter and fail-open to the authoritative read on cache outage. Never fail open on authorization failure. Track hit/miss rate, stale serves, errors and p95 latency without logging tokens or raw cache payloads.

## UI proposal

Reuse Routing/RBAC's compact 35/65 editor/review layout, shared controls, signals and 4px radius. Keep the current font/background. Two pages share a job-status/revision component rather than duplicating orchestration.

Caching: import saved routes/access rules; show route selection, freshness requirement and prompt. Agent proposes eligible layer, keys, TTL and invalidation. Review cards show per-route decisions, reasons, blockers and a before/after diff. Advanced settings expose validated fields, not free-form cloud code. Primary action Generate proposal; subsequent actions Save configuration and Validate. Distinguish unsaved proposal, saved revision, validated revision and applied policy.

Infrastructure: import saved entity/routing/auth/RBAC/cache revisions. Ask for project/stage, account/region, existing-versus-new identity/storage, service selection and intent. Show resources/dependencies, IAM changes, retention/replacement effects and cost drivers. Provide Generate proposal, Review code, Validate and Export. Deployment belongs to an explicit later action for a concrete target and artifact hash; exporting must never deploy.

Both pages preserve inputs on failure; disable duplicate submissions; show queued/running/reviewing/validating states, cancellation and retry for recoverable failures. Keep drafts across navigation, use server revisions for persistence, reject conflicts with a reload/merge choice, provide keyboard-reachable errors and narrow stacked layouts. Empty screens explain prerequisites; missing identity/account/schema requirements remain visible and block affected operations. Current previews intentionally offer no fake controls.

## Backend and agent ownership

Reuse runtime/AgentRuntime, builder-agents/shared/AgentBuilder, shared validate_agent_response and workflows/PromptChain. Introduce caching-builder and infrastructure-builder only when implementing the workflows: each owns agent.py and output-schema.py, registers in runtime/registry.py, keeps prompts inline and reuses shared configuration. Do not duplicate utils. The runtime already owns response validation; inspect that path before adding another validator.

1. Backend authenticates workspace/project access, validates the request and snapshots input revisions. Agent receives only sanitized authoritative context and service catalog.
2. Draft agent proposes typed intent; review pass checks relationships and unresolved requirements. Treat route text/prompts as untrusted data, never executable instructions.
3. Deterministic policy validator checks access isolation, supported services, naming, API/cache compatibility, quotas and references. Model schema validity alone is insufficient.
4. Renderer maps approved resource kinds to versioned templates. Allowlisted files, path confinement, no generated shell, no arbitrary imports or model-generated dependencies. Sandbox tests/synth without AWS credentials or network. Do not run arbitrary uploaded CDK.
5. Backend records artifact digest, template/dependency versions, input/output revisions, validation logs and provenance. UI displays artifacts/status; agents never determine authorization or deployment approval.

Proposed API (future): POST /api/caching/jobs and /api/infrastructure/jobs accepts project_id, input_revision, prompt, idempotency_key and allowlisted settings; returns 202 plus job_id. GET /api/builder-jobs/:id returns state/progress/artifacts/errors; POST /:id/cancel requests cooperative cancellation. GET/PUT /api/caching and /api/infrastructure load/save configurations using expected_revision (409 on conflict). POST /api/infrastructure/:revision/validate produces a report; GET /:revision/export returns the exact validated artifact. Authorization applies to every job, revision and download, not just frontend guards.

Job schema: id, project_id, owner, kind, input_revision, template_version, state, progress, attempt, created_at, updated_at, artifact_digest, result, error. States: queued → drafting → reviewing → validating → ready; failed/cancelled are terminal. Retries create bounded attempts; stale completions cannot overwrite newer input revisions. Persist jobs/results in the current backend DB and use a durable worker queue, never a Flask request thread for long generation. For an AWS runner use SQS + DLQ/Lambda or Step Functions for longer orchestration; align timeouts and retries, make tasks idempotent and store large artifacts in private S3.

Infrastructure proposal schema: schema_version, project, stage, resources[{id, kind, settings, depends_on}], routes, permissions, outputs, requirements, rationale. Resource kinds initially cloudfront/s3/http_api/lambda/dynamodb/cognito/logs; add sqs/eventbridge/step_functions/acm/route53 only with tested renderers. additionalProperties=false, bounded arrays/strings, enum values and cross-reference checks. Cache schema uses the policy fields above with the same strict bounds. Distinguish imported resources from owned resources and disallow mutation/deletion of imported resources by default.

Future deploy jobs use a separate least-privilege execution role, concrete account/region, validated artifact hash and reviewed CloudFormation change set. Block replacement/deletion of retained state without an explicit migration decision. Reject stale validation after edits. Record stack events and actual outputs; ready/synthesized is not deployed. Provide rollback guidance without implying data migrations are automatically reversible.

## Implementation sequence and checks

1. Add persistence/revision schemas and job lifecycle, reuse existing backend auth; test ownership, conflict, idempotency, cancellation and restart recovery.
2. Add cache agent and deterministic eligibility validator; test two-user/tenant isolation, query variants, no-store, expiry and invalidation failures.
3. Add infrastructure agent and deterministic renderer against this starter; test malicious names/paths, unknown kinds, IAM scope, retained state, dependency graph and synthesis.
4. Build editor/review screens against real jobs; test loading/errors, keyboard, desktop/narrow layouts, polling cleanup, stale responses and draft preservation.
5. Add credential-separated export/deploy integration only when requested; live tests verify JWT failures, actual data permissions, CORS, CDN private-origin access and applied cache behavior.

The current deliverable completes the resource foundation, navigation entry points and research. It does not implement these future job APIs or deploy any AWS resources.

## Implemented caching presets (2026-11-02 follow-up)

The Caching screen now edits and persists one project policy with optimistic revisions and exports templates. Choices are bounded process-local route caching, Redis cache-aside and encrypted API Gateway REST stage caching. Public GET routes only; literal paths and TTL 1–3600 seconds. UI confirmation declares public data; it is not a substitute for application authorization review. Existing Routing drafts are session state, so this version accepts an explicit route path rather than presenting them as authoritative deployed routes.

[Redis cache-aside guidance](https://redis.io/docs/latest/develop/use-cases/cache-aside/) supports TTL plus invalidation after committed writes. The adapter uses SET EX, bounded connection timeouts and fallback reads on Redis failure. Memory/Redis responses bypass identity-bearing requests and noncacheable responses; full queries and headers partition keys. Memory is worker-local; Redis needs separately configured runtime credentials. The export includes a runnable public Flask example. TTL-bounded eventual consistency is explicit; no stampede/strict invalidation guarantee.

[AWS cache settings](https://docs.aws.amazon.com/apigateway/latest/developerguide/api-gateway-caching.html) specify a 3600-second maximum TTL and 1 MiB cached response limit. The Gateway template enables caching only for its selected GET method and uses encryption; declared query keys map to method and integration settings. It synthesizes a standalone public MOCK API sample, not an attachment to an existing API. Replace the mock with a reviewed integration and all response-varying keys before deployment. Save/export never creates AWS or Redis resources.

Implemented endpoints: GET/PUT /api/caching and POST /api/caching/export; all require X-Project-ID. Persistence uses ProjectCachingConfiguration; saved revisions scope exported namespaces. Other job/agent APIs described above remain proposals. The management API inherits the repository's local-only authorization boundary and must not be exposed publicly without authentication/authorization.
