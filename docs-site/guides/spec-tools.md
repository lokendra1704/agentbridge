---
title: Tools
category:
  uri: documentation
parent:
  uri: spec-reference
slug: spec-tools
position: 4
privacy:
  view: public
---

Declared once in `tools/tools.yaml`, then referenced by name from agent frontmatter.

```yaml
tools:
  - name: web-search
    description: Search the web and return titled, dated, linked results.
    parameters:
      type: object
      properties:
        query: {type: string, description: What to search for.}
        limit: {type: integer, description: Maximum number of results.}
      required: [query]
    implementation: research_assistant_impl.tools:web_search

  - name: read-file
    description: Read a text file from the local filesystem.
    builtin: Read
```

| Key | Type | Required | Notes |
|---|---|---|---|
| `name` | string | ✅ | Referenced from agent `tools:` lists |
| `description` | string | ✅ | Reaches the model on both engines |
| `parameters` | JSON Schema | — | See "Where the schema comes from" below |
| `implementation` | `module:callable` | one of | Your Python |
| `builtin` | string | one of | An engine-provided tool |

**Exactly one** of `implementation` or `builtin` must be set. Setting both, or neither, is a
parse error. That constraint is deliberate: the same tool is free on one engine and needs an
implementation on the other, so the format makes you say which kind it is.

## Implementation-backed tools

A dotted path to a callable you own. The bridge never generates these.

```python
# research_assistant_impl/tools.py

def web_search(query: str, limit: int = 5) -> str:
    """Search the web and return titled, dated, linked results.

    Args:
        query: What to search for.
        limit: Maximum number of results to return.
    """
    ...
```

**On LangGraph** the dotted path becomes a real import:

```python
from research_assistant_impl.tools import web_search as _impl_web_search

tool_web_search = StructuredTool.from_function(
    func=_impl_web_search,
    name="web-search",
    description="""Search the web and return titled, dated, linked results.""",
)
```

**On Claude Code** it can only be *named*. The engine cannot import a Python callable, so the
agent's prompt is correct but nothing is wired up. You get `BRIDGE103`:

```
tool 'web-search' is a Python callable (research_assistant_impl.tools:web_search);
Claude Code cannot import it, so agent 'researcher' will name a tool that is not
wired up
    hint: expose it over MCP, or mark it builtin if the engine provides it
```

Connecting it over MCP is manual work the bridge doesn't do for you.

## Builtin tools

Capabilities the runtime is expected to provide.

| `builtin:` | Claude Code | LangGraph shim |
|---|---|---|
| `Read` | native | `read_file` |
| `Write` | native | `write_file` |
| `Edit` | native | `edit_file` |
| `Bash` | native | `run_bash` |
| `Glob` | native | `glob_files` |
| `Grep` | native | `grep_files` |

LangGraph ships no file or shell tools, so `agentbridge.runtime.builtins` provides small
equivalents. Without them a spec that reads a file would *compile* on both engines but only
*run* on one — which would make "same workflow, two runtimes" true only on paper.

The shims are deliberately simpler than Claude Code's: no diff view, no permission prompts, no
session state. That difference is recorded in the mapping table as `lowered` rather than
`exact`, and reported as `BRIDGE201` (informational).

> ⚠️ **`Bash` runs arbitrary model-authored commands**
>
> The shim executes with the caller's privileges and no sandbox. Treat any workflow that
> exposes it accordingly.

A builtin with no shim — `NotebookEdit`, say — becomes a stub that raises
`NotImplementedError` when called, plus a `BRIDGE201` warning at compile time. Loud, not a
silent no-op.

## Where the schema comes from

`parameters` is a JSON Schema describing the tool's inputs. The two engines use it
differently, and this is intentional:

- **Claude Code** needs it. There is no function to inspect, so the declared schema is all the
  engine has.
- **LangGraph** does not. The Python callable's own signature and type hints are the source of
  truth, so the emitter lets the signature drive the schema and writes your declared
  `parameters` beside it as a comment for cross-checking:

```python
# declared parameter schema: {'type': 'object', 'properties': {...}}
# (inferred here from the callable's signature, which is authoritative)
```

If the two disagree, the signature is right and the spec is stale. The comment is there so you
notice.

## Unused tools

A tool no agent lists raises `BRIDGE022`. Add it to an agent's `tools:` or delete the
declaration — a tool nothing can reach is dead weight in the spec and confusing in the output.
