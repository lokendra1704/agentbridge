"""Parsing and validating specs."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from agentbridge.diagnostics import SpecError
from agentbridge.ir.models import FieldType, Reducer, WorkflowMode
from agentbridge.spec import parse_spec
from agentbridge.spec.frontmatter import FrontmatterError, render
from agentbridge.spec.frontmatter import parse as parse_frontmatter


def test_parses_the_example(example_spec: Path) -> None:
    bundle, bag = parse_spec(example_spec)

    assert bundle.workflow.name == "research-assistant"
    assert bundle.workflow.mode is WorkflowMode.GRAPH
    assert bundle.workflow.entry == "plan"
    assert sorted(bundle.agents) == ["planner", "researcher", "writer"]
    assert sorted(bundle.skills) == ["citation-format"]
    assert sorted(bundle.tools) == ["read-file", "web-search", "write-file"]
    assert not bag.has_errors, [d.format() for d in bag]


def test_example_is_lint_clean(example_spec: Path) -> None:
    """The shipped example should produce no warnings at parse time.

    Emit-time warnings about lossy translation are expected and separate; a
    warning *here* would mean the example itself is malformed.
    """
    _, bag = parse_spec(example_spec)
    assert [d.format() for d in bag] == []


def test_state_field_reducers(example_spec: Path) -> None:
    bundle, _ = parse_spec(example_spec)
    state = bundle.workflow.state
    assert state.name == "ResearchState"
    assert state.transcript_field is not None
    assert state.transcript_field.name == "messages"

    findings = state.field("findings")
    assert findings is not None
    assert findings.type is FieldType.LIST
    assert findings.reducer is Reducer.APPEND


def test_function_node_is_parsed(example_spec: Path) -> None:
    bundle, _ = parse_spec(example_spec)
    tally = bundle.workflow.node("tally")
    assert tally is not None
    assert tally.agent is None
    assert tally.function == "research_assistant_impl.routing:record_round"


def test_absent_graph_means_autonomous(minimal_spec: Path) -> None:
    bundle, bag = parse_spec(minimal_spec)
    assert bundle.workflow.mode is WorkflowMode.AUTONOMOUS
    assert not bag.has_errors


def test_missing_workflow_file_raises(tmp_path: Path) -> None:
    (tmp_path / "empty").mkdir()
    with pytest.raises(SpecError, match=re.escape("missing workflow.yaml")):
        parse_spec(tmp_path / "empty")


def test_unknown_agent_reference_is_an_error(spec_factory) -> None:
    root = spec_factory(
        """
name: broken
description: References a node with no agent behind it.
mode: graph
graph:
  entry: only
  nodes:
    - name: only
      agent: nonexistent
  edges:
    - from: only
      to: END
""",
    )
    _, bag = parse_spec(root)
    assert "BRIDGE001" in bag.codes()
    assert bag.has_errors


def test_unknown_tool_reference_is_an_error(spec_factory) -> None:
    root = spec_factory(
        "name: t\ndescription: d\n",
        agents={
            "a": "---\nname: a\ndescription: d\ntools: [ghost]\n---\n\nbody\n",
        },
    )
    _, bag = parse_spec(root)
    assert "BRIDGE002" in bag.codes()


def test_unreachable_node_warns(spec_factory) -> None:
    root = spec_factory(
        """
name: island
description: Has a node nothing points at.
mode: graph
graph:
  entry: start
  nodes:
    - name: start
      agent: a
    - name: orphan
      agent: a
  edges:
    - from: start
      to: END
""",
        agents={"a": "---\nname: a\ndescription: d\n---\n\nbody\n"},
    )
    _, bag = parse_spec(root)
    assert "BRIDGE004" in bag.codes()


def test_unreferenced_capability_warns(spec_factory) -> None:
    """The one case where the two engines genuinely differ, caught at spec time."""
    root = spec_factory(
        "name: t\ndescription: d\n",
        agents={"a": "---\nname: a\ndescription: d\n---\n\nbody\n"},
        skills={"floating": "---\nname: floating\ndescription: Never attached.\n---\n\nb\n"},
    )
    _, bag = parse_spec(root)
    assert "BRIDGE023" in bag.codes()


def test_temperature_on_a_model_that_rejects_it_warns(spec_factory) -> None:
    root = spec_factory(
        "name: t\ndescription: d\nmodel:\n  name: claude-opus-5\n  temperature: 0.7\n",
        agents={"a": "---\nname: a\ndescription: d\n---\n\nbody\n"},
    )
    _, bag = parse_spec(root)
    warning = next(d for d in bag if d.code == "BRIDGE400")
    assert "reject" in warning.message


def test_unknown_frontmatter_key_is_reported_not_dropped(spec_factory) -> None:
    root = spec_factory(
        "name: t\ndescription: d\n",
        agents={"a": "---\nname: a\ndescription: d\ncolour: blue\n---\n\nbody\n"},
    )
    _, bag = parse_spec(root)
    assert "BRIDGE301" in bag.codes()


def test_reducer_must_fit_field_type(spec_factory) -> None:
    root = spec_factory(
        """
name: t
description: d
state:
  fields:
    - name: count
      type: int
      reducer: append
""",
        agents={"a": "---\nname: a\ndescription: d\n---\n\nbody\n"},
    )
    with pytest.raises(SpecError, match="append"):
        parse_spec(root)


class TestFrontmatter:
    def test_round_trips(self) -> None:
        text = render({"name": "x", "description": "y"}, "body text")
        front, body, _ = parse_frontmatter(text)
        assert front == {"name": "x", "description": "y"}
        assert body == "body text"

    def test_no_frontmatter_is_all_body(self) -> None:
        front, body, line = parse_frontmatter("just prose")
        assert front == {}
        assert body == "just prose"
        assert line == 1

    def test_unterminated_frontmatter_raises(self) -> None:
        with pytest.raises(FrontmatterError, match="never closed"):
            parse_frontmatter("---\nname: x\n\nbody")
