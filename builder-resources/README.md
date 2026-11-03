# Builder resources

Reusable resources for API Builder agents. The serverless starter is executable; agent skeletons require domain schemas and registration. Caching/infrastructure UI backend workflows remain a researched design.

```bash
python3 builder-resources/generate.py --project orders-api --stage dev --output /tmp/orders-api-dev
cd /tmp/orders-api-dev
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m unittest discover -s tests
.venv/bin/python app.py
```

The generator refuses existing destinations and invalid names. Project names allow 32 characters; stage names 12; lowercase letters/digits with single hyphens. It writes project.json without rewriting code. Run generation tests with `python3 -m unittest discover -s builder-resources -p 'test_*.py'`.

- [Serverless generation skill](skills/serverless-generation/SKILL.md)
- [Caching design skill](skills/cache-planning/SKILL.md)
- [Code style skill](skills/project-code-style/SKILL.md)
- [CDK starter](templates/serverless-cdk/README.md): CloudFront/OAC/private S3, HTTP API/JWT/Lambda, DynamoDB, Cognito, logs.
- [Agent skeleton](templates/agent/agent.py): copy both files to builder-agents/<name>, specialize schema/prompt and register in runtime/registry.py. These are templates, not active agents.
- [Research and GB Systems reuse map](research/caching-infrastructure.md)

Skills are intentionally stored here for resource consumers; they are not automatically registered as global Codex skills. Pass their paths to agents. Keep credentials, deployment outputs, caches and generated projects outside this resource library.

## Functional caching templates

Use the Caching page to select Route caching, Redis caching or API Gateway caching,
edit a public GET policy, save a project revision and export its integration ZIP.
[Template instructions](templates/caching/README.md) describe local runtime testing,
Redis setup and Gateway synthesis. Saving does not deploy a cache.

## Local observability in generated container APIs

The project build includes saved OpenTelemetry settings, the shared tested tracing
runtime, pinned SDK dependencies and Jaeger Compose service. The implementation
agent receives this context and preserves it while implementing records/validation.
See [observability research](research/observability.md) and the generated
[localhost guide](templates/container-api/OBSERVABILITY.md). Cloud serverless
scaffolding remains separate from this local container integration.
