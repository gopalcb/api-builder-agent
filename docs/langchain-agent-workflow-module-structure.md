# Agent workflows

Agents contain prompt functions and an output schema. Shared code builds and runs
them. The entity agent starts with **draft -> review**; each step receives the
original request and the previous result, and returns a validated dictionary.

```text
builder-agents/
  entity-builder/
    agent.py                 # prompt functions + create_workflow()
    output-schema.py         # OUTPUT_SCHEMA dictionary
  shared/
    agent_builder.py         # AgentBuilder: fresh Deep Agents graph
    configuration.py         # immutable settings and precedence
    agent_response_validator.py
runtime/
  agent_runtime.py           # AgentRuntime: invoke and validate one step
  codex_model.py             # existing Codex ChatGPT-login model adapter
  registry.py                # trusted local agent registrations
  runner.py                  # common JSON stdin/stdout worker
workflows/
  prompt_chain.py            # PromptChain: ordered functions
.codex/config/agents/
  entity-builder.json        # optional deployment settings
```

## Add a prompt step

Define functions in your agent's `agent.py`; prompts stay inline:

```python
from runtime.agent_runtime import AgentRuntime
from workflows.prompt_chain import PromptChain


def draft(context: dict, previous: dict | None, runtime: AgentRuntime) -> dict:
    """Draft a result from the original request."""
    return runtime.run("Draft the requested result. Return the output schema.", context)


def review(context: dict, previous: dict, runtime: AgentRuntime) -> dict:
    """Correct the draft using the original requirements."""
    return runtime.run(
        "Review the draft against the request. Return the corrected result.",
        {"request": context, "draft": previous},
    )


def create_workflow() -> PromptChain:
    """Choose the prompt sequence."""
    return PromptChain(draft, review)
```

Use `PromptChain(draft)` for one step. Add another function to the constructor for
another step. The first `previous` is `None`; later steps receive the prior output.
Each step gets a copy of the original context. An exception stops the workflow.
Call `runtime.run(prompt, context, schema=INTERMEDIATE_SCHEMA)` when a step needs
a different output shape. Keep the last step on the agent's final output schema.
A step can do deterministic Python work too; use the shared validator when it
introduces data that has not already been validated.

## Add an agent

1. Create `builder-agents/my-agent/agent.py` using the functions above.
2. Add `output-schema.py` with a JSON Schema dictionary:

   ```python
   OUTPUT_SCHEMA = {
       "title": "Summary",
       "description": "A short summary.",
       "type": "object",
       "properties": {"summary": {"type": "string"}},
       "required": ["summary"],
       "additionalProperties": False,
   }
   ```

3. Add one entry to `AGENTS` in `runtime/registry.py`:

   ```python
   "my-agent": AgentRegistration(
       ROOT / "builder-agents" / "my-agent", env_prefix="MY_AGENT",
   ),
   ```

4. Run from the project root:

   ```bash
   echo '{"text":"Summarize this"}' | .venv/bin/python runtime/runner.py my-agent
   ```

The registry executes only these trusted local Python files, including the
hyphenated `output-schema.py`; request data cannot select import paths. Importing
an agent file must not call a model. No config file is required. For deployment
settings, provide a third file under `.codex/config/agents/` and pass its path as
`AgentRegistration(..., config_path=...)`. This is registration, not auto-discovery.

## Inject dependencies

The design uses **composition**, a graph **factory**, and **constructor injection**.
There is no DI container or agent base class to subclass. `AgentBuilder` accepts a
LangChain-compatible model and a tool registry; `AgentRuntime` accepts the builder,
settings and schema. Model selection belongs at construction, not inside prompts.

```python
from runtime.agent_runtime import AgentRuntime
from runtime.codex_model import CodexChatModel
from runtime.registry import AGENTS
from shared.agent_builder import AgentBuilder
from shared.configuration import load_agent_settings

registration = AGENTS["entity-builder"]
settings = load_agent_settings(registration.config_path, env_prefix=registration.env_prefix)
builder = AgentBuilder(CodexChatModel(model_name=settings.model_name))
runtime = AgentRuntime(builder, settings, registration.load_schema())
result = registration.create_workflow().run(context, runtime)
```

For tools, supply `AgentBuilder(model, tool_registry={"lookup": lookup_tool})` and
include `lookup` in settings.tools. Tools must be constructed in trusted Python.
The default CLI has no application-tool registry; inject one in a Python entrypoint
when needed. Deep Agents built-ins are separate from these application tools.
Tests can inject a model/builder; workflow functions remain unchanged.

Settings precedence: defaults < optional JSON < environment < explicit overrides.
`<PREFIX>_CONFIG`, `<PREFIX>_MODEL`, `<PREFIX>_RECURSION_LIMIT` are supported. Entity
settings retain `ENTITY_AGENT_*`. Remove old `prompt_file`/`output_schema_file` keys.
Models still use existing Codex ChatGPT sign-in; this refactor adds no API provider.

## Extend later

- **Routing:** implement another workflow with `run(context, runtime)` that selects
  a registered chain using application rules. Agent prompt functions can be reused.
- **Parallel branches:** use separate runtimes/models for independent work, then
  combine results explicitly. No concurrency or thread-safety guarantee is added here.
- **Review loops:** add a bounded workflow with an explicit stop condition and
  maximum iterations; do not hide unbounded retries in prompt functions.
- **Other model adapters:** inject a tool-capable LangChain chat model. The builder
  uses ToolStrategy, so tool calling must work. The current CLI retains Codex.

Every prompt gets a fresh Deep Agents graph and scratch state. Deep Agents owns
the model/tool loop; PromptChain only orders completed prompt steps. A draft/review
workflow adds a model step and may take longer than one prompt. The backend's
existing 120-second default deadline covers both steps; each graph has its own
recursion limit. Review is a model judgment, not proof of semantic correctness.
The backend still validates the final contract before persistence.

## Verification and references

Run `.venv/bin/python -m pytest api-builder-backend/tests -q`. Tests exercise the
real harness and adapter with the external SDK mocked, ordered draft/review,
invalid-output stopping, separate requests, injected dependencies and CLI dispatch.
Live model behavior is a separate check; these tests do not prove live latency.

Reviewed 2026-11-02:
- [Anthropic basic workflows](https://platform.claude.com/cookbook/patterns-agents-basic-workflows): sequential prompt chaining is the starting pattern; routing and parallelization are later alternatives.
- [Deep Agents customization](https://docs.langchain.com/oss/python/deepagents/customization): model, tools, prompts and backend are supported graph construction inputs.
