"""Portable, resumable plans for sequential normalized-data acquisition."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, cast

from persistra._files import atomic_write_bytes
from persistra._portable import freeze_portable_mapping, thaw_portable_mapping
from persistra.errors import DataValidationError
from persistra.model import (
    BarSet,
    CommoditySpotQuote,
    ExchangeRateQuote,
    IndexCatalogResult,
    InstrumentSearchResult,
    MarketStatusResult,
    OptionChain,
    QuoteSet,
    SeriesSet,
    TopOfBookSet,
    VintageDatesResult,
    VintageSeriesSet,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from persistra.data.store import DuckDBStore, StoredResult


class AcquisitionCachePolicy(StrEnum):
    """Caller-declared network and raw-cache policy for one request."""

    DEFAULT = "default"
    REFRESH = "refresh"
    OFFLINE = "offline"


class AcquisitionFamily(StrEnum):
    """Normalized result families that an acquisition request can require."""

    BARS = "bars"
    COMMODITY_SPOT = "commodity_spot"
    EXCHANGE_RATE = "exchange_rate"
    INDEX_CATALOG = "index_catalog"
    MARKET_STATUS = "market_status"
    OPTIONS = "options"
    QUOTES = "quotes"
    SEARCH = "search"
    SERIES = "series"
    TOP_OF_BOOK = "top_of_book"
    VINTAGE_DATES = "vintage_dates"
    VINTAGE_SERIES = "vintage_series"


@dataclass(frozen=True, slots=True)
class AcquisitionRequest:
    """One portable provider operation with explicit scope and output contract."""

    request_id: str
    provider: str
    operation: str
    scope: Mapping[str, Any]
    parameters: Mapping[str, Any]
    cache_policy: AcquisitionCachePolicy
    expected_family: AcquisitionFamily

    def __post_init__(self) -> None:
        for name in ("request_id", "provider", "operation"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must not be empty")
        if not isinstance(cast("object", self.cache_policy), AcquisitionCachePolicy):
            raise ValueError("cache_policy must be an AcquisitionCachePolicy")
        if not isinstance(cast("object", self.expected_family), AcquisitionFamily):
            raise ValueError("expected_family must be an AcquisitionFamily")
        object.__setattr__(
            self,
            "scope",
            freeze_portable_mapping(self.scope, name="acquisition scope", redact_api_keys=True),
        )
        object.__setattr__(
            self,
            "parameters",
            freeze_portable_mapping(
                self.parameters,
                name="acquisition parameters",
                redact_api_keys=True,
            ),
        )
        if "refresh" in self.parameters or "offline" in self.parameters:
            raise ValueError("refresh and offline must be declared through cache_policy")

    @property
    def call_parameters(self) -> Mapping[str, Any]:
        """Return provider parameters with the declared cache flags applied."""
        parameters = thaw_portable_mapping(self.parameters)
        parameters["refresh"] = self.cache_policy is AcquisitionCachePolicy.REFRESH
        parameters["offline"] = self.cache_policy is AcquisitionCachePolicy.OFFLINE
        return MappingProxyType(parameters)


@dataclass(frozen=True, slots=True)
class AcquisitionPlan:
    """A versioned ordered collection of portable acquisition requests."""

    plan_id: str
    requests: tuple[AcquisitionRequest, ...]
    format_version: int = 1

    def __post_init__(self) -> None:
        if not isinstance(cast("object", self.plan_id), str) or not self.plan_id.strip():
            raise ValueError("plan_id must not be empty")
        if isinstance(cast("object", self.format_version), bool) or self.format_version != 1:
            raise ValueError("unsupported acquisition plan format version")
        requests = tuple(self.requests)
        if not requests:
            raise ValueError("acquisition plan must contain at least one request")
        identifiers = [request.request_id for request in requests]
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("acquisition request identifiers must be unique")
        object.__setattr__(self, "requests", requests)


@dataclass(frozen=True, slots=True)
class AcquisitionSuccess:
    """One successfully completed and durably checkpointed request."""

    request_id: str
    family: AcquisitionFamily
    completed_at: datetime
    retrieved_at: datetime
    snapshot_id: str | None

    def __post_init__(self) -> None:
        if not isinstance(cast("object", self.request_id), str) or not self.request_id.strip():
            raise ValueError("request_id must not be empty")
        if not isinstance(cast("object", self.family), AcquisitionFamily):
            raise ValueError("family must be an AcquisitionFamily")
        if (
            not isinstance(cast("object", self.completed_at), datetime)
            or not isinstance(cast("object", self.retrieved_at), datetime)
            or self.completed_at.tzinfo is None
            or self.retrieved_at.tzinfo is None
        ):
            raise ValueError("acquisition success timestamps must be timezone-aware")
        if self.completed_at < self.retrieved_at:
            raise ValueError("completed_at must not precede retrieved_at")
        if self.snapshot_id is not None and (
            not isinstance(cast("object", self.snapshot_id), str) or not self.snapshot_id.strip()
        ):
            raise ValueError("snapshot_id must not be empty")


@dataclass(frozen=True, slots=True)
class AcquisitionFailure:
    """One request failure retained in the explicit run report."""

    request_id: str
    error_type: str
    message: str


@dataclass(frozen=True, slots=True)
class AcquisitionReport:
    """Completeness report for one plan execution or resume attempt."""

    plan_id: str
    plan_sha256: str
    started_at: datetime
    finished_at: datetime
    successes: tuple[AcquisitionSuccess, ...]
    resumed_request_ids: tuple[str, ...]
    failures: tuple[AcquisitionFailure, ...]
    manifest_path: Path | None
    total_requests: int

    @property
    def is_complete(self) -> bool:
        """Return whether every declared request has a durable success checkpoint."""
        return len(self.successes) == self.total_requests and not self.failures


type AcquisitionHandler = Callable[[AcquisitionRequest], StoredResult]


class AcquisitionRunner:
    """Execute a portable plan sequentially with durable success checkpoints."""

    def __init__(
        self,
        handlers: Mapping[tuple[str, str], AcquisitionHandler],
        checkpoint_path: str | Path,
        *,
        store: DuckDBStore | None = None,
        manifest_path: str | Path | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._handlers = dict(handlers)
        self._checkpoint_path = Path(checkpoint_path)
        self._store = store
        self._manifest_path = None if manifest_path is None else Path(manifest_path)
        self._clock = clock or (lambda: datetime.now(UTC))

    def run(self, plan: AcquisitionPlan) -> AcquisitionReport:
        """Run pending requests in plan order and return explicit completeness."""
        started_at = self._now()
        plan_document = _plan_dictionary(plan)
        plan_hash = _document_hash(plan_document)
        successes = _read_checkpoint(self._checkpoint_path, plan, plan_hash)
        successes = _successes_retained_by_store(successes, self._store)
        resumed = tuple(
            request.request_id for request in plan.requests if request.request_id in successes
        )
        failures: list[AcquisitionFailure] = []
        for request in plan.requests:
            if request.request_id in successes:
                continue
            handler = self._handlers.get((request.provider, request.operation))
            if handler is None:
                failures.append(
                    AcquisitionFailure(
                        request.request_id,
                        "LookupError",
                        f"no handler for {request.provider}:{request.operation}",
                    )
                )
                continue
            try:
                result = handler(request)
                family = _result_family(result)
                if family is not request.expected_family:
                    raise DataValidationError(
                        f"expected {request.expected_family.value}, received {family.value}"
                    )
                snapshot_id = None if self._store is None else self._store.save(result)
                success = AcquisitionSuccess(
                    request.request_id,
                    family,
                    max(self._now(), result.metadata.retrieved_at.astimezone(UTC)),
                    result.metadata.retrieved_at,
                    snapshot_id,
                )
                updated = {**successes, request.request_id: success}
                _write_checkpoint(self._checkpoint_path, plan, plan_hash, updated)
                successes = updated
            except Exception as error:
                failures.append(
                    AcquisitionFailure(request.request_id, type(error).__name__, str(error))
                )
        finished_at = self._now()
        if successes:
            finished_at = max(
                finished_at,
                *(success.completed_at for success in successes.values()),
            )
        ordered = tuple(
            successes[request.request_id]
            for request in plan.requests
            if request.request_id in successes
        )
        report = AcquisitionReport(
            plan.plan_id,
            plan_hash,
            started_at,
            finished_at,
            ordered,
            resumed,
            tuple(failures),
            self._manifest_path,
            len(plan.requests),
        )
        if self._manifest_path is not None:
            _write_manifest(self._manifest_path, plan_document, report)
        return report

    def _now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None:
            raise ValueError("acquisition clock must return a timezone-aware datetime")
        return value.astimezone(UTC)


def acquisition_plan_to_json(plan: AcquisitionPlan, *, indent: int | None = 2) -> str:
    """Serialize a complete acquisition plan as stable portable JSON."""
    return (
        json.dumps(
            _plan_dictionary(plan),
            sort_keys=True,
            indent=indent,
            separators=(",", ":") if indent is None else None,
        )
        + "\n"
    )


def acquisition_plan_from_json(document: str) -> AcquisitionPlan:
    """Parse and strictly validate one versioned acquisition plan."""
    payload = _object_mapping(json.loads(document), name="acquisition plan")
    if set(payload) != {"format_version", "plan_id", "requests"}:
        raise ValueError("acquisition plan fields differ from the version 1 schema")
    raw_requests = payload["requests"]
    if not isinstance(raw_requests, list):
        raise ValueError("acquisition plan requests must be a list")
    request_items = cast("list[object]", raw_requests)
    requests: list[AcquisitionRequest] = []
    expected = {
        "request_id",
        "provider",
        "operation",
        "scope",
        "parameters",
        "cache_policy",
        "expected_family",
    }
    for item in request_items:
        raw = _object_mapping(item, name="acquisition request")
        if set(raw) != expected:
            raise ValueError("acquisition request fields differ from the version 1 schema")
        requests.append(
            AcquisitionRequest(
                request_id=_text(raw["request_id"], name="request_id"),
                provider=_text(raw["provider"], name="provider"),
                operation=_text(raw["operation"], name="operation"),
                scope=_object_mapping(raw["scope"], name="scope"),
                parameters=_object_mapping(raw["parameters"], name="parameters"),
                cache_policy=AcquisitionCachePolicy(
                    _text(raw["cache_policy"], name="cache_policy")
                ),
                expected_family=AcquisitionFamily(
                    _text(raw["expected_family"], name="expected_family")
                ),
            )
        )
    version = payload["format_version"]
    if isinstance(version, bool) or not isinstance(version, int):
        raise ValueError("acquisition plan format_version must be an integer")
    return AcquisitionPlan(_text(payload["plan_id"], name="plan_id"), tuple(requests), version)


def _plan_dictionary(plan: AcquisitionPlan) -> dict[str, Any]:
    return {
        "format_version": plan.format_version,
        "plan_id": plan.plan_id,
        "requests": [
            {
                "request_id": request.request_id,
                "provider": request.provider,
                "operation": request.operation,
                "scope": thaw_portable_mapping(request.scope),
                "parameters": thaw_portable_mapping(request.parameters),
                "cache_policy": request.cache_policy.value,
                "expected_family": request.expected_family.value,
            }
            for request in plan.requests
        ],
    }


def _document_hash(document: Mapping[str, Any]) -> str:
    encoded = json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
    return sha256(encoded).hexdigest()


def _read_checkpoint(
    path: Path, plan: AcquisitionPlan, plan_hash: str
) -> dict[str, AcquisitionSuccess]:
    try:
        loaded: object = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, json.JSONDecodeError) as error:
        raise DataValidationError(f"acquisition checkpoint is unreadable: {error}") from error
    try:
        payload = _object_mapping(loaded, name="acquisition checkpoint")
    except ValueError as error:
        raise DataValidationError(str(error)) from error
    if set(payload) != {
        "format_version",
        "plan_id",
        "plan_sha256",
        "successes",
    }:
        raise DataValidationError("acquisition checkpoint schema is invalid")
    if payload["format_version"] != 1:
        raise DataValidationError("acquisition checkpoint version is unsupported")
    if payload["plan_id"] != plan.plan_id or payload["plan_sha256"] != plan_hash:
        raise DataValidationError("acquisition checkpoint belongs to a different plan")
    raw_successes = payload["successes"]
    if not isinstance(raw_successes, list):
        raise DataValidationError("acquisition checkpoint successes must be a list")
    success_items = cast("list[object]", raw_successes)
    allowed = {request.request_id for request in plan.requests}
    expected_families = {request.request_id: request.expected_family for request in plan.requests}
    successes: dict[str, AcquisitionSuccess] = {}
    for item in success_items:
        try:
            raw = _object_mapping(item, name="checkpoint success")
            if set(raw) != {
                "request_id",
                "family",
                "completed_at",
                "retrieved_at",
                "snapshot_id",
            }:
                raise ValueError("success fields are invalid")
            success = AcquisitionSuccess(
                _text(raw["request_id"], name="request_id"),
                AcquisitionFamily(_text(raw["family"], name="family")),
                datetime.fromisoformat(_text(raw["completed_at"], name="completed_at")),
                datetime.fromisoformat(_text(raw["retrieved_at"], name="retrieved_at")),
                _optional_text(raw["snapshot_id"], name="snapshot_id"),
            )
        except (TypeError, ValueError) as error:
            raise DataValidationError(
                f"acquisition checkpoint success is invalid: {error}"
            ) from error
        if success.request_id not in allowed or success.request_id in successes:
            raise DataValidationError("acquisition checkpoint request identity is invalid")
        if success.family is not expected_families[success.request_id]:
            raise DataValidationError("acquisition checkpoint result family is invalid")
        if success.completed_at.tzinfo is None or success.retrieved_at.tzinfo is None:
            raise DataValidationError("acquisition checkpoint timestamps must be timezone-aware")
        successes[success.request_id] = success
    return successes


def _write_checkpoint(
    path: Path,
    plan: AcquisitionPlan,
    plan_hash: str,
    successes: Mapping[str, AcquisitionSuccess],
) -> None:
    payload = {
        "format_version": 1,
        "plan_id": plan.plan_id,
        "plan_sha256": plan_hash,
        "successes": [
            _success_dictionary(successes[request.request_id])
            for request in plan.requests
            if request.request_id in successes
        ],
    }
    _write_json(path, payload)


def _successes_retained_by_store(
    successes: Mapping[str, AcquisitionSuccess], store: DuckDBStore | None
) -> dict[str, AcquisitionSuccess]:
    if store is None:
        return dict(successes)
    retained: dict[str, AcquisitionSuccess] = {}
    for request_id, success in successes.items():
        if success.snapshot_id is None:
            continue
        result = store.load_snapshot(success.snapshot_id)
        if result is not None and _result_family(result) is success.family:
            retained[request_id] = success
    return retained


def _write_manifest(
    path: Path, plan_document: Mapping[str, Any], report: AcquisitionReport
) -> None:
    payload = {
        "manifest_version": 1,
        "plan": plan_document,
        "plan_sha256": report.plan_sha256,
        "execution": {
            "started_at": report.started_at.isoformat(),
            "finished_at": report.finished_at.isoformat(),
            "is_complete": report.is_complete,
            "total_requests": report.total_requests,
            "resumed_request_ids": list(report.resumed_request_ids),
            "successes": [_success_dictionary(success) for success in report.successes],
            "failures": [
                {
                    "request_id": failure.request_id,
                    "error_type": failure.error_type,
                    "message": failure.message,
                }
                for failure in report.failures
            ],
        },
    }
    _write_json(path, payload)


def _success_dictionary(success: AcquisitionSuccess) -> dict[str, Any]:
    return {
        "request_id": success.request_id,
        "family": success.family.value,
        "completed_at": success.completed_at.isoformat(),
        "retrieved_at": success.retrieved_at.isoformat(),
        "snapshot_id": success.snapshot_id,
    }


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    document = (json.dumps(payload, sort_keys=True, indent=2) + "\n").encode()
    atomic_write_bytes(path, document, overwrite=True)


def _result_family(result: StoredResult) -> AcquisitionFamily:
    value = cast("object", result)
    families: tuple[tuple[type[Any], AcquisitionFamily], ...] = (
        (BarSet, AcquisitionFamily.BARS),
        (QuoteSet, AcquisitionFamily.QUOTES),
        (TopOfBookSet, AcquisitionFamily.TOP_OF_BOOK),
        (OptionChain, AcquisitionFamily.OPTIONS),
        (SeriesSet, AcquisitionFamily.SERIES),
        (VintageSeriesSet, AcquisitionFamily.VINTAGE_SERIES),
        (VintageDatesResult, AcquisitionFamily.VINTAGE_DATES),
        (ExchangeRateQuote, AcquisitionFamily.EXCHANGE_RATE),
        (CommoditySpotQuote, AcquisitionFamily.COMMODITY_SPOT),
        (InstrumentSearchResult, AcquisitionFamily.SEARCH),
        (MarketStatusResult, AcquisitionFamily.MARKET_STATUS),
        (IndexCatalogResult, AcquisitionFamily.INDEX_CATALOG),
    )
    for result_type, family in families:
        if isinstance(value, result_type):
            return family
    raise DataValidationError(f"unsupported acquisition result: {type(result).__name__}")


def _object_mapping(value: object, *, name: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be a JSON object")
    mapping = cast("dict[object, object]", value)
    if any(not isinstance(key, str) for key in mapping):
        raise ValueError(f"{name} keys must be strings")
    return cast("dict[str, object]", mapping)


def _text(value: object, *, name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be text")
    return value


def _optional_text(value: object, *, name: str) -> str | None:
    if value is None or isinstance(value, str):
        return value
    raise ValueError(f"{name} must be text or null")
