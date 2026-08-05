"""IR bundle -> spec directory.

This is the output side of `engine -> spec`: the importer produces a Bundle,
and this turns it back into authored files. It is also what makes the
round-trip test meaningful — parse(write(parse(x))) must equal parse(x).
"""

from __future__ import annotations

from typing import Any

from agentbridge.backends.base import EmittedFile
from agentbridge.ir.models import Bundle, WorkflowMode
from agentbridge.spec.frontmatter import render as render_frontmatter
from agentbridge.spec.parser import (
    AGENTS_DIR,
    SKILL_FILE,
    SKILLS_DIR,
    TOOLS_DIR,
    TOOLS_FILE,
    WORKFLOW_FILE,
)


def write_spec(bundle: Bundle) -> list[EmittedFile]:
    """Render `bundle` as the files an author would have written."""
    files = [EmittedFile(path=WORKFLOW_FILE, content=_workflow_yaml(bundle))]

    for agent in bundle.ordered_agents():
        front: dict[str, Any] = {"name": agent.name, "description": agent.description}
        if agent.tools:
            front["tools"] = list(agent.tools)
        if agent.skills:
            front["skills"] = list(agent.skills)
        if agent.model is not None:
            front["model"] = _model_dict(agent.model)
        files.append(
            EmittedFile(
                path=f"{AGENTS_DIR}/{agent.name}.md",
                content=render_frontmatter(front, agent.prompt),
            )
        )

    for skill in bundle.ordered_skills():
        front = {"name": skill.name, "description": skill.description}
        if skill.allowed_tools:
            front["allowed-tools"] = list(skill.allowed_tools)
        files.append(
            EmittedFile(
                path=f"{SKILLS_DIR}/{skill.name}/{SKILL_FILE}",
                content=render_frontmatter(front, skill.body),
            )
        )

    if bundle.tools:
        files.append(EmittedFile(path=f"{TOOLS_DIR}/{TOOLS_FILE}", content=_tools_yaml(bundle)))

    return files


def _model_dict(model: Any) -> dict[str, Any]:
    out: dict[str, Any] = {"name": model.name}
    if model.max_tokens is not None:
        out["max_tokens"] = model.max_tokens
    if model.effort is not None:
        out["effort"] = model.effort.value
    if model.temperature is not None:
        out["temperature"] = model.temperature
    return out


def _workflow_yaml(bundle: Bundle) -> str:
    wf = bundle.workflow
    doc: dict[str, Any] = {
        "name": wf.name,
        "description": wf.description,
        "version": wf.version,
        "mode": wf.mode.value,
        "model": _model_dict(wf.model),
    }

    if wf.state.fields:
        doc["state"] = {
            "name": wf.state.name,
            "fields": [
                {
                    k: v
                    for k, v in (
                        ("name", f.name),
                        ("type", f.type.value),
                        ("reducer", f.reducer.value),
                        ("description", f.description),
                    )
                    if v is not None
                }
                for f in wf.state.fields
            ],
        }

    if wf.mode is WorkflowMode.GRAPH:
        graph: dict[str, Any] = {"entry": wf.entry}
        graph["nodes"] = [
            {
                k: v
                for k, v in (
                    ("name", n.name),
                    ("agent", n.agent),
                    ("function", n.function),
                    ("description", n.description),
                )
                if v is not None
            }
            for n in wf.nodes
        ]
        if wf.edges:
            graph["edges"] = [{"from": e.source, "to": e.target} for e in wf.edges]
        if wf.branches:
            graph["branches"] = [
                {
                    "from": b.source,
                    "condition": b.condition,
                    "description": b.description,
                    "targets": dict(b.targets),
                }
                for b in wf.branches
            ]
        doc["graph"] = graph

    return _dump(doc)


def _tools_yaml(bundle: Bundle) -> str:
    tools = []
    for tool in bundle.ordered_tools():
        entry: dict[str, Any] = {"name": tool.name, "description": tool.description}
        if tool.parameters:
            entry["parameters"] = tool.parameters
        if tool.implementation:
            entry["implementation"] = tool.implementation
        if tool.builtin:
            entry["builtin"] = tool.builtin
        tools.append(entry)
    return _dump({"tools": tools})


def _dump(doc: dict[str, Any]) -> str:
    import yaml

    return yaml.safe_dump(doc, sort_keys=False, default_flow_style=False, allow_unicode=True)
