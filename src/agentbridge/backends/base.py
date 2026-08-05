"""The `RuntimeBackend` contract.

Adding an engine means adding a module that implements this. It must never
mean editing the parser or the IR — if a new engine forces a change to
`agentbridge.ir`, that is a signal the IR leaked an assumption, not that the
IR needs a new field.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path, PurePosixPath
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, field_validator

from agentbridge.diagnostics import DiagnosticBag
from agentbridge.ir.models import Bundle, EngineContract


class EmittedFile(BaseModel):
    """One generated file, with a path relative to the output directory."""

    model_config = ConfigDict(frozen=True)

    path: PurePosixPath
    content: str
    executable: bool = False

    @field_validator("path", mode="before")
    @classmethod
    def _coerce(cls, v: Any) -> PurePosixPath:
        p = PurePosixPath(v)
        if p.is_absolute() or ".." in p.parts:
            raise ValueError(f"emitted path must be relative and contained, got {v!r}")
        return p

    def write_to(self, root: Path) -> Path:
        target = root / self.path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(self.content, encoding="utf-8")
        if self.executable:
            target.chmod(0o755)
        return target


class RuntimeBackend(ABC):
    """Turns an IR bundle into engine-native artifacts."""

    #: Registry key and CLI name, e.g. "langgraph".
    name: ClassVar[str]
    #: One line, shown by `agentbridge engines`.
    description: ClassVar[str] = ""

    @abstractmethod
    def emit(self, bundle: Bundle, diagnostics: DiagnosticBag) -> list[EmittedFile]:
        """Produce the files this engine needs to run `bundle`.

        Every lossy translation must append a diagnostic carrying the spec
        location, rather than dropping the construct quietly.
        """

    @abstractmethod
    def contract(self, bundle: Bundle, files: list[EmittedFile]) -> EngineContract:
        """Report what `files` actually materialised.

        Derive this by inspecting the emitted output, not by copying the
        bundle — the point is to catch a backend that silently skipped
        something, and a contract read off the input cannot do that.
        """

    def supports_run(self) -> bool:
        """Whether `run()` is implemented for in-process execution."""
        return False

    def run(self, bundle: Bundle, inputs: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError(f"{self.name} backend cannot run workflows in process")


class BackendRegistry:
    """Name -> backend. Populated by built-ins plus any installed plugins."""

    def __init__(self) -> None:
        self._backends: dict[str, type[RuntimeBackend]] = {}
        self._loaded_plugins = False

    def register(self, backend: type[RuntimeBackend]) -> None:
        self._backends[backend.name] = backend

    def _load_plugins(self) -> None:
        """Discover third-party backends via the `agentbridge.backends` group."""
        if self._loaded_plugins:
            return
        self._loaded_plugins = True
        from importlib.metadata import entry_points

        for ep in entry_points(group="agentbridge.backends"):
            if ep.name in self._backends:
                continue
            try:
                loaded = ep.load()
            except Exception:
                continue
            if isinstance(loaded, type) and issubclass(loaded, RuntimeBackend):
                self.register(loaded)

    def get(self, name: str) -> RuntimeBackend:
        self._load_plugins()
        try:
            return self._backends[name]()
        except KeyError:
            raise KeyError(
                f"unknown engine {name!r}; available: {sorted(self._backends)}"
            ) from None

    def names(self) -> list[str]:
        self._load_plugins()
        return sorted(self._backends)

    def all(self) -> list[RuntimeBackend]:
        return [self.get(n) for n in self.names()]
