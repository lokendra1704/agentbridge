"""The builtin shims. They are what make a spec using file tools actually run."""

from __future__ import annotations

from pathlib import Path

from agentbridge.runtime.builtins import (
    edit_file,
    glob_files,
    grep_files,
    read_file,
    run_bash,
    write_file,
)


def test_write_then_read(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "note.txt"
    write_file(str(target), "alpha\nbeta\n")
    out = read_file(str(target))
    assert "alpha" in out and "beta" in out
    assert out.startswith("     1\t")


def test_read_missing_file_reports_rather_than_raises(tmp_path: Path) -> None:
    assert "no such file" in read_file(str(tmp_path / "absent.txt"))


def test_read_windows_lines(tmp_path: Path) -> None:
    target = tmp_path / "w.txt"
    write_file(str(target), "\n".join(f"line{i}" for i in range(10)))
    assert "line5" in read_file(str(target), offset=4, limit=2)
    assert "line9" not in read_file(str(target), offset=4, limit=2)


def test_edit_requires_a_unique_match(tmp_path: Path) -> None:
    target = tmp_path / "e.txt"
    write_file(str(target), "x\nx\n")
    assert "appears 2 times" in edit_file(str(target), "x", "y")
    assert "not found" in edit_file(str(target), "zzz", "y")

    write_file(str(target), "keep\nchange\n")
    edit_file(str(target), "change", "changed")
    assert "changed" in target.read_text()


def test_glob_and_grep(tmp_path: Path) -> None:
    write_file(str(tmp_path / "a.py"), "def hello():\n    pass\n")
    write_file(str(tmp_path / "b.txt"), "nothing here\n")

    listed = glob_files("*.py", root=str(tmp_path))
    assert "a.py" in listed and "b.txt" not in listed

    hits = grep_files(r"def \w+", root=str(tmp_path))
    assert "a.py" in hits
    assert "No matches" in grep_files("zzzz", root=str(tmp_path))
    assert "invalid pattern" in grep_files("[", root=str(tmp_path))


def test_bash_returns_output_and_exit_code() -> None:
    assert "hi" in run_bash("echo hi")
    assert "(exit 3)" in run_bash("exit 3")
