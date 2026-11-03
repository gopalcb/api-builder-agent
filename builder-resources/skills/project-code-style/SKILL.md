---
name: project-code-style
description: Match API Builder coding conventions in generated Python, agent, Angular and CDK code. Use alongside a concrete coding task, not for unrelated repositories.
---

Inspect the nearest source and AGENTS.md. Python uses short module/function docstrings, top-level imports, simple type annotations, two blank lines between top-level definitions and one between logical steps. Catch specific errors only at recovery/translation boundaries. Keep validation at the boundary and trust validated data. Do not create ARCHITECTURE.md or code-map.yaml.
New agents contain agent.py and output-schema.py, register in runtime/registry.py, compose PromptChain and reuse shared AgentBuilder via AgentRuntime. Prompts stay short and inline; no per-agent utils copies. See ../../templates/agent/ for a coding skeleton.
Angular uses standalone components, separate HTML, signals, guarded lazy routes and headerNavigation. Reuse shared theme controls, typography, backgrounds and 4px radius. Do not fabricate backend calls or claim session drafts are saved.
CDK uses the executable ../../templates/serverless-cdk/ starter; scope IAM grants to actual handler operations, retain data, avoid account-specific constants. Test/synth before reporting a generated project as valid.
