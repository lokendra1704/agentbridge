---
title: Core concepts
category:
  uri: documentation
slug: core-concepts
position: 3
privacy:
  view: public
---

Five ideas. Learn these and the rest of the docs is reference material.

## Agent

A unit of delegated work: a system prompt, a description, and a set of capabilities. One
Markdown file.

```markdown
---
name: researcher
description: Gathers source material and records where each claim came from.
tools: [web-search, read-file]
skills: [citation-format]
---

You gather source material for the open questions.
```

The `description` is not a comment. It is how an engine decides whether to route work here,
so write it as a trigger condition rather than a label.

## Skill

Reference material an agent loads **only when it becomes relevant** — so it costs nothing
until it's needed. Claude Code has this as a first-class idea. LangGraph does not, so
agentbridge lowers each skill into a tool the agent can call to pull the instructions in.

The skill's `description` carries the trigger; the body carries the instructions.

```markdown
---
name: citation-format
description: >-
  Use when recording a finding or writing a claim that came from a source —
  before writing the first citation, not after.
---

Every finding is one line, in this shape:
...
```

## Tool

Something an agent can do. Exactly one of two kinds:

| Kind | Declared as | Claude Code | LangGraph |
|---|---|---|---|
| **Your Python** | `implementation: pkg.mod:func` | Named only, not wired (`BRIDGE103`) | Imported directly |
| **Engine builtin** | `builtin: Read` | Native | Served by a bridge shim (`BRIDGE201`) |

This split exists because the same tool is free on one engine and needs an implementation on
the other. Making the author say which kind it is keeps that visible.

## Workflow mode

The one decision that shapes everything else.

### Autonomous

No declared structure. The model decides what to do next.

```yaml
name: helper
description: Answers questions.
```

Native to Claude Code. On LangGraph this collapses to a single node running one agent —
because "the model decides" contains no graph to build. You get a `BRIDGE200` warning naming
the agents that became unreachable.

### Graph

Nodes, edges, and branches, declared explicitly.

```yaml
mode: graph
graph:
  entry: plan
  nodes:
    - {name: plan, agent: planner}
    - {name: research, agent: researcher}
    - {name: write, agent: writer}
  edges:
    - {from: plan, to: research}
    - {from: write, to: END}
```

Native to LangGraph, which *enforces* it. Claude Code degrades it into a slash command that
spells out the sequence in prose — advisory, not enforced, and it says so (`BRIDGE100`).

> **Rule of thumb**
>
> If you care what order things happen in, declare a graph. Both engines then work: Claude
> Code reads it as instructions, LangGraph enforces it. Without one, only Claude Code is
> faithful.

## State

What gets carried between steps. Each field has a type and a **reducer** — how two writes to
the same field combine.

```yaml
state:
  fields:
    - {name: messages, type: messages, reducer: append}
    - {name: findings, type: list, reducer: append}
    - {name: rounds, type: int}
```

| Reducer | Meaning | Valid on |
|---|---|---|
| `replace` (default) | Last write wins | any type |
| `append` | Concatenate | `list`, `messages` |
| `merge` | Merge keys, right wins | `dict` |

On LangGraph this becomes a `TypedDict` with real reducers, enforced by the runtime. Claude
Code has no state object, so non-transcript fields become prose the model is asked to track
(`BRIDGE102`). Nothing enforces them there.

## Putting it together

Nodes come in two kinds, and the difference matters more than it looks:

```yaml
nodes:
  - {name: research, agent: researcher}                      # a model turn
  - {name: tally, function: myapp.routing:record_round}      # plain Python
```

The bundled example uses a `function:` node to increment the counter that bounds its research
loop. That is deliberate: a counter the model is merely *asked* to increment is not a bound.
Bookkeeping that a loop's termination depends on should not be a model's job.

## Next

- [Spec reference](doc:spec-reference) — every field, in detail
- [How concepts map to each engine](doc:engine-mapping)
