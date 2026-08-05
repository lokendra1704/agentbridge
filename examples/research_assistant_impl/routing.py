"""Branch conditions the spec points at by dotted path.

A condition takes the workflow state and returns one of the labels declared in
`targets:`. On LangGraph this runs. On Claude Code it cannot — only the
branch's prose `description` survives (BRIDGE101), which is why that field is
required in the spec rather than optional.
"""

from __future__ import annotations

from typing import Any

MIN_SOURCES = 3
MAX_ROUNDS = 3


def record_round(state: dict[str, Any]) -> dict[str, Any]:
    """Count the research pass that just finished.

    A plain node, not an agent. The counter that bounds the research loop has
    to be incremented by something that always runs — leaving it to the model
    means the bound is advisory, and an advisory bound is not a bound.
    """
    return {"rounds": (state.get("rounds") or 0) + 1}


def needs_more_research(state: dict[str, Any]) -> str:
    """Decide whether to research again or hand off to the writer.

    Keep this in step with the branch's `description:` in workflow.yaml — on
    the Claude Code side that prose *is* the routing logic.
    """
    findings = state.get("findings") or []
    rounds = state.get("rounds") or 0
    if len(findings) < MIN_SOURCES and rounds < MAX_ROUNDS:
        return "more"
    return "done"
