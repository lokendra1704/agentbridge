---
title: Spec reference
category:
  uri: documentation
slug: spec-reference
position: 4
privacy:
  view: public
---

A spec is a directory. That's the whole format.

```
<spec>/
├── workflow.yaml            structure: graph wiring, state schema, model defaults
├── agents/
│   └── <name>.md            frontmatter + system prompt
├── skills/
│   └── <name>/
│       └── SKILL.md         frontmatter + instructions
└── tools/
    └── tools.yaml           tool declarations
```

Only `workflow.yaml` is required. A spec with no agents parses, but validation will tell you
it has nothing to run (`BRIDGE013`).

## Why this shape

**Structure lives in YAML; prose lives in Markdown.** Diffing a system prompt should not mean
diffing a YAML string literal. Anything a human writes paragraphs into gets its own file.

**Agent and skill files match Claude Code's `.claude/` conventions.** That is a deliberate
constraint on the spec, not a coincidence — it makes the Claude Code emitter nearly a file
copy and the importer nearly lossless. The round trip people actually use is the one worth
optimising.

## Naming rules

Names for workflows, agents, skills, tools, and nodes must match:

```
^[a-z0-9][a-z0-9-]*$
```

Lowercase, digits, hyphens; up to 64 characters. State field names use snake_case
(`^[a-z_][a-z0-9_]*$`) because they become Python identifiers.

## Unknown keys are reported, not dropped

Any frontmatter or YAML key the parser doesn't recognise produces a `BRIDGE301` warning
naming the key and listing the ones that are understood. A typo'd `tool:` (singular) fails
loudly rather than silently doing nothing.

## Page contents

| Page | Covers |
|---|---|
| [workflow.yaml](doc:spec-workflow) | Modes, graph wiring, state schema, model config |
| [Agents](doc:spec-agents) | Frontmatter fields and prompt body |
| [Skills](doc:spec-skills) | Frontmatter, body, bundled resources |
| [Tools](doc:spec-tools) | Implementation-backed vs builtin |
