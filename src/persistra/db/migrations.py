"""Immutable forward database migration registry."""

from __future__ import annotations

from dataclasses import dataclass

from persistra.domain import ContentId
from persistra.domain.serialization import canonical_bytes

CURRENT_SCHEMA_VERSION = 6
MINIMUM_MIGRATABLE_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class MigrationStep:
    number: int
    name: str
    source_version: int
    target_version: int
    statements: tuple[str, ...]
    market_statements: tuple[str, ...]
    research_statements: tuple[str, ...]
    checksum: str


def _step(
    number: int,
    name: str,
    source_version: int,
    target_version: int,
    statements: tuple[str, ...],
    market_statements: tuple[str, ...] = (),
    research_statements: tuple[str, ...] = (),
) -> MigrationStep:
    checksum = str(
        ContentId.from_bytes(
            canonical_bytes(
                {
                    "name": name,
                    "number": number,
                    "source_version": source_version,
                    "statements": statements,
                    "market_statements": market_statements,
                    "research_statements": research_statements,
                    "target_version": target_version,
                }
            )
        )
    )
    return MigrationStep(
        number,
        name,
        source_version,
        target_version,
        statements,
        market_statements,
        research_statements,
        checksum,
    )


MIGRATION_2 = _step(
    2,
    "operation_diagnostics",
    1,
    2,
    (
        """CREATE TABLE _persistra.operation_diagnostics (
            diagnostic_id UUID PRIMARY KEY,
            operation_name VARCHAR NOT NULL,
            outcome VARCHAR NOT NULL,
            evidence_json JSON NOT NULL,
            recorded_at TIMESTAMPTZ NOT NULL
        )""",
    ),
    (
        "ALTER TABLE catalog.batches ADD COLUMN expected_batch_content_id VARCHAR",
        "ALTER TABLE catalog.batches ADD COLUMN parent_batch_id UUID",
        """CREATE TABLE catalog.source_state (
            source_id UUID NOT NULL,
            source_version INTEGER NOT NULL,
            latest_catalog_sequence BIGINT NOT NULL,
            revision_count BIGINT NOT NULL,
            terminal_batch_count BIGINT NOT NULL,
            disposition_count BIGINT NOT NULL,
            validation_attempt_count BIGINT NOT NULL,
            finding_count BIGINT NOT NULL,
            state_content_id VARCHAR NOT NULL,
            PRIMARY KEY (source_id, source_version)
        )""",
        """CREATE TABLE catalog.dataset_state (
            dataset_id UUID NOT NULL,
            dataset_version INTEGER NOT NULL,
            latest_catalog_sequence BIGINT NOT NULL,
            revision_count BIGINT NOT NULL,
            terminal_batch_count BIGINT NOT NULL,
            disposition_count BIGINT NOT NULL,
            validation_attempt_count BIGINT NOT NULL,
            finding_count BIGINT NOT NULL,
            state_content_id VARCHAR NOT NULL,
            PRIMARY KEY (dataset_id, dataset_version)
        )""",
    ),
    (
        "ALTER TABLE {database}.research.composite_snapshot_members "
        "ADD COLUMN verified_copy_id UUID",
    ),
)

MIGRATION_3 = _step(
    3,
    "atomic_disposition_groups",
    2,
    3,
    (),
    (
        "ALTER TABLE catalog.batch_records ADD COLUMN disposition_group_id UUID",
        "ALTER TABLE catalog.record_dispositions ADD COLUMN disposition_group_id UUID",
        "ALTER TABLE quality.findings ADD COLUMN disposition_group_id UUID",
        "ALTER TABLE quality.quarantined_records ADD COLUMN disposition_group_id UUID",
    ),
)

