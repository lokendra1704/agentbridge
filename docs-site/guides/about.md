---
title: What is agentbridge?
category:
  uri: documentation
slug: about-agentbridge
position: 1
privacy:
  view: public
---

**Write an agentic workflow once. Run it in Claude Code *and* as a deployed LangGraph program.**

Normally these are two separate builds. You prototype an agent in Claude Code because the
feedback loop is fast and you can watch it work — then, to ship it, you rewrite the whole
thing as a LangGraph program. Two codebases, drifting apart from the first commit.

agentbridge removes the rewrite. You describe the workflow once, in plain files, and it
compiles both versions.

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

## What you get

| | |
|---|---|
| **One source of truth** | A folder of Markdown and YAML. No code required to describe a workflow. |
| **Two runtimes** | A `.claude/` plugin, and a runnable LangGraph program with `langgraph.json` for deployment. |
| **A way back** | Import an existing `.claude/` plugin into the spec and lift it onto LangGraph. |
| **Honest translation** | Every place the two engines genuinely differ is reported with the exact spec file, not discovered at runtime. |

## What it does *not* do

- It does not make the two engines equivalent. They aren't. It makes the differences
  explicit and puts them in one place.
- It does not generate your business logic. Tools and branch conditions are ordinary Python
  you own; the bridge wires them up.
- It does not maintain a model registry. Model IDs pass through verbatim.

## Is this for you?

**Yes**, if you build AI agents, you iterate in Claude Code, and you eventually need to run
them somewhere real.

**Probably not**, if you only ever need one of the two runtimes. The value is entirely in
not maintaining two copies.

## Next

- [Quickstart](doc:quickstart) — install and compile both targets in five minutes
- [Core concepts](doc:core-concepts) — agents, skills, tools, and the two workflow modes
- [How concepts map to each engine](doc:engine-mapping) — including the two lossy directions
