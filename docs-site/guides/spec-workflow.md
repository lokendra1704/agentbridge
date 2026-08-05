---
title: workflow.yaml
category:
  uri: documentation
parent:
  uri: spec-reference
slug: spec-workflow
position: 1
privacy:
  view: public
---

The only required file. Holds structure: how steps connect, what state they share, and which
model they run on.

## Top level

| Key | Type | Default | Notes |
|---|---|---|---|
| `name` | string | directory name | Must match `^[a-z0-9][a-z0-9-]*$` |
| `description` | string | — | Reaches both engines; write it for a reader |
| `version` | string | `0.1.0` | Free-form |
| `mode` | `graph` \| `autonomous` | inferred | Inferred as `graph` if a `graph:` section exists |
| `model` | string or mapping | `claude-opus-5` | Workflow-wide default; agents may override |
| `state` | mapping | empty | See below |
| `graph` | mapping | — | See below |

```yaml
name: research-assistant
description: >-
  Researches a topic, loops until the sources are good enough, then writes a
  cited brief.
version: 0.1.0
mode: graph
```

## `model`

Shorthand or full form:

```yaml
model: claude-opus-5
```

```yaml
model:
  name: claude-opus-5
  max_tokens: 16000
  effort: high
```

| Key | Type | Notes |
|---|---|---|
| `name` | string | Passed through verbatim — the bridge keeps no model registry |
| `max_tokens` | integer > 0 | |
| `effort` | `low` \| `medium` \| `high` \| `xhigh` \| `max` | How much reasoning to spend |
| `temperature` | 0.0–2.0 | See the warning below |

> ⚠️ **`temperature` is rejected by current Claude models**
>
> `claude-opus-5`, `claude-sonnet-5`, the Opus 4.7/4.8 line, and Fable/Mythos 5 reject
> sampling parameters outright — the request fails with a 400. If you set one on those
> models, validation raises `BRIDGE400` at compile time so you find out before deploying.
>
> Use `effort` to control reasoning depth, and the prompt to control behaviour. The field
> exists at all because other providers still accept it.

## `state`

```yaml
state:
  name: ResearchState
  fields:
    - name: messages
      type: messages
      reducer: append
      description: The running transcript.
    - name: findings
      type: list
      reducer: append
    - name: rounds
      type: int
```

| Key | Notes |
|---|---|
| `name` | Class name for the generated state type. Default `WorkflowState` |
| `fields[].name` | snake_case — becomes a Python identifier |
| `fields[].type` | `str`, `int`, `float`, `bool`, `list`, `dict`, `messages` |
| `fields[].reducer` | `replace` (default), `append`, `merge` |
| `fields[].description` | Reaches both engines; on Claude Code it is the *only* thing that survives |

`messages` is the conversation transcript. Every engine has one; only some make it an explicit
value. Declaring it is what lets agent turns accumulate rather than overwrite.

Reducers are validated against types: `append` needs `list` or `messages`, `merge` needs
`dict`. A mismatch is a parse error, not a warning.

## `graph`

Omit this section entirely for autonomous mode.

```yaml
graph:
  entry: plan

  nodes:
    - name: plan
      agent: planner
      description: Turn the request into research questions.
    - name: tally
      function: research_assistant_impl.routing:record_round

  edges:
    - {from: plan, to: research}
    - {from: write, to: END}

  branches:
    - from: tally
      condition: research_assistant_impl.routing:needs_more_research
      description: >-
        If fewer than three distinct sources have been gathered and this is
        under the third research pass, research again; otherwise hand off to
        the writer.
      targets:
        more: research
        done: write
```

### `nodes`

Each node sets **exactly one** of `agent:` or `function:`.

| Key | Notes |
|---|---|
| `name` | Node identifier, referenced by edges and branches |
| `agent` | Name of an agent in `agents/` — a model turn |
| `function` | Dotted `module:callable` — plain Python that takes state and returns a state update |
| `description` | Shown in Claude Code's generated command |

Prefer a `function:` node for anything a loop's termination depends on. A counter the model is
merely asked to increment is not a bound.

### `edges`

`from` and `to`, where `to` may be the sentinel `END`.

A node with no outgoing edge raises `BRIDGE006` — the workflow stops there without reaching
`END`, which is usually a mistake rather than an intent.

### `branches`

| Key | Required | Notes |
|---|---|---|
| `from` | ✅ | Source node |
| `condition` | ✅ | Dotted `module:callable` returning one of the `targets` keys |
| `description` | ✅ | Prose statement of the same rule |
| `targets` | ✅ | Label → node name (or `END`) |

> **`description` is required, and it is load-bearing.**
>
> On LangGraph the `condition` callable runs and selects the edge. On Claude Code it cannot
> run at all — only the prose survives (`BRIDGE101`), and it becomes the routing logic. Keep
> the two in step; drift between them is drift between your engines.

## Validation

`agentbridge validate` checks relationships the file format can't:

| Check | Code |
|---|---|
| Node references an agent that doesn't exist | `BRIDGE001` |
| Edge or branch names an undeclared node | `BRIDGE005` |
| `mode: graph` with no entry / no nodes | `BRIDGE010` / `BRIDGE011` |
| Node unreachable from entry | `BRIDGE004` |
| Node with no outgoing edge | `BRIDGE006` |
| Graph declared but mode is autonomous | `BRIDGE012` |

See [Diagnostics](doc:diagnostics) for the full list.
