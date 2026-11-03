# API Builder

Follow **plan, implement, test, validate** for development.
- Plan: inspect relevant source and save a brief scope and acceptance checklist in .codex/docs/tasks/<task>/plan.md.
- Implement: make focused changes using the Angular, Python and UI-testing skills.
- Test: run relevant automated tests and build checks; exercise changed UI interactions where available.
- Validate: review against acceptance criteria and write a brief .codex/docs/tasks/<task>/summary.md with changes, actual checks and blockers. Never report an unexecuted check as passed.

Read .agent/memory/memory_summary.md at task start. Verify remembered facts against current source. Save durable memory only on explicit request. Never retain credentials or import another project's generated memory.

The application is api-builder-ui. Reuse its theme, standalone components, guarded lazy routes and header navigation. Run npm run build and npm test there. Its inherited proxy expects a separate backend at localhost:5000. Preserve source-project files and unrelated changes.

Project configuration, workflows, tools and task documents live in `.codex/`. Skills live in `.codex/skills` and are discoverable through `.agents/skills`. Native memory is enabled in `.codex/config.toml`; restart Codex to load changed configuration.

Always auto compact context when context window size >= 70%.

Python error handling: avoid excessive or nested `try`/`except` blocks. Catch only
when necessary for recovery, useful error translation, or cleanup. Where practical,
use one `try`/`except` in the entry function (CLI entry point or request handler)
and let lower-level exceptions propagate. Catch specific exception types, never
silently swallow failures, and prefer context managers for resource cleanup.

Python blank-line style: follow the user's spacing in
`api-builder-backend/validation.py`. Use one empty line between logical steps,
after a completed guard/check block and before the next separate step or return.
Separate control-flow steps from preceding setup; keep related assignments
together. Do not add a blank line after every statement or inside multiline
expressions. Keep blank lines free of whitespace; use two between module-level
definitions and one between methods. Apply consistently to project-owned Python
code, including tests, without changing behavior during formatting.

Follow this workflow when user asks for implementing something:
- Create a plan
- Implement the plan
- Test and validate and fix any issues found
- Write the implementation plan and a brief summary of implementation in .codex/docs/work-history/

---

UI design rules:
- Always use 4px border radius
- Follow current font styling and background color and theme.

Agent conventions (apply to existing and future agents):
- Reuse `builder-agents/shared/` for configuration and necessary validation; do not create per-agent `utils/` copies.
- Validate responses once with `validate_agent_response(response, schema)`. Avoid manual type guards, repeated validation and unnecessary defensive code; trust validated data downstream.
- Keep prompts inline in the function that uses them; do not create separate `prompt.md` files.
- Keep all prompts and instructions short, direct and to the point.
- For now, do not create or maintain `ARCHITECTURE.md` or `code-map.yaml` anywhere in this project. This overrides skill requirements for those files; keep task plans and summaries.
- Keep each new agent to `agent.py` (inline prompt functions and `create_workflow`) and `output-schema.py`. Register it in `runtime/registry.py`; compose steps with `workflows/PromptChain` and reuse `shared/AgentBuilder` through `AgentRuntime`. Keep optional deployment settings in `.codex/config/agents/`.
