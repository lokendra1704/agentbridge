"""Claude Code backend: emits a `.claude/` plugin, and imports one back."""

from agentbridge.backends.claude_code.emitter import ClaudeCodeBackend
from agentbridge.backends.claude_code.importer import import_plugin

__all__ = ["ClaudeCodeBackend", "import_plugin"]
