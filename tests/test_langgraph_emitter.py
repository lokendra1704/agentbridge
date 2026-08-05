"""LangGraph emitter: structure of the generated program, and that it runs."""

from __future__ import annotations

from pathlib import Path

import pytest

from agentbridge.backends import registry
from agentbridge.backends.base import EmittedFile
from agentbridge.diagnostics import DiagnosticBag
from agentbridge.spec import parse_spec


def _emit(spec: Path) -> tuple[dict[str, str], DiagnosticBag]:
    bundle, bag = parse_spec(spec)
    files = registry.get("langgraph").emit(bundle, bag)
    return {str(f.path): f.content for f in files}, bag


def test_emits_the_expected_modules(example_spec: Path) -> None:
    files, _ = _emit(example_spec)
    for expected in (
        "workflow/__init__.py",
        "workflow/state.py",
        "workflow/tools.py",
        "workflow/skills.py",
        "workflow/agents.py",
        "workflow/graph.py",
        "requirements.txt",
    ):
        assert expected in files


def test_state_carries_reducers(example_spec: Path) -> None:
    files, _ = _emit(example_spec)
    state = files["workflow/state.py"]
    assert "class ResearchState(TypedDict, total=False):" in state
    assert "messages: Annotated[list[AnyMessage], add_messages]" in state
    assert "findings: Annotated[list[Any], operator.add]" in state
    assert "rounds: int" in state


def test_skill_becomes_a_load_on_demand_tool(example_spec: Path) -> None:
    """The canonical skill lowering: a tool returning the skill body."""
    files, bag = _emit(example_spec)
    skills = files["workflow/skills.py"]
    assert "CITATION_FORMAT_BODY" in skills
    assert 'name="skill_citation_format"' in skills
    assert "Call this to load the full instructions" in skills
    # The body itself has to survive; a tool returning a summary is not the skill.
    assert "Number entries once and never renumber" in skills
    assert "BRIDGE202" in bag.codes()


def test_python_tool_is_imported_directly(example_spec: Path) -> None:
    files, _ = _emit(example_spec)
    tools = files["workflow/tools.py"]
    assert "from research_assistant_impl.tools import web_search as _impl_web_search" in tools


def test_builtin_tool_uses_the_runtime_shim(example_spec: Path) -> None:
    files, bag = _emit(example_spec)
    tools = files["workflow/tools.py"]
    assert "from agentbridge.runtime.builtins import read_file as _impl_read_file" in tools
    assert "BRIDGE201" in bag.codes()


def test_unknown_builtin_becomes_a_loud_stub(spec_factory) -> None:
    """A builtin with no equivalent must fail at call time, not silently no-op."""
    root = spec_factory(
        "name: t\ndescription: d\n",
        agents={"a": "---\nname: a\ndescription: d\ntools: [notebook]\n---\n\nbody\n"},
        tools=(
            "tools:\n  - name: notebook\n"
            "    description: Edit a notebook.\n    builtin: NotebookEdit\n"
        ),
    )
    files, bag = _emit(root)
    assert "raise NotImplementedError" in files["workflow/tools.py"]
    warning = next(d for d in bag if d.code == "BRIDGE201")
    assert "NotebookEdit" in warning.message


def test_graph_wires_edges_and_branches(example_spec: Path) -> None:
    files, _ = _emit(example_spec)
    graph = files["workflow/graph.py"]
    assert 'builder.set_entry_point("plan")' in graph
    assert 'builder.add_edge("plan", "research")' in graph
    assert 'builder.add_edge("write", END)' in graph
    assert "builder.add_conditional_edges(" in graph
    assert '"more": "research"' in graph
    assert '"done": "write"' in graph
    assert (
        "from research_assistant_impl.routing import needs_more_research as _route_tally" in graph
    )


def test_function_node_is_imported_not_wrapped_in_an_agent(example_spec: Path) -> None:
    files, _ = _emit(example_spec)
    graph = files["workflow/graph.py"]
    assert "from research_assistant_impl.routing import record_round as _fn_tally" in graph
    assert 'builder.add_node("tally", _fn_tally)' in graph


def test_per_agent_model_override_is_honoured(example_spec: Path) -> None:
    files, _ = _emit(example_spec)
    agents = files["workflow/agents.py"]
    # writer.md overrides max_tokens; the others inherit the workflow default.
    assert "max_tokens=32000" in agents
    assert "max_tokens=16000" in agents
    assert 'effort="high"' in agents


def test_autonomous_spec_collapses_to_one_node_and_says_so(minimal_spec: Path) -> None:
    files, bag = _emit(minimal_spec)
    graph = files["workflow/graph.py"]
    assert 'builder.add_node("helper"' in graph
    assert "declared no graph" in graph
    assert "BRIDGE200" in bag.codes()
    assert "Add a `graph:` section" in files["README.md"]


class TestGeneratedProgramRuns:
    """Build and invoke the emitted graph for real. This is the claim that matters."""

    @pytest.fixture(autouse=True)
    def _requires_langgraph(self) -> None:
        pytest.importorskip("langgraph")

    def _build(self, spec: Path, tmp_path: Path, model_factory) -> object:
        import sys

        bundle, bag = parse_spec(spec)
        files: list[EmittedFile] = registry.get("langgraph").emit(bundle, bag)
        out = tmp_path / "generated"
        out.mkdir(parents=True, exist_ok=True)
        for f in files:
            f.write_to(out)

        sys.path.insert(0, str(out))
        try:
            for stale in [m for m in sys.modules if m == "workflow" or m.startswith("workflow.")]:
                del sys.modules[stale]
            from workflow import build_graph  # type: ignore[import-not-found]

            return build_graph(model_factory=model_factory)
        finally:
            sys.path.remove(str(out))

    def test_graph_compiles_with_the_declared_nodes(
        self, example_spec: Path, tmp_path: Path, fake_model_factory
    ) -> None:
        graph = self._build(example_spec, tmp_path, fake_model_factory)
        nodes = set(graph.get_graph().nodes)  # type: ignore[attr-defined]
        assert {"plan", "research", "tally", "write"} <= nodes

    def test_direct_path_runs_each_stage_once(
        self, example_spec: Path, tmp_path: Path, fake_model_factory
    ) -> None:
        graph = self._build(example_spec, tmp_path, fake_model_factory)
        result = graph.invoke(  # type: ignore[attr-defined]
            {
                "messages": [("user", "why did the Bronze Age collapse?")],
                "topic": "bronze age",
                "findings": ["a", "b", "c"],
                "rounds": 0,
            }
        )
        # Enough sources on the first pass, so the branch goes straight to write.
        assert result["rounds"] == 1

    def test_branch_loops_and_terminates(
        self, example_spec: Path, tmp_path: Path, fake_model_factory
    ) -> None:
        """The declared loop must actually loop, and actually stop."""
        graph = self._build(example_spec, tmp_path, fake_model_factory)
        result = graph.invoke(  # type: ignore[attr-defined]
            {"messages": [("user", "q")], "topic": "t", "findings": [], "rounds": 0}
        )
        # No findings ever arrive, so the round cap is what ends it.
        assert result["rounds"] == 3
