"""agentbridge — author an agentic workflow once, run it on more than one engine.

    spec files  --parse-->  IR  --emit-->  engine artifacts  --deploy-->  platform
        ^                    |
        +-----import---------+

Dependencies run one way only: backends import the IR, the IR imports nothing
below it. See TechnicalREADME.md for the architecture and CodeIndex.md for a
map of the source.
"""

from agentbridge.diagnostics import Diagnostic, DiagnosticBag, Severity, SpecError
from agentbridge.ir import Bundle
from agentbridge.spec import parse_spec, write_spec

__version__ = "0.1.0"

__all__ = [
    "Bundle",
    "Diagnostic",
    "DiagnosticBag",
    "Severity",
    "SpecError",
    "__version__",
    "parse_spec",
    "write_spec",
]
