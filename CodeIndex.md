# Code index

A map of the source, organised by **what you're trying to do** rather than by directory.
Architecture and rationale live in `TechnicalREADME.md`.

---

## Start here

| I want to… | Go to |
|---|---|
| Understand the whole translation at a glance | `src/agentbridge/mapping/concepts.py` — `MAPPINGS` |
| See what a spec can contain | `src/agentbridge/ir/models.py` |
| Change what the spec format accepts | `src/agentbridge/spec/parser.py` |
| Change what Claude Code output looks like | `src/agentbridge/backends/claude_code/emitter.py` |
| Change what LangGraph output looks like | `src/agentbridge/backends/langgraph/emitter.py` |
| Add a validation rule | `src/agentbridge/ir/validate.py` |
| Add a CLI command | `src/agentbridge/cli.py` |
| Add a whole new engine | `src/agentbridge/backends/base.py`, then a new `backends/<engine>/` |
| See a complete working spec | `examples/research-assistant/` |

---

## Layer 1 — Spec (`src/agentbridge/spec/`)

The authored artifact, in and out. Depends on the IR; knows nothing about engines.

**`parser.py`** (364 lines) — spec directory → `Bundle`.
- `parse_spec(root)` → `(Bundle, DiagnosticBag)`. The entry point everything else calls.
- `_parse_workflow` / `_parse_agents` / `_parse_skills` / `_parse_tools` — one per file kind.
- `_report_unknown_keys` — an unrecognised frontmatter key becomes `BRIDGE301`, never a
  silent drop.
- Raises `SpecError` only when no bundle can be produced; everything recoverable becomes a
  diagnostic, so one run reports every problem.

**`writer.py`** (149 lines) — `Bundle` → spec files. The output side of `import`, and what
makes the lossless round-trip test possible.

**`frontmatter.py`** (54 lines) — `parse()` / `render()` for Markdown-with-YAML-frontmatter.
`parse` returns `(frontmatter, body, body_start_line)`; the line number lets a diagnostic
point into the prose.

---

## Layer 2 — IR (`src/agentbridge/ir/`)

The contract. **Names no engine** — enforced by `tests/test_ir_neutrality.py`.

**`models.py`** (371 lines) — the vocabulary.

| Type | Notes |
|---|---|
| `Bundle` | Everything a backend needs: workflow + agents + skills + tools |
| `Workflow` | Name, `mode`, entry, nodes, edges, branches, state, model |
| `Agent` | Prompt, description, tool names, skill names, optional model override |
| `Skill` | `description` is the trigger condition, not documentation — it's what engines route on |
| `Tool` | Exactly one of `implementation` (dotted path) or `builtin` (engine-provided) |
| `Node` | Exactly one of `agent:` or `function:` |
| `Branch` | `condition` (callable) **and** `description` (prose) — the prose is required because it's all that survives on Claude Code |
| `StateField` | Type + `Reducer`; validator rejects `append` on a scalar |
| `ModelConfig` | Model id passed through verbatim; no registry, by design |
| `EngineContract` | What a backend claims it materialised — the conformance currency |
| `Located` | Base class carrying `location`. Named `location`, not `source`, because `Edge.source` is a node name |

**`validate.py`** (220 lines) — cross-object checks Pydantic can't do alone.
- `_check_agent_references` → `BRIDGE002` / `BRIDGE003` (dangling tool / skill)
- `_check_unreferenced` → `BRIDGE022` / `BRIDGE023` (declared but unreachable)
- `_check_model_config` → `BRIDGE400` (sampling params on a model that rejects them)
- `_check_graph` → `BRIDGE001`, `BRIDGE005`, `BRIDGE010`, `BRIDGE011` (structure)
- `_check_reachability` → `BRIDGE004` (unreachable node), `BRIDGE006` (dead end)
- `_check_autonomous` → `BRIDGE012`, `BRIDGE013`

---

## Layer 3 — Backends (`src/agentbridge/backends/`)

**`base.py`** (121 lines) — the plugin seam.
- `RuntimeBackend` — ABC: `emit()`, `contract()`, optional `run()`.
- `EmittedFile` — path + content; a validator rejects absolute paths and `..`.
- `BackendRegistry` — built-ins plus anything under the `agentbridge.backends` entry-point
  group.

### `claude_code/`

**`emitter.py`** (342 lines) — IR → `.claude/` plugin.
- `_agent_file` — frontmatter + prompt + skill list, plus the machine-readable trailers.
- **`_command`** — the interesting function. Declared control flow can't be enforced here, so
  it's spelled out in prose: `_graph_prose` renders steps, order, and branch rules;
  `_state_prose` renders typed state as things to track by hand. Raises `BRIDGE100`,
  `BRIDGE101`, `BRIDGE102`.
- `tools_named_in` / `skills_named_in` — read the trailers back. Used by `contract()` **and**
  by the importer.

