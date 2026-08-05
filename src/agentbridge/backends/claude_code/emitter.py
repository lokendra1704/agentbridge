"""IR -> a Claude Code plugin.

The spec format was designed to sit close to `.claude/` conventions, so most
of this file is a rename. The interesting part is `_command()`, which is where
declared control flow gets lowered into prose — the lossy direction the design
has to confront rather than paper over.
"""

from __future__ import annotations

from typing import Any

from agentbridge.backends.base import EmittedFile, RuntimeBackend
from agentbridge.diagnostics import DiagnosticBag
from agentbridge.ir.models import (
    END,
    Bundle,
    EngineContract,
    FieldType,
    WorkflowMode,
)
from agentbridge.spec.frontmatter import render as render_frontmatter

PLUGIN_DIR = ".claude-plugin"
AGENTS_DIR = ".claude/agents"
SKILLS_DIR = ".claude/skills"
COMMANDS_DIR = ".claude/commands"


class ClaudeCodeBackend(RuntimeBackend):
    name = "claude-code"
    description = "A Claude Code plugin: .claude/ agents, skills, and commands."

    def emit(self, bundle: Bundle, diagnostics: DiagnosticBag) -> list[EmittedFile]:
        files: list[EmittedFile] = [
            EmittedFile(path=f"{PLUGIN_DIR}/plugin.json", content=_plugin_manifest(bundle))
        ]

        for agent in bundle.ordered_agents():
            files.append(
                EmittedFile(
                    path=f"{AGENTS_DIR}/{agent.name}.md",
                    content=_agent_file(bundle, agent),
                )
            )
            for tool in bundle.agent_tools(agent):
                if tool.implementation:
                    diagnostics.warn(
                        "BRIDGE103",
                        f"tool {tool.name!r} is a Python callable "
                        f"({tool.implementation}); Claude Code cannot import it, so "
                        f"agent {agent.name!r} will name a tool that is not wired up",
                        location=tool.location,
                        hint="expose it over MCP, or mark it builtin if the engine provides it",
                    )

        for skill in bundle.ordered_skills():
            files.append(
                EmittedFile(
                    path=f"{SKILLS_DIR}/{skill.name}/SKILL.md",
                    content=render_frontmatter(
                        _skill_frontmatter(skill), skill.body or _SKILL_PLACEHOLDER
                    ),
                )
            )

        files.append(
            EmittedFile(
                path=f"{COMMANDS_DIR}/{bundle.workflow.name}.md",
                content=_command(bundle, diagnostics),
            )
        )
        files.append(EmittedFile(path="README.md", content=_readme(bundle)))
        return files

    def contract(self, bundle: Bundle, files: list[EmittedFile]) -> EngineContract:
        paths = {str(f.path) for f in files}
        agents = {a.name for a in bundle.ordered_agents() if f"{AGENTS_DIR}/{a.name}.md" in paths}
        skills = {
            s.name for s in bundle.ordered_skills() if f"{SKILLS_DIR}/{s.name}/SKILL.md" in paths
        }
        # Tools are named inside agent frontmatter rather than getting their own
        # file, so read them back out of what was actually written.
        command = next((f for f in files if str(f.path).startswith(COMMANDS_DIR)), None)
        emitted_agent_files = [f for f in files if str(f.path).startswith(AGENTS_DIR)]
        tools: set[str] = set()
        for f in emitted_agent_files:
            tools |= _tools_named_in(f.content)
        nodes = _nodes_named_in(command.content) if command else set()
        return EngineContract(
            engine=self.name,
            agents=frozenset(agents),
            skills=frozenset(skills),
            tools=frozenset(tools),
            nodes=frozenset(nodes),
            entry=bundle.workflow.entry,
        )


_SKILL_PLACEHOLDER = "_This skill has no body yet._"

