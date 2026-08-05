# agentbridge — architecture

How the compiler is put together, and why. For a user-level introduction see `README.md`;
for a file-by-file map see `CodeIndex.md`.

---

## 1. The shape

Four layers, strictly one-directional. Later layers import earlier ones and never the
reverse.

```
  spec files  ──parse──▶  IR  ──emit──▶  engine artifacts  ──prepare──▶  platform files
      ▲                    │                   │
      │                    │                   │
      └────import──────────┘                   └── diagnostics carry spec locations
        (engine → spec)                            back to the authored file
```

| Layer | Package | Job |
|---|---|---|
| **Spec** | `agentbridge.spec` | The authored artifact. Markdown-with-frontmatter for prose, YAML for structure. |
| **IR** | `agentbridge.ir` | Engine-neutral models. The project's contract. |
| **Backends** | `agentbridge.backends` | One module per engine behind `RuntimeBackend`. |
| **Deployment** | `agentbridge.deploy` | One module per platform behind `DeploymentTarget`. |

The one-directional rule is enforced by tests, not convention — `tests/test_ir_neutrality.py`
parses the IR's AST and fails if it imports from `backends` or `deploy`.

### Why the split is where it is

**Why the IR names no engine.** If a field exists only because LangGraph has typed graph
state, it isn't a contract — it's LangGraph's shape wearing a neutral name, and the third
engine will need the IR edited rather than extended. `test_ir_neutrality.py` strips comments
and string literals from `ir/` and `spec/` and greps the remaining code for `langgraph`,
`langchain`, `crewai`, `claude_code`, `.claude`. Prose may explain the rule; code may not
break it.

**Why deployment is a separate ABC from the runtime.** LangGraph Platform is a different
product from LangGraph. You can run the engine locally with no deployment target at all, and
one engine may eventually have several. Folding `deploy()` into `RuntimeBackend` would make
the common case (just run it) carry the uncommon case's baggage. The split also draws a clean
line in the output: the backend emits the *program*, the target emits everything about
*shipping* it (`langgraph.json`, `.env.example`, `DEPLOY.md`).

**Why engines are plugins.** `BackendRegistry` and `DeploymentRegistry` hold built-ins plus
anything advertised under the `agentbridge.backends` / `agentbridge.deploy` entry-point
groups. Adding CrewAI means adding a module and an entry point — never editing the parser or
the IR.

---

## 2. The spec format

```
<spec>/
  workflow.yaml            structure: graph wiring, state schema, model defaults
  agents/<name>.md         frontmatter + system prompt
  skills/<name>/SKILL.md   frontmatter + instructions
  tools/tools.yaml         tool declarations
```

Structure lives in YAML; prose lives in Markdown. Diffing a system prompt should not mean
diffing a YAML string literal.

The agent and skill files deliberately match Claude Code's `.claude/` conventions. That is a
constraint on the spec, chosen so the Claude Code emitter is nearly a file copy and the
importer is nearly lossless — the round trip that matters most is the one people will
actually use.

### Two modes

`workflow.yaml` is in one of two modes, inferred from whether a `graph:` section exists (or
stated explicitly with `mode:`).

- **`autonomous`** — no declared structure. The model decides. Native to Claude Code; lossy
  on LangGraph.
- **`graph`** — nodes, edges, and branches. Native to LangGraph; advisory on Claude Code.

A node is either an `agent:` (a model turn) or a `function:` (a dotted path to plain Python).
The example uses both: bookkeeping that bounds a loop is a `function:` node, because a
counter the model is merely *asked* to increment is not a bound.

---

## 3. The concept mapping

The hard part of this project is not file generation — it's deciding how each idea lands on
each engine. Those decisions live in one place, `agentbridge/mapping/concepts.py`, as data
with a `fidelity` and a written rationale, rather than as `if` statements scattered through
emitters. `agentbridge mapping` prints the table.

| Concept | Claude Code | LangGraph |
|---|---|---|
| agent | `.claude/agents/<name>.md` *(exact)* | a node running a tool-calling loop *(lowered)* |
| skill | `.claude/skills/<name>/SKILL.md` *(exact)* | a tool returning the skill body *(lowered)* |
| tool (user implementation) | a named MCP tool *(lossy)* | an imported callable *(exact)* |
| tool (builtin) | the engine's own tool *(exact)* | a shim from `agentbridge.runtime.builtins` *(lowered)* |
| explicit graph | prose in a slash command *(lossy)* | `StateGraph` edges *(exact)* |
| branch condition | prose *(lossy)* | a callable in `add_conditional_edges` *(exact)* |
| autonomous mode | native *(exact)* | one flattened node *(lossy)* |
| typed state | nothing; the transcript is the state *(lossy)* | `TypedDict` with reducers *(exact)* |
| persistence | session files *(lowered)* | a checkpointer at build time *(lowered)* |

