"""Tests for offline Trading Engine bundle verification and comparison."""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import replace
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, Literal, cast

import pandas as pd
import pytest

from persistra import _cli
from persistra.integrations.trading_engine import (
    ReplayBundleError,
    compare_replay_bundles,
    scenario_from_json,
    scenario_to_jsonl,
    verify_replay_bundle,
)

if TYPE_CHECKING:
    from pathlib import Path

    from persistra.integrations.trading_engine import StrategyTranscript


def write_bundle(
    root: Path,
    *,
    metadata: dict[str, object] | None = None,
    initial_cash: str = "10000",
    scenario_format: Literal["json", "jsonl"] = "json",
) -> Path:
    """Write one valid minimal v3 replay bundle."""
    root.mkdir(parents=True, exist_ok=True)
    scenario_document = {
        "contract_version": "3",
        "run_id": "empty-demo",
        "base_currency": "USD",
        "initial_cash": [{"currency": "USD", "amount": initial_cash}],
        "instruments": [
            {
                "instrument_id": "asset-a",
                "symbol": "AAA",
                "quote_currency": "USD",
                "tick_size": "0.01",
                "lot_size": "1",
            }
        ],
        "risk": {
            "max_order_quantity": "1000",
            "max_long_position": "1000",
            "max_short_position": "1000",
            "max_gross_exposure": "1000000",
            "max_leverage": "2",
            "initial_margin_bps": 5000,
            "maintenance_margin_bps": 2500,
            "short_borrow_bps": 0,
        },
        "execution": {
            "model": "completed_bar_v1",
            "participation_bps": 5000,
            "fixed_fee": "0",
            "fee_bps": 0,
        },
        "max_internal_events": 1000,
        "metadata": metadata or {},
        "schedule": [],
        "slices": [],
    }
    if scenario_format == "json":
        scenario = root / "empty-demo.scenario.json"
        scenario_text = json.dumps(scenario_document, separators=(",", ":"))
    else:
        assert scenario_format == "jsonl"
        scenario = root / "empty-demo.scenario.jsonl"
        scenario_text = scenario_to_jsonl(scenario_from_json(json.dumps(scenario_document)))
    scenario.write_text(scenario_text, encoding="utf-8")
    scenario_hash = sha256(scenario)
    valuation = {
        "base_currency": "USD",
        "cash": initial_cash,
        "net_market_value": "0",
        "long_market_value": "0",
        "short_market_value": "0",
        "gross_exposure": "0",
        "cost_basis": "0",
        "realized_pnl": "0",
        "unrealized_pnl": "0",
        "equity": initial_cash,
        "dividend_pnl": "0",
        "execution_fees": "0",
        "borrow_fees": "0",
        "total_fees": "0",
        "cash_balances": [
            {
                "currency": "USD",
                "amount": initial_cash,
                "fx_rate": "1",
                "base_value": initial_cash,
            }
        ],
        "positions": [],
        "margin": {
            "initial_requirement": "0",
            "maintenance_requirement": "0",
            "initial_excess": initial_cash,
            "maintenance_excess": initial_cash,
            "margin_call": False,
        },
    }
    records: list[dict[str, object]] = [
        {
            "contract_version": "3",
            "engine_sequence": "1",
            "event_id": "empty-demo-event-000000000001",
            "causation_ids": [],
            "run_id": "empty-demo",
            "recorded_at": "1970-01-01T00:00:00.000000Z",
            "event_type": "run_started",
            "payload": {
                "scenario_sha256": scenario_hash,
                "execution_model": "completed_bar_v1",
            },
        },
        {
            "contract_version": "3",
            "engine_sequence": "2",
            "event_id": "empty-demo-event-000000000002",
            "causation_ids": ["empty-demo-event-000000000001"],
            "run_id": "empty-demo",
            "recorded_at": "1970-01-01T00:00:00.000000Z",
            "event_type": "run_completed",
            "payload": {
                "scenario_sha256": scenario_hash,
                "execution_model": "completed_bar_v1",
                "valuation": valuation,
                "order_counts": {
                    "total": 0,
                    "active": 0,
                    "filled": 0,
                    "rejected": 0,
                    "cancelled": 0,
                },
            },
        },
    ]
    journal = root / "empty-demo.journal.jsonl"
    journal.write_text(
        "".join(json.dumps(record, separators=(",", ":")) + "\n" for record in records),
        encoding="utf-8",
    )
    manifest = root / "empty-demo.manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "run_id": "empty-demo",
                "contract": {"version": "3"},
                "execution": {"model": "completed_bar_v1"},
                "environment": {},
                "persistra": {"version": "test", "vcs": {}},
                "engine": {
                    "version": "test-engine-1",
                    "capabilities": {
                        "engine_version": "test-engine-1",
                        "scenario_contract_versions": ["3"],
                        "journal_contract_versions": ["3"],
                        "scenario_formats": ["json", "jsonl"],
                        "journal_formats": ["jsonl"],
                        "execution_models": ["completed_bar_v1"],
                        "strategy_protocol_versions": ["3"],
                    },
                    "executable": {"name": "engine", "sha256": "0" * 64},
                    "vcs": {},
                },
                "artifacts": {
                    "scenario": {
                        "path": scenario.name,
                        "sha256": scenario_hash,
                        "format": scenario_format,
                    },
                    "journal": {"path": journal.name, "sha256": sha256(journal)},
                },
                "scenario_metadata": metadata or {},
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return manifest


