"""Small implementations of engine builtins, for runtimes that ship none.

Claude Code provides file and shell tools; LangGraph does not. Without these,
a spec that reads a file would compile on both engines but only *run* on one,
which would make "same workflow, two runtimes" true only on paper.

These are deliberately simpler than the native tools — no diff view, no
permission prompts, no session state. The mapping table records that as a
`lowered` fidelity so the difference is on the record.

Imported only by generated LangGraph code; nothing in the compiler path
depends on this module.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

MAX_OUTPUT_CHARS = 30_000


def read_file(path: str, offset: int = 0, limit: int = 2000) -> str:
    """Read a text file. `offset` and `limit` are in lines, `offset` 0-indexed."""
    target = Path(path).expanduser()
    if not target.is_file():
        return f"Error: no such file: {path}"
    lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
    window = lines[offset : offset + limit]
    return "\n".join(f"{i:6d}\t{line}" for i, line in enumerate(window, start=offset + 1))


def write_file(path: str, content: str) -> str:
    """Write `content` to `path`, creating parent directories as needed."""
    target = Path(path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return f"Wrote {len(content)} characters to {path}"


def edit_file(path: str, old_string: str, new_string: str) -> str:
    """Replace the single occurrence of `old_string` in `path`."""
    target = Path(path).expanduser()
    if not target.is_file():
        return f"Error: no such file: {path}"
    text = target.read_text(encoding="utf-8")
    count = text.count(old_string)
    if count == 0:
        return f"Error: old_string not found in {path}"
    if count > 1:
        return f"Error: old_string appears {count} times in {path}; it must be unique"
    target.write_text(text.replace(old_string, new_string), encoding="utf-8")
    return f"Edited {path}"


def run_bash(command: str, timeout: int = 120) -> str:
    """Run a shell command and return its combined output.

    Runs with the caller's privileges and no sandbox. Treat any workflow that
    exposes this tool as running arbitrary model-authored commands, and gate it
    the way you would gate that.
    """
    try:
        proc = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return f"Error: command timed out after {timeout}s"
    out = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode != 0:
        out = f"(exit {proc.returncode})\n{out}"
    return _truncate(out) or "(no output)"


def glob_files(pattern: str, root: str = ".") -> str:
    """List paths matching a glob pattern, newest first."""
    base = Path(root).expanduser()
    matches = sorted(base.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    if not matches:
        return f"No files matching {pattern!r} under {root}"
    return _truncate("\n".join(str(p) for p in matches))


def grep_files(pattern: str, root: str = ".", glob: str = "**/*") -> str:
    """Search file contents for a regular expression."""
    import re

    try:
        regex = re.compile(pattern)
    except re.error as exc:
        return f"Error: invalid pattern: {exc}"

    base = Path(root).expanduser()
    hits: list[str] = []
    for path in sorted(base.glob(glob)):
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="strict")
        except (UnicodeDecodeError, OSError):
            continue
        for number, line in enumerate(text.splitlines(), start=1):
            if regex.search(line):
                hits.append(f"{path}:{number}:{line.strip()}")
    if not hits:
        return f"No matches for {pattern!r}"
    return _truncate("\n".join(hits))


def _truncate(text: str) -> str:
    if len(text) <= MAX_OUTPUT_CHARS:
        return text
    return text[:MAX_OUTPUT_CHARS] + f"\n... (truncated at {MAX_OUTPUT_CHARS} characters)"


__all__ = [
    "edit_file",
    "glob_files",
    "grep_files",
    "read_file",
    "run_bash",
    "write_file",
]
