"""The concept mapping table, in one place.

Most of the real work of this project is deciding how an IR concept lands on
each engine, and the decisions are not obvious. Keeping them here — as data
with rationale attached, rather than scattered `if` statements inside
emitters — means a reader can see the whole translation at once, and a new
backend author has a checklist rather than an archaeology exercise.

The `Fidelity` on each row is the honest answer to "does this survive the
round trip?", and it is what the emitters use to decide whether to raise a
diagnostic.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class Fidelity(StrEnum):
    #: Survives translation with no loss; a round trip returns the same IR.
    EXACT = "exact"
    #: Meaning is preserved but the shape changes, so a round trip is not
    #: byte-identical. Recorded as an INFO diagnostic.
    LOWERED = "lowered"
    #: Information is genuinely lost. Always accompanied by a WARNING carrying
    #: the spec location, per the project rule that nothing drops silently.
    LOSSY = "lossy"


class Mapping(BaseModel):
    model_config = ConfigDict(frozen=True)

    concept: str
    engine: str
    target: str
    fidelity: Fidelity
    #: Why this lowering and not another. Read this before changing a row.
    rationale: str
    #: Diagnostic code emitted when the row is exercised, for non-EXACT rows.
    diagnostic: str | None = None


CLAUDE_CODE = "claude-code"
LANGGRAPH = "langgraph"


MAPPINGS: tuple[Mapping, ...] = (
    # ---------------------------------------------------------------- agents
    Mapping(
        concept="agent",
        engine=CLAUDE_CODE,
        target=".claude/agents/<name>.md",
        fidelity=Fidelity.EXACT,
        rationale=(
            "The spec's agent format was chosen to match Claude Code's subagent "
            "frontmatter, so this emitter is close to a copy and the importer is "
            "close to lossless. That was a deliberate constraint on the spec."
        ),
    ),
    Mapping(
        concept="agent",
        engine=LANGGRAPH,
        target="a node running a tool-calling loop",
        fidelity=Fidelity.LOWERED,
        rationale=(
            "A subagent is a prompt plus a tool set plus a private context. A "
            "LangGraph node with its own model binding is the closest thing; the "
            "private context becomes whatever slice of state the node reads."
        ),
    ),
    # ---------------------------------------------------------------- skills
    Mapping(
        concept="skill",
        engine=CLAUDE_CODE,
        target=".claude/skills/<name>/SKILL.md",
        fidelity=Fidelity.EXACT,
        rationale=(
            "Native concept. Lazy, model-triggered loading is preserved "
            "exactly, including the description-as-trigger semantics that the "
            "other engines have to reconstruct."
        ),
    ),
    Mapping(
        concept="skill",
        engine=LANGGRAPH,
        target="a zero-argument tool whose return value is the skill body",
        fidelity=Fidelity.LOWERED,
        diagnostic="BRIDGE202",
        rationale=(
            "THE CANONICAL SKILL LOWERING. LangGraph has no 'load these "
            "instructions when they become relevant' primitive, so something has "
            "to give. Making the skill a tool preserves the property that "
            "actually matters — the model decides when to pull the instructions "
            "into context, and pays no token cost until it does. The skill's "
            "`description` becomes the tool description, which is what the model "
            "routes on, so the trigger semantics carry over too.\n\n"
            "Rejected alternatives: (a) concatenating every skill body into the "
            "system prompt — correct output, but destroys laziness and inflates "
            "every request; (b) making each skill a graph node — forces the "
            "author to declare control flow the spec deliberately left implicit."
        ),
    ),
    # ----------------------------------------------------------------- tools
    Mapping(
        concept="tool (user implementation)",
        engine=CLAUDE_CODE,
        target="an MCP tool name listed in agent frontmatter",
        fidelity=Fidelity.LOSSY,
        diagnostic="BRIDGE103",
        rationale=(
            "Claude Code cannot import a Python callable. The emitted plugin "
            "names the tool so the agent's prompt is correct, but wiring the "
            "implementation is the user's job — hence a warning rather than "
            "silence."
        ),
    ),
    Mapping(
        concept="tool (user implementation)",
        engine=LANGGRAPH,
        target="an imported callable wrapped as a structured tool",
        fidelity=Fidelity.EXACT,
        rationale=(
            "Python to Python; the dotted path becomes a real import, so the "
            "author's callable runs unmodified with its signature driving the "
            "tool schema."
        ),
    ),
    Mapping(
        concept="tool (builtin, e.g. file read)",
        engine=CLAUDE_CODE,
        target="the engine's own tool of that name",
        fidelity=Fidelity.EXACT,
        rationale=(
            "Claude Code ships these, so the emitter only has to name them. "
            "This is why the spec keeps `builtin:` separate from an "
            "implementation path: the same tool is free here and needs a shim "
            "elsewhere."
        ),
    ),
    Mapping(
        concept="tool (builtin, e.g. file read)",
        engine=LANGGRAPH,
        target="a shim from agentbridge.runtime.builtins",
        fidelity=Fidelity.LOWERED,
        diagnostic="BRIDGE201",
        rationale=(
            "LangGraph ships no file or shell tools. The bridge provides small "
            "equivalents so a spec that uses them actually runs on both engines "
            "rather than merely compiling. Behaviour is close but not identical "
            "— the shims are deliberately simpler than Claude Code's."
        ),
    ),
    # ---------------------------------------------------------- control flow
    Mapping(
        concept="explicit graph (nodes, edges, branches)",
        engine=CLAUDE_CODE,
        target="a slash command describing the sequence in prose",
        fidelity=Fidelity.LOSSY,
        diagnostic="BRIDGE100",
        rationale=(
            "Claude Code's control flow is the model's judgement, so a declared "
            "graph cannot be enforced — only described. The emitted command "
            "spells out the steps and the branch conditions as instructions, "
            "which is why Branch.description is a required field rather than an "
            "optional comment: it is the only thing that survives here."
        ),
    ),
    Mapping(
        concept="explicit graph (nodes, edges, branches)",
        engine=LANGGRAPH,
        target="StateGraph nodes, edges, and conditional edges",
        fidelity=Fidelity.EXACT,
        rationale=(
            "Native concept, one to one. This is the direction the spec's "
            "graph section exists to serve: the structure is enforced here, "
            "not merely suggested, which is the whole reason for declaring it."
        ),
    ),
    Mapping(
        concept="branch condition (a Python callable)",
        engine=CLAUDE_CODE,
        target="prose in the orchestrating command",
        fidelity=Fidelity.LOSSY,
        diagnostic="BRIDGE101",
        rationale=(
            "The callable cannot run inside Claude Code. Only the branch's "
            "prose description survives, so the routing becomes advisory."
        ),
    ),
    Mapping(
        concept="branch condition (a Python callable)",
        engine=LANGGRAPH,
        target="an imported callable passed to add_conditional_edges",
        fidelity=Fidelity.EXACT,
        rationale=(
            "Python to Python. The condition runs against real state and its "
            "return value selects the edge, so the routing is enforced rather "
            "than advisory."
        ),
    ),
    Mapping(
        concept="autonomous mode (no declared structure)",
        engine=CLAUDE_CODE,
        target="agents the model may delegate to at will",
        fidelity=Fidelity.EXACT,
        rationale=(
            "This is Claude Code's native execution model: the model decides "
            "what to delegate and when, which is exactly what an autonomous "
            "spec describes. Nothing is lost because nothing was declared."
        ),
    ),
    Mapping(
        concept="autonomous mode (no declared structure)",
        engine=LANGGRAPH,
        target="a single node running one agent's tool-calling loop",
        fidelity=Fidelity.LOSSY,
        diagnostic="BRIDGE200",
        rationale=(
            "A spec that says only 'the model decides' contains no graph to "
            "build. The emitter produces a one-node graph so the workflow still "
            "runs, but multi-agent delegation is flattened away. This is the "
            "second of the two genuinely lossy directions, and the reason the "
            "spec format has a `graph:` section at all."
        ),
    ),
    # ----------------------------------------------------------------- state
    Mapping(
        concept="typed state schema",
        engine=CLAUDE_CODE,
        target="nothing — the transcript is the state",
        fidelity=Fidelity.LOSSY,
        diagnostic="BRIDGE102",
        rationale=(
            "Claude Code has no state object to reduce into. Non-transcript "
            "fields are documented in the emitted command so the model knows to "
            "track them in prose, but nothing enforces the shape."
        ),
    ),
    Mapping(
        concept="typed state schema",
        engine=LANGGRAPH,
        target="a TypedDict with Annotated reducers",
        fidelity=Fidelity.EXACT,
        rationale=(
            "Native concept, one to one, including per-field reducers. Every "
            "IR reducer has a direct equivalent, so no state semantics are "
            "approximated."
        ),
    ),
    Mapping(
        concept="persistence",
        engine=CLAUDE_CODE,
        target="session files (implicit)",
        fidelity=Fidelity.LOWERED,
        rationale=(
            "Sessions persist automatically, so there is nothing to emit — but "
            "the persistence is transcript-shaped rather than state-shaped, so "
            "it is not interchangeable with a checkpointer."
        ),
    ),
    Mapping(
        concept="persistence",
        engine=LANGGRAPH,
        target="a checkpointer supplied at build time",
        fidelity=Fidelity.LOWERED,
        rationale=(
            "The generated build_graph() takes an optional checkpointer rather "
            "than hardcoding one, because the right choice (memory, SQLite, "
            "Postgres) is a deployment decision, not a workflow decision."
        ),
    ),
)


def for_engine(engine: str) -> tuple[Mapping, ...]:
    return tuple(m for m in MAPPINGS if m.engine == engine)


def lookup(concept: str, engine: str) -> Mapping | None:
    return next((m for m in MAPPINGS if m.concept == concept and m.engine == engine), None)


def lossy_rows(engine: str) -> tuple[Mapping, ...]:
    return tuple(m for m in for_engine(engine) if m.fidelity is Fidelity.LOSSY)


def render_table() -> str:
    """Render the mapping as Markdown, for docs and for `agentbridge mapping`."""
    engines = sorted({m.engine for m in MAPPINGS})
    concepts: list[str] = []
    for m in MAPPINGS:
        if m.concept not in concepts:
            concepts.append(m.concept)

    lines = ["| Concept | " + " | ".join(engines) + " |"]
    lines.append("|---" * (len(engines) + 1) + "|")
    for concept in concepts:
        cells = []
        for engine in engines:
            row = lookup(concept, engine)
            cells.append(f"{row.target} _({row.fidelity.value})_" if row else "—")
        lines.append(f"| {concept} | " + " | ".join(cells) + " |")
    return "\n".join(lines)
