---
title: Engine mapping
category:
  uri: documentation
slug: engine-mapping
position: 6
privacy:
  view: public
---

How each concept lands on each engine, and where the translation is honest about losing
something.

Run `agentbridge mapping` to print this table from the source of truth. It lives in
`agentbridge/mapping/concepts.py` as data with a rationale attached — not as `if` statements
scattered through emitters — so the whole translation can be read in one sitting.

## The table

| Concept | Claude Code | LangGraph |
|---|---|---|
| agent | `.claude/agents/<name>.md` *(exact)* | a node running a tool-calling loop *(lowered)* |
| skill | `.claude/skills/<name>/SKILL.md` *(exact)* | a tool returning the skill body *(lowered)* |
| tool (user implementation) | a named MCP tool *(lossy)* | an imported callable *(exact)* |
| tool (builtin, e.g. file read) | the engine's own tool *(exact)* | a runtime shim *(lowered)* |
| explicit graph (nodes, edges, branches) | prose in a slash command *(lossy)* | `StateGraph` edges *(exact)* |
| branch condition (a Python callable) | prose *(lossy)* | a callable in `add_conditional_edges` *(exact)* |
| autonomous mode (no declared structure) | native *(exact)* | one flattened node *(lossy)* |
| typed state schema | nothing; the transcript is the state *(lossy)* | `TypedDict` with reducers *(exact)* |
| persistence | session files *(lowered)* | a checkpointer at build time *(lowered)* |

The concept names match `MAPPINGS` exactly, so grepping either the table or the source finds
the same row.

## Fidelity levels

| Level | Meaning | Reported as |
|---|---|---|
| **exact** | Survives with no loss; a round trip returns the same spec | nothing |
| **lowered** | Meaning preserved, shape changed | `info` |
| **lossy** | Information is genuinely lost | `warning` with the spec location |

Every lossy row carries a diagnostic code, and a test fails the build if one doesn't — the
project's central rule is that nothing is dropped silently.

## The two genuinely lossy directions

Everything else is bookkeeping. These two are real design problems, and the design confronts
them rather than papering over them.

### 1. Skills are lazy and model-triggered; LangGraph has no such primitive

A skill's defining property is that its instructions enter context *only when the model
decides they're relevant*. LangGraph has no "load these when they matter" primitive, so
something has to give.

**The canonical lowering: skill → a zero-argument tool whose return value is the skill body.**

This preserves the property that actually matters. The model still decides when to pull the
instructions in, and pays no token cost until it does. And because the skill's `description`
becomes the tool description — which is exactly what a model routes on — the trigger
semantics carry over too.

Rejected alternatives, recorded so nobody re-derives them from scratch:

| Alternative | Why not |
|---|---|
| Concatenate every skill body into the system prompt | Correct output, but destroys the laziness and inflates every request |
| Make each skill a graph node | Forces the author to declare control flow the spec deliberately left implicit |

Reported as `BRIDGE202` (info) — the meaning survives, the shape doesn't.

### 2. Claude Code's control flow is implicit; "the model decides" is not a graph

Claude Code's control flow *is* the model's judgement. A spec that says only "the model
decides" contains nothing to build a graph from.

The spec answers this with the optional `graph:` section — structure becomes *declarable*, and
each engine takes what it can:

| | With `graph:` | Without |
|---|---|---|
| **LangGraph** | Enforced. Real edges, real conditional routing | One node, everything else unreachable (`BRIDGE200`) |
| **Claude Code** | Prose in a slash command — advisory (`BRIDGE100`) | Native. Nothing lost |

This is why `Branch.description` is a **required** field rather than an optional comment. On
the Claude Code side that prose *is* the routing logic — the Python condition cannot run
(`BRIDGE101`), so nothing else survives.

What the Claude Code command actually looks like:

```markdown
## Steps

Work through these in order, starting at **plan**. This sequence is the workflow's
definition — follow it rather than improvising an order.

1. **plan** — delegate to the **planner** agent. ...

### Decisions

- After **tally**: If fewer than three distinct sources have been gathered and this
  is under the third research pass, research again; otherwise hand off to the
  writer. (`done` -> **write**, `more` -> **research**)
```

## The asymmetry, stated plainly

Neither engine is the "real" one, but they fail in opposite directions:

- **Write for Claude Code only** and the LangGraph version collapses to a single node.
- **Write for LangGraph only** and the Claude Code version follows your sequence as strong
  advice rather than a guarantee.
- **Declare a graph** and both work — enforced on one, described on the other.

The practical consequence: if you care what order things happen in, say so. If you genuinely
don't, leave `graph:` out and accept that LangGraph gets one agent.

## Typed state

LangGraph gets a real `TypedDict` with per-field reducers, enforced by the runtime. Claude
Code has no state object to reduce into, so non-transcript fields become a section in the
generated command:

```markdown
## Information to carry through

Track these as you work. Nothing enforces them here, so restate them explicitly
when you hand off between steps:

- `topic` (str) — What the user asked about.
- `findings` (list) — Source snippets gathered so far.
```

Reported as `BRIDGE102`. The transcript field is native to Claude Code, so it isn't listed.

## Adding an engine

New rows are required, not optional — `tests/test_mapping.py` fails until every concept has a
row for every registered engine, every lossy row has a diagnostic code, and every row has a
real rationale. See [Adding an engine](doc:adding-an-engine).