def sha256(path: Path) -> str:
    """Return an artifact digest."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def manifest_document(path: Path) -> dict[str, Any]:
    """Read a mutable manifest fixture."""
    return json.loads(path.read_text(encoding="utf-8"))


def write_manifest(path: Path, document: dict[str, Any]) -> None:
    """Replace a manifest fixture."""
    path.write_text(json.dumps(document), encoding="utf-8")


def test_bundle_verification_accepts_manifest_directory_and_relocation(
    tmp_path: Path,
) -> None:
    manifest = write_bundle(tmp_path / "bundle")

    direct = verify_replay_bundle(manifest)
    discovered = verify_replay_bundle(manifest.parent)
    relocated = tmp_path / "relocated"
    shutil.copytree(manifest.parent, relocated)
    moved = verify_replay_bundle(relocated)

    assert direct.run_id == discovered.run_id == moved.run_id == "empty-demo"
    assert direct.contract_version == "3"
    assert direct.execution_model == "completed_bar_v1"
    assert direct.strategy_identity is None
    assert direct.replay.completion.equity_micros == 10_000_000_000
    assert direct.to_dict()["status"] == "verified"


def test_bundle_verification_accepts_nested_metadata_arrays(tmp_path: Path) -> None:
    metadata: dict[str, object] = {
        "persistra": {
            "original_targets": [["2025-01-02", {"asset-a": "0.25"}]],
            "source_identities": [{"series": ["bars", "asset-a"]}],
        }
    }
    manifest = write_bundle(
        tmp_path / "nested-metadata",
        metadata=metadata,
        scenario_format="jsonl",
    )

    verified = verify_replay_bundle(manifest)

    assert verified.run_id == "empty-demo"


def test_bundle_verification_reconciles_structured_engine_status(tmp_path: Path) -> None:
    manifest = write_bundle(tmp_path / "structured-status")
    document = manifest_document(manifest)
    scenario = manifest.parent / document["artifacts"]["scenario"]["path"]
    journal = manifest.parent / document["artifacts"]["journal"]["path"]
    document["status"] = {
        "result_version": "1",
        "status": "success",
        "operation": "replay",
        "run_id": "empty-demo",
        "hashes": {
            "scenario_sha256": sha256(scenario),
            "journal_sha256": sha256(journal),
            "strategy_transcript_sha256": None,
        },
        "counts": {
            "instruments": 1,
            "schedule_batches": 0,
            "slices": 0,
            "audits": 2,
            "orders": 0,
            "active_orders": 0,
            "filled_orders": 0,
            "rejected_orders": 0,
        },
        "valuation": {"equity": "10000"},
        "artifacts": {"journal": str(journal), "strategy_transcript": None},
    }
    write_manifest(manifest, document)

    result = verify_replay_bundle(manifest)

    assert result.engine_status["operation"] == "replay"
    result_status = cast("dict[str, object]", result.to_dict()["engine_status"])
    assert result_status["status"] == "success"

    status = cast("dict[str, Any]", document["status"])
    status["counts"]["audits"] = 3
    write_manifest(manifest, document)
    with pytest.raises(ReplayBundleError, match="status reconciliation failed"):
        verify_replay_bundle(manifest)


def test_bundle_verification_rejects_unsupported_status(tmp_path: Path) -> None:
    manifest = write_bundle(tmp_path / "unsupported-status")
    document = manifest_document(manifest)
    document["status"] = {"state": "failed"}
    write_manifest(manifest, document)

    with pytest.raises(ReplayBundleError, match="status is unsupported"):
        verify_replay_bundle(manifest)


def test_bundle_verification_rejects_tampering_missing_and_unsafe_paths(
    tmp_path: Path,
) -> None:
    tampered = write_bundle(tmp_path / "tampered")
    journal = tampered.parent / "empty-demo.journal.jsonl"
    journal.write_text(journal.read_text(encoding="utf-8") + "{}\n", encoding="utf-8")
    with pytest.raises(ReplayBundleError, match="checksum differs"):
        verify_replay_bundle(tampered)

    missing = write_bundle(tmp_path / "missing")
    (missing.parent / "empty-demo.journal.jsonl").unlink()
    with pytest.raises(ReplayBundleError, match="missing or escapes"):
        verify_replay_bundle(missing)

    unsafe = write_bundle(tmp_path / "unsafe")
    document = json.loads(unsafe.read_text(encoding="utf-8"))
    document["artifacts"]["journal"]["path"] = "../outside.jsonl"
    unsafe.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ReplayBundleError, match="path is unsafe"):
        verify_replay_bundle(unsafe)


def test_bundle_verification_rejects_malformed_manifests_and_relationships(
    tmp_path: Path,
) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(ReplayBundleError, match="exactly one"):
        verify_replay_bundle(empty)
    write_bundle(empty)
    (empty / "second.manifest.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ReplayBundleError, match="exactly one"):
        verify_replay_bundle(empty)
    with pytest.raises(ReplayBundleError, match="does not exist"):
        verify_replay_bundle(tmp_path / "absent.manifest.json")

    invalid_json = write_bundle(tmp_path / "invalid-json")
    invalid_json.write_text("{", encoding="utf-8")
    with pytest.raises(ReplayBundleError, match="not valid JSON"):
        verify_replay_bundle(invalid_json)

    duplicate = write_bundle(tmp_path / "duplicate")
    duplicate.write_text('{"run_id":"a","run_id":"b"}', encoding="utf-8")
    with pytest.raises(ReplayBundleError, match="duplicate JSON field"):
        verify_replay_bundle(duplicate)

    non_object = write_bundle(tmp_path / "non-object")
    non_object.write_text("[]", encoding="utf-8")
    with pytest.raises(ReplayBundleError, match="must be an object"):
        verify_replay_bundle(non_object)

    empty_run = write_bundle(tmp_path / "empty-run")
    document = manifest_document(empty_run)
    document["run_id"] = ""
    write_manifest(empty_run, document)
    with pytest.raises(ReplayBundleError, match="nonempty string"):
        verify_replay_bundle(empty_run)

    invalid_array = write_bundle(tmp_path / "invalid-array")
    document = manifest_document(invalid_array)
    document["engine"]["capabilities"]["execution_models"] = "completed_bar_v1"
    write_manifest(invalid_array, document)
    with pytest.raises(ReplayBundleError, match="must be an array"):
        verify_replay_bundle(invalid_array)

    extra = write_bundle(tmp_path / "extra")
    document = manifest_document(extra)
    extra_file = extra.parent / "extra.txt"
    extra_file.write_text("extra", encoding="utf-8")
    document["artifacts"]["extra"] = {
        "path": extra_file.name,
        "sha256": sha256(extra_file),
    }
    write_manifest(extra, document)
    with pytest.raises(ReplayBundleError, match="scenario and journal only"):
        verify_replay_bundle(extra)

    unsupported = write_bundle(tmp_path / "unsupported")
    document = manifest_document(unsupported)
    document["artifacts"]["scenario"]["format"] = "yaml"
    write_manifest(unsupported, document)
    with pytest.raises(ReplayBundleError, match="format is unsupported"):
        verify_replay_bundle(unsupported)

    bad_digest = write_bundle(tmp_path / "bad-digest")
    document = manifest_document(bad_digest)
    document["artifacts"]["journal"]["sha256"] = "invalid"
    write_manifest(bad_digest, document)
    with pytest.raises(ReplayBundleError, match="lowercase SHA-256"):
        verify_replay_bundle(bad_digest)

    directory_artifact = write_bundle(tmp_path / "directory-artifact")
    document = manifest_document(directory_artifact)
    artifact_directory = directory_artifact.parent / "artifact-directory"
    artifact_directory.mkdir()
    document["artifacts"]["journal"] = {
        "path": artifact_directory.name,
        "sha256": "0" * 64,
    }
    write_manifest(directory_artifact, document)
    with pytest.raises(ReplayBundleError, match="not a regular file"):
        verify_replay_bundle(directory_artifact)


def test_bundle_verification_rejects_scenario_journal_and_capability_drift(
    tmp_path: Path,
) -> None:
    invalid_scenario = write_bundle(tmp_path / "invalid-scenario")
    document = manifest_document(invalid_scenario)
    scenario_path = invalid_scenario.parent / "empty-demo.scenario.json"
    scenario_path.write_text("{", encoding="utf-8")
    document["artifacts"]["scenario"]["sha256"] = sha256(scenario_path)
    write_manifest(invalid_scenario, document)
    with pytest.raises(ReplayBundleError, match="scenario reconciliation failed"):
        verify_replay_bundle(invalid_scenario)

    relationships = (
        ("run", "run_id", "other-run", "scenario run_id differs"),
        ("metadata", "scenario_metadata", {"other": True}, "metadata differs"),
    )
    for directory, key, value, message in relationships:
        manifest = write_bundle(tmp_path / directory)
        document = manifest_document(manifest)
        document[key] = value
        write_manifest(manifest, document)
        with pytest.raises(ReplayBundleError, match=message):
            verify_replay_bundle(manifest)

    contract = write_bundle(tmp_path / "contract")
    document = manifest_document(contract)
    document["contract"]["version"] = "4"
    capabilities = document["engine"]["capabilities"]
    capabilities["scenario_contract_versions"] = ["4"]
    capabilities["journal_contract_versions"] = ["4"]
    write_manifest(contract, document)
    with pytest.raises(ReplayBundleError, match="scenario contract version differs"):
        verify_replay_bundle(contract)

    model = write_bundle(tmp_path / "model")
    document = manifest_document(model)
    document["execution"]["model"] = "other_model"
    document["engine"]["capabilities"]["execution_models"] = ["other_model"]
    write_manifest(model, document)
    with pytest.raises(ReplayBundleError, match="scenario execution model differs"):
        verify_replay_bundle(model)

    strategy = write_bundle(tmp_path / "strategy")
    document = manifest_document(strategy)
    document["strategy"] = {}
    write_manifest(strategy, document)
    with pytest.raises(ReplayBundleError, match="requires a strategy transcript"):
        verify_replay_bundle(strategy)

    capability_version = write_bundle(tmp_path / "capability-version")
    document = manifest_document(capability_version)
    document["engine"]["capabilities"]["engine_version"] = "other-engine"
    write_manifest(capability_version, document)
    with pytest.raises(ReplayBundleError, match="capability version differs"):
        verify_replay_bundle(capability_version)

    capability_claim = write_bundle(tmp_path / "capability-claim")
    document = manifest_document(capability_claim)
    document["engine"]["capabilities"]["execution_models"] = ["other_model"]
    write_manifest(capability_claim, document)
    with pytest.raises(ReplayBundleError, match="do not advertise"):
        verify_replay_bundle(capability_claim)

    invalid_journal = write_bundle(tmp_path / "invalid-journal")
    document = manifest_document(invalid_journal)
    journal_path = invalid_journal.parent / "empty-demo.journal.jsonl"
    journal_path.write_text("{}\n", encoding="utf-8")
    document["artifacts"]["journal"]["sha256"] = sha256(journal_path)
    write_manifest(invalid_journal, document)
    with pytest.raises(ReplayBundleError, match="journal reconciliation failed"):
        verify_replay_bundle(invalid_journal)


def test_bundle_comparison_separates_inputs_outputs_and_first_divergence(
    tmp_path: Path,
) -> None:
    left = write_bundle(tmp_path / "left")
    same = write_bundle(tmp_path / "same")
    changed_input = write_bundle(tmp_path / "input", metadata={"variant": "b"})
    changed_output = write_bundle(tmp_path / "output", initial_cash="10001")

    identical = compare_replay_bundles(left, same)
    input_difference = compare_replay_bundles(left, changed_input)
    output_difference = compare_replay_bundles(left, changed_output)

    assert identical.identical
    assert identical.to_dict()["status"] == "identical"
    assert input_difference.input_changes == ("scenario",)
    assert input_difference.output_changes == ()
    assert input_difference.first_divergence == "input:scenario"
    assert output_difference.input_changes == ("scenario",)
    assert output_difference.output_changes == ("completion",)
    assert output_difference.first_divergence == "completion"

    tampered = write_bundle(tmp_path / "tampered-comparison")
    journal = tampered.parent / "empty-demo.journal.jsonl"
    journal.write_text(journal.read_text(encoding="utf-8") + "{}\n", encoding="utf-8")
    with pytest.raises(ReplayBundleError, match="checksum differs"):
        compare_replay_bundles(left, tampered)


def test_bundle_comparison_reports_frame_fee_and_aggregate_differences(
    tmp_path: Path,
) -> None:
    verified = verify_replay_bundle(write_bundle(tmp_path / "bundle"))
    left_replay = replace(
        verified.replay,
        orders=pd.DataFrame({"order_id": ["order-a"], "quantity": [1]}),
        fills=pd.DataFrame({"fill_id": ["fill-a"], "fee_micros": [10]}),
        valuations=pd.DataFrame({"equity": [10_000.0]}),
        metrics=pd.DataFrame({"metric_name": ["score"], "value": [1.0]}),
    )
    right_replay = replace(
        left_replay,
        orders=pd.DataFrame({"order_id": ["order-a"], "quantity": [2]}),
        fills=pd.DataFrame({"fill_id": ["fill-a"], "fee_micros": [20]}),
        valuations=pd.DataFrame({"equity": [10_001.0]}),
        metrics=pd.DataFrame({"metric_name": ["score"], "value": [2.0]}),
        completion=replace(
            left_replay.completion,
            execution_fees_micros=20,
            total_fees_micros=20,
        ),
    )

    comparison = compare_replay_bundles(
        replace(verified, replay=left_replay),
        replace(verified, replay=right_replay),
    )

    assert comparison.output_changes == (
        "orders",
        "fills",
        "fees",
        "valuations",
        "metrics",
        "completion",
    )
    assert comparison.first_divergence == "orders[order_id=order-a]"
    assert comparison.aggregate_differences["orders"]["quantity_delta"] == 1.0
    assert comparison.aggregate_differences["fees"]["total_fees_micros_delta"] == 20


def test_bundle_comparison_reports_strategy_decision_divergence(tmp_path: Path) -> None:
    verified = verify_replay_bundle(write_bundle(tmp_path / "bundle"))
    left = replace(
        verified,
        transcript=cast("StrategyTranscript", SimpleNamespace(decisions=("decision-a",))),
    )
    changed = replace(
        verified,
        transcript=cast("StrategyTranscript", SimpleNamespace(decisions=("decision-b",))),
    )
    extended = replace(
        verified,
        transcript=cast(
            "StrategyTranscript",
            SimpleNamespace(decisions=("decision-a", "decision-b")),
        ),
    )

    changed_comparison = compare_replay_bundles(left, changed)
    extended_comparison = compare_replay_bundles(left, extended)

    assert changed_comparison.output_changes == ("decisions",)
    assert changed_comparison.first_divergence == "decisions[0]"
    assert extended_comparison.first_divergence == "decisions[1]"


def test_bundle_cli_reports_human_and_machine_status(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    left = write_bundle(tmp_path / "left")
    same = write_bundle(tmp_path / "same")
    changed = write_bundle(tmp_path / "changed", metadata={"variant": "b"})

    assert _cli.run(["trading-engine", "bundle", "verify", str(left.parent)]) == 0
    assert "Verified replay bundle empty-demo" in capsys.readouterr().out
    assert _cli.run(["trading-engine", "bundle", "compare", str(left), str(same), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["identical"] is True
    assert _cli.run(["trading-engine", "bundle", "compare", str(left), str(changed)]) == 1
    assert "inputs [scenario]" in capsys.readouterr().out
