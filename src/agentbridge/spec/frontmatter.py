"""Markdown-with-YAML-frontmatter, read and written.

Used for anything a human writes prose into: agent system prompts and skill
bodies. Chosen so the Claude Code emitter is nearly a file copy.
"""

from __future__ import annotations

from typing import Any

import yaml

_DELIM = "---"


class FrontmatterError(ValueError):
    pass


def parse(text: str) -> tuple[dict[str, Any], str, int]:
    """Split `text` into (frontmatter, body, body_start_line).

    `body_start_line` is 1-indexed, so a diagnostic about the body can point at
    a real line in the file.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != _DELIM:
        return {}, text, 1

    for index in range(1, len(lines)):
        if lines[index].strip() == _DELIM:
            raw = "\n".join(lines[1:index])
            try:
                loaded = yaml.safe_load(raw) or {}
            except yaml.YAMLError as exc:
                raise FrontmatterError(f"invalid YAML frontmatter: {exc}") from exc
            if not isinstance(loaded, dict):
                raise FrontmatterError(
                    f"frontmatter must be a mapping, got {type(loaded).__name__}"
                )
            body = "\n".join(lines[index + 1 :]).lstrip("\n")
            return loaded, body, index + 2

    raise FrontmatterError("frontmatter opened with '---' but never closed")


def render(frontmatter: dict[str, Any], body: str) -> str:
    """Inverse of `parse`, with keys emitted in insertion order."""
    if not frontmatter:
        return body.rstrip() + "\n"
    dumped = yaml.safe_dump(
        frontmatter, sort_keys=False, default_flow_style=False, allow_unicode=True
    ).rstrip()
    return f"{_DELIM}\n{dumped}\n{_DELIM}\n\n{body.rstrip()}\n"
