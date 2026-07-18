"""Independently validate the current research-database structural contract."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from persistra import Project
from persistra.db.connection import ManagedConnection, inspect_database
from persistra.db.migrations import CURRENT_SCHEMA_VERSION

_REQUIRED_TABLES = frozenset(
    {
        "analysis.validation_plans",
        "experiments.attempts",
        "experiments.objective_observations",
        "experiments.progress_events",
        "experiments.run_plans",
        "experiments.worker_assignments",
        "result_data.equity",
        "result_data.fills",
        "result_data.logs",
        "result_data.orders",
        "results.run_records",
        "simulation.event_runs",
        "simulation.vectorized_runs",
    }
)


def main() -> None:
    """Create schema head and validate version, migration ledger, and core topology."""
    with TemporaryDirectory(prefix="persistra-schema-check-") as temporary:
        layout = Project.init(Path(temporary) / "project")
        if layout.research_database_path is None:
            raise SystemExit("schema check did not create a research database")
        connection = ManagedConnection(layout.research_database_path, read_only=True)
        try:
            metadata = inspect_database(connection)
            migration_numbers = [
                int(row[0])
                for row in connection.execute(
                    "SELECT migration_number FROM _persistra.schema_migrations "
                    "ORDER BY migration_number"
                ).fetchall()
            ]
            tables = {
                f"{row[0]}.{row[1]}"
                for row in connection.execute(
                    "SELECT table_schema, table_name FROM information_schema.tables"
                ).fetchall()
            }
        finally:
            connection.close()
    if metadata.schema_version != CURRENT_SCHEMA_VERSION:
        raise SystemExit("created database is not at schema head")
    if migration_numbers != list(range(1, CURRENT_SCHEMA_VERSION + 1)):
        raise SystemExit("schema migration ledger is not contiguous")
    missing = sorted(_REQUIRED_TABLES - tables)
    if missing:
        raise SystemExit(f"current schema is missing core tables: {', '.join(missing)}")


if __name__ == "__main__":
    main()
