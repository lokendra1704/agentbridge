"""Shared fixtures.

`examples/` is on the path because the example spec points at real Python
(`research_assistant_impl.tools:web_search`), and generated LangGraph code
imports it for real.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = REPO_ROOT / "examples"
EXAMPLE_SPEC = EXAMPLES / "research-assistant"

if str(EXAMPLES) not in sys.path:
    sys.path.insert(0, str(EXAMPLES))


@pytest.fixture
def example_spec() -> Path:
    return EXAMPLE_SPEC


@pytest.fixture
def spec_factory(tmp_path: Path):
    """Build a minimal spec directory on disk from plain strings."""

    def build(
        workflow: str,
        agents: dict[str, str] | None = None,
        skills: dict[str, str] | None = None,
        tools: str | None = None,
        name: str = "spec",
    ) -> Path:
        root = tmp_path / name
        root.mkdir(parents=True, exist_ok=True)
        (root / "workflow.yaml").write_text(workflow, encoding="utf-8")
        for agent_name, body in (agents or {}).items():
            path = root / "agents" / f"{agent_name}.md"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(body, encoding="utf-8")
        for skill_name, body in (skills or {}).items():
            path = root / "skills" / skill_name / "SKILL.md"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(body, encoding="utf-8")
        if tools is not None:
            path = root / "tools" / "tools.yaml"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(tools, encoding="utf-8")
        return root

    return build


MINIMAL_WORKFLOW = """
name: minimal
description: A one-agent workflow with no declared structure.
"""

MINIMAL_AGENT = """---
name: helper
description: Answers questions.
---

You answer questions concisely.
"""


@pytest.fixture
def minimal_spec(spec_factory) -> Path:
    return spec_factory(MINIMAL_WORKFLOW, agents={"helper": MINIMAL_AGENT})


@pytest.fixture
def fake_model_factory() -> Any:
    """A chat model that accepts bind_tools, which react agents require.

    Lets the conformance suite build and run the real graph without an API
    key — the injectable `model_factory` on the generated `build_graph` exists
    for exactly this.
    """
    pytest.importorskip("langchain_core")
    from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
    from langchain_core.messages import AIMessage

    class ToolBindingFake(GenericFakeChatModel):  # type: ignore[misc]
        def bind_tools(self, tools: Any, **kwargs: Any) -> Any:
            return self

    def factory(name: str, **kwargs: Any) -> Any:
        return ToolBindingFake(messages=iter([AIMessage(content=f"[{name}] ok")] * 200))

    return factory
