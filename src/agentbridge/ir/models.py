"""The intermediate representation — the project's contract.

Nothing in this module may name an engine (Claude Code, LangGraph, CrewAI) or
an engine-specific concept. If a field only makes sense because one engine has
a particular shape, it does not belong here. Backends translate *from* these
types; they never extend them.

There is a test that enforces this (`tests/test_ir_neutrality.py`).
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from agentbridge.diagnostics import SpecLocation

# Sentinel node name meaning "the workflow finishes here". Engine-neutral: every
# engine has *some* notion of termination, even if only "the model stops".
END = "END"

_IDENT = r"^[a-z0-9][a-z0-9-]*$"
Name = Annotated[str, Field(pattern=_IDENT, min_length=1, max_length=64)]


class Located(BaseModel):
    """Base for anything that can be traced back to a spec file.

    The field is named `location` rather than `source` because `Edge` and
    `Branch` already use `source` for the node an edge leaves from.
    """

    model_config = ConfigDict(extra="forbid")

    location: SpecLocation | None = None


# --------------------------------------------------------------------------
# Model configuration
# --------------------------------------------------------------------------


class Effort(StrEnum):
    """How much reasoning budget a model should spend on a turn."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    XHIGH = "xhigh"
    MAX = "max"


class ModelConfig(Located):
    """Which model an agent runs on, and how hard it should think.

    `name` is a provider model id, deliberately passed through verbatim: the
    bridge does not maintain a model registry, because that would rot faster
    than the rest of the project.
    """

    name: str = "claude-opus-5"
    max_tokens: int | None = Field(default=None, gt=0)
    effort: Effort | None = None
    # Present because non-Anthropic providers (a CrewAI crew on another vendor)
    # still accept it. Current Claude models reject it; the validator warns.
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)


# --------------------------------------------------------------------------
# Tools
# --------------------------------------------------------------------------


class Tool(Located):
    """A capability an agent can invoke.

    Exactly one of `implementation` (a dotted `module:callable` path the user
    supplies) or `builtin` (a capability the runtime is expected to provide,
    e.g. reading a file) must be set.
    """

    name: Name
    description: str = Field(min_length=1)
    parameters: dict[str, Any] = Field(default_factory=dict)
    implementation: str | None = None
    builtin: str | None = None

    @model_validator(mode="after")
    def _exactly_one_source(self) -> Tool:
        if bool(self.implementation) == bool(self.builtin):
            raise ValueError(
                f"tool {self.name!r} must set exactly one of 'implementation' or 'builtin'"
            )
        return self

    @field_validator("implementation")
    @classmethod
    def _dotted_path(cls, v: str | None) -> str | None:
        if v is not None and ":" not in v:
            raise ValueError(f"implementation must look like 'package.module:callable', got {v!r}")
        return v


# --------------------------------------------------------------------------
# Skills
# --------------------------------------------------------------------------


class Skill(Located):
    """A bundle of instructions loaded on demand rather than held in context.

    `description` is load-bearing, not documentation: it is the only thing an
    engine sees when deciding whether the skill is relevant, so it must state
    the trigger condition.
    """

    name: Name
    description: str = Field(min_length=1)
    body: str = ""
    resources: list[str] = Field(default_factory=list)
    allowed_tools: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------
# Agents
# --------------------------------------------------------------------------


class Agent(Located):
    """A unit of delegated work with its own instructions and capabilities."""

    name: Name
    description: str = Field(min_length=1)
    prompt: str = ""
    model: ModelConfig | None = None
    tools: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------
# State
# --------------------------------------------------------------------------


class FieldType(StrEnum):
    STR = "str"
    INT = "int"
    FLOAT = "float"
    BOOL = "bool"
    LIST = "list"
    DICT = "dict"
    #: An ordered transcript of turns. Every engine has one; only some make it
    #: an explicit value.
    MESSAGES = "messages"


class Reducer(StrEnum):
    """How two writes to the same state field combine."""

    REPLACE = "replace"
    APPEND = "append"
    MERGE = "merge"


class StateField(Located):
    name: str = Field(pattern=r"^[a-z_][a-z0-9_]*$")
    type: FieldType
    reducer: Reducer = Reducer.REPLACE
    description: str | None = None
    default: Any = None

    @model_validator(mode="after")
    def _reducer_fits_type(self) -> StateField:
        if self.reducer is Reducer.APPEND and self.type not in (
            FieldType.LIST,
            FieldType.MESSAGES,
        ):
            raise ValueError(
                f"state field {self.name!r}: reducer 'append' needs a list or messages type"
            )
        if self.reducer is Reducer.MERGE and self.type is not FieldType.DICT:
            raise ValueError(f"state field {self.name!r}: reducer 'merge' needs a dict type")
        return self


