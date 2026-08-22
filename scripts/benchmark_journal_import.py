"""Measure Trading Engine journal parsing or complete import memory and throughput."""

from __future__ import annotations

import argparse
import json
import time
import tracemalloc
from pathlib import Path

from persistra.integrations.trading_engine import read_journal
from persistra.integrations.trading_engine._journal_parsing import iter_json_records


def main() -> None:
    """Run one explicit benchmark against a retained representative journal."""
    parser = argparse.ArgumentParser()
    parser.add_argument("journal", type=Path)
    parser.add_argument("--scenario", type=Path)
    parser.add_argument("--mode", choices=("parse", "import"), default="import")
    arguments = parser.parse_args()

    tracemalloc.start()
    started = time.perf_counter()
    if arguments.mode == "parse":
        record_count = sum(1 for _line, _record in iter_json_records(arguments.journal))
    else:
        replay = read_journal(arguments.journal, scenario=arguments.scenario)
        record_count = len(replay.events)
    elapsed = time.perf_counter() - started
    _current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    print(
        json.dumps(
            {
                "elapsed_seconds": elapsed,
                "journal_bytes": arguments.journal.stat().st_size,
                "mode": arguments.mode,
                "peak_traced_bytes": peak,
                "record_count": record_count,
                "records_per_second": record_count / elapsed,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