MIGRATION_4 = _step(
    4,
    "daily_market_research_foundation",
    3,
    4,
    (),
    (
        """CREATE TABLE canonical.issuers (
            issuer_id UUID PRIMARY KEY,
            created_catalog_sequence BIGINT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL
        )""",
        """CREATE TABLE canonical.securities (
            security_id UUID PRIMARY KEY,
            issuer_id UUID NOT NULL,
            created_catalog_sequence BIGINT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL
        )""",
        """CREATE TABLE canonical.venues (
            venue_id UUID PRIMARY KEY,
            mic VARCHAR NOT NULL UNIQUE,
            timezone_name VARCHAR NOT NULL,
            created_catalog_sequence BIGINT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL
        )""",
        """CREATE TABLE canonical.listings (
            listing_id UUID PRIMARY KEY,
            security_id UUID NOT NULL,
            venue_id UUID NOT NULL,
            created_catalog_sequence BIGINT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL
        )""",
        """CREATE TABLE canonical.instruments (
            instrument_id UUID PRIMARY KEY,
            listing_id UUID NOT NULL UNIQUE,
            created_catalog_sequence BIGINT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL
        )""",
        """CREATE TABLE canonical.instrument_observations (
            observation_id UUID PRIMARY KEY,
            instrument_id UUID NOT NULL,
            security_kind VARCHAR NOT NULL,
            security_status VARCHAR NOT NULL,
            listing_status VARCHAR NOT NULL,
            currency VARCHAR NOT NULL,
            valid_from TIMESTAMPTZ NOT NULL,
            valid_to TIMESTAMPTZ,
            available_at TIMESTAMPTZ NOT NULL,
            ingested_at TIMESTAMPTZ NOT NULL,
            catalog_sequence BIGINT NOT NULL,
            content_id VARCHAR NOT NULL UNIQUE,
            CHECK (valid_to IS NULL OR valid_from < valid_to)
        )""",
        """CREATE TABLE canonical.identifier_namespaces (
            identifier_namespace_id UUID NOT NULL,
            namespace_version INTEGER NOT NULL,
            qualified_name VARCHAR NOT NULL,
            identifier_kind VARCHAR NOT NULL,
            entity_kind VARCHAR NOT NULL,
            case_sensitive BOOLEAN NOT NULL,
            venue_scoped BOOLEAN NOT NULL,
            definition_content_id VARCHAR NOT NULL UNIQUE,
            created_catalog_sequence BIGINT NOT NULL,
            PRIMARY KEY (identifier_namespace_id, namespace_version),
            UNIQUE (qualified_name, namespace_version)
        )""",
        """CREATE TABLE canonical.identifier_assignments (
            identifier_assignment_id UUID PRIMARY KEY,
            namespace_id UUID NOT NULL,
            namespace_version INTEGER NOT NULL,
            raw_value VARCHAR NOT NULL,
            normalized_value VARCHAR NOT NULL,
            entity_kind VARCHAR NOT NULL,
            entity_id UUID NOT NULL,
            venue_id UUID,
            is_primary BOOLEAN NOT NULL,
            valid_from TIMESTAMPTZ NOT NULL,
            valid_to TIMESTAMPTZ,
            available_at TIMESTAMPTZ NOT NULL,
            ingested_at TIMESTAMPTZ NOT NULL,
            catalog_sequence BIGINT NOT NULL,
            content_id VARCHAR NOT NULL UNIQUE,
            CHECK (valid_to IS NULL OR valid_from < valid_to)
        )""",
        """CREATE TABLE canonical.calendar_definitions (
            calendar_id UUID NOT NULL,
            calendar_version INTEGER NOT NULL,
            qualified_name VARCHAR NOT NULL,
            venue_id UUID NOT NULL,
            timezone_name VARCHAR NOT NULL,
            coverage_start DATE NOT NULL,
            coverage_end DATE NOT NULL,
            definition_content_id VARCHAR NOT NULL UNIQUE,
            schedule_root_content_id VARCHAR NOT NULL,
            created_catalog_sequence BIGINT NOT NULL,
            PRIMARY KEY (calendar_id, calendar_version),
            UNIQUE (qualified_name, calendar_version),
            CHECK (coverage_start < coverage_end)
        )""",
        """CREATE TABLE canonical.calendar_dates (
            calendar_id UUID NOT NULL,
            calendar_version INTEGER NOT NULL,
            calendar_date DATE NOT NULL,
            is_session BOOLEAN NOT NULL,
            open_at TIMESTAMPTZ,
            break_start_at TIMESTAMPTZ,
            break_end_at TIMESTAMPTZ,
            close_at TIMESTAMPTZ,
            is_early_close BOOLEAN NOT NULL,
            closure_reason VARCHAR,
            available_at TIMESTAMPTZ NOT NULL,
            catalog_sequence BIGINT NOT NULL,
            content_id VARCHAR NOT NULL,
            PRIMARY KEY (calendar_id, calendar_version, calendar_date)
        )""",
        """CREATE TABLE canonical.classification_schemes (
            classification_scheme_id UUID NOT NULL,
            scheme_version INTEGER NOT NULL,
            qualified_name VARCHAR NOT NULL,
            allows_multiple BOOLEAN NOT NULL,
            definition_content_id VARCHAR NOT NULL UNIQUE,
            created_catalog_sequence BIGINT NOT NULL,
            PRIMARY KEY (classification_scheme_id, scheme_version),
            UNIQUE (qualified_name, scheme_version)
        )""",
        """CREATE TABLE canonical.classification_nodes (
            classification_node_id UUID PRIMARY KEY,
            classification_scheme_id UUID NOT NULL,
            scheme_version INTEGER NOT NULL,
            code VARCHAR NOT NULL,
            display_name VARCHAR NOT NULL,
            parent_node_id UUID,
            valid_from TIMESTAMPTZ NOT NULL,
            valid_to TIMESTAMPTZ,
            available_at TIMESTAMPTZ NOT NULL,
            catalog_sequence BIGINT NOT NULL,
            content_id VARCHAR NOT NULL UNIQUE,
            CHECK (valid_to IS NULL OR valid_from < valid_to)
        )""",
        """CREATE TABLE canonical.classification_assignments (
            classification_assignment_id UUID PRIMARY KEY,
            classification_scheme_id UUID NOT NULL,
            scheme_version INTEGER NOT NULL,
            entity_kind VARCHAR NOT NULL,
            entity_id UUID NOT NULL,
            classification_node_id UUID NOT NULL,
            valid_from TIMESTAMPTZ NOT NULL,
            valid_to TIMESTAMPTZ,
            available_at TIMESTAMPTZ NOT NULL,
            catalog_sequence BIGINT NOT NULL,
            content_id VARCHAR NOT NULL UNIQUE,
            CHECK (valid_to IS NULL OR valid_from < valid_to)
        )""",
        """CREATE TABLE canonical.universe_memberships (
            membership_id UUID PRIMARY KEY,
            source_universe_key VARCHAR NOT NULL,
            instrument_id UUID NOT NULL,
            membership_role VARCHAR NOT NULL,
            weight DECIMAL(38, 18),
            valid_from TIMESTAMPTZ NOT NULL,
            valid_to TIMESTAMPTZ,
            available_at TIMESTAMPTZ NOT NULL,
            ingested_at TIMESTAMPTZ NOT NULL,
            catalog_sequence BIGINT NOT NULL,
            content_id VARCHAR NOT NULL UNIQUE,
            CHECK (valid_to IS NULL OR valid_from < valid_to),
            CHECK (weight IS NULL OR weight >= 0)
        )""",
        """CREATE TABLE canonical.bar_specs (
            bar_spec_id UUID NOT NULL,
            bar_spec_version INTEGER NOT NULL,
            qualified_name VARCHAR NOT NULL,
            definition_content_id VARCHAR NOT NULL UNIQUE,
            definition_json JSON NOT NULL,
            created_catalog_sequence BIGINT NOT NULL,
            PRIMARY KEY (bar_spec_id, bar_spec_version),
            UNIQUE (qualified_name, bar_spec_version)
        )""",
        """CREATE TABLE canonical.bars (
            bar_id UUID PRIMARY KEY,
            instrument_id UUID NOT NULL,
            bar_spec_id UUID NOT NULL,
            bar_spec_version INTEGER NOT NULL,
            interval_start TIMESTAMPTZ NOT NULL,
            interval_end TIMESTAMPTZ NOT NULL,
            session_date DATE NOT NULL,
            bar_state VARCHAR NOT NULL,
            currency VARCHAR NOT NULL,
            open_price DECIMAL(38, 12),
            high_price DECIMAL(38, 12),
            low_price DECIMAL(38, 12),
            close_price DECIMAL(38, 12),
            volume DECIMAL(38, 12) NOT NULL,
            trade_count BIGINT,
            available_at TIMESTAMPTZ NOT NULL,
            ingested_at TIMESTAMPTZ NOT NULL,
            catalog_sequence BIGINT NOT NULL,
            content_id VARCHAR NOT NULL UNIQUE,
            UNIQUE (instrument_id, bar_spec_id, bar_spec_version, interval_start, catalog_sequence),
            CHECK (interval_start < interval_end),
            CHECK (volume >= 0)
        )""",
        """CREATE TABLE canonical.trading_status (
            status_id UUID PRIMARY KEY,
            instrument_id UUID NOT NULL,
            status VARCHAR NOT NULL,
            effective_at TIMESTAMPTZ NOT NULL,
            effective_to TIMESTAMPTZ,
            available_at TIMESTAMPTZ NOT NULL,
            ingested_at TIMESTAMPTZ NOT NULL,
            catalog_sequence BIGINT NOT NULL,
            content_id VARCHAR NOT NULL UNIQUE,
            CHECK (effective_to IS NULL OR effective_at < effective_to)
        )""",
        """CREATE TABLE canonical.corporate_actions (
            corporate_action_id UUID PRIMARY KEY,
            action_kind VARCHAR NOT NULL,
            subject_security_id UUID NOT NULL,
            subject_instrument_id UUID,
            created_catalog_sequence BIGINT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL
        )""",
        """CREATE TABLE canonical.corporate_action_observations (
            observation_id UUID PRIMARY KEY,
            corporate_action_id UUID NOT NULL,
            action_status VARCHAR NOT NULL,
            ex_at TIMESTAMPTZ,
            effective_at TIMESTAMPTZ,
            share_ratio DECIMAL(38, 18),
            cash_per_subject_unit DECIMAL(38, 12),
            currency VARCHAR,
            available_at TIMESTAMPTZ NOT NULL,
            ingested_at TIMESTAMPTZ NOT NULL,
            catalog_sequence BIGINT NOT NULL,
            content_id VARCHAR NOT NULL UNIQUE
        )""",
    ),
    (
        "CREATE SCHEMA research_data",
        """CREATE TABLE {database}.research.universe_definitions (
            universe_definition_id UUID NOT NULL,
            definition_version INTEGER NOT NULL,
            qualified_name VARCHAR NOT NULL,
            definition_content_id VARCHAR NOT NULL UNIQUE,
            definition_json JSON NOT NULL,
            created_at TIMESTAMPTZ NOT NULL,
            PRIMARY KEY (universe_definition_id, definition_version),
            UNIQUE (qualified_name, definition_version)
        )""",
        """CREATE TABLE {database}.research.universe_evaluations (
            universe_evaluation_id UUID PRIMARY KEY,
            universe_definition_id UUID NOT NULL,
            definition_version INTEGER NOT NULL,
            composite_snapshot_id UUID NOT NULL,
            execution_content_id VARCHAR NOT NULL UNIQUE,
            start_at TIMESTAMPTZ NOT NULL,
            end_at TIMESTAMPTZ NOT NULL,
            cutoff_mode VARCHAR NOT NULL,
            public_cutoff_policy_content_id VARCHAR NOT NULL,
            project_cutoff_at TIMESTAMPTZ,
            calendar_schedule_content_id VARCHAR NOT NULL,
            created_at TIMESTAMPTZ NOT NULL
        )""",
        """CREATE TABLE {database}.research.universe_eligibility (
            universe_evaluation_id UUID NOT NULL,
            decision_at TIMESTAMPTZ NOT NULL,
            session_date DATE,
            instrument_id UUID NOT NULL,
            eligible BOOLEAN NOT NULL,
            primary_reason_code VARCHAR NOT NULL,
            reason_codes_json JSON NOT NULL,
            warning_codes_json JSON NOT NULL,
            lineage_content_id VARCHAR NOT NULL,
            PRIMARY KEY (universe_evaluation_id, decision_at, instrument_id)
        )""",
        """CREATE TABLE {database}.research.universe_rule_outcomes (
            universe_evaluation_id UUID NOT NULL,
            decision_at TIMESTAMPTZ NOT NULL,
            instrument_id UUID NOT NULL,
            rule_ordinal INTEGER NOT NULL,
            rule_name VARCHAR NOT NULL,
            outcome VARCHAR NOT NULL,
            reason_code VARCHAR NOT NULL,
            evidence_content_id VARCHAR NOT NULL,
            PRIMARY KEY (universe_evaluation_id, decision_at, instrument_id, rule_ordinal)
        )""",
        """CREATE TABLE {database}.research.research_datasets (
            research_dataset_id UUID PRIMARY KEY,
            qualified_name VARCHAR NOT NULL UNIQUE,
            created_at TIMESTAMPTZ NOT NULL
        )""",
        """CREATE TABLE {database}.research.research_dataset_versions (
            research_dataset_id UUID NOT NULL,
            definition_version INTEGER NOT NULL,
            definition_content_id VARCHAR NOT NULL UNIQUE,
            definition_json JSON NOT NULL,
            created_at TIMESTAMPTZ NOT NULL,
            PRIMARY KEY (research_dataset_id, definition_version)
        )""",
        """CREATE TABLE {database}.research.research_dataset_builds (
            research_dataset_build_id UUID PRIMARY KEY,
            research_dataset_id UUID NOT NULL,
            definition_version INTEGER NOT NULL,
            composite_snapshot_id UUID NOT NULL,
            universe_evaluation_id UUID NOT NULL,
            execution_content_id VARCHAR NOT NULL UNIQUE,
            output_relation_name VARCHAR NOT NULL UNIQUE,
            output_manifest_content_id VARCHAR NOT NULL,
            row_count BIGINT NOT NULL,
            usable_count BIGINT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL
        )""",
        """CREATE TABLE {database}.research.research_dataset_row_audit (
            research_dataset_build_id UUID NOT NULL,
            decision_at TIMESTAMPTZ NOT NULL,
            session_date DATE,
            instrument_id UUID NOT NULL,
            universe_eligible BOOLEAN NOT NULL,
            included BOOLEAN NOT NULL,
            row_usable BOOLEAN NOT NULL,
            primary_reason_code VARCHAR NOT NULL,
            reason_codes_json JSON NOT NULL,
            lineage_content_id VARCHAR,
            PRIMARY KEY (research_dataset_build_id, decision_at, instrument_id)
        )""",
        """CREATE TABLE {database}.research.research_dataset_input_outcomes (
            research_dataset_build_id UUID NOT NULL,
            input_ordinal INTEGER NOT NULL,
            decision_at TIMESTAMPTZ NOT NULL,
            instrument_id UUID NOT NULL,
            outcome VARCHAR NOT NULL,
            selected_id UUID,
            selected_at TIMESTAMPTZ,
            reason_codes_json JSON NOT NULL,
            evidence_content_id VARCHAR,
            PRIMARY KEY (
                research_dataset_build_id, input_ordinal, decision_at, instrument_id
            )
        )""",
    ),
)