class StateSchema(Located):
    name: str = Field(default="WorkflowState", pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    fields: list[StateField] = Field(default_factory=list)

    def field(self, name: str) -> StateField | None:
        return next((f for f in self.fields if f.name == name), None)

    @property
    def transcript_field(self) -> StateField | None:
        """The field holding the conversation, if the author declared one."""
        return next((f for f in self.fields if f.type is FieldType.MESSAGES), None)


# --------------------------------------------------------------------------
# Workflow structure
# --------------------------------------------------------------------------


class Node(Located):
    """One step of the workflow: either an agent turn or a plain function."""

    name: Name
    agent: str | None = None
    function: str | None = None
    description: str | None = None

    @model_validator(mode="after")
    def _exactly_one_body(self) -> Node:
        if bool(self.agent) == bool(self.function):
            raise ValueError(f"node {self.name!r} must set exactly one of 'agent' or 'function'")
        return self


class Edge(Located):
    source: str
    target: str


class Branch(Located):
    """A fork in the workflow.

    `condition` is a dotted path to a callable that inspects state and returns
    one of the keys of `targets`. `description` states the same rule in prose —
    it is what an engine that has no explicit control flow falls back to, so it
    is required rather than optional.
    """

    source: str
    condition: str
    description: str = Field(min_length=1)
    targets: dict[str, str] = Field(min_length=1)

    @field_validator("condition")
    @classmethod
    def _dotted_path(cls, v: str) -> str:
        if ":" not in v:
            raise ValueError(f"condition must look like 'package.module:callable', got {v!r}")
        return v


class WorkflowMode(StrEnum):
    #: Structure is declared: nodes, edges, branches.
    GRAPH = "graph"
    #: No structure declared; the model decides what to do next.
    AUTONOMOUS = "autonomous"


class Workflow(Located):
    name: Name
    description: str = Field(min_length=1)
    version: str = "0.1.0"
    mode: WorkflowMode = WorkflowMode.AUTONOMOUS
    entry: str | None = None
    nodes: list[Node] = Field(default_factory=list)
    edges: list[Edge] = Field(default_factory=list)
    branches: list[Branch] = Field(default_factory=list)
    state: StateSchema = Field(default_factory=StateSchema)
    model: ModelConfig = Field(default_factory=ModelConfig)

    def node(self, name: str) -> Node | None:
        return next((n for n in self.nodes if n.name == name), None)

    def successors(self, name: str) -> list[str]:
        out = [e.target for e in self.edges if e.source == name]
        for b in self.branches:
            if b.source == name:
                out.extend(b.targets.values())
        return out


# --------------------------------------------------------------------------
# The bundle
# --------------------------------------------------------------------------


class Bundle(BaseModel):
    """A fully parsed workflow: everything a backend needs to emit."""

    model_config = ConfigDict(extra="forbid")

    workflow: Workflow
    agents: dict[str, Agent] = Field(default_factory=dict)
    skills: dict[str, Skill] = Field(default_factory=dict)
    tools: dict[str, Tool] = Field(default_factory=dict)

    def agent_tools(self, agent: Agent) -> list[Tool]:
        return [self.tools[t] for t in agent.tools if t in self.tools]

    def agent_skills(self, agent: Agent) -> list[Skill]:
        return [self.skills[s] for s in agent.skills if s in self.skills]

    def ordered_agents(self) -> list[Agent]:
        return [self.agents[k] for k in sorted(self.agents)]

    def ordered_skills(self) -> list[Skill]:
        return [self.skills[k] for k in sorted(self.skills)]

    def ordered_tools(self) -> list[Tool]:
        return [self.tools[k] for k in sorted(self.tools)]


class ContractKind(StrEnum):
    AGENT = "agent"
    SKILL = "skill"
    TOOL = "tool"
    NODE = "node"


class EngineContract(BaseModel):
    """What a backend claims it actually materialised.

    The conformance suite asserts that every backend produces the *same*
    contract for the same spec. That is what makes "one spec, many engines" a
    checkable statement rather than a slogan: it catches a backend that quietly
    drops a skill, far more directly than comparing generated file bytes.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    engine: str
    agents: frozenset[str]
    skills: frozenset[str]
    tools: frozenset[str]
    nodes: frozenset[str]
    entry: str | None

    def differences(self, other: EngineContract) -> list[str]:
        out: list[str] = []
        for kind in ("agents", "skills", "tools", "nodes"):
            mine: frozenset[str] = getattr(self, kind)
            theirs: frozenset[str] = getattr(other, kind)
            if missing := theirs - mine:
                out.append(f"{self.engine} is missing {kind}: {sorted(missing)}")
            if extra := mine - theirs:
                out.append(f"{self.engine} has extra {kind}: {sorted(extra)}")
        if self.entry != other.entry:
            out.append(
                f"entry differs: {self.engine}={self.entry!r} vs {other.engine}={other.entry!r}"
            )
        return out


__all__ = [
    "END",
    "Agent",
    "Branch",
    "Bundle",
    "ContractKind",
    "Edge",
    "Effort",
    "EngineContract",
    "FieldType",
    "Located",
    "ModelConfig",
    "Name",
    "Node",
    "Reducer",
    "Skill",
    "StateField",
    "StateSchema",
    "Tool",
    "Workflow",
    "WorkflowMode",
]