#: Machine-readable trailers. Claude Code reads agent frontmatter, not these,
#: so they carry the associations that would otherwise be recoverable only by
#: parsing prose — which is what makes the importer close the loop instead of
#: guessing. Inert in Markdown, and invisible when the file is rendered.
_TOOL_MARKER = "<!-- agentbridge:tools "
_SKILL_MARKER = "<!-- agentbridge:skills "
_NODE_MARKER = "<!-- agentbridge:nodes "


def _tools_named_in(content: str) -> set[str]:
    return set(tools_named_in(content))


def tools_named_in(content: str) -> dict[str, str]:
    """Read back the agent's tools as `spec name -> engine builtin`.

    The pairing matters: frontmatter carries the *engine's* name for a tool
    (`Read`), which is what Claude Code needs, but the spec's own name for it
    (`read-file`) is what the IR uses. Recording both is what lets an import
    land back on the spec it came from.
    """
    out: dict[str, str] = {}
    for entry in _marked(content, _TOOL_MARKER):
        name, _, builtin = entry.partition("=")
        out[name] = builtin
    return out


def skills_named_in(content: str) -> set[str]:
    """Read back the agent's skill list. Used by the importer."""
    return _marked(content, _SKILL_MARKER)


def _nodes_named_in(content: str) -> set[str]:
    return _marked(content, _NODE_MARKER)


def _marked(content: str, marker: str) -> set[str]:
    for line in content.splitlines():
        if line.startswith(marker):
            payload = line[len(marker) :].removesuffix("-->").strip()
            return {p for p in payload.split(",") if p}
    return set()


def _plugin_manifest(bundle: Bundle) -> str:
    import json

    wf = bundle.workflow
    return (
        json.dumps(
            {
                "name": wf.name,
                "description": wf.description,
                "version": wf.version,
            },
            indent=2,
        )
        + "\n"
    )


def _skill_frontmatter(skill: Any) -> dict[str, Any]:
    front: dict[str, Any] = {"name": skill.name, "description": skill.description}
    if skill.allowed_tools:
        front["allowed-tools"] = list(skill.allowed_tools)
    return front


def _agent_file(bundle: Bundle, agent: Any) -> str:
    front: dict[str, Any] = {"name": agent.name, "description": agent.description}
    tools = [t.builtin or t.name for t in bundle.agent_tools(agent)]
    if tools:
        front["tools"] = tools
    model = agent.model or bundle.workflow.model
    front["model"] = model.name

    body = agent.prompt.rstrip()
    skills = bundle.agent_skills(agent)
    if skills:
        lines = [
            "",
            "## Skills available to you",
            "",
            "Load one of these when its trigger condition applies:",
            "",
        ]
        lines += [f"- **{s.name}** — {s.description}" for s in skills]
        body = body + "\n" + "\n".join(lines)

    # Trailers so `contract()` can read back what was emitted instead of
    # trusting the input bundle, and so the importer recovers the agent's
    # capabilities rather than re-deriving them from prose.
    named_tools = ",".join(
        f"{t.name}={t.builtin or ''}"
        for t in sorted(bundle.agent_tools(agent), key=lambda t: t.name)
    )
    named_skills = ",".join(sorted(s.name for s in skills))
    body = f"{body}\n\n{_TOOL_MARKER}{named_tools} -->\n{_SKILL_MARKER}{named_skills} -->"
    return render_frontmatter(front, body)


