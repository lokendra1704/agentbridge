---
title: Quickstart
category:
  uri: documentation
slug: quickstart
position: 2
privacy:
  view: public
---

Compile the bundled example to both engines, then run the LangGraph version.

## Install

Requires Python 3.11 or later.

```bash
uv venv
uv pip install -e .
```

The compiler itself depends only on `pydantic` and `PyYAML` — you can emit a LangGraph
program on a machine with no LangGraph installed. To *run* generated code:

```bash
uv pip install -e '.[langgraph]'
```

## 1. Look at the example

```bash
agentbridge validate examples/research-assistant
```

```
research-assistant v0.1.0 — mode: graph
  agents: 3  skills: 1  tools: 3
  nodes: 4  edges: 3  branches: 1
  state fields: 4
```

A clean run prints the summary and nothing else. Anything odd about the spec is reported
here, before you compile.

## 2. Compile for Claude Code

```bash
agentbridge compile examples/research-assistant --engine claude-code --out ./my-plugin
```

```
examples/research-assistant/workflow.yaml: warning[BRIDGE100]: workflow
'research-assistant' declares an explicit graph, which Claude Code cannot
enforce; it is lowered to prose guidance in the command
    hint: the LangGraph target keeps the structure; this side is advisory
wrote 7 claude-code file(s) to ./my-plugin
```

Those warnings are the point, not noise — see [Diagnostics](doc:diagnostics). You get:

```
my-plugin/
├── .claude-plugin/plugin.json
├── .claude/agents/{planner,researcher,writer}.md
├── .claude/skills/citation-format/SKILL.md
├── .claude/commands/research-assistant.md
└── README.md
```

Copy `.claude/` into a project and run `/research-assistant`.

## 3. Compile for LangGraph

```bash
agentbridge compile examples/research-assistant --engine langgraph --out ./my-service
```

```
my-service/
├── workflow/
│   ├── state.py      TypedDict with reducers
│   ├── tools.py      imported callables and builtin shims
│   ├── skills.py     each skill as a load-on-demand tool
│   ├── agents.py     one node factory per agent
│   └── graph.py      StateGraph assembly and build_graph()
├── requirements.txt
└── README.md
```

## 4. Run it

```python
from workflow import build_graph

graph = build_graph()
result = graph.invoke({
    "messages": [("user", "why did the Bronze Age collapse?")],
    "topic": "bronze age collapse",
    "findings": [],
    "rounds": 0,
})
```

Set `ANTHROPIC_API_KEY` first. To run without one — in tests, or to swap provider —
`build_graph()` takes an injectable model factory:

```python
graph = build_graph(model_factory=my_fake_factory)
```

## 5. Add deployment files

```bash
agentbridge compile examples/research-assistant -e langgraph -o ./my-service \
    --deploy langgraph-platform
```

Adds `langgraph.json`, `.env.example`, and `DEPLOY.md`. Then `langgraph dev` to serve it
locally. See [Deploying](doc:deploying).

## Going the other way

Already have agents in Claude Code?

```bash
agentbridge import ./existing-project --out ./my-workflow
```

This recovers agents, skills, prompts, and capabilities. It cannot recover control flow —
a plugin doesn't contain any — so the imported workflow is in autonomous mode and says so
(`BRIDGE300`). Adding a `graph:` section is a decision only you can make.

## Next

- [Core concepts](doc:core-concepts)
- [Spec reference](doc:spec-reference)
- [CLI reference](doc:cli-reference)
