"""Shared standard-library command line interface."""

from __future__ import annotations

import argparse
import json
import shlex
import sys
from typing import TYPE_CHECKING

from persistra._inspection import (
    DirectoryInspection,
    InspectionError,
    discover_stores,
    inventory_document,
    serve_inspector,
)
from persistra.errors import ProjectError
from persistra.integrations.trading_engine import (
    ReplayBundleComparison,
    ReplayBundleError,
    ReplayBundleVerification,
    ReplaySuiteError,
    ReplaySuiteResult,
    compare_replay_bundles,
    run_replay_suite,
    verify_replay_bundle,
)
from persistra.project import ProjectValidation, create_project, validate_project

if TYPE_CHECKING:
    from collections.abc import Sequence


def build_parser() -> argparse.ArgumentParser:
    """Build the shared Persistra command parser."""
    parser = argparse.ArgumentParser(prog="persistra")
    commands = parser.add_subparsers(dest="command", required=True)
    inspect_parser = commands.add_parser("inspect", help="inspect local Persistra stores")
    inspect_parser.add_argument("directory")
    inspect_parser.add_argument(
        "--recursive", action="store_true", help="include descendant directories"
    )
    inspect_parser.add_argument("--no-open", action="store_true", help="do not open a browser")
    inspect_parser.add_argument("--port", type=int, help="local server port")
    inspect_parser.add_argument(
        "--list", dest="list_mode", action="store_true", help="print a headless store inventory"
    )
    inspect_parser.add_argument(
        "--json", action="store_true", help="write the headless inventory as versioned JSON"
    )
    init_parser = commands.add_parser("init", help="create a standard Persistra project")
    init_parser.add_argument("directory")
    init_parser.add_argument("--name", help="explicit normalized project name")
    project_parser = commands.add_parser("project", help="work with a Persistra project")
    project_commands = project_parser.add_subparsers(dest="project_command", required=True)
    validate_parser = project_commands.add_parser(
        "validate", help="diagnose a project without changing it"
    )
    validate_parser.add_argument("directory")
    validate_parser.add_argument(
        "--json", action="store_true", help="write versioned JSON diagnostics"
    )
    engine_parser = commands.add_parser(
        "trading-engine", help="work with Trading Engine replay artifacts"
    )
    engine_commands = engine_parser.add_subparsers(dest="trading_engine_command", required=True)
    bundle_parser = engine_commands.add_parser("bundle", help="verify and compare replay bundles")
    bundle_commands = bundle_parser.add_subparsers(dest="bundle_command", required=True)
    bundle_verify = bundle_commands.add_parser(
        "verify", help="verify an existing replay bundle offline"
    )
    bundle_verify.add_argument("path")
    bundle_verify.add_argument("--json", action="store_true", help="write JSON results")
    bundle_compare = bundle_commands.add_parser(
        "compare", help="compare two verified replay bundles"
    )
    bundle_compare.add_argument("left")
    bundle_compare.add_argument("right")
    bundle_compare.add_argument("--json", action="store_true", help="write JSON results")
    suite_parser = engine_commands.add_parser("suite", help="run declared replay suites")
    suite_commands = suite_parser.add_subparsers(dest="suite_command", required=True)
    suite_run = suite_commands.add_parser("run", help="run one replay suite")
    suite_run.add_argument("manifest")
    suite_run.add_argument("--executable", required=True)
    suite_run.add_argument("--output", required=True)
    suite_run.add_argument("--workers", type=int, default=1)
    suite_run.add_argument(
        "--failure-policy", choices=("continue", "fail_fast"), default="continue"
    )
    suite_run.add_argument("--timeout", type=float, default=300.0)
    suite_run.add_argument("--resume", action="store_true")
    suite_run.add_argument("--json", action="store_true", help="write JSON results")
    return parser


def run(argv: Sequence[str] | None = None) -> int:
    """Run one parsed command and return its process status."""
    parser = build_parser()
    arguments = parser.parse_args(argv)
    if arguments.command == "inspect":
        if arguments.list_mode and (arguments.no_open or arguments.port is not None):
            parser.error("--list cannot be combined with server options --no-open or --port")
        if arguments.json and not arguments.list_mode:
            parser.error("--json requires --list")
        if arguments.list_mode:
            inspection = discover_stores(
                arguments.directory,
                recursive=arguments.recursive,
                allow_empty=True,
            )
            _render_inspection_inventory(inspection, as_json=arguments.json)
            if not inspection.stores and not inspection.artifacts:
                print(
                    f"persistra: error: no supported Persistra stores or artifacts found in "
                    f"{inspection.directory}",
                    file=sys.stderr,
                )
                return 1
            return 0
        inspection = discover_stores(arguments.directory, recursive=arguments.recursive)
        _render_inspection_warnings(inspection)
        serve_inspector(
            inspection,
            port=arguments.port,
            open_browser=not arguments.no_open,
        )
        return 0
    if arguments.command == "init":
        project = create_project(arguments.directory, name=arguments.name)
        print(f"Created Persistra project {project.name} at {project.root}")
        print()
        print(f"cd {shlex.quote(str(project.root))}")
        print("uv sync")
        print("uv run python main.py")
        print("uv run persistra project validate .")
        print("uv run persistra inspect .")
        return 0
    if arguments.command == "project" and arguments.project_command == "validate":
        validation = validate_project(arguments.directory)
        _render_project_validation(validation, as_json=arguments.json)
        return 0 if validation.is_valid else 1
    if arguments.command == "trading-engine":
        if arguments.trading_engine_command == "bundle" and arguments.bundle_command == "verify":
            verification = verify_replay_bundle(arguments.path)
            _render_bundle_verification(verification, as_json=arguments.json)
            return 0
        if arguments.trading_engine_command == "bundle" and arguments.bundle_command == "compare":
            comparison = compare_replay_bundles(arguments.left, arguments.right)
            _render_bundle_comparison(comparison, as_json=arguments.json)
            return 0 if comparison.identical else 1
        if arguments.trading_engine_command == "suite" and arguments.suite_command == "run":
            result = run_replay_suite(
                arguments.manifest,
                executable=arguments.executable,
                output_directory=arguments.output,
                workers=arguments.workers,
                failure_policy=arguments.failure_policy,
                timeout=arguments.timeout,
                resume=arguments.resume,
            )
            _render_suite_result(result, as_json=arguments.json)
            return 0 if result.is_complete else 1
    raise AssertionError(f"unhandled command: {arguments.command}")


