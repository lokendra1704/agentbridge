# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is

`agentbridge` — a compiler that takes one neutral workflow spec and emits engine-native
artifacts for more than one agent runtime.

- **Spec → engine.** Compile a spec into a Claude Code plugin (`.claude/` agents, skills,
  commands) *and* into a runnable LangGraph program. Same workflow, two runtimes.
- **Engine → spec.** Import an existing `.claude/` plugin back into the spec, so work already
  done in Claude Code can move to LangGraph without a rewrite.

Three docs, three audiences: `README.md` (non-technical users), `TechnicalREADME.md`
(architecture and rationale), `CodeIndex.md` (a map of the source). Keep all three current.

## Commands

```bash
uv venv && uv pip install -e .                    # install
uv pip install pytest mypy ruff types-PyYAML      # dev tools
uv pip install -e '.[langgraph]'                  # only to RUN generated code

python -m pytest                                   # all 99 tests
python -m pytest -p no:warnings                    # quieter
python -m pytest tests/test_conformance.py         # one file
python -m pytest tests/test_conformance.py -k skill    # one test by name
python -m pytest -k "not GeneratedProgramRuns"     # skip tests needing langgraph

mypy                                               # strict, config in pyproject.toml
ruff check src tests && ruff format src tests
```

CLI, for manual checks:

```bash
agentbridge validate examples/research-assistant
agentbridge compile examples/research-assistant -e langgraph -o /tmp/out --deploy langgraph-platform
agentbridge import /tmp/plugin -o /tmp/spec
agentbridge engines      # registered backends and their deployment targets
agentbridge mapping      # the concept mapping table
```

## Architecture

Four layers, strictly one-directional — later layers import earlier ones, never the reverse:

```
spec files  ──parse──▶  IR  ──emit──▶  engine artifacts  ──prepare──▶  platform files
   ▲                     │
   └────import───────────┘
```

1. **Spec** (`agentbridge.spec`) — Markdown-with-frontmatter for prose, YAML for structure.
   Deliberately shaped like `.claude/` so the Claude Code emitter is nearly a copy.
2. **IR** (`agentbridge.ir`) — engine-neutral Pydantic models. The contract.
3. **Backends** (`agentbridge.backends`) — one module per engine behind `RuntimeBackend`
   (`emit()`, `contract()`).
4. **Deployment** (`agentbridge.deploy`) — a separate `DeploymentTarget` ABC, deliberately not
   folded into `RuntimeBackend`: platforms are different products from runtimes, and an engine
   can run locally with no target at all.

Read `TechnicalREADME.md` before making structural changes; it explains why each seam is where
it is.

## Rules this codebase enforces

**The IR names no engine.** `tests/test_ir_neutrality.py` strips comments and string literals
from `ir/` and `spec/`, then fails on `langgraph`, `langchain`, `crewai`, `claude_code`,
`.claude`. It also AST-checks that the IR imports nothing from `backends` or `deploy`. If a new
engine makes you want to add an IR field, that is the signal an assumption is leaking — fix the
backend, not the contract.

**Nothing is dropped silently.** Every lossy translation appends a `Diagnostic` with the spec
location attached. `tests/test_mapping.py` fails if a `Fidelity.LOSSY` row in the mapping table
has no diagnostic code, and `tests/test_conformance.py::test_every_lossy_row_actually_reports`
fails if a declared lossy row never actually fires.

**The mapping table is code, not prose.** All translation decisions live in
`agentbridge/mapping/concepts.py` as data with rationale — not as `if` statements inside
emitters. Adding a backend means adding rows there; the tests fail until the table is complete.

**Diagnostic codes are stable.** Tests assert on them. Don't renumber.

## The two genuinely lossy directions

Both are settled, documented in `mapping/concepts.py`, and tested. Read the rationale there
before changing either.

1. **Skills are lazy and model-triggered; LangGraph has no such primitive.** Canonical
   lowering: **skill → a zero-argument tool returning the skill body**, with the skill
   description as the tool description. Preserves what matters (the model decides when to
   load; no token cost until it does). Rejected alternatives are recorded in the table.

2. **Claude Code control flow is implicit; "the model decides" is not a graph.** The spec has
   an optional `graph:` section. LangGraph enforces it; Claude Code degrades it to prose in a
   slash command (`BRIDGE100`/`BRIDGE101`/`BRIDGE102`); a spec without it collapses to one
   LangGraph node (`BRIDGE200`). This is why `Branch.description` is required — on the Claude
   Code side that prose *is* the routing logic.

## Conformance testing

`tests/test_conformance.py` is parametrised over `registry.names()`, so a new backend inherits
the suite by existing. It asserts on observable behaviour — each backend's
`contract(bundle, files)` reports what it materialised, **derived by inspecting its own
output**, not by copying the input bundle. Claude Code output carries machine-readable
HTML-comment trailers (`<!-- agentbridge:tools name=Builtin -->`) so Markdown can be read back;
those trailers also carry the spec-name↔engine-name pairing the importer needs.

`tests/test_langgraph_emitter.py::TestGeneratedProgramRuns` goes further: it writes the
generated program, imports it, builds the real graph, and invokes both branch paths. No API key
needed — `build_graph()` takes an injectable `model_factory`.

## Working notes

- The user originally wrote "Langrath"; it means **LangGraph**.
- "Claude Code SDK" now ships as the **Claude Agent SDK** (`claude-agent-sdk` on PyPI).
- Default model in generated code is `claude-opus-5`. Current Claude models **reject**
  `temperature`/`top_p`/`top_k`; `BRIDGE400` lints for it. Reasoning depth goes through
  `effort`, not sampling params. Load the `claude-api` skill before touching model config
  rather than recalling ids or parameters from memory.
- Generated LangGraph code shims the prebuilt-agent API: LangGraph 1.0 moved
  `create_react_agent` to `langchain.agents.create_agent` *and* renamed its prompt keyword to
  `system_prompt`, so the import path alone can't distinguish them. `_build_agent` in the
  generated `agents.py` handles both; both paths are covered by tests.
- **CrewAI is not implemented.** The interfaces avoid LangGraph-shaped assumptions and the
  neutrality test enforces it, but that claim stays untested until a third backend exists.
