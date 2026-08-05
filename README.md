# agentbridge

**Write your AI workflow once. Run it in Claude Code *and* as a deployed LangGraph program.**

Normally these are two separate builds. You prototype an agent in Claude Code because the
feedback loop is fast and you can watch it work — then, to ship it, you rewrite the whole
thing as a LangGraph program. Two codebases, drifting apart from day one.

agentbridge removes the rewrite. You describe the workflow once, in plain files, and it
generates both versions.

---

## The idea in one picture

```
                    ┌──────────────────────────┐
                    │   Your workflow, once    │
                    │  (folders and Markdown)  │
                    └────────────┬─────────────┘
                                 │
                  ┌──────────────┴──────────────┐
                  ▼                             ▼
       ┌─────────────────────┐      ┌──────────────────────┐
       │    Claude Code      │      │      LangGraph       │
       │  try it, watch it,  │      │  deploy it, run it   │
       │   change it fast    │      │      at scale        │
       └─────────────────────┘      └──────────────────────┘
                  │
                  └──── already built something here?
                        Import it and go the other way.
```

---

## What you write

A folder. That's the whole format.

```
research-assistant/
├── workflow.yaml              ← the steps, and how they connect
├── agents/
│   ├── planner.md             ← plain English: "you turn a request into questions"
│   ├── researcher.md
│   └── writer.md
├── skills/
│   └── citation-format/
│       └── SKILL.md           ← reference material an agent pulls in when needed
└── tools/
    └── tools.yaml             ← what the agents are allowed to do
```

Each agent file is instructions you'd give a capable colleague, with a short header:

```markdown
---
name: researcher
description: Gathers source material and records where each claim came from.
tools: [web-search, read-file]
skills: [citation-format]
---

You gather source material for the open questions.

For each question, search, then record what you found and where it came from.
A finding without a traceable source is not a finding — drop it rather than
carrying it forward unattributed.
```

No programming required for this part. If you can write a clear brief, you can write an agent.

---

## Try it in five minutes

```bash
# 1. Install
uv venv && uv pip install -e .

# 2. Look at the example that ships with it
agentbridge validate examples/research-assistant

# 3. Build the Claude Code version
agentbridge compile examples/research-assistant --engine claude-code --out ./my-plugin

# 4. Build the LangGraph version
agentbridge compile examples/research-assistant --engine langgraph --out ./my-service
```

Now `./my-plugin` is a Claude Code plugin you can drop into a project, and `./my-service`
is a Python program you can run and deploy. Same workflow, both times.

**Already built agents in Claude Code?** Go the other direction:

```bash
agentbridge import ./existing-project --out ./my-workflow
```

---

## The five commands

| Command | What it does |
|---|---|
| `agentbridge validate <folder>` | Checks your workflow makes sense and reports anything odd |
| `agentbridge compile <folder> -e <engine> -o <out>` | Builds the version for one engine |
| `agentbridge import <project> -o <folder>` | Turns existing Claude Code agents into a workflow |
| `agentbridge engines` | Lists what it can build for |
| `agentbridge mapping` | Shows exactly how each idea is translated |

Add `--deploy langgraph-platform` when compiling to also get the files you need to put the
LangGraph version on a server.

---

## What it tells you (and why that matters)

The two engines are genuinely different, and some things don't translate cleanly.
agentbridge always says so — out loud, pointing at the exact file:

```
workflow.yaml: warning[BRIDGE100]: workflow 'research-assistant' declares an
explicit graph, which Claude Code cannot enforce; it is lowered to prose
guidance in the command
    hint: the LangGraph target keeps the structure; this side is advisory
```

That message is doing real work. It means: *the fixed sequence you wrote is a guarantee on
LangGraph, but only a strong suggestion in Claude Code, because Claude Code lets the model
decide what to do next.* Knowing that up front is much better than discovering it when the
two behave differently.

Nothing is ever dropped quietly. If no warning appeared, the translation was clean.

---

## Two things worth understanding

**1. Say what order things happen in — if you care.**
Claude Code lets the model decide what to do next. LangGraph wants a fixed map. If your
`workflow.yaml` has no `graph:` section, the Claude Code version is perfect and the
LangGraph version collapses into a single step, because "the model decides" isn't a map.
Add a `graph:` section and both work — Claude Code reads it as instructions, LangGraph
enforces it.

**2. Skills work differently, but they still work.**
A skill is reference material an agent loads only when it becomes relevant, so it costs
nothing until it's needed. Claude Code has this built in. LangGraph doesn't, so agentbridge
turns each skill into something the agent can reach for on demand. Same behaviour, different
plumbing. You don't have to do anything.

---

## Is this for me?

**Yes, if** you're building AI agents, you like iterating in Claude Code, and you
eventually need to run them somewhere real.

**Probably not, if** you only ever need one of the two. The value here is entirely in not
maintaining two copies.

---

## Where to go next

- **`TechnicalREADME.md`** — how it works inside, and why it's built this way
- **`CodeIndex.md`** — a map of the source, for finding things fast
- **`examples/research-assistant/`** — a complete, working workflow to copy

---

## Status

Working and tested — 99 tests, including ones that build the generated LangGraph program
and actually run it. Two engines today (Claude Code and LangGraph); the internals are set
up so a third is a new folder, not a rewrite.