`tests/test_mapping.py` holds the table to its own claims: every engine has a row for every
concept, every lossy row carries a diagnostic code, and every row has a real rationale.

### The two genuinely lossy directions

These are the spots the design has to confront rather than paper over.

**Skills are lazy and model-triggered; LangGraph has no such primitive.**
The canonical lowering is **skill → a zero-argument tool whose return value is the skill
body**, with the skill's `description` as the tool description. This keeps the property that
actually matters: the model decides when to pull the instructions into context, and pays no
token cost until it does. Because engines route on the description, the trigger semantics
carry over too.

Rejected alternatives, recorded in the table so nobody re-litigates them from scratch:
concatenating skill bodies into the system prompt (correct output, destroys laziness,
inflates every request); making each skill a graph node (forces the author to declare control
flow the spec deliberately left implicit).

**Claude Code's control flow is implicit; a spec that says only "the model decides" contains
no graph.**
The spec answers this with the optional `graph:` section — structure is *declarable*, and
each engine takes what it can:

- LangGraph enforces it (`BRIDGE100` never fires here).
- Claude Code degrades it into a slash command that spells out the sequence and every branch
  rule in prose, and warns (`BRIDGE100`, `BRIDGE101`, `BRIDGE102`).
- A spec with no `graph:` collapses to one LangGraph node, and warns (`BRIDGE200`) naming the
  agents that became unreachable.

This is why `Branch.description` is a required field rather than an optional comment: on the
Claude Code side, that prose *is* the routing logic. Nothing else survives.

---

## 4. Diagnostics

Every lossy translation appends a `Diagnostic` carrying the spec location. That is the rule
the design turns on, so the codes are worth knowing.

| Range | Raised by | Meaning |
|---|---|---|
| `BRIDGE0xx` | parser / validator | Spec problems: dangling references, unreachable nodes, unused capabilities |
| `BRIDGE1xx` | Claude Code emitter | What this engine cannot enforce: graphs, branch conditions, typed state, Python tools |
| `BRIDGE2xx` | LangGraph emitter | What this engine has no primitive for: autonomous mode, builtin tools, skills |
| `BRIDGE3xx` | importer | What a plugin cannot carry back: control flow, tool implementations |
| `BRIDGE4xx` | validator | Model-configuration lints |
| `BRIDGE5xx` | deployment target | Deployment prerequisites |

Two worth calling out:

- **`BRIDGE400`** warns when a spec sets `temperature` on a model that rejects sampling
  parameters (`claude-opus-5`, `claude-sonnet-5`, the Opus 4.7/4.8 line, Fable/Mythos 5).
  That request would 400 at runtime; catching it at compile time is cheap. It is a lint over
  a short prefix list, deliberately *not* a model registry — a registry would rot faster than
  the rest of the project.
- **`BRIDGE022` / `BRIDGE023`** flag a tool or skill no agent references. This is the one case
  where the engines genuinely disagree: a Claude Code skill is model-triggered whether or not
  an agent names it, while a lowered skill-tool is reachable only if bound to an agent. Rather
  than let that surface as a confusing conformance failure, the spec is asked to say which
  agents can use it.

`--strict` turns warnings into a non-zero exit, which is what you want in CI.

---

## 5. Conformance testing

"Same spec, both engines" is only real if something checks it. `tests/test_conformance.py`
does, and it asserts on **observable behaviour** rather than generated bytes.

Each backend implements `contract(bundle, files) -> EngineContract`, reporting which agents,
skills, tools, and nodes it actually materialised — derived by **inspecting its own output**,
not by copying the input bundle. A contract read off the input could not catch a backend that
silently skipped something, which is the entire point.

Reading that back needs the output to be introspectable. LangGraph output is Python, so the
contract greps for the symbols it emitted. Claude Code output is Markdown, so the emitter
leaves machine-readable HTML-comment trailers in each agent file:

```html
<!-- agentbridge:tools read-file=Read,web-search= -->
<!-- agentbridge:skills citation-format -->
```

These pay for themselves twice. Frontmatter has to name tools the way the *engine* does
(`Read`), but the IR uses the spec's name (`read-file`) — the trailer records the pairing, so
`import` lands back on the spec it came from instead of a slugified approximation. It also
carries the agent→skill association, which the plugin format has nowhere else to put. Without
them the round trip silently degrades; `tests/test_claude_code.py::test_agent_capabilities_survive`
pins that.

The suite is parametrised over `registry.names()`, so a third engine inherits it by existing.
It checks that every backend emits without errors, materialises every agent, skill, tool and
node, agrees with every other backend, emits syntactically valid Python, keeps paths relative
and contained, and — the load-bearing one — that **every lossy row in the mapping table
actually produces a diagnostic** when its case is exercised.

