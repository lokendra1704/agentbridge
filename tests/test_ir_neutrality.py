"""The IR must not know about any engine.

This is the project's central constraint made testable. If it fails, an engine
assumption has leaked into the contract, and adding the third engine will mean
editing the IR instead of adding a module.
"""

from __future__ import annotations

import ast
import io
import tokenize
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parent.parent / "src" / "agentbridge"

#: Names that would mean an engine has leaked in. Deliberately does not
#: include "claude": model ids like claude-opus-5 are a *provider* concern,
#: which the IR is allowed to carry.
FORBIDDEN = ("langgraph", "langchain", "crewai", "claude_code", "claude-code", ".claude")

#: Layers that must stay engine-neutral, in dependency order.
NEUTRAL_MODULES = ("ir", "spec", "diagnostics.py")


def _neutral_files() -> list[Path]:
    files: list[Path] = []
    for entry in NEUTRAL_MODULES:
        target = SRC / entry
        files.extend(sorted(target.rglob("*.py")) if target.is_dir() else [target])
    return files


def _code_only(path: Path) -> str:
    """Source with comments and string literals removed.

    Prose may name engines — the modules explain the rule they follow, and
    that explanation is worth more than a grep-clean file. Leakage that
    matters shows up as an identifier, import, or attribute, so strip the
    text and check what is left.
    """
    kept: list[str] = []
    source = path.read_text(encoding="utf-8")
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type in (tokenize.COMMENT, tokenize.STRING):
            continue
        kept.append(token.string)
    return " ".join(kept).lower()


@pytest.mark.parametrize("path", _neutral_files(), ids=lambda p: p.name)
def test_neutral_layer_names_no_engine(path: Path) -> None:
    code = _code_only(path)
    hits = [token for token in FORBIDDEN if token in code]
    assert not hits, f"{path.relative_to(SRC)} mentions {hits}; the IR must stay engine-neutral"


def test_ir_imports_nothing_from_backends() -> None:
    """Dependencies run one way: backends import the IR, never the reverse."""
    for path in sorted((SRC / "ir").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            module = ""
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
            elif isinstance(node, ast.Import):
                module = ",".join(a.name for a in node.names)
            assert "backends" not in module and "deploy" not in module, (
                f"{path.name} imports {module!r}; the IR must not depend on a backend"
            )


def test_spec_layer_does_not_import_backends_except_for_file_type() -> None:
    """The spec writer may borrow EmittedFile, but nothing engine-specific."""
    for path in sorted((SRC / "spec").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and "backends" in (node.module or ""):
                assert node.module == "agentbridge.backends.base", (
                    f"{path.name} imports {node.module!r}; only the backend base "
                    "types are shareable with the spec layer"
                )