MIGRATION_5 = _step(
    5,
    "flagship_vectorized_slice",
    4,
    5,
    (),
    (),
    (
        "CREATE SCHEMA {database}.portfolio",
        "CREATE SCHEMA {database}.accounting",
        "CREATE SCHEMA {database}.journal_data",
        "CREATE SCHEMA {database}.simulation",
        "CREATE SCHEMA {database}.simulation_data",
        "CREATE SCHEMA {database}.result_data",
        "CREATE SCHEMA {database}.analysis_data",
        """CREATE TABLE {database}.research.feature_definitions (
            feature_definition_id UUID PRIMARY KEY,
            qualified_name VARCHAR NOT NULL UNIQUE,
            created_at TIMESTAMPTZ NOT NULL
        )""",
        """CREATE TABLE {database}.research.feature_versions (
            feature_definition_id UUID NOT NULL,
            definition_version INTEGER NOT NULL,
            definition_content_id VARCHAR NOT NULL UNIQUE,
            definition_json JSON NOT NULL,
            created_at TIMESTAMPTZ NOT NULL,
            PRIMARY KEY (feature_definition_id, definition_version)
        )""",
        """CREATE TABLE {database}.research.feature_materializations (
            feature_materialization_id UUID PRIMARY KEY,
            feature_definition_id UUID NOT NULL,
            definition_version INTEGER NOT NULL,
            research_dataset_build_id UUID NOT NULL,
            execution_content_id VARCHAR NOT NULL UNIQUE,
            output_manifest_content_id VARCHAR NOT NULL,
            row_count BIGINT NOT NULL,
            computed_count BIGINT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL
        )""",
        """CREATE TABLE {database}.research_data.feature_values (
            feature_materialization_id UUID NOT NULL,
            decision_at TIMESTAMPTZ NOT NULL,
            session_date DATE,
            instrument_id UUID NOT NULL,
            value DOUBLE,
            state VARCHAR NOT NULL,
            reason_code VARCHAR,
            logical_available_at TIMESTAMPTZ NOT NULL,
            lineage_content_id VARCHAR NOT NULL,
            PRIMARY KEY (feature_materialization_id, decision_at, instrument_id),
            CHECK ((state = 'computed') = (value IS NOT NULL))
        )""",
        """CREATE TABLE {database}.portfolio.signal_definitions (
            signal_definition_id UUID PRIMARY KEY,
            qualified_name VARCHAR NOT NULL UNIQUE,
            created_at TIMESTAMPTZ NOT NULL
        )""",
        """CREATE TABLE {database}.portfolio.signal_versions (
            signal_definition_id UUID NOT NULL,
            definition_version INTEGER NOT NULL,
            definition_content_id VARCHAR NOT NULL UNIQUE,
            definition_json JSON NOT NULL,
            created_at TIMESTAMPTZ NOT NULL,
            PRIMARY KEY (signal_definition_id, definition_version)
        )""",
        """CREATE TABLE {database}.portfolio.signal_materializations (
            signal_materialization_id UUID PRIMARY KEY,
            signal_definition_id UUID NOT NULL,
            definition_version INTEGER NOT NULL,
            feature_materialization_id UUID NOT NULL,
            execution_content_id VARCHAR NOT NULL UNIQUE,
            output_manifest_content_id VARCHAR NOT NULL,
            row_count BIGINT NOT NULL,
            computed_count BIGINT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL
        )""",
        """CREATE TABLE {database}.portfolio.signal_values (
            signal_materialization_id UUID NOT NULL,
            decision_at TIMESTAMPTZ NOT NULL,
            session_date DATE,
            instrument_id UUID NOT NULL,
            value DOUBLE,
            state VARCHAR NOT NULL,
            reason_code VARCHAR,
            logical_available_at TIMESTAMPTZ NOT NULL,
            lineage_content_id VARCHAR NOT NULL,
            PRIMARY KEY (signal_materialization_id, decision_at, instrument_id),
            CHECK ((state = 'computed') = (value IS NOT NULL))
        )""",
        """CREATE TABLE {database}.portfolio.constructor_definitions (
            portfolio_constructor_id UUID PRIMARY KEY,
            qualified_name VARCHAR NOT NULL UNIQUE,
            created_at TIMESTAMPTZ NOT NULL
        )""",
        """CREATE TABLE {database}.portfolio.constructor_versions (
            portfolio_constructor_id UUID NOT NULL,
            definition_version INTEGER NOT NULL,
            definition_content_id VARCHAR NOT NULL UNIQUE,
            definition_json JSON NOT NULL,
            created_at TIMESTAMPTZ NOT NULL,
            PRIMARY KEY (portfolio_constructor_id, definition_version)
        )""",
        """CREATE TABLE {database}.portfolio.construction_results (
            portfolio_construction_result_id UUID PRIMARY KEY,
            portfolio_constructor_id UUID NOT NULL,
            definition_version INTEGER NOT NULL,
            signal_materialization_id UUID NOT NULL,
            execution_content_id VARCHAR NOT NULL UNIQUE,
            output_manifest_content_id VARCHAR NOT NULL,
            decision_count BIGINT NOT NULL,
            target_row_count BIGINT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL
        )""",
        """CREATE TABLE {database}.portfolio.target_decisions (
            portfolio_construction_result_id UUID NOT NULL,
            decision_at TIMESTAMPTZ NOT NULL,
            session_date DATE NOT NULL,
            status VARCHAR NOT NULL,
            cash_weight DOUBLE,
            reason_code VARCHAR,
            target_content_id VARCHAR NOT NULL,
            PRIMARY KEY (portfolio_construction_result_id, decision_at)
        )""",
        """CREATE TABLE {database}.portfolio.target_weights (
            portfolio_construction_result_id UUID NOT NULL,
            decision_at TIMESTAMPTZ NOT NULL,
            instrument_id UUID NOT NULL,
            signal_value DOUBLE,
            selected BOOLEAN NOT NULL,
            target_weight DOUBLE NOT NULL,
            state VARCHAR NOT NULL,
            reason_code VARCHAR,
            PRIMARY KEY (
                portfolio_construction_result_id, decision_at, instrument_id
            )
        )""",
        """CREATE TABLE {database}.accounting.books (
            accounting_book_id UUID PRIMARY KEY,
            opening_content_id VARCHAR NOT NULL UNIQUE,
            opening_at TIMESTAMPTZ NOT NULL,
            created_at TIMESTAMPTZ NOT NULL
        )""",
        """CREATE TABLE {database}.accounting.journal_transactions (
            journal_transaction_id UUID PRIMARY KEY,
            accounting_book_id UUID NOT NULL,
            book_sequence BIGINT NOT NULL,
            source_content_id VARCHAR NOT NULL,
            transaction_kind VARCHAR NOT NULL,
            effective_at TIMESTAMPTZ NOT NULL,
            transaction_content_id VARCHAR NOT NULL UNIQUE,
            created_at TIMESTAMPTZ NOT NULL,
            UNIQUE (accounting_book_id, book_sequence),
            UNIQUE (accounting_book_id, source_content_id)
        )""",
        """CREATE TABLE {database}.journal_data.journal_postings (
            journal_transaction_id UUID NOT NULL,
            posting_ordinal INTEGER NOT NULL,
            posting_book VARCHAR NOT NULL,
            account_code VARCHAR NOT NULL,
            commodity VARCHAR NOT NULL,
            amount DECIMAL(38, 12) NOT NULL,
            instrument_id UUID,
            posting_content_id VARCHAR NOT NULL,
            PRIMARY KEY (journal_transaction_id, posting_ordinal)
        )""",
        """CREATE TABLE {database}.accounting.inventory_lots (
            inventory_lot_id UUID PRIMARY KEY,
            accounting_book_id UUID NOT NULL,
            instrument_id UUID NOT NULL,
            opened_by_transaction_id UUID NOT NULL,
            acquired_at TIMESTAMPTZ NOT NULL,
            original_quantity DECIMAL(38, 12) NOT NULL,
            original_basis_usd DECIMAL(38, 12) NOT NULL,
            lot_content_id VARCHAR NOT NULL UNIQUE
        )""",
        """CREATE TABLE {database}.journal_data.lot_events (
            inventory_lot_id UUID NOT NULL,
            event_ordinal INTEGER NOT NULL,
            journal_transaction_id UUID NOT NULL,
            event_kind VARCHAR NOT NULL,
            quantity_delta DECIMAL(38, 12) NOT NULL,
            basis_delta_usd DECIMAL(38, 12) NOT NULL,
            event_content_id VARCHAR NOT NULL,
            PRIMARY KEY (inventory_lot_id, event_ordinal)
        )""",
        """CREATE TABLE {database}.simulation.vectorized_runs (
            vectorized_simulation_id UUID PRIMARY KEY,
            run_record_id UUID NOT NULL UNIQUE,
            accounting_book_id UUID NOT NULL,
            construction_result_id UUID NOT NULL,
            execution_content_id VARCHAR NOT NULL UNIQUE,
            result_manifest_content_id VARCHAR NOT NULL,
            decision_count BIGINT NOT NULL,
            fill_count BIGINT NOT NULL,
            status VARCHAR NOT NULL,
            created_at TIMESTAMPTZ NOT NULL
        )""",
        """CREATE TABLE {database}.simulation_data.rebalance_decisions (
            vectorized_simulation_id UUID NOT NULL,
            decision_at TIMESTAMPTZ NOT NULL,
            execution_at TIMESTAMPTZ,
            state VARCHAR NOT NULL,
            pretrade_nav_usd DECIMAL(38, 12),
            reason_code VARCHAR,
            decision_content_id VARCHAR NOT NULL,
            PRIMARY KEY (vectorized_simulation_id, decision_at)
        )""",
        """CREATE TABLE {database}.simulation_data.synthetic_fills (
            vectorized_simulation_id UUID NOT NULL,
            fill_ordinal BIGINT NOT NULL,
            decision_at TIMESTAMPTZ NOT NULL,
            execution_at TIMESTAMPTZ NOT NULL,
            instrument_id UUID NOT NULL,
            side VARCHAR NOT NULL,
            quantity DECIMAL(38, 12) NOT NULL,
            reference_price_usd DECIMAL(38, 12) NOT NULL,
            fill_price_usd DECIMAL(38, 12) NOT NULL,
            commission_usd DECIMAL(38, 12) NOT NULL,
            slippage_usd DECIMAL(38, 12) NOT NULL,
            fill_content_id VARCHAR NOT NULL,
            PRIMARY KEY (vectorized_simulation_id, fill_ordinal)
        )""",
        """CREATE TABLE {database}.results.run_records (
            run_record_id UUID PRIMARY KEY,
            vectorized_simulation_id UUID NOT NULL UNIQUE,
            execution_content_id VARCHAR NOT NULL,
            result_manifest_content_id VARCHAR NOT NULL,
            decision_count BIGINT NOT NULL,
            fill_count BIGINT NOT NULL,
            fidelity_findings_json JSON NOT NULL,
            created_at TIMESTAMPTZ NOT NULL
        )""",
        """CREATE TABLE {database}.result_data.equity (
            run_record_id UUID NOT NULL,
            sample_ordinal BIGINT NOT NULL,
            valued_at TIMESTAMPTZ NOT NULL,
            journal_prefix_sequence BIGINT NOT NULL,
            nav_usd DECIMAL(38, 12) NOT NULL,
            gross_exposure_usd DECIMAL(38, 12) NOT NULL,
            net_exposure_usd DECIMAL(38, 12) NOT NULL,
            state VARCHAR NOT NULL,
            source_content_id VARCHAR NOT NULL,
            PRIMARY KEY (run_record_id, sample_ordinal)
        )""",
        """CREATE TABLE {database}.result_data.returns (
            run_record_id UUID NOT NULL,
            return_ordinal BIGINT NOT NULL,
            interval_start TIMESTAMPTZ NOT NULL,
            interval_end TIMESTAMPTZ NOT NULL,
            opening_nav_usd DECIMAL(38, 12) NOT NULL,
            closing_nav_usd DECIMAL(38, 12) NOT NULL,
            return_value DOUBLE,
            state VARCHAR NOT NULL,
            source_content_id VARCHAR NOT NULL,
            PRIMARY KEY (run_record_id, return_ordinal)
        )""",
        """CREATE TABLE {database}.result_data.positions (
            run_record_id UUID NOT NULL,
            sample_ordinal BIGINT NOT NULL,
            valued_at TIMESTAMPTZ NOT NULL,
            instrument_id UUID NOT NULL,
            quantity DECIMAL(38, 12) NOT NULL,
            mark_price_usd DECIMAL(38, 12) NOT NULL,
            market_value_usd DECIMAL(38, 12) NOT NULL,
            source_content_id VARCHAR NOT NULL,
            PRIMARY KEY (run_record_id, sample_ordinal, instrument_id)
        )""",
        """CREATE TABLE {database}.result_data.cash (
            run_record_id UUID NOT NULL,
            sample_ordinal BIGINT NOT NULL,
            valued_at TIMESTAMPTZ NOT NULL,
            cash_usd DECIMAL(38, 12) NOT NULL,
            source_content_id VARCHAR NOT NULL,
            PRIMARY KEY (run_record_id, sample_ordinal)
        )""",
        """CREATE TABLE {database}.result_data.targets (
            run_record_id UUID NOT NULL,
            decision_at TIMESTAMPTZ NOT NULL,
            instrument_id UUID NOT NULL,
            target_weight DOUBLE NOT NULL,
            target_quantity DECIMAL(38, 12),
            filled_quantity DECIMAL(38, 12),
            shortfall_quantity DECIMAL(38, 12),
            PRIMARY KEY (run_record_id, decision_at, instrument_id)
        )""",
        """CREATE TABLE {database}.result_data.cost_components (
            run_record_id UUID NOT NULL,
            fill_ordinal BIGINT NOT NULL,
            component_kind VARCHAR NOT NULL,
            amount_usd DECIMAL(38, 12) NOT NULL,
            state VARCHAR NOT NULL,
            source_content_id VARCHAR NOT NULL,
            PRIMARY KEY (run_record_id, fill_ordinal, component_kind)
        )""",
        """CREATE TABLE {database}.analysis.artifacts (
            analysis_artifact_id UUID PRIMARY KEY,
            artifact_kind VARCHAR NOT NULL,
            run_record_id UUID NOT NULL,
            execution_content_id VARCHAR NOT NULL UNIQUE,
            output_content_id VARCHAR NOT NULL,
            created_at TIMESTAMPTZ NOT NULL
        )""",
        """CREATE TABLE {database}.analysis_data.metric_results (
            analysis_artifact_id UUID NOT NULL,
            metric_name VARCHAR NOT NULL,
            state VARCHAR NOT NULL,
            estimate DOUBLE,
            unit VARCHAR NOT NULL,
            observation_count BIGINT NOT NULL,
            reason_code VARCHAR,
            PRIMARY KEY (analysis_artifact_id, metric_name)
        )""",
        """CREATE TABLE {database}.analysis.report_plans (
            report_plan_id UUID PRIMARY KEY,
            run_record_id UUID NOT NULL,
            metrics_artifact_id UUID NOT NULL,
            execution_content_id VARCHAR NOT NULL UNIQUE,
            created_at TIMESTAMPTZ NOT NULL
        )""",
        """CREATE TABLE {database}.analysis.report_outputs (
            report_output_id UUID PRIMARY KEY,
            report_plan_id UUID NOT NULL UNIQUE,
            analysis_artifact_id UUID NOT NULL UNIQUE,
            output_content_id VARCHAR NOT NULL UNIQUE,
            html_bytes BLOB NOT NULL,
            byte_count BIGINT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL
        )""",
    ),
)

