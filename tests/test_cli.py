"""CLI behaviour, including exit codes — these are the CI contract."""

from __future__ import annotations

from pathlib import Path

import pytest

from agentbridge.cli import EXIT_DIAGNOSTIC_ERROR, EXIT_OK, EXIT_USAGE, main


def test_engines_lists_backends_and_their_targets(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["engines"]) == EXIT_OK
    out = capsys.readouterr().out
    assert "claude-code" in out
    assert "langgraph" in out
    assert "deploy: langgraph-platform" in out


def test_mapping_prints_the_table(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["mapping"]) == EXIT_OK
    out = capsys.readouterr().out
    assert "skill" in out
    assert "lossy" in out


def test_validate_succeeds_on_the_example(
    example_spec: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["validate", str(example_spec)]) == EXIT_OK
    assert "research-assistant" in capsys.readouterr().out


def test_compile_writes_both_engines(example_spec: Path, tmp_path: Path) -> None:
    cc = ["compile", str(example_spec), "-e", "claude-code", "-o", str(tmp_path / "cc")]
    assert main(cc) == 0
    assert main(["compile", str(example_spec), "-e", "langgraph", "-o", str(tmp_path / "lg")]) == 0
    assert (tmp_path / "cc" / ".claude" / "agents" / "planner.md").is_file()
    assert (tmp_path / "lg" / "workflow" / "graph.py").is_file()


def test_compile_with_deploy_target_adds_platform_files(example_spec: Path, tmp_path: Path) -> None:
    code = main(
        [
            "compile",
            str(example_spec),
            "-e",
            "langgraph",
            "-o",
            str(tmp_path / "out"),
            "--deploy",
            "langgraph-platform",
        ]
    )
    assert code == EXIT_OK
    manifest = tmp_path / "out" / "langgraph.json"
    assert manifest.is_file()
    assert "build_graph" in manifest.read_text(encoding="utf-8")
    assert (tmp_path / "out" / ".env.example").is_file()
    assert (tmp_path / "out" / "DEPLOY.md").is_file()


def test_deploy_target_rejects_a_mismatched_engine(
    example_spec: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(
        [
            "compile",
            str(example_spec),
            "-e",
            "claude-code",
            "-o",
            str(tmp_path / "out"),
            "--deploy",
            "langgraph-platform",
        ]
    )
    assert code == EXIT_USAGE
    assert "ships 'langgraph' output" in capsys.readouterr().err


def test_dry_run_writes_nothing(example_spec: Path, tmp_path: Path) -> None:
    out = tmp_path / "nothing"
    assert main(["compile", str(example_spec), "-e", "langgraph", "-o", str(out), "--dry-run"]) == 0
    assert not out.exists()


def test_strict_turns_warnings_into_failure(example_spec: Path, tmp_path: Path) -> None:
    """Claude Code emission is warning-heavy by design, so --strict must fail it."""
    code = main(
        ["compile", str(example_spec), "-e", "claude-code", "-o", str(tmp_path / "out"), "--strict"]
    )
    assert code == EXIT_DIAGNOSTIC_ERROR
    assert not (tmp_path / "out").exists()


def test_spec_errors_block_writing(spec_factory, tmp_path: Path) -> None:
    root = spec_factory(
        "name: bad\ndescription: d\nmode: graph\n"
        "graph:\n  entry: ghost\n  nodes:\n    - name: real\n      agent: missing\n",
    )
    code = main(["compile", str(root), "-e", "langgraph", "-o", str(tmp_path / "out")])
    assert code == EXIT_DIAGNOSTIC_ERROR
    assert not (tmp_path / "out").exists()


def test_unknown_engine_is_a_usage_error(
    example_spec: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(["compile", str(example_spec), "-e", "nonexistent", "-o", str(tmp_path)])
    assert code == EXIT_USAGE
    assert "unknown engine" in capsys.readouterr().err


def test_import_writes_a_spec(example_spec: Path, tmp_path: Path) -> None:
    plugin = tmp_path / "plugin"
    assert main(["compile", str(example_spec), "-e", "claude-code", "-o", str(plugin)]) == 0
    assert main(["import", str(plugin), "-o", str(tmp_path / "spec")]) == EXIT_OK
    assert (tmp_path / "spec" / "workflow.yaml").is_file()
    assert (tmp_path / "spec" / "agents" / "planner.md").is_file()


def test_no_command_prints_help(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == EXIT_USAGE
    assert "usage" in capsys.readouterr().out.lower()
