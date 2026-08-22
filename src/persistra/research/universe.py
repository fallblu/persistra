"""Point-in-time investable-universe membership and panel alignment."""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
from typing import TYPE_CHECKING, Any, cast

import pandas as pd

from persistra.research._validation import calendar_index
from persistra.research.model import DatasetScope

if TYPE_CHECKING:
    from collections.abc import Sequence


UNIVERSE_COLUMNS = (
    "asset_id",
    "valid_from",
    "valid_through",
    "state",
    "source",
    "source_as_of",
    "retrieved_at",
)


class InclusionState(StrEnum):
    """Declared membership state during one effective interval."""

    INCLUDED = "included"
    EXCLUDED = "excluded"
    DELISTED = "delisted"


class MissingMembershipPolicy(StrEnum):
    """Behavior when no interval covers an asset and date."""

    ERROR = "error"
    EXCLUDE = "exclude"


class DelistingPolicy(StrEnum):
    """Behavior when a covering interval declares an asset delisted."""

    ERROR = "error"
    EXCLUDE = "exclude"


@dataclass(frozen=True, slots=True)
class UniverseMembership:
    """Immutable dated membership intervals with source provenance."""

    universe_id: str
    frame: pd.DataFrame

    def __post_init__(self) -> None:
        if not isinstance(cast("object", self.universe_id), str) or not self.universe_id.strip():
            raise ValueError("universe_id must not be empty")
        frame = self.frame.copy(deep=True).reset_index(drop=True)
        if tuple(frame.columns) != UNIVERSE_COLUMNS:
            raise ValueError("universe membership columns differ from the contract")
        if frame.empty:
            raise ValueError("universe membership must contain at least one interval")
        for column in ("asset_id", "state", "source"):
            frame[column] = frame[column].astype("string")
            if frame[column].isna().any() or frame[column].str.strip().eq("").any():
                raise ValueError(f"universe {column} must contain nonempty text")
        for column in ("valid_from", "valid_through", "source_as_of"):
            frame[column] = pd.to_datetime(frame[column], errors="raise")
            values = pd.DatetimeIndex(frame[column].dropna())
            if values.tz is not None or not values.equals(values.normalize()):
                raise ValueError(f"universe {column} must contain timezone-naive dates")
        frame["retrieved_at"] = pd.to_datetime(frame["retrieved_at"], utc=True, errors="raise")
        if (
            frame["valid_from"].isna().any()
            or frame["source_as_of"].isna().any()
            or frame["retrieved_at"].isna().any()
        ):
            raise ValueError("valid_from, source_as_of, and retrieved_at must not be missing")
        states = set(frame["state"].tolist())
        supported = {state.value for state in InclusionState}
        if not states.issubset(supported):
            raise ValueError(f"unsupported universe states: {sorted(states - supported)}")
        bounded = frame["valid_through"].notna()
        if (frame.loc[bounded, "valid_through"] < frame.loc[bounded, "valid_from"]).any():
            raise ValueError("universe intervals must not end before they start")
        frame = frame.sort_values(["asset_id", "valid_from"], kind="stable").reset_index(drop=True)
        for _asset, group in frame.groupby("asset_id", sort=False, observed=True):
            previous_end: pd.Timestamp | None = None
            rows = list(group.itertuples(index=False))
            for position, row in enumerate(rows):
                start = cast("pd.Timestamp", row.valid_from)
                if previous_end is not None and start <= previous_end:
                    raise ValueError("universe intervals must not overlap")
                end = row.valid_through
                if pd.isna(end):
                    if position != len(rows) - 1:
                        raise ValueError("an open universe interval must be last")
                else:
                    previous_end = cast("pd.Timestamp", end)
        object.__setattr__(self, "frame", frame)

    @property
    def content_identity(self) -> str:
        """Return a stable SHA-256 identity for normalized membership and provenance."""
        records = self.frame.assign(
            valid_from=self.frame["valid_from"].map(_isoformat),
            valid_through=self.frame["valid_through"].map(_optional_isoformat),
            source_as_of=self.frame["source_as_of"].map(_isoformat),
            retrieved_at=self.frame["retrieved_at"].map(_isoformat),
        ).to_dict(orient="records")
        document = json.dumps(records, sort_keys=True, separators=(",", ":"))
        return sha256(document.encode()).hexdigest()

    def dataset_scope(self, *, name: str = "investable_universe") -> DatasetScope:
        """Return the manifest dataset identity for this exact universe history."""
        return DatasetScope(
            name,
            {"universe_id": self.universe_id},
            "universe-membership-v1",
            content_identity=self.content_identity,
        )


def align_universe(
    universe: UniverseMembership,
    dates: pd.Index,
    assets: Sequence[str] | pd.Index,
    *,
    missing: MissingMembershipPolicy = MissingMembershipPolicy.ERROR,
    delistings: DelistingPolicy = DelistingPolicy.EXCLUDE,
) -> pd.DataFrame:
    """Return an exact date-by-asset membership mask without forward filling."""
    index = calendar_index(dates, name="universe alignment index")
    columns = pd.Index(list(assets))
    if (
        columns.hasnans
        or not columns.is_unique
        or any(not isinstance(cast("object", asset), str) or not asset for asset in columns)
    ):
        raise ValueError("universe alignment assets must be unique nonempty strings")
    if not isinstance(cast("object", missing), MissingMembershipPolicy):
        raise ValueError("missing must be a MissingMembershipPolicy")
    if not isinstance(cast("object", delistings), DelistingPolicy):
        raise ValueError("delistings must be a DelistingPolicy")
    mask = pd.DataFrame(False, index=index, columns=columns, dtype=bool)
    by_asset = {asset: group for asset, group in universe.frame.groupby("asset_id", sort=False)}
    for asset in columns:
        intervals = by_asset.get(asset)
        for date in index:
            matches = (
                None
                if intervals is None
                else intervals.loc[
                    intervals["valid_from"].le(date)
                    & (intervals["valid_through"].isna() | intervals["valid_through"].ge(date))
                ]
            )
            if matches is None or matches.empty:
                if missing is MissingMembershipPolicy.ERROR:
                    raise ValueError(f"membership is missing for {asset} on {date.date()}")
                continue
            state = InclusionState(str(matches.iloc[0]["state"]))
            if state is InclusionState.DELISTED and delistings is DelistingPolicy.ERROR:
                raise ValueError(f"{asset} is delisted on {date.date()}")
            mask.loc[date, asset] = state is InclusionState.INCLUDED
    return mask


def apply_universe(
    panel: pd.DataFrame,
    universe: UniverseMembership,
    *,
    missing: MissingMembershipPolicy = MissingMembershipPolicy.ERROR,
    delistings: DelistingPolicy = DelistingPolicy.EXCLUDE,
) -> pd.DataFrame:
    """Mask nonmembers in a feature, label, evaluation, or portfolio input panel."""
    mask = align_universe(
        universe,
        panel.index,
        panel.columns,
        missing=missing,
        delistings=delistings,
    )
    return panel.copy(deep=True).where(mask)


def _isoformat(value: Any) -> str:
    return pd.Timestamp(value).isoformat()


def _optional_isoformat(value: Any) -> str | None:
    return None if pd.isna(value) else pd.Timestamp(value).isoformat()
