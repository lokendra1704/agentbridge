"""Claude Code: emitting a plugin, and importing one back."""

from __future__ import annotations

from pathlib import Path

from agentbridge.backends import registry
from agentbridge.backends.claude_code import import_plugin
from agentbridge.diagnostics import DiagnosticBag
from agentbridge.ir.models import WorkflowMode
from agentbridge.spec import parse_spec, write_spec
from agentbridge.spec.frontmatter import parse as parse_frontmatter


def _emit(spec: Path) -> tuple[dict[str, str], DiagnosticBag]:
    bundle, bag = parse_spec(spec)
    files = registry.get("claude-code").emit(bundle, bag)
    return {str(f.path): f.content for f in files}, bag


class TestEmit:
    def test_emits_plugin_layout(self, example_spec: Path) -> None:
        files, _ = _emit(example_spec)
        assert ".claude-plugin/plugin.json" in files
        assert ".claude/agents/planner.md" in files
        assert ".claude/skills/citation-format/SKILL.md" in files
        assert ".claude/commands/research-assistant.md" in files

    def test_agent_frontmatter_uses_engine_tool_names(self, example_spec: Path) -> None:
        files, _ = _emit(example_spec)
        front, body, _ = parse_frontmatter(files[".claude/agents/researcher.md"])
        assert front["name"] == "researcher"
        # `read-file` is declared with `builtin: Read`, so the plugin must name
        # the engine's tool, not the spec's alias.
        assert "Read" in front["tools"]
        assert "A finding without a traceable source" in body

    def test_skills_are_advertised_to_agents_that_use_them(self, example_spec: Path) -> None:
        files, _ = _emit(example_spec)
        _, body, _ = parse_frontmatter(files[".claude/agents/researcher.md"])
        assert "citation-format" in body

    def test_graph_is_lowered_to_prose_with_a_warning(self, example_spec: Path) -> None:
        files, bag = _emit(example_spec)
        command = files[".claude/commands/research-assistant.md"]
        assert "## Steps" in command
        assert "starting at **plan**" in command
        assert "BRIDGE100" in bag.codes()

    def test_branch_condition_survives_only_as_prose(self, example_spec: Path) -> None:
        """The Python callable cannot run here; its description is the routing."""
        files, bag = _emit(example_spec)
        command = files[".claude/commands/research-assistant.md"]
        assert "fewer than three distinct sources" in command
        assert "`more` -> **research**" in command
        assert "BRIDGE101" in bag.codes()

    def test_typed_state_is_flagged_as_unenforced(self, example_spec: Path) -> None:
        files, bag = _emit(example_spec)
        command = files[".claude/commands/research-assistant.md"]
        assert "Information to carry through" in command
        assert "`findings` (list)" in command
        # The transcript field is native here, so it should not be listed.
        assert "`messages` (messages)" not in command
        assert "BRIDGE102" in bag.codes()

    def test_python_tool_is_reported_as_unwired(self, example_spec: Path) -> None:
        _, bag = _emit(example_spec)
        warning = next(d for d in bag if d.code == "BRIDGE103")
        assert "web-search" in warning.message

    def test_autonomous_spec_gets_a_delegation_brief(self, minimal_spec: Path) -> None:
        files, bag = _emit(minimal_spec)
        command = files[".claude/commands/minimal.md"]
        assert "No fixed sequence is defined" in command
        assert "BRIDGE100" not in bag.codes()


