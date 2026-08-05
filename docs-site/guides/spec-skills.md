---
title: Skills
category:
  uri: documentation
parent:
  uri: spec-reference
slug: spec-skills
position: 3
privacy:
  view: public
---

A skill is reference material an agent loads **only when it becomes relevant**. That laziness
is the whole point: the instructions cost nothing until the model decides it needs them.

One directory per skill, under `skills/`:

```
skills/
└── citation-format/
    ├── SKILL.md          required
    └── examples.md       optional bundled resource
```

## SKILL.md

```markdown
---
name: citation-format
description: >-
  Use when recording a finding or writing a claim that came from a source —
  before writing the first citation, not after.
---

# Citation format

Every finding is one line, in this shape:

```
[n] <claim, one sentence> — <source title>, <publisher>, <date> — <url>
```

Rules that matter:

- **One claim per entry.** If a sentence has two facts from different places, it is two entries.
- **Number entries once and never renumber.** Later text refers to `[3]`; if `[3]` moves,
  every reference silently breaks.
```

| Key | Type | Required | Notes |
|---|---|---|---|
| `name` | string | — | Defaults to the directory name |
| `description` | string | ✅ | The trigger condition — see below |
| `resources` | list of strings | — | Defaults to every other file in the directory |
| `allowed-tools` | list of strings | — | Tools the skill may use |

## `description` is the trigger

This is the highest-leverage field in the whole spec format.

Both engines route on it. Claude Code uses it to decide when to load the skill; on LangGraph
it becomes the tool description, which is exactly what the model reads when deciding whether
to call it. Since it's the same signal either way, the trigger semantics carry across.

Write it as *when*, not *what*:

| | |
|---|---|
| ❌ | `Citation formatting rules.` |
| ❌ | `Describes how to format citations.` |
| ✅ | `Use when recording a finding or writing a claim that came from a source — before writing the first citation, not after.` |

The third one tells the model the timing, which is the part it gets wrong.

## The body

Whatever the agent needs once it has decided to load. Nothing is truncated or summarised —
the full body reaches both engines.

Two habits that pay off:

- **Lead with the shape, then the rules.** The model is loading this to act on it, not to
  study it.
- **State the failure the rule prevents.** "Number entries once and never renumber" is
  followable; "be consistent with numbering" is not.

## How it reaches each engine

**Claude Code** — a native `.claude/skills/<name>/SKILL.md`. Exact translation, including the
lazy, model-triggered loading.

**LangGraph** — no such primitive exists, so the skill becomes a zero-argument tool that
returns the body:

```python
CITATION_FORMAT_BODY = """..."""


def _load_citation_format() -> str:
    """<your description> Call this to load the full instructions..."""
    return CITATION_FORMAT_BODY


skill_citation_format = StructuredTool.from_function(
    func=_load_citation_format,
    name="skill_citation_format",
    description="""<your description> Call this to load the full instructions before you act on them.""",
)
```

This keeps the property that matters — the model decides when to pull the instructions into
context, and pays no token cost until it does. Reported as `BRIDGE202` (informational).

Two alternatives were considered and rejected, recorded in the mapping table so nobody
re-derives them:

- **Concatenate every skill body into the system prompt.** Correct output, but destroys the
  laziness and inflates every request.
- **Make each skill a graph node.** Forces the author to declare control flow the spec
  deliberately left implicit.

## Attach skills to agents

A skill no agent lists raises `BRIDGE023`:

```
skill 'citation-format' is declared but no agent lists it; engines disagree
about whether an unattached skill is reachable
```

This is not tidiness. It is the one place the two engines genuinely differ in kind: a Claude
Code skill is model-triggered whether or not an agent names it, while a lowered skill-tool is
reachable only if bound to an agent. Rather than let that become a confusing behaviour
difference later, the spec is asked to say which agents can use it.

## Bundled resources

Extra files in the skill directory are listed as resources. On Claude Code they sit alongside
`SKILL.md`; on LangGraph their names are appended to the returned body under a
`## Bundled resources` heading, so the model knows they exist.
