---
name: serverless-generation
description: Generate a named AWS serverless CDK project from API Builder resources when asked for infrastructure scaffolding. Excludes ECS and deployment unless separately requested.
---

Read ../../README.md and ../../research/caching-infrastructure.md. Inspect the supplied API, entity and identity revisions; identify missing account/region and access requirements without inventing them.
Run ../../generate.py with project, stage and a new destination. Preserve the starter's private storage, retained state, JWT authorization and scoped permissions. Add only required serverless services. Use AWS CDK L2 constructs; consult the GB Systems reuse map before adapting existing modules. Never copy account IDs, domains, credentials or generated outputs.
Keep project style from ../project-code-style/SKILL.md. Extend inline prompts and schema contracts through AgentRuntime/PromptChain when integrating an agent; validate each response once through shared validation. Do not execute model-supplied shell or arbitrary code.
Run generated unittest tests and synth; report artifacts and actual checks. Show unresolved requirements and infrastructure diff before any requested deployment. A synth is not a deployment verification.
