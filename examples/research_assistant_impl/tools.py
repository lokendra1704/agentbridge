"""Tool implementations the spec points at by dotted path.

The bridge never generates these — they are ordinary Python that the author
owns. `tools/tools.yaml` names `research_assistant_impl.tools:web_search`, and
the LangGraph emitter turns that into a real import.
"""

from __future__ import annotations


def web_search(query: str, limit: int = 5) -> str:
    """Search the web and return titled, dated, linked results.

    Args:
        query: What to search for.
        limit: Maximum number of results to return.
    """
    # Stand-in so the example runs without a search provider configured.
    # Swap in a real client here; nothing else has to change.
    return (
        f"(no search provider configured — returning a placeholder for {query!r}, "
        f"limit {limit})"
    )