class TestImport:
    def _plugin(self, example_spec: Path, tmp_path: Path) -> Path:
        bundle, bag = parse_spec(example_spec)
        out = tmp_path / "plugin"
        for f in registry.get("claude-code").emit(bundle, bag):
            f.write_to(out)
        return out

    def test_agents_and_skills_survive_the_round_trip(
        self, example_spec: Path, tmp_path: Path
    ) -> None:
        plugin = self._plugin(example_spec, tmp_path)
        imported, _ = import_plugin(plugin)
        original, _ = parse_spec(example_spec)

        assert set(imported.agents) == set(original.agents)
        assert set(imported.skills) == set(original.skills)
        for name, agent in original.agents.items():
            assert agent.prompt.strip() in imported.agents[name].prompt

    def test_agent_capabilities_survive(self, example_spec: Path, tmp_path: Path) -> None:
        """Tools and skills must come back attached to the right agent.

        The plugin format has no frontmatter field for skills, so a naive
        emitter loses the association and the reimported spec trips the
        unreferenced-capability lint. Machine-readable trailers close that gap.
        """
        plugin = self._plugin(example_spec, tmp_path)
        imported, bag = import_plugin(plugin)
        original, _ = parse_spec(example_spec)

        for name, agent in original.agents.items():
            assert sorted(imported.agents[name].skills) == sorted(agent.skills)
            assert sorted(imported.agents[name].tools) == sorted(agent.tools)
        assert "BRIDGE023" not in bag.codes()

    def test_control_flow_is_lost_and_the_importer_says_so(
        self, example_spec: Path, tmp_path: Path
    ) -> None:
        """The known-lossy direction, surfaced rather than discovered later."""
        plugin = self._plugin(example_spec, tmp_path)
        imported, bag = import_plugin(plugin)
        assert imported.workflow.mode is WorkflowMode.AUTONOMOUS
        assert imported.workflow.nodes == []
        warning = next(d for d in bag if d.code == "BRIDGE300")
        assert "autonomous mode" in warning.message
        assert warning.hint is not None and "BRIDGE200" in warning.hint

    def test_imported_bundle_writes_a_parseable_spec(
        self, example_spec: Path, tmp_path: Path
    ) -> None:
        plugin = self._plugin(example_spec, tmp_path)
        imported, _ = import_plugin(plugin)
        spec_out = tmp_path / "spec"
        for f in write_spec(imported):
            f.write_to(spec_out)

        reparsed, bag = parse_spec(spec_out)
        assert not bag.has_errors, [d.format() for d in bag]
        assert set(reparsed.agents) == set(imported.agents)

    def test_import_of_a_handwritten_plugin(self, tmp_path: Path) -> None:
        """The real use case: a plugin nobody generated."""
        agents = tmp_path / ".claude" / "agents"
        agents.mkdir(parents=True)
        (agents / "triage.md").write_text(
            "---\nname: triage\ndescription: Sorts incoming issues.\n"
            "tools: Read, Grep\nmodel: inherit\n---\n\nYou sort issues by severity.\n",
            encoding="utf-8",
        )
        bundle, bag = import_plugin(tmp_path)

        agent = bundle.agents["triage"]
        assert agent.description == "Sorts incoming issues."
        # Comma-separated tools are a real Claude Code idiom.
        assert sorted(agent.tools) == ["grep", "read"]
        # "inherit" is not a model id any other engine can use.
        assert agent.model is None
        assert not bag.has_errors


def _without_locations(value: object) -> object:
    """Strip spec locations recursively — they name paths, which move."""
    if isinstance(value, dict):
        return {k: _without_locations(v) for k, v in value.items() if k != "location"}
    if isinstance(value, list):
        return [_without_locations(v) for v in value]
    return value


def test_spec_writer_round_trips_losslessly(example_spec: Path, tmp_path: Path) -> None:
    """spec -> IR -> spec -> IR must be a fixed point.

    This is the tighter of the two round trips: unlike the Claude Code one, it
    goes through no engine, so anything lost here is a bug in the spec format
    rather than an engine limitation.
    """
    original, _ = parse_spec(example_spec)
    out = tmp_path / "rewritten"
    for f in write_spec(original):
        f.write_to(out)
    reparsed, bag = parse_spec(out)

    assert not bag.has_errors, [d.format() for d in bag]
    assert _without_locations(reparsed.workflow.model_dump()) == _without_locations(
        original.workflow.model_dump()
    )
    for name, agent in original.agents.items():
        assert _without_locations(reparsed.agents[name].model_dump()) == _without_locations(
            agent.model_dump()
        )
    for name, skill in original.skills.items():
        assert reparsed.skills[name].body.strip() == skill.body.strip()
    for name, tool in original.tools.items():
        assert _without_locations(reparsed.tools[name].model_dump()) == _without_locations(
            tool.model_dump()
        )