Beyond structure, `tests/test_langgraph_emitter.py::TestGeneratedProgramRuns` writes the
generated program to disk, imports it, builds the real graph, and invokes it. Both branch
paths are covered: enough sources on the first pass goes straight to the writer; no sources
loops until the round cap stops it. This is possible without an API key because
`build_graph()` takes an injectable `model_factory` — a seam that exists for exactly this,
and doubles as the way to change provider or route agents to different models.

Two round trips are tested, and they check different things:

- `spec → IR → spec → IR` must be a fixed point. It goes through no engine, so anything lost
  is a bug in the *spec format*.
- `spec → Claude Code plugin → IR` preserves agents, skills, prompts and capabilities, and
  loses control flow **by design** — the importer warns (`BRIDGE300`) and points forward at
  the consequence (`BRIDGE200`).

---

## 6. What the LangGraph backend generates

```
workflow/
  state.py      TypedDict with Annotated reducers (add_messages, operator.add, merge)
  tools.py      imported callables and builtin shims, wrapped as StructuredTools
  skills.py     each skill as a load-on-demand tool
  agents.py     one node factory per agent, plus the model factory
  graph.py      StateGraph assembly and build_graph()
requirements.txt
README.md
```

Three details that are decisions rather than accidents:

**`build_graph(config=None, *, checkpointer=None, model_factory=None)`.** `config` is
accepted and ignored so the function doubles as a LangGraph Platform graph factory —
`langgraph.json` points at `build_graph` rather than a module-level graph object, so importing
the module doesn't require credentials. `checkpointer` defaults to `None` because the platform
supplies its own, and the right local choice (memory, SQLite, Postgres) is a deployment
decision, not a workflow decision.

**Builtin tools get real implementations.** `agentbridge.runtime.builtins` provides small
`read_file` / `write_file` / `edit_file` / `run_bash` / `glob_files` / `grep_files` shims.
Without them, a spec that reads a file would compile on both engines but only *run* on one,
making "same workflow, two runtimes" true only on paper. They are deliberately simpler than
Claude Code's, which the mapping table records as `lowered` rather than `exact`. A builtin
with no shim becomes a stub that raises `NotImplementedError` — loud, not a silent no-op —
plus a `BRIDGE201` warning.

**The prebuilt-agent API is version-shimmed.** LangGraph 1.0 moved `create_react_agent` to
`langchain.agents.create_agent` *and* renamed its prompt keyword to `system_prompt`, so the
import path alone can't tell the two apart. Generated `agents.py` carries a `_build_agent`
helper that tries the current API and falls back. Both paths are exercised by the test suite.

**Tool schemas come from the Python signature, not the spec.** For an implementation-backed
tool the callable is the source of truth, so the emitter lets the signature drive the schema
and writes the spec's declared `parameters` beside it as a comment for cross-checking. The
declared schema is what the *Claude Code* side needs, where there is no function to inspect.

---

## 7. Toolchain

```bash
uv venv && uv pip install -e .           # install
uv pip install pytest mypy ruff types-PyYAML

python -m pytest                          # all tests (99)
python -m pytest tests/test_conformance.py -k skill    # one test
python -m pytest -p no:warnings           # quieter
mypy                                      # strict; config in pyproject.toml
ruff check src tests && ruff format src tests
```

The LangGraph extra (`uv pip install -e '.[langgraph]'`) is only needed to *run* generated
code. The compiler itself depends on `pydantic` and `PyYAML` and nothing else — it can emit a
LangGraph program on a machine with no LangGraph installed. Tests that build and invoke the
generated graph `importorskip` when it's absent.

---

## 8. Adding an engine

1. Add `agentbridge/backends/<engine>/`, implementing `emit()` and `contract()`.
2. Add rows to `MAPPINGS` in `mapping/concepts.py` — one per concept, with a rationale.
   `test_mapping.py` fails until the table is complete.
3. Register it in `backends/__init__.py`, or ship it separately under the
   `agentbridge.backends` entry-point group.

The conformance suite picks it up automatically. If step 1 makes you want to add a field to
`agentbridge.ir`, stop: that is the signal an engine assumption is leaking into the contract.

---

## 9. Known limits

- **CrewAI is not implemented.** The interfaces avoid LangGraph-shaped assumptions, and the
  neutrality test enforces it, but the claim is untested until a third backend exists.
- **`RuntimeBackend.run()` is unimplemented on both backends.** `supports_run()` returns
  `False`; in-process execution goes through the generated code.
- **Claude Code tool wiring is the user's job.** A Python-callable tool can be *named* in a
  plugin but not imported; `BRIDGE103` says so, and connecting it over MCP is manual.
- **The importer recovers no control flow.** By construction — a plugin doesn't contain any.
  Round-tripping `spec → plugin → spec` returns an autonomous workflow, and re-adding a
  `graph:` section is a human decision.
