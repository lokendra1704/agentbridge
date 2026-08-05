---
title: Adding an engine
category:
  uri: documentation
slug: adding-an-engine
position: 10
privacy:
  view: public
---

Adding a runtime means adding a module. It must never mean editing the parser or the IR.

## 1. Implement `RuntimeBackend`

```python
from agentbridge.backends.base import EmittedFile, RuntimeBackend
from agentbridge.diagnostics import DiagnosticBag
from agentbridge.ir.models import Bundle, EngineContract


class CrewAIBackend(RuntimeBackend):
    name = "crewai"
    description = "A CrewAI crew."

    def emit(self, bundle: Bundle, diagnostics: DiagnosticBag) -> list[EmittedFile]:
        ...

    def contract(self, bundle: Bundle, files: list[EmittedFile]) -> EngineContract:
        ...
```

### `emit`

Produce the files the engine needs. **Every lossy translation must append a diagnostic
carrying the spec location** — that's the project's central rule, and tests enforce it.

```python
diagnostics.warn(
    "BRIDGE6xx",
    f"workflow {bundle.workflow.name!r} declares typed state, which this "
    "engine has no equivalent for",
    location=bundle.workflow.state.location,
    hint="the LangGraph target keeps it; here it is advisory",
)
```

Pick a fresh code range. `0xx`–`5xx` are taken; see [Diagnostics](doc:diagnostics).

### `contract`

Report what you materialised — **by inspecting your own output**, not by copying the bundle.

```python
def contract(self, bundle, files):
    by_path = {str(f.path): f.content for f in files}
    src = by_path.get("crew/agents.py", "")
    agents = {a.name for a in bundle.ordered_agents() if _node_fn(a.name) in src}
    ...
```

This is the part that catches a backend which silently skipped something. A contract read off
the input cannot do that, and the conformance suite exists to compare these across engines.

If your output isn't machine-readable — Markdown, say — leave yourself a trailer. The Claude
Code emitter does exactly this:

```html
<!-- agentbridge:tools read-file=Read,web-search= -->
```

## 2. Add rows to the mapping table

Not optional. `tests/test_mapping.py` fails until every concept has a row for your engine.

```python
# agentbridge/mapping/concepts.py

Mapping(
    concept="skill",
    engine=CREWAI,
    target="...",
    fidelity=Fidelity.LOWERED,
    diagnostic="BRIDGE6xx",
    rationale=(
        "Why this lowering and not another, in enough detail that the next "
        "person does not re-derive it. Rejected alternatives belong here too."
    ),
),
```

The tests check that:

- every concept has a row for every registered engine
- every `Fidelity.LOSSY` row carries a diagnostic code
- every row has a rationale of real length

That last one sounds like box-ticking. It isn't: the rationale is where "we tried the obvious
thing and it didn't work" gets recorded, and it's the only thing standing between you and
someone re-litigating a settled decision in six months.

## 3. Register it

In-tree:

```python
# agentbridge/backends/__init__.py
registry.register(CrewAIBackend)
```

Or ship it separately, discovered at runtime:

```toml
[project.entry-points."agentbridge.backends"]
crewai = "my_package.backend:CrewAIBackend"
```

`agentbridge engines` and the conformance suite both pick it up automatically.

## 4. Run the suite

```bash
python -m pytest tests/test_conformance.py
```

Parametrised over `registry.names()`, so your engine is now covered by:

| Test | Asserts |
|---|---|
| `test_every_backend_emits_without_errors` | No error diagnostics on a valid spec |
| `test_every_agent_is_materialised` | Contract lists every agent |
| `test_every_skill_is_materialised` | Contract lists every skill |
| `test_every_tool_is_materialised` | Contract lists every tool |
| `test_declared_nodes_survive` | Nodes and entry point preserved |
| `test_all_backends_agree` | Your contract matches the others' |
| `test_every_lossy_row_actually_reports` | Every lossy row you declared actually fires |
| `test_emitted_python_is_syntactically_valid` | Generated Python parses |
| `test_emitted_paths_are_relative_and_contained` | No absolute paths or `..` |
| `test_autonomous_spec_compiles_on_every_engine` | A structureless spec still produces something |

## The design constraint

> **If implementing your backend makes you want to add a field to `agentbridge.ir`, stop.**

That is the signal an engine assumption is leaking into the contract. The IR is meant to be
the thing all engines agree on; a field that exists for one of them is that engine's shape
wearing a neutral name.

`tests/test_ir_neutrality.py` will also catch the blunt version — it strips comments and string
literals from `ir/` and `spec/` and fails on any engine name in the remaining code.

Two ways out that are usually right:

- **Express it with what's there.** Most engine-specific needs turn out to be a rendering
  decision, not a missing concept.
- **Lower it, and say so.** If the concept genuinely doesn't exist on your engine, that's a
  mapping row with `Fidelity.LOSSY` and a diagnostic — not an IR change.

## Deployment targets

Same shape, separate ABC:

```python
class MyPlatformTarget(DeploymentTarget):
    name = "my-platform"
    engine = "crewai"          # which backend's output it ships
    description = "..."

    def prepare(self, bundle, emitted, diagnostics) -> list[EmittedFile]: ...
    def commands(self, bundle) -> list[DeployCommand]: ...
```

Registered under `agentbridge.deploy`. The CLI checks `target.engine` matches the compiled
engine and refuses the mismatch with a usage error.
