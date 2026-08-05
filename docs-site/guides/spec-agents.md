---
title: Agents
category:
  uri: documentation
parent:
  uri: spec-reference
slug: spec-agents
position: 2
privacy:
  view: public
---

One Markdown file per agent, in `agents/`. Frontmatter declares capabilities; the body is the
system prompt.

```markdown
---
name: researcher
description: Gathers source material and records where each claim came from.
tools: [web-search, read-file]
skills: [citation-format]
model:
  name: claude-opus-5
  max_tokens: 32000
---

You gather source material for the open questions.

For each question, search, then record what you found and where it came from.
A finding without a traceable source is not a finding — drop it rather than
carrying it forward unattributed.

When sources disagree, say so and record both. Do not silently pick one.
```

## Frontmatter

| Key | Type | Required | Notes |
|---|---|---|---|
| `name` | string | — | Defaults to the filename stem |
| `description` | string | ✅ | See below — this one matters |
| `tools` | list of strings | — | Names declared in `tools/tools.yaml` |
| `skills` | list of strings | — | Directory names under `skills/` |
| `model` | string or mapping | — | Overrides the workflow default; same shape as [workflow.yaml](doc:spec-workflow) |

Any other key produces `BRIDGE301` and reaches no engine.

## `description` is routing, not documentation

This is the single field most worth spending time on. It is what an engine reads when
deciding whether to delegate here, and on the Claude Code side it is what appears in the
generated command's agent list.

Write it as a description of *when this agent is the right one*:

| | |
|---|---|
| ❌ | `The researcher agent.` |
| ❌ | `Does research.` |
| ✅ | `Gathers source material and records where each claim came from.` |

## The prompt body

Everything after the frontmatter is the system prompt, passed through unchanged to both
engines. Write it as a brief for a capable colleague.

Two things worth knowing:

**Skills are advertised automatically.** If an agent lists skills, the Claude Code emitter
appends a section to the prompt naming each one and its trigger. On LangGraph, the skills
become tools bound to that agent. You don't need to mention them yourself — but you *should*
say when to reach for them, because that's judgement the format can't express:

> Record findings in the format the `citation-format` skill describes. Load that skill before
> you write your first citation, not after.

**Tool names reach the model differently per engine.** A tool declared as `builtin: Read`
appears in Claude Code frontmatter as `Read` (the engine's own name) but is called
`read-file` (your spec's name) on LangGraph. The emitter handles the translation; write your
prompt against the spec's name.

## Model overrides

An agent with no `model:` inherits the workflow default. Override when one step genuinely
needs different settings:

```yaml
model:
  name: claude-opus-5
  max_tokens: 32000
```

In the bundled example, only the writer overrides — it produces the long final document, so
it gets a larger output budget. The others inherit.

## What survives to each engine

| | Claude Code | LangGraph |
|---|---|---|
| Prompt | Verbatim | Verbatim, as the agent's system prompt |
| Description | Frontmatter + command listing | Node factory docstring |
| Tools | Named in frontmatter | Imported and bound |
| Skills | Listed in the prompt body | Bound as load-on-demand tools |
| Model | Frontmatter `model:` | Passed to the model factory |

Agents are the one concept that translates cleanly in both directions — the spec format was
shaped around Claude Code's subagent frontmatter precisely so that would be true.
