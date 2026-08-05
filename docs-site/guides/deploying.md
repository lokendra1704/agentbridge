---
title: Deploying
category:
  uri: documentation
slug: deploying
position: 8
privacy:
  view: public
---

Deployment is a separate step from compilation, and separate from the runtime.

## Why it's separate

LangGraph Platform is a different product from LangGraph. You can run the engine locally with
no deployment target at all, and one engine may eventually have several. Folding deployment
into the backend would make the common case — just run it — carry the uncommon case's baggage.

The split shows up in the output: the **backend** emits the program, the **target** emits
everything about shipping it.

## Compile with a target

```bash
agentbridge compile ./spec -e langgraph -o ./service --deploy langgraph-platform
```

Adds three files alongside the generated program:

| File | Contents |
|---|---|
| `langgraph.json` | Platform manifest |
| `.env.example` | Environment template |
| `DEPLOY.md` | Step-by-step commands for this workflow |

The target must ship the engine you compiled for. Mismatching them is a usage error:

```
error: deployment target 'langgraph-platform' ships 'langgraph' output, but you
compiled for 'claude-code'
```

## The manifest

```json
{
  "dependencies": ["."],
  "graphs": {
    "research-assistant": "./workflow/graph.py:build_graph"
  },
  "env": ".env"
}
```

Note it points at `build_graph` as a **factory**, not at a module-level graph object.
Constructing the graph at import time would require credentials just to import the module —
which breaks tooling, CI, and anything that wants to inspect the program without running it.

## Deploy

```bash
pip install -U 'langgraph-cli[inmem]'

cp .env.example .env      # add ANTHROPIC_API_KEY
langgraph dev             # local server + Studio
```

| Command | Notes |
|---|---|
| `langgraph dev` | Live-reload server, opens Studio against it |
| `langgraph up` | Runs the production container locally. Needs Docker |
| `langgraph build -t <name>:latest` | Builds a deployable image |

## Checkpointers

`build_graph()` takes an optional `checkpointer` and defaults to `None`:

```python
def build_graph(config=None, *, checkpointer=None, model_factory=None): ...
```

**Leave it unset when deployed** — the platform supplies its own. The default is `None` rather
than a hardcoded checkpointer because the right local choice (memory, SQLite, Postgres) is a
deployment decision, not a workflow decision. Set it explicitly for local runs that need
persistence:

```python
from langgraph.checkpoint.memory import MemorySaver

graph = build_graph(checkpointer=MemorySaver())
```

## Swapping the model

The same factory seam changes provider, routes agents to different models, or stubs the model
entirely:

```python
def my_factory(name, *, max_tokens=None, effort=None, temperature=None):
    ...  # return any BaseChatModel

graph = build_graph(model_factory=my_factory)
```

This is what lets the test suite build and invoke the real graph with no API key.

## Deploying the Claude Code side

There is no deployment target, because there's nothing to deploy. Copy `.claude/` into a
project:

```bash
agentbridge compile ./spec -e claude-code -o ./plugin
cp -r ./plugin/.claude ./my-project/
```

Then run `/<workflow-name>` in that project. The generated `README.md` in the output says the
same thing, in case the plugin travels without these docs.

## Keeping generated output current

```yaml
- name: Check generated LangGraph output is current
  run: |
    agentbridge compile ./spec -e langgraph -o ./generated --deploy langgraph-platform
    git diff --exit-code ./generated
```

Catches a spec edited without regenerating — the drift the project exists to prevent.