MIGRATION_6 = _step(
    6,
    "source_precedence_and_availability",
    5,
    6,
    (),
    (
        "ALTER TABLE catalog.batch_records ADD COLUMN published_at TIMESTAMPTZ",
        "ALTER TABLE catalog.batch_records ADD COLUMN source_updated_at TIMESTAMPTZ",
        "ALTER TABLE catalog.batch_records ADD COLUMN availability_quality VARCHAR",
        "ALTER TABLE catalog.canonical_revisions ADD COLUMN published_at TIMESTAMPTZ",
        "ALTER TABLE catalog.canonical_revisions ADD COLUMN source_updated_at TIMESTAMPTZ",
        "ALTER TABLE catalog.canonical_revisions ADD COLUMN availability_quality VARCHAR",
        """CREATE TABLE catalog.source_precedence_policies (
            policy_name VARCHAR NOT NULL,
            policy_version INTEGER NOT NULL CHECK (policy_version >= 1),
            dataset_id UUID NOT NULL,
            dataset_version INTEGER NOT NULL CHECK (dataset_version >= 1),
            definition_json JSON NOT NULL,
            definition_content_id VARCHAR NOT NULL UNIQUE,
            PRIMARY KEY (policy_name, policy_version)
        )""",
        """CREATE TABLE catalog.dataset_source_precedence_bindings (
            dataset_id UUID NOT NULL,
            dataset_version INTEGER NOT NULL CHECK (dataset_version >= 1),
            policy_name VARCHAR NOT NULL,
            policy_version INTEGER NOT NULL CHECK (policy_version >= 1),
            binding_content_id VARCHAR NOT NULL UNIQUE,
            PRIMARY KEY (dataset_id, dataset_version)
        )""",
        """CREATE TABLE catalog.observation_entity_resolutions (
            canonical_revision_id UUID NOT NULL,
            entity_role VARCHAR NOT NULL,
            source_entity_key VARCHAR NOT NULL,
            resolved_entity_id UUID,
            resolution_status VARCHAR NOT NULL,
            resolution_content_id VARCHAR NOT NULL,
            recorded_at TIMESTAMPTZ NOT NULL,
            PRIMARY KEY (canonical_revision_id, entity_role, source_entity_key)
        )""",
    ),
    (),
)

MIGRATIONS = (MIGRATION_2, MIGRATION_3, MIGRATION_4, MIGRATION_5, MIGRATION_6)


def migration_statements(
    step: MigrationStep, *, role: str, database_name: str
) -> tuple[str, ...]:
    role_statements = (
        step.market_statements if role == "market" else step.research_statements
    )
    escaped_database = database_name.replace('"', '""')
    database = f'"{escaped_database}"'
    return tuple(
        statement.replace("{database}", database)
        for statement in step.statements + role_statements
    )
