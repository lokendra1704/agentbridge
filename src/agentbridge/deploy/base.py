"""The `DeploymentTarget` contract.

Kept separate from `RuntimeBackend` on purpose. LangGraph Platform and CrewAI's
hosted offering are different products from their runtimes: you can run either
engine locally with no deployment target at all, and a single engine may have
several. Folding deployment into the backend would make the common case (run
it locally) carry the uncommon case's baggage.

The split also draws a clean line in the generated output: the backend emits
the program, the target emits everything about *shipping* it — manifests,
environment templates, the commands to run.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar

from pydantic import BaseModel, ConfigDict

from agentbridge.backends.base import EmittedFile
from agentbridge.diagnostics import DiagnosticBag
from agentbridge.ir.models import Bundle


class DeployCommand(BaseModel):
    model_config = ConfigDict(frozen=True)

    label: str
    command: str
    note: str | None = None


class DeploymentTarget(ABC):
    name: ClassVar[str]
    description: ClassVar[str] = ""
    #: Which runtime backend's output this target ships.
    engine: ClassVar[str]

    @abstractmethod
    def prepare(
        self, bundle: Bundle, emitted: list[EmittedFile], diagnostics: DiagnosticBag
    ) -> list[EmittedFile]:
        """Produce the deployment artifacts that sit alongside `emitted`."""

    @abstractmethod
    def commands(self, bundle: Bundle) -> list[DeployCommand]:
        """The commands a user runs to deploy, in order."""


class DeploymentRegistry:
    def __init__(self) -> None:
        self._targets: dict[str, type[DeploymentTarget]] = {}
        self._loaded_plugins = False

    def register(self, target: type[DeploymentTarget]) -> None:
        self._targets[target.name] = target

    def _load_plugins(self) -> None:
        if self._loaded_plugins:
            return
        self._loaded_plugins = True
        from importlib.metadata import entry_points

        for ep in entry_points(group="agentbridge.deploy"):
            if ep.name in self._targets:
                continue
            try:
                loaded = ep.load()
            except Exception:
                continue
            if isinstance(loaded, type) and issubclass(loaded, DeploymentTarget):
                self.register(loaded)

    def get(self, name: str) -> DeploymentTarget:
        self._load_plugins()
        try:
            return self._targets[name]()
        except KeyError:
            raise KeyError(
                f"unknown deployment target {name!r}; available: {sorted(self._targets)}"
            ) from None

    def names(self) -> list[str]:
        self._load_plugins()
        return sorted(self._targets)

    def for_engine(self, engine: str) -> list[str]:
        self._load_plugins()
        return sorted(n for n, t in self._targets.items() if t.engine == engine)