def _command(bundle: Bundle, diagnostics: DiagnosticBag) -> str:
    """The orchestrating slash command.

    For an autonomous workflow this is a short brief. For a declared graph it
    is the degradation path: the structure cannot be enforced here, only
    described, so the command spells out the sequence and every branch rule in
    prose.
    """
    wf = bundle.workflow
    front = {
        "name": wf.name,
        "description": wf.description,
    }
    parts: list[str] = [f"# {wf.name}", "", wf.description, ""]

    if wf.mode is WorkflowMode.GRAPH:
        diagnostics.warn(
            "BRIDGE100",
            f"workflow {wf.name!r} declares an explicit graph, which Claude Code "
            "cannot enforce; it is lowered to prose guidance in the command",
            location=wf.location,
            hint="the LangGraph target keeps the structure; this side is advisory",
        )
        parts += _graph_prose(bundle, diagnostics)
    else:
        parts += [
            "## How to run this",
            "",
            "No fixed sequence is defined. Delegate to the agents below as the "
            "task requires, and use their descriptions to decide which fits.",
            "",
            "## Agents",
            "",
        ]
        parts += [f"- **{a.name}** — {a.description}" for a in bundle.ordered_agents()]
        parts.append("")

    parts += _state_prose(bundle, diagnostics)

    node_names = ",".join(sorted(n.name for n in wf.nodes))
    parts += ["", f"{_NODE_MARKER}{node_names} -->"]
    return render_frontmatter(front, "\n".join(parts))


def _graph_prose(bundle: Bundle, diagnostics: DiagnosticBag) -> list[str]:
    wf = bundle.workflow
    out = [
        "## Steps",
        "",
        f"Work through these in order, starting at **{wf.entry}**. "
        "This sequence is the workflow's definition — follow it rather than "
        "improvising an order.",
        "",
    ]

    for index, node in enumerate(wf.nodes, start=1):
        agent = bundle.agents.get(node.agent) if node.agent else None
        what = agent.description if agent else (node.description or node.function or "")
        label = f"the **{node.agent}** agent" if node.agent else f"`{node.function}`"
        out.append(f"{index}. **{node.name}** — delegate to {label}. {what}")

    out.append("")
    successors = [(e.source, e.target) for e in wf.edges]
    if successors:
        out += ["### Order", ""]
        for source, target in successors:
            arrow = "finish" if target == END else f"then **{target}**"
            out.append(f"- After **{source}**, {arrow}.")
        out.append("")

    if wf.branches:
        out += ["### Decisions", ""]
        for branch in wf.branches:
            diagnostics.warn(
                "BRIDGE101",
                f"branch condition {branch.condition!r} is a Python callable and "
                "cannot run in Claude Code; only its prose description survives",
                location=branch.location,
                hint="keep the description accurate — here it *is* the routing logic",
            )
            options = ", ".join(
                f"`{label}` -> {'finish' if target == END else f'**{target}**'}"
                for label, target in sorted(branch.targets.items())
            )
            out.append(f"- After **{branch.source}**: {branch.description} ({options})")
        out.append("")
    return out


def _state_prose(bundle: Bundle, diagnostics: DiagnosticBag) -> list[str]:
    fields = [f for f in bundle.workflow.state.fields if f.type is not FieldType.MESSAGES]
    if not fields:
        return []
    diagnostics.warn(
        "BRIDGE102",
        f"workflow {bundle.workflow.name!r} declares {len(fields)} typed state "
        "field(s); Claude Code has no state object, so they become prose the "
        "model is asked to track",
        location=bundle.workflow.state.location,
        hint="nothing enforces these on this engine; the LangGraph target does",
    )
    out = [
        "## Information to carry through",
        "",
        "Track these as you work. Nothing enforces them here, so restate them "
        "explicitly when you hand off between steps:",
        "",
    ]
    for field in fields:
        desc = f" — {field.description}" if field.description else ""
        out.append(f"- `{field.name}` ({field.type.value}){desc}")
    out.append("")
    return out


def _readme(bundle: Bundle) -> str:
    wf = bundle.workflow
    return "\n".join(
        [
            f"# {wf.name} (Claude Code plugin)",
            "",
            wf.description,
            "",
            "Generated by agentbridge. Edit the spec, not these files.",
            "",
            "## Use it",
            "",
            "Copy `.claude/` into your project, then run:",
            "",
            "```",
            f"/{wf.name}",
            "```",
            "",
            f"Agents: {', '.join(a.name for a in bundle.ordered_agents()) or 'none'}",
            "",
            f"Skills: {', '.join(s.name for s in bundle.ordered_skills()) or 'none'}",
            "",
        ]
    )