def _render_inspection_warnings(inspection: DirectoryInspection) -> None:
    for warning in inspection.warnings:
        print(f"persistra: warning: {warning}", file=sys.stderr)


def _render_inspection_inventory(inspection: DirectoryInspection, *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(inventory_document(inspection), indent=2))
        return
    _render_inspection_warnings(inspection)
    print(f"Persistra store inventory: {inspection.directory}")
    if inspection.project_name is not None:
        print(
            f"Project: {inspection.project_name} "
            f"(format version {inspection.project_format_version})"
        )
    for artifact in inspection.artifacts:
        label = "Research manifest" if artifact.kind == "research_manifest" else "Replay bundle"
        print(f"Artifact: {label} / {artifact.path}")
        print("  Verification: verified")
    for store in inspection.stores:
        print(f"Store: {store.path}")
        print(f"  Schema version: {store.schema_version}")
        if not store.datasets:
            print("  Datasets: none")
        for dataset in store.datasets:
            print(f"  Dataset: {dataset.family} / {dataset.scope_key}")
            print(f"    Snapshots: {dataset.snapshot_count}")
            print(f"    First seen: {dataset.first_seen.isoformat()}")
            print(f"    Last seen: {dataset.last_seen.isoformat()}")
            print(f"    Latest snapshot: {dataset.latest_snapshot_id}")


def _render_project_validation(validation: ProjectValidation, *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(validation.to_dict(), indent=2))
        return
    print(f"Persistra project validation: {validation.root}")
    if validation.project_name is not None:
        print(f"Project: {validation.project_name}")
    for finding in validation.findings:
        location = "" if finding.location is None else f" [{finding.location}]"
        print(f"{finding.severity.value}: {finding.code}{location}: {finding.message}")
    print(
        f"Validation completed: {validation.error_count} error(s), "
        f"{validation.warning_count} warning(s)."
    )


def _render_bundle_verification(verification: ReplayBundleVerification, *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(verification.to_dict(), indent=2, sort_keys=True))
        return
    strategy = "none"
    if verification.strategy_identity is not None:
        strategy = verification.strategy_identity.name
    print(
        f"Verified replay bundle {verification.run_id}: contract "
        f"v{verification.contract_version}, {verification.execution_model}, "
        f"{len(verification.replay.events)} journal records, strategy {strategy}."
    )


def _render_bundle_comparison(comparison: ReplayBundleComparison, *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(comparison.to_dict(), indent=2, sort_keys=True))
        return
    if comparison.identical:
        print("Replay bundles are identical at every compared layer.")
        return
    inputs = ", ".join(comparison.input_changes) or "none"
    outputs = ", ".join(comparison.output_changes) or "none"
    print(
        f"Replay bundles differ: inputs [{inputs}]; outputs [{outputs}]; "
        f"first divergence {comparison.first_divergence}."
    )


def _render_suite_result(result: ReplaySuiteResult, *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
        return
    status = "complete" if result.is_complete else "incomplete"
    print(
        f"Replay suite {status}: {len(result.runs)} run(s), "
        f"{result.succeeded} succeeded, {result.resumed} resumed, "
        f"{result.failed} failed, {result.skipped} skipped."
    )
    for run_result in result.runs:
        detail = "" if run_result.error is None else f" — {run_result.error}"
        print(f"{run_result.run_id}: {run_result.status}{detail}")


def main(argv: Sequence[str] | None = None) -> None:
    """Run the CLI without exposing tracebacks for expected user errors."""
    try:
        status = run(argv)
    except KeyboardInterrupt:
        print("persistra: cancelled", file=sys.stderr)
        raise SystemExit(130) from None
    except (
        InspectionError,
        ProjectError,
        ReplayBundleError,
        ReplaySuiteError,
        OSError,
    ) as error:
        print(f"persistra: error: {error}", file=sys.stderr)
        raise SystemExit(2) from None
    raise SystemExit(status)
