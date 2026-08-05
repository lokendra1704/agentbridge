"""The authored artifact: parsing spec directories into IR, and back."""

from agentbridge.spec.parser import parse_spec
from agentbridge.spec.writer import write_spec

__all__ = ["parse_spec", "write_spec"]
