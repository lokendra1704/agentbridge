"""Diagnostics: how the bridge reports information loss.

The design rule from CLAUDE.md is that a mapping must never *silently* drop
information. Every place a construct cannot survive a translation, the parser,
emitter, or importer appends a `Diagnostic` here with the spec location
attached, and the CLI prints it.
"""

from __future__ import annotations

from collections.abc import Iterator
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict


class Severity(StrEnum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class SpecLocation(BaseModel):
    """Where in the authored spec a diagnostic came from."""

    model_config = ConfigDict(frozen=True)

    file: Path
    line: int | None = None

    def __str__(self) -> str:
        return f"{self.file}:{self.line}" if self.line is not None else str(self.file)


class Diagnostic(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: str
    severity: Severity
    message: str
    location: SpecLocation | None = None
    hint: str | None = None

    def format(self) -> str:
        where = f"{self.location}: " if self.location is not None else ""
        out = f"{where}{self.severity.value}[{self.code}]: {self.message}"
        if self.hint:
            out += f"\n    hint: {self.hint}"
        return out


class DiagnosticBag:
    """Collects diagnostics across a parse/emit/import run."""

    def __init__(self) -> None:
        self._items: list[Diagnostic] = []

    def add(
        self,
        code: str,
        severity: Severity,
        message: str,
        *,
        location: SpecLocation | None = None,
        hint: str | None = None,
    ) -> None:
        self._items.append(
            Diagnostic(code=code, severity=severity, message=message, location=location, hint=hint)
        )

    def error(self, code: str, message: str, **kw: object) -> None:
        self.add(code, Severity.ERROR, message, **kw)  # type: ignore[arg-type]

    def warn(self, code: str, message: str, **kw: object) -> None:
        self.add(code, Severity.WARNING, message, **kw)  # type: ignore[arg-type]

    def info(self, code: str, message: str, **kw: object) -> None:
        self.add(code, Severity.INFO, message, **kw)  # type: ignore[arg-type]

    @property
    def items(self) -> list[Diagnostic]:
        return list(self._items)

    def by_severity(self, severity: Severity) -> list[Diagnostic]:
        return [d for d in self._items if d.severity is severity]

    @property
    def has_errors(self) -> bool:
        return any(d.severity is Severity.ERROR for d in self._items)

    def extend(self, other: DiagnosticBag) -> None:
        self._items.extend(other._items)

    def codes(self) -> set[str]:
        return {d.code for d in self._items}

    def __iter__(self) -> Iterator[Diagnostic]:
        return iter(self._items)

    def __len__(self) -> int:
        return len(self._items)

    def __bool__(self) -> bool:
        return bool(self._items)


class SpecError(Exception):
    """Raised when a spec cannot be parsed into an IR bundle at all."""

    def __init__(self, message: str, diagnostics: DiagnosticBag | None = None) -> None:
        super().__init__(message)
        self.diagnostics = diagnostics or DiagnosticBag()
