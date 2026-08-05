"""Semantic validation of a parsed bundle.

Pydantic checks each object in isolation; this checks the relationships
between them — dangling references, unreachable nodes, dead ends. It is
engine-neutral: every check here would be a real problem on any runtime.
"""

from __future__ import annotations

from agentbridge.diagnostics import DiagnosticBag
from agentbridge.ir.models import END, Bundle, WorkflowMode

#: Model families that reject sampling parameters outright. Kept small and
#: prefix-matched on purpose — this is a lint, not a model registry.
_NO_SAMPLING_PARAMS = (
    "claude-opus-5",
    "claude-opus-4-8",
    "claude-opus-4-7",
    "claude-fable-5",
    "claude-mythos-5",
    "claude-sonnet-5",
)


def validate_bundle(bundle: Bundle, diagnostics: DiagnosticBag) -> None:
    """Append every cross-object problem found in `bundle` to `diagnostics`."""
    _check_agent_references(bundle, diagnostics)
    _check_unreferenced(bundle, diagnostics)
    _check_model_config(bundle, diagnostics)
    if bundle.workflow.mode is WorkflowMode.GRAPH:
        _check_graph(bundle, diagnostics)
    else:
        _check_autonomous(bundle, diagnostics)


def _check_agent_references(bundle: Bundle, diagnostics: DiagnosticBag) -> None:
    for agent in bundle.ordered_agents():
        for tool_name in agent.tools:
            if tool_name not in bundle.tools:
                diagnostics.error(
                    "BRIDGE002",
                    f"agent {agent.name!r} references unknown tool {tool_name!r}",
                    location=agent.location,
                    hint=f"declare it in tools/tools.yaml, or remove it from {agent.name}'s tools",
                )
        for skill_name in agent.skills:
            if skill_name not in bundle.skills:
                diagnostics.error(
                    "BRIDGE003",
                    f"agent {agent.name!r} references unknown skill {skill_name!r}",
                    location=agent.location,
                    hint=f"add skills/{skill_name}/SKILL.md",
                )


def _check_unreferenced(bundle: Bundle, diagnostics: DiagnosticBag) -> None:
    """Flag capabilities no agent can reach.

    This is more than tidiness. Engines disagree about what an unreferenced
    capability means — a Claude Code skill is model-triggered whether or not an
    agent names it, while a lowered skill-tool is reachable only if it is bound
    to an agent. So an unreferenced skill is the one thing that genuinely lands
    differently on each engine, and the honest fix is to make the spec say
    which agents can use it.
    """
    used_tools = {t for a in bundle.agents.values() for t in a.tools}
    used_skills = {s for a in bundle.agents.values() for s in a.skills}

    for tool in bundle.ordered_tools():
        if tool.name not in used_tools:
            diagnostics.warn(
                "BRIDGE022",
                f"tool {tool.name!r} is declared but no agent lists it",
                location=tool.location,
                hint="add it to an agent's 'tools:', or delete the declaration",
            )
    for skill in bundle.ordered_skills():
        if skill.name not in used_skills:
            diagnostics.warn(
                "BRIDGE023",
                f"skill {skill.name!r} is declared but no agent lists it; engines "
                "disagree about whether an unattached skill is reachable",
                location=skill.location,
                hint="add it to an agent's 'skills:', or delete it",
            )


def _check_model_config(bundle: Bundle, diagnostics: DiagnosticBag) -> None:
    configs = [(bundle.workflow.name, bundle.workflow.model)]
    configs += [(a.name, a.model) for a in bundle.ordered_agents() if a.model is not None]
    for owner, cfg in configs:
        if cfg.temperature is None:
            continue
        if any(cfg.name.startswith(p) for p in _NO_SAMPLING_PARAMS):
            diagnostics.warn(
                "BRIDGE400",
                f"{owner!r} sets temperature on model {cfg.name!r}, which rejects sampling "
                "parameters — the request will fail with a 400",
                location=cfg.location,
                hint="drop 'temperature' and steer with the prompt, or set 'effort' instead",
            )


def _check_graph(bundle: Bundle, diagnostics: DiagnosticBag) -> None:
    wf = bundle.workflow
    names = {n.name for n in wf.nodes}

    if not wf.nodes:
        diagnostics.error(
            "BRIDGE011",
            f"workflow {wf.name!r} declares mode 'graph' but has no nodes",
            location=wf.location,
            hint="add a graph.nodes list, or set mode to 'autonomous'",
        )
        return

    if wf.entry is None:
        diagnostics.error(
            "BRIDGE010",
            f"workflow {wf.name!r} declares mode 'graph' but has no entry node",
            location=wf.location,
        )
    elif wf.entry not in names:
        diagnostics.error(
            "BRIDGE010",
            f"entry node {wf.entry!r} is not one of the declared nodes",
            location=wf.location,
            hint=f"known nodes: {sorted(names)}",
        )

    for node in wf.nodes:
        if node.agent is not None and node.agent not in bundle.agents:
            diagnostics.error(
                "BRIDGE001",
                f"node {node.name!r} references unknown agent {node.agent!r}",
                location=node.location,
                hint=f"add agents/{node.agent}.md",
            )

    for edge in wf.edges:
        if edge.source not in names:
            diagnostics.error(
                "BRIDGE005",
                f"edge source {edge.source!r} is not a declared node",
                location=edge.location,
            )
        if edge.target not in names and edge.target != END:
            diagnostics.error(
                "BRIDGE005",
                f"edge target {edge.target!r} is neither a declared node nor {END}",
                location=edge.location,
            )

    for branch in wf.branches:
        if branch.source not in names:
            diagnostics.error(
                "BRIDGE005",
                f"branch source {branch.source!r} is not a declared node",
                location=branch.location,
            )
        for label, target in sorted(branch.targets.items()):
            if target not in names and target != END:
                diagnostics.error(
                    "BRIDGE005",
                    f"branch {branch.source!r} target {label!r} -> {target!r} "
                    f"is neither a declared node nor {END}",
                    location=branch.location,
                )

    _check_reachability(bundle, diagnostics, names)


def _check_reachability(bundle: Bundle, diagnostics: DiagnosticBag, names: set[str]) -> None:
    wf = bundle.workflow
    if wf.entry is None or wf.entry not in names:
        return

    seen: set[str] = set()
    stack = [wf.entry]
    while stack:
        current = stack.pop()
        if current in seen or current == END:
            continue
        seen.add(current)
        stack.extend(wf.successors(current))

    for node in wf.nodes:
        if node.name not in seen:
            diagnostics.warn(
                "BRIDGE004",
                f"node {node.name!r} is unreachable from entry {wf.entry!r}",
                location=node.location,
                hint="add an edge to it, or delete it",
            )
        elif not wf.successors(node.name):
            diagnostics.warn(
                "BRIDGE006",
                f"node {node.name!r} has no outgoing edge, so the workflow stops there "
                "without reaching END",
                location=node.location,
                hint=f"add an edge from {node.name} to {END} to make termination explicit",
            )


def _check_autonomous(bundle: Bundle, diagnostics: DiagnosticBag) -> None:
    wf = bundle.workflow
    if wf.nodes or wf.edges or wf.branches:
        diagnostics.warn(
            "BRIDGE012",
            f"workflow {wf.name!r} is in autonomous mode, so its declared graph "
            "structure is ignored",
            location=wf.location,
            hint="set mode: graph to use the nodes and edges you declared",
        )
    if not bundle.agents:
        diagnostics.error(
            "BRIDGE013",
            f"workflow {wf.name!r} has no agents",
            location=wf.location,
        )
