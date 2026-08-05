"""Command-line entry point.

argparse rather than a CLI framework: five commands do not justify a
dependency, and the IR is the thing that should be worth depending on.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from agentbridge.backends import registry as backend_registry
from agentbridge.backends.base import EmittedFile
from agentbridge.backends.claude_code import import_plugin
from agentbridge.deploy import registry as deploy_registry
from agentbridge.diagnostics import DiagnosticBag, Severity, SpecError
from agentbridge.ir.models import Bundle
from agentbridge.mapping import render_table
from agentbridge.spec import parse_spec, write_spec

EXIT_OK = 0
EXIT_DIAGNOSTIC_ERROR = 1
EXIT_USAGE = 2


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    handler = getattr(args, "handler", None)
    if handler is None:
        parser.print_help()
        return EXIT_USAGE
    try:
        return int(handler(args))
    except SpecError as exc:
        _print_diagnostics(exc.diagnostics)
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_DIAGNOSTIC_ERROR
    except KeyError as exc:
        print(f"error: {exc.args[0] if exc.args else exc}", file=sys.stderr)
        return EXIT_USAGE


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agentbridge",
        description="Author an agentic workflow once; run it on more than one engine.",
    )
    sub = parser.add_subparsers(dest="command")

    compile_cmd = sub.add_parser("compile", help="Compile a spec into engine artifacts.")
    compile_cmd.add_argument("spec", type=Path, help="Path to the spec directory.")
    compile_cmd.add_argument(
        "-e", "--engine", required=True, help="Target engine (see `agentbridge engines`)."
    )
    compile_cmd.add_argument("-o", "--out", type=Path, required=True, help="Output directory.")
    compile_cmd.add_argument("--deploy", help="Also emit artifacts for this deployment target.")
    compile_cmd.add_argument(
        "--dry-run", action="store_true", help="List what would be written; write nothing."
    )
    compile_cmd.add_argument("--strict", action="store_true", help="Treat warnings as errors.")
    compile_cmd.set_defaults(handler=_cmd_compile)

    import_cmd = sub.add_parser(
        "import", help="Import an existing .claude/ plugin back into a spec."
    )
    import_cmd.add_argument(
        "plugin", type=Path, help="Project dir containing .claude/, or .claude/."
    )
    import_cmd.add_argument(
        "-o", "--out", type=Path, required=True, help="Spec directory to write."
    )
    import_cmd.add_argument("--dry-run", action="store_true", help="Write nothing.")
    import_cmd.set_defaults(handler=_cmd_import)

    validate_cmd = sub.add_parser("validate", help="Parse and check a spec without emitting.")
    validate_cmd.add_argument("spec", type=Path)
    validate_cmd.add_argument("--strict", action="store_true", help="Treat warnings as errors.")
    validate_cmd.set_defaults(handler=_cmd_validate)

    engines_cmd = sub.add_parser("engines", help="List engines and deployment targets.")
    engines_cmd.set_defaults(handler=_cmd_engines)

    mapping_cmd = sub.add_parser("mapping", help="Print the concept mapping table.")
    mapping_cmd.set_defaults(handler=_cmd_mapping)

    return parser


# --------------------------------------------------------------------------
# commands
# --------------------------------------------------------------------------


def _cmd_compile(args: argparse.Namespace) -> int:
    bundle, bag = parse_spec(args.spec)
    backend = backend_registry.get(args.engine)
    files = backend.emit(bundle, bag)

    if args.deploy:
        target = deploy_registry.get(args.deploy)
        if target.engine != backend.name:
            print(
                f"error: deployment target {target.name!r} ships {target.engine!r} "
                f"output, but you compiled for {backend.name!r}",
                file=sys.stderr,
            )
            return EXIT_USAGE
        files = files + target.prepare(bundle, files, bag)

    _print_diagnostics(bag)
    if bag.has_errors:
        print("error: spec has errors; nothing written", file=sys.stderr)
        return EXIT_DIAGNOSTIC_ERROR
    if args.strict and bag.by_severity(Severity.WARNING):
        print("error: warnings present and --strict was given; nothing written", file=sys.stderr)
        return EXIT_DIAGNOSTIC_ERROR

    return _write(files, args.out, dry_run=args.dry_run, label=backend.name)


def _cmd_import(args: argparse.Namespace) -> int:
    bundle, bag = import_plugin(args.plugin)
    files = write_spec(bundle)
    _print_diagnostics(bag)
    if bag.has_errors:
        return EXIT_DIAGNOSTIC_ERROR
    return _write(files, args.out, dry_run=args.dry_run, label="spec")


def _cmd_validate(args: argparse.Namespace) -> int:
    bundle, bag = parse_spec(args.spec)
    _print_diagnostics(bag)
    _print_summary(bundle)
    if bag.has_errors:
        return EXIT_DIAGNOSTIC_ERROR
    if args.strict and bag.by_severity(Severity.WARNING):
        return EXIT_DIAGNOSTIC_ERROR
    return EXIT_OK


def _cmd_engines(_: argparse.Namespace) -> int:
    print("Engines:")
    for name in backend_registry.names():
        backend = backend_registry.get(name)
        runs = " (can run in process)" if backend.supports_run() else ""
        print(f"  {name:<14} {backend.description}{runs}")
        for target in deploy_registry.for_engine(name):
            print(f"      deploy: {target} — {deploy_registry.get(target).description}")
    return EXIT_OK


def _cmd_mapping(_: argparse.Namespace) -> int:
    print(render_table())
    return EXIT_OK


# --------------------------------------------------------------------------
# output
# --------------------------------------------------------------------------


def _write(files: list[EmittedFile], out: Path, *, dry_run: bool, label: str) -> int:
    if dry_run:
        print(f"would write {len(files)} file(s) to {out}:")
        for f in sorted(files, key=lambda f: str(f.path)):
            print(f"  {f.path}")
        return EXIT_OK

    out.mkdir(parents=True, exist_ok=True)
    for f in files:
        f.write_to(out)
    print(f"wrote {len(files)} {label} file(s) to {out}")
    return EXIT_OK


def _print_diagnostics(bag: DiagnosticBag) -> None:
    for diagnostic in bag:
        stream = sys.stderr if diagnostic.severity is not Severity.INFO else sys.stdout
        print(diagnostic.format(), file=stream)


def _print_summary(bundle: Bundle) -> None:
    wf = bundle.workflow
    print(f"{wf.name} v{wf.version} — mode: {wf.mode.value}")
    print(
        f"  agents: {len(bundle.agents)}  skills: {len(bundle.skills)}  tools: {len(bundle.tools)}"
    )
    if wf.nodes:
        print(f"  nodes: {len(wf.nodes)}  edges: {len(wf.edges)}  branches: {len(wf.branches)}")
    print(f"  state fields: {len(wf.state.fields)}")


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
