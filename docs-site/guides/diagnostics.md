---
title: Diagnostics reference
category:
  uri: documentation
slug: diagnostics
position: 7
privacy:
  view: public
---

Every code agentbridge can emit, what triggers it, and what to do.

## The rule

**Nothing is dropped silently.** Every lossy translation appends a diagnostic carrying the
spec location. If no warning appeared, the translation was clean.

Two tests enforce this: one fails if a lossy row in the mapping table has no code, another
fails if a declared lossy row never actually fires.

## Format

```
<spec file>: <severity>[<code>]: <message>
    hint: <what to do about it>
```

Errors and warnings go to stderr; info goes to stdout. Errors block output entirely.

| Severity | Effect |
|---|---|
| `error` | Nothing is written. Exit code `1` |
| `warning` | Output is written. Blocks under `--strict` |
| `info` | Output is written. Never blocks |

## Code ranges

| Range | Raised by |
|---|---|
| `BRIDGE0xx` | Parser and validator — spec problems |
| `BRIDGE1xx` | Claude Code emitter — what this engine cannot enforce |
| `BRIDGE2xx` | LangGraph emitter — what this engine has no primitive for |
| `BRIDGE3xx` | Importer — what a plugin cannot carry back |
| `BRIDGE4xx` | Validator — model configuration |
| `BRIDGE5xx` | Deployment targets |

---

## 0xx — Spec problems

| Code | Severity | Meaning | Fix |
|---|---|---|---|
| `BRIDGE001` | error | Node references an agent that doesn't exist | Add `agents/<name>.md`, or fix the node's `agent:` |
| `BRIDGE002` | error | Agent references an undeclared tool | Declare it in `tools/tools.yaml` |
| `BRIDGE003` | error | Agent references a missing skill | Add `skills/<name>/SKILL.md` |
| `BRIDGE004` | warning | Node unreachable from entry | Add an edge to it, or delete it |
| `BRIDGE005` | error | Edge or branch names an undeclared node | Check spelling against `graph.nodes` |
| `BRIDGE006` | warning | Node has no outgoing edge — the workflow stops there without reaching `END` | Add an edge to `END` to make termination explicit |
| `BRIDGE010` | error | `mode: graph` with no entry, or an entry that isn't a declared node | Set `graph.entry` |
| `BRIDGE011` | error | `mode: graph` with no nodes | Add nodes, or switch to autonomous |
| `BRIDGE012` | warning | Autonomous mode, but graph structure was declared and is being ignored | Set `mode: graph` to use it |
| `BRIDGE013` | error | Workflow has no agents | Add at least one |
| `BRIDGE020` | warning | Duplicate tool name; the later one wins | Rename or remove one |
| `BRIDGE021` | warning | Skill directory has no `SKILL.md` and is ignored | Add the file, or remove the directory |
| `BRIDGE022` | warning | Tool declared but no agent lists it | Add to an agent's `tools:`, or delete |
| `BRIDGE023` | warning | Skill declared but no agent lists it | Add to an agent's `skills:`, or delete |

> **Why `BRIDGE023` is more than tidiness**
>
> It marks the one case where the two engines genuinely differ in kind. A Claude Code skill is
> model-triggered whether or not an agent names it; a lowered skill-tool is reachable only if
> bound to an agent. Rather than let that become a confusing behaviour difference later, the
> spec is asked to say which agents can use it.

---

## 1xx — Claude Code emitter

Claude Code's control flow is the model's judgement, so declared structure can be *described*
here but not enforced. These four are the honest accounting of that.

| Code | Severity | Meaning |
|---|---|---|
| `BRIDGE100` | warning | An explicit graph was declared; it is lowered to prose guidance in the generated command |
| `BRIDGE101` | warning | A branch condition is a Python callable and cannot run here — only its prose `description` survives |
| `BRIDGE102` | warning | Typed state fields become prose the model is asked to track; nothing enforces them |
| `BRIDGE103` | warning | A tool backed by a Python callable can be named but not wired up |

**None of these mean you did something wrong.** A declared graph *always* raises `BRIDGE100`
on this target. They mean: the guarantee you have on LangGraph is strong advice here.

`BRIDGE101` is the one to act on: keep the branch's `description` accurate, because on this
engine that prose *is* the routing logic.

`BRIDGE103` needs real work if you want the tool to function — expose it over MCP, or mark it
`builtin:` if the engine provides it.

---

## 2xx — LangGraph emitter

| Code | Severity | Meaning |
|---|---|---|
| `BRIDGE200` | warning | No graph declared, so the workflow compiles to a single node; names the agents that became unreachable |
| `BRIDGE201` | info / warning | A builtin tool is served by a runtime shim (info) or has no equivalent and became a stub (warning) |
| `BRIDGE202` | info | A skill was lowered to a tool that returns its body |

`BRIDGE200` is the one worth reading carefully:

```
workflow 'my-workflow' declares no graph, so it compiles to a single node
running 'planner'; 3 other agent(s) are unreachable: ['researcher', 'writer']
    hint: add a graph: section to workflow.yaml to keep multi-agent structure
```

Three agents silently doing nothing is exactly the failure this project exists to prevent.

`BRIDGE201` at **warning** severity means no shim exists and the tool became a stub that
raises `NotImplementedError` when called — loud, not a silent no-op. Supply an
`implementation:` instead.

---

## 3xx — Importer

| Code | Severity | Meaning |
|---|---|---|
| `BRIDGE300` | warning | A plugin declares no control flow, so the imported workflow is autonomous |
| `BRIDGE301` | warning | An unknown frontmatter or YAML key; it will not reach any engine |
| `BRIDGE302` | warning | No agents found under the plugin's `agents/` |
| `BRIDGE303` | warning | An imported skill has no description — on engines without a skill primitive that's the only trigger signal |
| `BRIDGE304` | warning | A tool isn't a known engine builtin, so it's imported without an implementation |

`BRIDGE300` fires on **every** import, by construction. It points forward at the consequence:

```
    hint: add a graph: section to workflow.yaml before compiling to LangGraph,
          or that target will collapse to a single node (BRIDGE200)
```

`BRIDGE301` is why a typo doesn't silently do nothing — it names the key and lists the ones
that are understood.

---

## 4xx — Model configuration

| Code | Severity | Meaning |
|---|---|---|
| `BRIDGE400` | warning | `temperature` set on a model that rejects sampling parameters |

```
'research-assistant' sets temperature on model 'claude-opus-5', which rejects
sampling parameters — the request will fail with a 400
    hint: drop 'temperature' and steer with the prompt, or set 'effort' instead
```

Covers `claude-opus-5`, `claude-sonnet-5`, `claude-opus-4-8`, `claude-opus-4-7`,
`claude-fable-5`, `claude-mythos-5`. Matched on prefix, deliberately kept to a short list —
this is a lint, not a model registry, because a registry would rot faster than the rest of the
project.

---

## 5xx — Deployment

| Code | Severity | Meaning |
|---|---|---|
| `BRIDGE500` | error | A deployment target expected output that isn't there |

Usually means the target and engine were mismatched. The CLI catches most of these earlier
with a usage error (exit `2`).

---

## Using them in CI

```bash
agentbridge validate ./spec --strict
```

Fails on any warning. Good for the spec itself, where a clean run should be genuinely clean.

For `compile`, `--strict` is only realistic on the LangGraph target — Claude Code emission is
warning-heavy by design. To gate on errors only, drop `--strict` and rely on the exit code:

```bash
agentbridge compile ./spec -e claude-code -o ./plugin   # exit 1 only on errors
```
