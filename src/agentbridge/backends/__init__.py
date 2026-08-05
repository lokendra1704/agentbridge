"""Engine backends. One module per engine, behind `RuntimeBackend`."""

from agentbridge.backends.base import BackendRegistry, EmittedFile, RuntimeBackend
from agentbridge.backends.claude_code import ClaudeCodeBackend
from agentbridge.backends.langgraph import LangGraphBackend

registry = BackendRegistry()
registry.register(ClaudeCodeBackend)
registry.register(LangGraphBackend)

__all__ = [
    "BackendRegistry",
    "ClaudeCodeBackend",
    "EmittedFile",
    "LangGraphBackend",
    "RuntimeBackend",
    "registry",
]