**`importer.py`** (275 lines) — `.claude/` plugin → IR.
- `import_plugin(root)` accepts a project dir or `.claude/` itself.
- `_tool_from_trailer` — reconstructs the spec's tool name from a generated plugin.
  `_tool_for` — the fallback for hand-written plugins, slugifying engine names.
- `BUILTIN_TOOLS` — the engine's own tools; anything else is assumed to be MCP (`BRIDGE304`).
- Always warns `BRIDGE300`: a plugin declares no control flow, so the import is autonomous.

### `langgraph/`

**`emitter.py`** (696 lines) — IR → a runnable Python package. One function per generated
file:

| Function | Emits | Watch for |
|---|---|---|
| `_state_py` | `workflow/state.py` | `_annotation()` maps reducer → `add_messages` / `operator.add` / `merge_dicts` |
| `_skills_py` | `workflow/skills.py` | **The canonical skill lowering.** Body → constant, tool returns it. `BRIDGE202` |
| `_tools_py` | `workflow/tools.py` | `_BUILTIN_SHIMS` maps engine builtins to runtime shims; unmapped ones become loud stubs. `BRIDGE201` |
| `_agents_py` | `workflow/agents.py` | `_build_agent` version shim; `default_model_factory`; one node factory per agent |
| `_graph_py` | `workflow/graph.py` | `_graph_body` for declared graphs, `_autonomous_body` for the flattened single node |

- `_warn_autonomous` → `BRIDGE200`, naming the agents that became unreachable.
- `_literal()` — readable string literals, because generated code gets read.

---

## Layer 4 — Deployment (`src/agentbridge/deploy/`)

Separate from `RuntimeBackend` on purpose — see `TechnicalREADME.md` §1.

**`base.py`** (90 lines) — `DeploymentTarget` ABC (`prepare()`, `commands()`), `DeployCommand`,
`DeploymentRegistry`. Each target declares which `engine` it ships.

**`langgraph_platform.py`** (113 lines) — emits `langgraph.json`, `.env.example`, `DEPLOY.md`.
The manifest points at `build_graph` as a **factory**, so importing the module doesn't require
credentials.

---

## Cross-cutting

**`diagnostics.py`** (113 lines) — `Severity`, `SpecLocation`, `Diagnostic`, `DiagnosticBag`,
`SpecError`. `DiagnosticBag` is threaded through parse → emit → deploy so one run reports
everything; `.codes()` is what tests assert on.

**`mapping/concepts.py`** (305 lines) — `MAPPINGS`, the single source of truth for how each
concept lands on each engine, with `Fidelity` (`exact` / `lowered` / `lossy`), a rationale,
and the diagnostic code raised. `render_table()` backs `agentbridge mapping`.

**`cli.py`** (196 lines) — argparse, five commands. Exit codes are the CI contract: `0` ok,
`1` diagnostic error, `2` usage error.

**`runtime/builtins.py`** (127 lines) — file and shell shims imported *only by generated code*.
Nothing in the compiler path depends on this. `run_bash` executes model-authored commands with
the caller's privileges and says so in its docstring.

---

## Tests (`tests/`, 99 tests)

| File | Guards |
|---|---|
| `test_conformance.py` | **The central claim.** Parametrised over every registered backend: all materialise everything, all agree, every lossy row emits a diagnostic, emitted Python parses |
| `test_ir_neutrality.py` | The IR names no engine (AST + comment/string-stripped grep) and imports no backend |
| `test_mapping.py` | The mapping table is complete, every lossy row has a code, every row has a rationale |
| `test_langgraph_emitter.py` | Generated structure, **and** `TestGeneratedProgramRuns` which builds the real graph and invokes both branch paths |
| `test_claude_code.py` | Emission, import, capability survival, and both round trips |
| `test_spec_parser.py` | Parsing, validation, frontmatter |
| `test_cli.py` | Commands and exit codes |
| `test_runtime_builtins.py` | The shims |
| `conftest.py` | `example_spec`, `spec_factory` (build a spec from strings), `minimal_spec`, `fake_model_factory` (a chat model that accepts `bind_tools`) |

---

## Example (`examples/`)

`research-assistant/` is the fixture the conformance suite runs on, chosen to exercise every
interesting path: a graph with a loop, an agent-node and a function-node, a Python-callable
tool and two builtins, a skill, per-agent model override, and four state fields across three
reducers.

`research_assistant_impl/` is the author-owned Python it points at — `tools.py:web_search`
and `routing.py` (`record_round`, `needs_more_research`). The bridge never generates these.

---

## Conventions

- **Diagnostic codes** are stable identifiers. Tests assert on them; don't renumber.
- **`location=` everywhere.** Every diagnostic that can name a spec file should.
- **Generated code is read by humans.** Keep it formatted and commented; that's why
  `_literal()` prefers triple-quoted strings.
- **Emitters own their lossiness.** If a translation loses something, the emitter raises the
  diagnostic — the caller should never have to infer it.
