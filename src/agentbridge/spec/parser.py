"""Spec directory -> IR bundle.

Layout::

    <spec>/
      workflow.yaml            structure: graph wiring, state, model defaults
      agents/<name>.md         frontmatter + system prompt
      skills/<name>/SKILL.md   frontmatter + instructions
      tools/tools.yaml         tool declarations

Structure lives in YAML and prose lives in Markdown, on the theory that
diffing a system prompt should not mean diffing a YAML string literal.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from agentbridge.diagnostics import DiagnosticBag, SpecError, SpecLocation
from agentbridge.ir.models import (
    Agent,
    Branch,
    Bundle,
    Edge,
    ModelConfig,
    Node,
    Skill,
    StateField,
    StateSchema,
    Tool,
    Workflow,
    WorkflowMode,
)
from agentbridge.ir.validate import validate_bundle
from agentbridge.spec.frontmatter import FrontmatterError
from agentbridge.spec.frontmatter import parse as parse_frontmatter

WORKFLOW_FILE = "workflow.yaml"
AGENTS_DIR = "agents"
SKILLS_DIR = "skills"
TOOLS_DIR = "tools"
SKILL_FILE = "SKILL.md"
TOOLS_FILE = "tools.yaml"

#: Frontmatter keys the agent parser understands. Anything else is reported
#: rather than dropped, per the no-silent-loss rule.
_AGENT_KEYS = {"name", "description", "tools", "skills", "model"}
_SKILL_KEYS = {"name", "description", "resources", "allowed-tools", "allowed_tools"}


def parse_spec(
    root: Path, diagnostics: DiagnosticBag | None = None
) -> tuple[Bundle, DiagnosticBag]:
    """Parse the spec rooted at `root`.

    Raises `SpecError` only when the spec cannot be turned into a bundle at
    all. Recoverable problems come back as diagnostics so the caller can show
    every issue at once instead of one per run.
    """
    bag = diagnostics or DiagnosticBag()
    root = Path(root)
    if not root.is_dir():
        raise SpecError(f"spec directory not found: {root}", bag)

    workflow_path = root / WORKFLOW_FILE
    if not workflow_path.is_file():
        raise SpecError(f"missing {WORKFLOW_FILE} in {root}", bag)

    tools = _parse_tools(root / TOOLS_DIR / TOOLS_FILE, bag)
    skills = _parse_skills(root / SKILLS_DIR, bag)
    agents = _parse_agents(root / AGENTS_DIR, bag)
    workflow = _parse_workflow(workflow_path, bag)

    bundle = Bundle(workflow=workflow, agents=agents, skills=skills, tools=tools)
    validate_bundle(bundle, bag)
    return bundle, bag


# --------------------------------------------------------------------------
# workflow.yaml
# --------------------------------------------------------------------------


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise SpecError(f"{path}: invalid YAML: {exc}") from exc
    if loaded is None:
        return {}
    if not isinstance(loaded, dict):
        raise SpecError(f"{path}: expected a mapping at the top level")
    return loaded


def _parse_workflow(path: Path, bag: DiagnosticBag) -> Workflow:
    raw = _load_yaml(path)
    loc = SpecLocation(file=path)

    graph = raw.get("graph") or {}
    if not isinstance(graph, dict):
        raise SpecError(f"{path}: 'graph' must be a mapping")

    declared_mode = raw.get("mode")
    if declared_mode is None:
        mode = WorkflowMode.GRAPH if graph else WorkflowMode.AUTONOMOUS
    else:
        try:
            mode = WorkflowMode(declared_mode)
        except ValueError as exc:
            raise SpecError(f"{path}: unknown mode {declared_mode!r}") from exc

    fields = {
        "name": raw.get("name") or path.parent.name,
        "description": raw.get("description") or "",
        "version": str(raw.get("version", "0.1.0")),
        "mode": mode,
        "entry": graph.get("entry"),
        "nodes": [_node(n, loc) for n in graph.get("nodes", [])],
        "edges": [_edge(e, loc) for e in graph.get("edges", [])],
        "branches": [_branch(b, loc) for b in graph.get("branches", [])],
        "state": _state(raw.get("state") or {}, loc),
        "model": _model(raw.get("model") or {}, loc),
        "location": loc,
    }
    _report_unknown_keys(
        raw,
        {"name", "description", "version", "mode", "graph", "state", "model"},
        loc,
        bag,
        "workflow.yaml",
    )
    try:
        return Workflow(**fields)
    except ValidationError as exc:
        raise SpecError(f"{path}: {_format_validation(exc)}") from exc


def _node(raw: Any, loc: SpecLocation) -> Node:
    if not isinstance(raw, dict):
        raise SpecError(f"{loc}: each graph node must be a mapping, got {raw!r}")
    return Node(
        name=raw.get("name", ""),
        agent=raw.get("agent"),
        function=raw.get("function"),
        description=raw.get("description"),
        location=loc,
    )


def _edge(raw: Any, loc: SpecLocation) -> Edge:
    if not isinstance(raw, dict):
        raise SpecError(f"{loc}: each graph edge must be a mapping, got {raw!r}")
    if "from" not in raw or "to" not in raw:
        raise SpecError(f"{loc}: an edge needs both 'from' and 'to', got {raw!r}")
    return Edge(source=str(raw["from"]), target=str(raw["to"]), location=loc)


def _branch(raw: Any, loc: SpecLocation) -> Branch:
    if not isinstance(raw, dict):
        raise SpecError(f"{loc}: each graph branch must be a mapping, got {raw!r}")
    missing = {"from", "condition", "description", "targets"} - set(raw)
    if missing:
        raise SpecError(f"{loc}: branch is missing {sorted(missing)}")
    targets = raw["targets"]
    if not isinstance(targets, dict):
        raise SpecError(f"{loc}: branch 'targets' must be a mapping of label -> node")
    try:
        return Branch(
            source=str(raw["from"]),
            condition=str(raw["condition"]),
            description=str(raw["description"]),
            targets={str(k): str(v) for k, v in targets.items()},
            location=loc,
        )
    except ValidationError as exc:
        raise SpecError(f"{loc}: {_format_validation(exc)}") from exc


def _state(raw: Any, loc: SpecLocation) -> StateSchema:
    if not raw:
        return StateSchema(location=loc)
    if not isinstance(raw, dict):
        raise SpecError(f"{loc}: 'state' must be a mapping")
    fields: list[StateField] = []
    for item in raw.get("fields", []):
        if not isinstance(item, dict):
            raise SpecError(f"{loc}: each state field must be a mapping, got {item!r}")
        try:
            fields.append(
                StateField(
                    name=item.get("name", ""),
                    type=item.get("type", "str"),
                    reducer=item.get("reducer", "replace"),
                    description=item.get("description"),
                    default=item.get("default"),
                    location=loc,
                )
            )
        except ValidationError as exc:
            raise SpecError(f"{loc}: {_format_validation(exc)}") from exc
    try:
        return StateSchema(name=raw.get("name", "WorkflowState"), fields=fields, location=loc)
    except ValidationError as exc:
        raise SpecError(f"{loc}: {_format_validation(exc)}") from exc


def _model(raw: Any, loc: SpecLocation) -> ModelConfig:
    if not raw:
        return ModelConfig(location=loc)
    if isinstance(raw, str):
        return ModelConfig(name=raw, location=loc)
    if not isinstance(raw, dict):
        raise SpecError(f"{loc}: 'model' must be a string or a mapping")
    try:
        return ModelConfig(
            name=raw.get("name", "claude-opus-5"),
            max_tokens=raw.get("max_tokens"),
            effort=raw.get("effort"),
            temperature=raw.get("temperature"),
            location=loc,
        )
    except ValidationError as exc:
        raise SpecError(f"{loc}: {_format_validation(exc)}") from exc


# --------------------------------------------------------------------------
# tools/tools.yaml
# --------------------------------------------------------------------------


def _parse_tools(path: Path, bag: DiagnosticBag) -> dict[str, Tool]:
    if not path.is_file():
        return {}
    raw = _load_yaml(path)
    loc = SpecLocation(file=path)
    out: dict[str, Tool] = {}
    for item in raw.get("tools", []):
        if not isinstance(item, dict):
            raise SpecError(f"{path}: each tool must be a mapping, got {item!r}")
        try:
            tool = Tool(
                name=item.get("name", ""),
                description=item.get("description", ""),
                parameters=item.get("parameters") or {},
                implementation=item.get("implementation"),
                builtin=item.get("builtin"),
                location=loc,
            )
        except ValidationError as exc:
            raise SpecError(f"{path}: {_format_validation(exc)}") from exc
        if tool.name in out:
            bag.warn("BRIDGE020", f"duplicate tool {tool.name!r}; the later one wins", location=loc)
        out[tool.name] = tool
    return out


# --------------------------------------------------------------------------
# skills/<name>/SKILL.md
# --------------------------------------------------------------------------


def _parse_skills(root: Path, bag: DiagnosticBag) -> dict[str, Skill]:
    if not root.is_dir():
        return {}
    out: dict[str, Skill] = {}
    for skill_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        path = skill_dir / SKILL_FILE
        if not path.is_file():
            bag.warn(
                "BRIDGE021",
                f"skill directory {skill_dir.name!r} has no {SKILL_FILE}; ignoring it",
                location=SpecLocation(file=skill_dir),
            )
            continue
        loc = SpecLocation(file=path)
        try:
            front, body, _ = parse_frontmatter(path.read_text(encoding="utf-8"))
        except FrontmatterError as exc:
            raise SpecError(f"{path}: {exc}") from exc

        _report_unknown_keys(front, _SKILL_KEYS, loc, bag, "skill")
        resources = [p.name for p in sorted(skill_dir.iterdir()) if p.name != SKILL_FILE]
        allowed = front.get("allowed-tools") or front.get("allowed_tools") or []
        try:
            skill = Skill(
                name=front.get("name") or skill_dir.name,
                description=front.get("description", ""),
                body=body,
                resources=list(front.get("resources") or resources),
                allowed_tools=list(allowed),
                location=loc,
            )
        except ValidationError as exc:
            raise SpecError(f"{path}: {_format_validation(exc)}") from exc
        out[skill.name] = skill
    return out


# --------------------------------------------------------------------------
# agents/<name>.md
# --------------------------------------------------------------------------


def _parse_agents(root: Path, bag: DiagnosticBag) -> dict[str, Agent]:
    if not root.is_dir():
        return {}
    out: dict[str, Agent] = {}
    for path in sorted(root.glob("*.md")):
        loc = SpecLocation(file=path)
        try:
            front, body, _ = parse_frontmatter(path.read_text(encoding="utf-8"))
        except FrontmatterError as exc:
            raise SpecError(f"{path}: {exc}") from exc

        _report_unknown_keys(front, _AGENT_KEYS, loc, bag, "agent")
        model_raw = front.get("model")
        try:
            agent = Agent(
                name=front.get("name") or path.stem,
                description=front.get("description", ""),
                prompt=body,
                model=_model(model_raw, loc) if model_raw else None,
                tools=list(front.get("tools") or []),
                skills=list(front.get("skills") or []),
                location=loc,
            )
        except ValidationError as exc:
            raise SpecError(f"{path}: {_format_validation(exc)}") from exc
        out[agent.name] = agent
    return out


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------


def _report_unknown_keys(
    raw: dict[str, Any],
    known: set[str],
    loc: SpecLocation,
    bag: DiagnosticBag,
    what: str,
) -> None:
    for key in sorted(set(raw) - known):
        bag.warn(
            "BRIDGE301",
            f"unknown {what} key {key!r}; it will not reach any engine",
            location=loc,
            hint=f"known keys: {sorted(known)}",
        )


def _format_validation(exc: ValidationError) -> str:
    parts = []
    for err in exc.errors():
        where = ".".join(str(p) for p in err["loc"]) or "<root>"
        parts.append(f"{where}: {err['msg']}")
    return "; ".join(parts)
