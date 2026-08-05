"""The mapping table is a contract with the backends, so check they agree."""

from __future__ import annotations

import pytest

from agentbridge.backends import registry
from agentbridge.mapping import MAPPINGS, Fidelity, for_engine, lookup, lossy_rows, render_table


def test_every_engine_in_the_table_is_a_registered_backend() -> None:
    engines = {m.engine for m in MAPPINGS}
    assert engines <= set(registry.names()), (
        "the mapping table names an engine with no backend behind it"
    )


@pytest.mark.parametrize("engine", sorted({m.engine for m in MAPPINGS}))
def test_every_engine_has_a_row_per_concept(engine: str) -> None:
    concepts = {m.concept for m in MAPPINGS}
    covered = {m.concept for m in for_engine(engine)}
    assert covered == concepts, f"{engine} has no row for: {sorted(concepts - covered)}"


def test_lossy_rows_carry_a_diagnostic_code() -> None:
    """A lossy translation with no diagnostic would be a silent drop."""
    for row in MAPPINGS:
        if row.fidelity is Fidelity.LOSSY:
            assert row.diagnostic, f"{row.concept} on {row.engine} is lossy but has no code"


def test_every_row_explains_itself() -> None:
    for row in MAPPINGS:
        assert len(row.rationale) > 40, f"{row.concept}/{row.engine} needs a real rationale"


def test_skill_lowering_is_documented_as_canonical() -> None:
    row = lookup("skill", "langgraph")
    assert row is not None
    assert "CANONICAL" in row.rationale
    assert "Rejected alternatives" in row.rationale


def test_the_two_known_lossy_directions_are_recorded() -> None:
    """CLAUDE.md names these as the spots the design must confront."""
    codes = {row.diagnostic for row in (*lossy_rows("claude-code"), *lossy_rows("langgraph"))}
    assert "BRIDGE100" in codes  # explicit control flow cannot be enforced
    assert "BRIDGE200" in codes  # implicit control flow yields no graph


def test_table_renders(capsys: pytest.CaptureFixture[str]) -> None:
    table = render_table()
    assert "| Concept |" in table
    assert "claude-code" in table and "langgraph" in table
