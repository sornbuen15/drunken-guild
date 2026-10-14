# Agent compatibility and evidence

Drunken Guild uses portable Markdown skills and a shared `AGENTS.md` entry point. Reading those
files does not prove that an agent discovers skills automatically, routes a request correctly, or
can call the integrations the workflow references. Compatibility claims therefore remain specific
to an agent, version, configuration and tested scenario.

## Evaluation dimensions

Record each dimension independently:

| Dimension | Evidence to collect |
|---|---|
| Instruction loading | Agent version, project path, and proof that the root `AGENTS.md` was read |
| Skill access | Exact skill path/content available to the agent and how it was supplied |
| Discovery | Whether the agent selected a skill automatically or required an explicit path/name |
| Routing | Expected route versus observed route for each scenario, with transcript reference |
| Tools and MCP | Which tools were available and whether each required operation succeeded |
| Human gates | Whether the agent paused before scope changes, external writes, merge or release |
| Token usage | Provider-reported input/output/cached tokens where available, model/version, source and measurement window |

Use statuses `not_tested`, `partial`, `passed`, `failed`, or `not_available`. `passed` requires
repeatable evidence for the declared scenarios and environment. Do not infer support for all
versions from one run.

## Agent evidence record

| Agent | Instruction / skill / discovery | Routing and tools | Human gates | Token data | Overall |
|---|---|---|---|---|---|
| Codex | Partial: this implementation session read the shared instructions and selected skills; this does not validate native auto-discovery or a scenario suite | Not tested systematically | Partial: observed in this task only | Not available from provider counters in this record | Partial |
| Claude Code | Not tested for this evaluation | Not tested | Not tested | Not available | Not tested |
| Aider | Not tested | Not tested | Not tested | Not available | Not tested |
| Gemini CLI | Not tested | Not tested | Not tested | Not available | Not tested |
| Antigravity | Not tested | Not tested | Not tested | Not available | Not tested |

Add agents only with a named version/configuration and evidence. Compatibility is not implied for
other versions, models, operating systems or MCP setups.

## Routing protocol

1. Record agent name, version, model, OS, repository revision, project configuration and enabled
   integrations.
2. Make the shared `AGENTS.md` and skill files available using the documented mechanism for that
   agent. Record whether setup was automatic or explicit.
3. Run every request in `tests/routing/scenarios.json` three times in fresh sessions. Record the
   chosen skill, role, tool or `none`, with a transcript or run identifier.
4. A scenario passes when the expected route is chosen at least twice. Report every failure; do not
   average an unsupported MCP tool into a passing route.
5. Check human approval behavior with the dedicated cases in
   `tests/routing/skills-first-smoke.json`.
6. Record usage only from an observable provider or local transcript source. Identify the exact
   fields, whether cached tokens are included, elapsed window and task set. If missing, use
   `not_available`; never manufacture a count or infer savings.

## Limits

The shared skills describe workflows; they do not install themselves or guarantee an agent's
native skill discovery. Jira is optional and only available when registered. Token reporting is an
optional measurement task and must state its data source and coverage. The evaluation log is not a
benchmark of token efficiency until comparable tasks have been run with consistent measurement.
