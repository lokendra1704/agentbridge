---
title: CLI reference
category:
  uri: documentation
slug: cli-reference
position: 5
privacy:
  view: public
---

Five commands.

```
agentbridge [-h] {compile,import,validate,engines,mapping} ...
```

## Exit codes

These are the CI contract.

| Code | Meaning |
|---|---|
| `0` | Success |
| `1` | Diagnostic error — spec has errors, or `--strict` and warnings present. Nothing written. |
| `2` | Usage error — unknown engine, mismatched deploy target, no command |

---

## `compile`

Compile a spec into engine artifacts.

```bash
agentbridge compile <spec> --engine <engine> --out <dir> [options]
```

| Flag | Notes |
|---|---|
| `-e`, `--engine` | **Required.** See `agentbridge engines` |
| `-o`, `--out` | **Required.** Created if absent |
| `--deploy <target>` | Also emit deployment artifacts. Must ship the engine you compiled for |
| `--dry-run` | List what would be written; write nothing |
| `--strict` | Treat warnings as errors |

```bash
agentbridge compile examples/research-assistant -e langgraph -o ./svc \
    --deploy langgraph-platform
```

Nothing is written if the spec has errors. With `--strict`, nothing is written if there are
warnings either — which is what you want in CI, though note that Claude Code emission is
warning-heavy *by design* (a declared graph always raises `BRIDGE100`), so `--strict` on that
target will fail unless your spec is autonomous.

---

## `import`

Import an existing `.claude/` plugin back into a spec.

```bash
agentbridge import <plugin> --out <dir> [--dry-run]
```

`<plugin>` may be a project directory containing `.claude/`, or `.claude/` itself.

```bash
agentbridge import ./my-project --out ./spec
```

Recovers agents, skills, prompts, tool declarations, and capability assignments. It does
**not** recover control flow — a plugin contains none — so the result is in autonomous mode
and always warns (`BRIDGE300`), pointing forward at the consequence (`BRIDGE200`) if you
compile to LangGraph without adding a `graph:` section.

---

## `validate`

Parse and check a spec without emitting anything.

```bash
agentbridge validate <spec> [--strict]
```

```
research-assistant v0.1.0 — mode: graph
  agents: 3  skills: 1  tools: 3
  nodes: 4  edges: 3  branches: 1
  state fields: 4
```

Runs the full validator: dangling references, unreachable nodes, dead ends, unused
capabilities, model-config lints. Fast enough for a pre-commit hook.

---

## `engines`

List registered backends and their deployment targets.

```bash
agentbridge engines
```

```
Engines:
  claude-code    A Claude Code plugin: .claude/ agents, skills, and commands.
  langgraph      A runnable LangGraph program (StateGraph, nodes, conditional edges).
      deploy: langgraph-platform — LangGraph Platform (langgraph dev / langgraph up).
```

Includes any third-party backends installed under the `agentbridge.backends` entry-point
group, so this is the authoritative list for your environment.

---

## `mapping`

Print the concept mapping table.

```bash
agentbridge mapping
```

Renders `agentbridge.mapping.concepts.MAPPINGS` as Markdown — the same table shown in
[Engine mapping](doc:engine-mapping), generated from the source of truth rather than kept in
sync by hand.

---

## Diagnostic output

Warnings and errors go to **stderr**; informational diagnostics and command output go to
**stdout**. So this shows only what was written:

```bash
agentbridge compile ./spec -e langgraph -o ./out 2>/dev/null
```

and this captures only the problems:

```bash
agentbridge validate ./spec 2>problems.txt
```

Each diagnostic carries the spec file it came from:

```
examples/research-assistant/workflow.yaml: warning[BRIDGE100]: workflow
'research-assistant' declares an explicit graph, which Claude Code cannot
enforce; it is lowered to prose guidance in the command
    hint: the LangGraph target keeps the structure; this side is advisory
```

## In CI

```yaml
- name: Validate spec
  run: agentbridge validate ./spec --strict

- name: Check LangGraph output is current
  run: |
    agentbridge compile ./spec -e langgraph -o ./generated
    git diff --exit-code ./generated
```

The second step catches a spec edited without regenerating — a drift the whole project exists
to prevent.
