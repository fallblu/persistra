"""Deterministic generator and measured runner for the v3 daily-equity benchmark."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb
import exchange_calendars as xcals  # pyright: ignore[reportMissingTypeStubs]

from persistra.domain.serialization import canonical_bytes

WORKLOAD = "persistra.benchmark.daily_equity_1000x10@1"
SEED = 20250300


@dataclass(frozen=True, slots=True)
class BenchmarkShape:
    instruments: int = 1_000
    start: str = "2015-01-02"
    end: str = "2024-12-31"

    def __post_init__(self) -> None:
        if self.instruments < 1 or self.start > self.end:
            raise ValueError("benchmark shape is invalid")


_DEFAULT_SHAPE = BenchmarkShape()


def draw(label: str, *parts: int | str) -> float:
    """Return the exact benchmark U draw in the open interval (0, 1)."""
    payload = canonical_bytes((SEED, WORKLOAD, label, *parts, 0))
    value = int.from_bytes(hashlib.sha256(payload).digest()[:8], "big")
    return (value + 0.5) / 2**64


def generate_fixture(
    path: Path, shape: BenchmarkShape = _DEFAULT_SHAPE
) -> dict[str, Any]:
    """Generate the immutable raw-bar fixture outside the measured boundary."""
    if path.exists():
        raise ValueError("benchmark fixture destination already exists")
    calendar = xcals.get_calendar("XNYS")
    sessions = calendar.sessions_in_range(shape.start, shape.end)
    connection = duckdb.connect(str(path))
    checksum = hashlib.sha256()
    row_count = 0
    try:
        connection.execute(
            "CREATE TABLE bars (session_ordinal INTEGER, decision_at TIMESTAMPTZ, "
            "instrument_ordinal INTEGER, sector INTEGER, close DOUBLE, volume BIGINT, "
            "PRIMARY KEY (session_ordinal, instrument_ordinal))"
        )
        batch: list[tuple[int, datetime, int, int, float, int]] = []
        closes = [20.0 + (ordinal % 180) for ordinal in range(1, shape.instruments + 1)]
        for session_ordinal, session in enumerate(sessions):
            instant = session.to_pydatetime().replace(tzinfo=UTC)
            common = 2 * draw("common", session_ordinal) - 1
            for index in range(shape.instruments):
                instrument = index + 1
                sector = index % 10
                shock = (
                    0.0002
                    + 0.004 * common
                    + 0.003 * (2 * draw("sector", sector, session_ordinal) - 1)
                    + 0.020 * (2 * draw("idio", instrument, session_ordinal) - 1)
                )
                close = round(closes[index] * math.exp(shock), 6)
                closes[index] = close
                volume = 100 * max(
                    1,
                    math.floor(
                        (
                            (10_000 + 200 * (instrument % 5_000))
                            * (0.5 + draw("volume", instrument, session_ordinal))
                        )
                        / 100
                    ),
                )
                row = (session_ordinal, instant, instrument, sector, close, volume)
                batch.append(row)
                checksum.update(
                    canonical_bytes(
                        (
                            session_ordinal,
                            instant,
                            instrument,
                            sector,
                            format(close, ".6f"),
                            volume,
                        )
                    )
                )
                row_count += 1
                if len(batch) == 100_000:
                    connection.executemany("INSERT INTO bars VALUES (?, ?, ?, ?, ?, ?)", batch)
                    batch.clear()
        if batch:
            connection.executemany("INSERT INTO bars VALUES (?, ?, ?, ?, ?, ?)", batch)
        connection.execute("CHECKPOINT")
    finally:
        connection.close()
    return {
        "schema": f"{WORKLOAD}.fixture@1",
        "instrument_count": shape.instruments,
        "session_count": len(sessions),
        "bar_count": row_count,
        "logical_root": f"sha256:{checksum.hexdigest()}",
    }


def run(fixture: Path, output: Path, manifest_path: Path) -> dict[str, Any]:
    """Execute the bounded feature/universe workload into a new output directory."""
    if not fixture.is_file() or output.exists():
        raise ValueError("benchmark paths are invalid or output is not new")
    expected = json.loads(manifest_path.read_text(encoding="utf-8"))
    if expected.get("schema") != f"{WORKLOAD}.manifest@1":
        raise ValueError("benchmark manifest schema is invalid")
    output.mkdir(parents=False)
    result_path = output / "result.duckdb"
    connection = duckdb.connect(str(result_path))
    try:
        escaped_fixture = str(fixture).replace("'", "''")
        connection.execute(
            f"ATTACH '{escaped_fixture}' AS fixture (READ_ONLY)"
        )
        connection.execute(
            """CREATE TABLE features AS
            SELECT *, close / lag(close) OVER entity - 1 AS return_1d,
              close / lag(close, 5) OVER entity - 1 AS return_5d,
              close / lag(close, 21) OVER entity - 1 AS momentum_21d,
              close / lag(close, 126) OVER entity - 1 AS momentum_126d_skip5,
              close / lag(close, 252) OVER entity - 1 AS momentum_252d_skip21,
              stddev_samp(ln(close / lag_close)) OVER recent21 * sqrt(252)
                AS realized_volatility_21d,
              stddev_samp(ln(close / lag_close)) OVER recent63 * sqrt(252)
                AS realized_volatility_63d,
              avg(close * volume) OVER recent21 AS mean_dollar_volume_21d
            FROM (
              SELECT *, lag(close) OVER entity AS lag_close FROM fixture.bars
              WINDOW entity AS (
                PARTITION BY instrument_ordinal ORDER BY session_ordinal
              )
            )
            WINDOW entity AS (
              PARTITION BY instrument_ordinal ORDER BY session_ordinal
            ), recent21 AS (
              PARTITION BY instrument_ordinal ORDER BY session_ordinal
              ROWS BETWEEN 20 PRECEDING AND CURRENT ROW
            ), recent63 AS (
              PARTITION BY instrument_ordinal ORDER BY session_ordinal
              ROWS BETWEEN 62 PRECEDING AND CURRENT ROW
            )"""
        )
        connection.execute(
            """CREATE TABLE decisions AS
            SELECT session_ordinal, instrument_ordinal,
              percent_rank() OVER (
                PARTITION BY session_ordinal ORDER BY momentum_126d_skip5
              ) AS cross_sectional_percentile_momentum_126,
              (momentum_126d_skip5 - avg(momentum_126d_skip5) OVER sector_window)
                / nullif(stddev_pop(momentum_126d_skip5) OVER sector_window, 0)
                AS sector_zscore_momentum_126
            FROM features
            WINDOW sector_window AS (
              PARTITION BY session_ordinal, sector
            )"""
        )
        feature_count = connection.execute(
            "SELECT count(*) FROM features"
        ).fetchone()
        decision_count = connection.execute(
            "SELECT count(*) FROM decisions"
        ).fetchone()
        if feature_count is None or decision_count is None:
            raise ValueError("benchmark output counts are unavailable")
        counts = {
            "feature_rows": int(feature_count[0]),
            "decision_rows": int(decision_count[0]),
        }
        connection.execute("CHECKPOINT")
    finally:
        connection.close()
    result = {"schema": f"{WORKLOAD}.result@1", **counts}
    (output / "result.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--generate", action="store_true")
    parser.add_argument("--instruments", type=int, default=1_000)
    parser.add_argument("--start", default="2015-01-02")
    parser.add_argument("--end", default="2024-12-31")
    arguments = parser.parse_args()
    if arguments.generate:
        print(json.dumps(generate_fixture(
            arguments.fixture,
            BenchmarkShape(arguments.instruments, arguments.start, arguments.end),
        ), sort_keys=True))
        return
    if arguments.output is None or arguments.manifest is None:
        parser.error("--output and --manifest are required for a measured run")
    print(json.dumps(run(arguments.fixture, arguments.output, arguments.manifest), sort_keys=True))


if __name__ == "__main__":
    main()
