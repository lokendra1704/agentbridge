"""A `.claude/` plugin -> IR.

This is the direction that lets work already done in Claude Code be lifted
onto LangGraph without a rewrite. It is close to lossless for agents and
skills, and *structurally* lossy in one specific way: a Claude Code plugin
contains no declared control flow, so the imported workflow lands in
autonomous mode and the author has to add a `graph:` section before the
LangGraph target produces anything more than a single node. The importer says
so rather than leaving it to be discovered later.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agentbridge.backends.claude_code.emitter import skills_named_in, tools_named_in
from agentbridge.diagnostics import DiagnosticBag, SpecError, SpecLocation
from agentbridge.ir.models import (
    Agent,
    Bundle,
    ModelConfig,
    Skill,
    Tool,
    Workflow,
    WorkflowMode,
)
from agentbridge.spec.frontmatter import FrontmatterError
from agentbridge.spec.frontmatter import parse as parse_frontmatter

#: Tool names Claude Code provides itself. Anything an agent names that is not
#: in here is assumed to come from MCP and is imported as a declared-but-
#: unimplemented tool, so the spec still type-checks.
BUILTIN_TOOLS = frozenset(
    {
        "Bash",
        "Edit",
        "Glob",
        "Grep",
        "NotebookEdit",
        "Read",
        "Task",
        "TodoWrite",
        "WebFetch",
        "WebSearch",
        "Write",
    }
)


def import_plugin(
    root: Path, diagnostics: DiagnosticBag | None = None
) -> tuple[Bundle, DiagnosticBag]:
    """Import the Claude Code plugin rooted at `root`.

    `root` may be the project directory containing `.claude/`, or `.claude/`
    itself — both are common ways to point at a plugin.
    """
    bag = diagnostics or DiagnosticBag()
    root = Path(root)
    claude_dir = root / ".claude" if (root / ".claude").is_dir() else root
    if not claude_dir.is_dir():
        raise SpecError(f"no .claude directory found at {root}", bag)

    agents, tools = _import_agents(claude_dir / "agents", bag)
    skills = _import_skills(claude_dir / "skills", bag)
    workflow = _import_workflow(root, claude_dir, bag)

    if not agents:
        bag.warn(
            "BRIDGE302",
            f"no agents found under {claude_dir / 'agents'}",
            location=SpecLocation(file=claude_dir),
        )

    bag.warn(
        "BRIDGE300",
        "a Claude Code plugin declares no control flow, so the imported "
        "workflow is in autonomous mode",
        location=SpecLocation(file=claude_dir),
        hint=(
            "add a graph: section to workflow.yaml before compiling to LangGraph, "
            "or that target will collapse to a single node (BRIDGE200)"
        ),
    )

    return Bundle(workflow=workflow, agents=agents, skills=skills, tools=tools), bag


def _import_agents(
    agents_dir: Path, bag: DiagnosticBag
) -> tuple[dict[str, Agent], dict[str, Tool]]:
    agents: dict[str, Agent] = {}
    tools: dict[str, Tool] = {}
    if not agents_dir.is_dir():
        return agents, tools

    for path in sorted(agents_dir.glob("*.md")):
        loc = SpecLocation(file=path)
        try:
            front, body, _ = parse_frontmatter(path.read_text(encoding="utf-8"))
        except FrontmatterError as exc:
            raise SpecError(f"{path}: {exc}") from exc

        # A trailer left by a previous emit is authoritative when present: it
        # carries the spec's own name for each tool, which frontmatter cannot
        # (frontmatter must name the tool the way the engine does). Fall back
        # to frontmatter for plugins nobody generated.
        tool_names: list[str] = []
        trailer = tools_named_in(body)
        if trailer:
            for spec_name, builtin in sorted(trailer.items()):
                tool = _tool_from_trailer(spec_name, builtin, loc)
                tools.setdefault(tool.name, tool)
                tool_names.append(tool.name)
        else:
            for raw in _as_list(front.get("tools")):
                tool = _tool_for(raw, loc, bag)
                tools.setdefault(tool.name, tool)
                tool_names.append(tool.name)

        skills = _as_list(front.get("skills")) or sorted(skills_named_in(body))

        name = _slug(front.get("name") or path.stem)
        agents[name] = Agent(
            name=name,
            description=front.get("description") or f"Imported from {path.name}.",
            prompt=body,
            model=_model_for(front.get("model"), loc),
            tools=tool_names,
            skills=[_slug(s) for s in skills],
            location=loc,
        )
    return agents, tools


def _import_skills(skills_dir: Path, bag: DiagnosticBag) -> dict[str, Skill]:
    skills: dict[str, Skill] = {}
    if not skills_dir.is_dir():
        return skills

    for skill_dir in sorted(p for p in skills_dir.iterdir() if p.is_dir()):
        path = skill_dir / "SKILL.md"
        if not path.is_file():
            continue
        loc = SpecLocation(file=path)
        try:
            front, body, _ = parse_frontmatter(path.read_text(encoding="utf-8"))
        except FrontmatterError as exc:
            raise SpecError(f"{path}: {exc}") from exc

        name = _slug(front.get("name") or skill_dir.name)
        description = front.get("description") or ""
        if not description:
            bag.warn(
                "BRIDGE303",
                f"skill {name!r} has no description; on engines without a skill "
                "primitive that description is the only trigger signal",
                location=loc,
                hint="add a 'description' stating when the skill applies",
            )
            description = f"The {name} skill."
        skills[name] = Skill(
            name=name,
            description=description,
            body=body,
            resources=[p.name for p in sorted(skill_dir.iterdir()) if p.name != "SKILL.md"],
            allowed_tools=_as_list(front.get("allowed-tools")),
            location=loc,
        )
    return skills


def _import_workflow(root: Path, claude_dir: Path, bag: DiagnosticBag) -> Workflow:
    manifest_path = next(
        (
            p
            for p in (root / ".claude-plugin" / "plugin.json", claude_dir / "plugin.json")
            if p.is_file()
        ),
        None,
    )
    data: dict[str, Any] = {}
    if manifest_path is not None:
        try:
            loaded = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise SpecError(f"{manifest_path}: invalid JSON: {exc}") from exc
        if isinstance(loaded, dict):
            data = loaded

    name = _slug(data.get("name") or root.resolve().name)
    return Workflow(
        name=name,
        description=data.get("description") or f"Imported from {claude_dir}.",
        version=str(data.get("version", "0.1.0")),
        mode=WorkflowMode.AUTONOMOUS,
        location=SpecLocation(file=manifest_path or claude_dir),
    )


def _tool_from_trailer(spec_name: str, builtin: str, loc: SpecLocation) -> Tool:
    """Rebuild a tool from a generated plugin's trailer.

    An empty `builtin` means the spec backed this tool with a Python callable,
    which the plugin could not carry (BRIDGE103 said so on the way out). The
    name and description survive; the implementation path does not.
    """
    if builtin:
        return Tool(
            name=spec_name,
            description=f"The {builtin} tool provided by the engine.",
            builtin=builtin,
            location=loc,
        )
    return Tool(
        name=spec_name,
        description=f"Tool {spec_name!r}; its implementation did not survive the plugin format.",
        implementation="unwired:placeholder",
        location=loc,
    )


def _tool_for(raw: str, loc: SpecLocation, bag: DiagnosticBag) -> Tool:
    if raw in BUILTIN_TOOLS:
        return Tool(
            name=_slug(raw),
            description=f"The {raw} tool provided by the engine.",
            builtin=raw,
            location=loc,
        )
    bag.warn(
        "BRIDGE304",
        f"tool {raw!r} is not a known engine builtin, so it is imported without an implementation",
        location=loc,
        hint=f"add an 'implementation:' for {_slug(raw)} in tools/tools.yaml before compiling",
    )
    return Tool(
        name=_slug(raw),
        description=f"Imported tool {raw!r}; implementation not yet supplied.",
        builtin=raw,
        location=loc,
    )


def _model_for(raw: Any, loc: SpecLocation) -> ModelConfig | None:
    if not raw:
        return None
    if isinstance(raw, str):
        # Claude Code accepts aliases like "inherit" / "sonnet"; only a concrete
        # id is meaningful to another engine.
        if raw in {"inherit", "default"}:
            return None
        return ModelConfig(name=raw, location=loc)
    if isinstance(raw, dict):
        return ModelConfig(name=str(raw.get("name", "claude-opus-5")), location=loc)
    return None


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [p.strip() for p in value.split(",") if p.strip()]
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    return []


def _slug(value: str) -> str:
    out = "".join(c if c.isalnum() else "-" for c in str(value).lower())
    while "--" in out:
        out = out.replace("--", "-")
    return out.strip("-") or "unnamed"
