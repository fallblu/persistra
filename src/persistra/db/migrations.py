"""Immutable forward database migration registry."""

from __future__ import annotations

from dataclasses import dataclass

from persistra.domain import ContentId
from persistra.domain.serialization import canonical_bytes

CURRENT_SCHEMA_VERSION = 12
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

MIGRATION_7 = _step(
    7,
    "canonical_market_families",
    6,
    7,
    (),
    (
        "ALTER TABLE canonical.bar_specs ADD COLUMN interval_kind VARCHAR DEFAULT 'session'",
        "ALTER TABLE canonical.bar_specs ADD COLUMN nominal_interval_us BIGINT",
        "ALTER TABLE canonical.bar_specs ADD COLUMN alignment VARCHAR DEFAULT 'session_open'",
        "ALTER TABLE canonical.bar_specs ADD COLUMN phase VARCHAR DEFAULT 'regular'",
        "ALTER TABLE canonical.bar_specs ADD COLUMN phase_boundary_policy_content_id VARCHAR",
        "ALTER TABLE canonical.bar_specs "
        "ADD COLUMN allow_short_final_interval BOOLEAN DEFAULT false",
        "ALTER TABLE canonical.bars ADD COLUMN canonical_revision_id UUID",
        "UPDATE canonical.bars SET canonical_revision_id = bar_id",
        "CREATE UNIQUE INDEX canonical_bars_revision_idx "
        "ON canonical.bars(canonical_revision_id)",
        "ALTER TABLE canonical.bars ADD COLUMN observation_scope VARCHAR DEFAULT 'consolidated'",
        "ALTER TABLE canonical.bars ADD COLUMN venue_id UUID",
        "ALTER TABLE canonical.bars ADD COLUMN aggregation_name VARCHAR "
        "DEFAULT 'persistra.market.consolidated'",
        "ALTER TABLE canonical.bars ADD COLUMN aggregation_version INTEGER DEFAULT 1",
        "ALTER TABLE canonical.bars ADD COLUMN aggregation_content_id VARCHAR",
        "ALTER TABLE canonical.bars ADD COLUMN observed_through_at TIMESTAMPTZ",
        "UPDATE canonical.bars SET observed_through_at = interval_end",
        "ALTER TABLE canonical.bars ADD COLUMN bar_phase VARCHAR DEFAULT 'regular'",
        "ALTER TABLE canonical.bars ADD COLUMN calendar_schedule_content_id VARCHAR",
        "ALTER TABLE canonical.bars ADD COLUMN vwap DECIMAL(38, 12)",
        "ALTER TABLE canonical.bars ADD COLUMN notional_amount DECIMAL(38, 12)",
        "ALTER TABLE canonical.bars ADD COLUMN source_condition_codes_json JSON DEFAULT '[]'",
        """CREATE TABLE canonical.market_revision_metadata (
            canonical_revision_id UUID PRIMARY KEY,
            source_id UUID,
            event_at TIMESTAMPTZ,
            available_at TIMESTAMPTZ NOT NULL,
            availability_quality VARCHAR NOT NULL,
            ingested_at TIMESTAMPTZ NOT NULL,
            catalog_sequence BIGINT NOT NULL,
            content_id VARCHAR NOT NULL UNIQUE
        )""",
        """INSERT INTO canonical.market_revision_metadata
            SELECT canonical_revision_id, NULL, interval_end, available_at, 'observed',
                   ingested_at, catalog_sequence, content_id
            FROM canonical.bars""",
        """CREATE TABLE canonical.trades (
            canonical_revision_id UUID PRIMARY KEY,
            source_trade_key VARCHAR NOT NULL,
            instrument_id UUID NOT NULL,
            venue_id UUID NOT NULL,
            currency VARCHAR NOT NULL,
            source_sequence BIGINT NOT NULL CHECK (source_sequence >= 0),
            price DECIMAL(38, 12) NOT NULL CHECK (price > 0),
            quantity DECIMAL(38, 12) NOT NULL CHECK (quantity > 0),
            trade_condition_codes_json JSON NOT NULL,
            raw_condition_codes_json JSON NOT NULL,
            price_forming BOOLEAN NOT NULL,
            volume_forming BOOLEAN NOT NULL,
            extended_hours BOOLEAN NOT NULL,
            correction_reference_key VARCHAR
        )""",
        """CREATE TABLE canonical.quotes (
            canonical_revision_id UUID PRIMARY KEY,
            source_quote_key VARCHAR NOT NULL,
            instrument_id UUID NOT NULL,
            quote_state VARCHAR NOT NULL CHECK (quote_state IN ('active', 'empty')),
            quote_scope VARCHAR NOT NULL CHECK (
                quote_scope IN ('venue_top', 'consolidated_nbbo')
            ),
            venue_id UUID,
            bid_venue_id UUID,
            ask_venue_id UUID,
            currency VARCHAR NOT NULL,
            source_sequence BIGINT NOT NULL CHECK (source_sequence >= 0),
            bid_price DECIMAL(38, 12),
            bid_size DECIMAL(38, 12),
            ask_price DECIMAL(38, 12),
            ask_size DECIMAL(38, 12),
            quote_condition_codes_json JSON NOT NULL,
            raw_condition_codes_json JSON NOT NULL,
            indicative BOOLEAN NOT NULL
        )""",
        """CREATE TABLE canonical.trading_status_observations (
            canonical_revision_id UUID PRIMARY KEY,
            source_status_key VARCHAR NOT NULL,
            instrument_id UUID NOT NULL,
            venue_id UUID,
            source_sequence BIGINT NOT NULL CHECK (source_sequence >= 0),
            trading_status VARCHAR NOT NULL,
            status_reason_code VARCHAR,
            expected_resume_at TIMESTAMPTZ,
            source_condition_codes_json JSON NOT NULL,
            effective_to TIMESTAMPTZ
        )""",
        """CREATE TABLE canonical.corporate_action_legs (
            canonical_revision_id UUID NOT NULL,
            leg_ordinal INTEGER NOT NULL CHECK (leg_ordinal >= 1),
            leg_kind VARCHAR NOT NULL,
            target_security_id UUID,
            target_instrument_id UUID,
            cash_per_subject_unit DECIMAL(38, 12),
            quantity_per_subject_unit DECIMAL(38, 18),
            currency VARCHAR,
            entitlement_code VARCHAR,
            terms_basis VARCHAR NOT NULL,
            leg_details_json JSON NOT NULL,
            PRIMARY KEY (canonical_revision_id, leg_ordinal)
        )""",
        "ALTER TABLE canonical.corporate_action_observations "
        "ADD COLUMN canonical_revision_id UUID",
        "UPDATE canonical.corporate_action_observations "
        "SET canonical_revision_id = observation_id",
        "CREATE UNIQUE INDEX canonical_action_revision_idx "
        "ON canonical.corporate_action_observations(canonical_revision_id)",
        "ALTER TABLE canonical.corporate_action_observations "
        "ADD COLUMN source_action_key VARCHAR DEFAULT ''",
        "ALTER TABLE canonical.corporate_action_observations "
        "ADD COLUMN resolution_method VARCHAR DEFAULT 'created'",
        "ALTER TABLE canonical.corporate_action_observations "
        "ADD COLUMN resolution_evidence_content_id VARCHAR",
        "ALTER TABLE canonical.corporate_action_observations ADD COLUMN announced_date DATE",
        "ALTER TABLE canonical.corporate_action_observations "
        "ADD COLUMN announced_at TIMESTAMPTZ",
        "ALTER TABLE canonical.corporate_action_observations ADD COLUMN declaration_date DATE",
        "ALTER TABLE canonical.corporate_action_observations ADD COLUMN ex_date DATE",
        "ALTER TABLE canonical.corporate_action_observations ADD COLUMN record_date DATE",
        "ALTER TABLE canonical.corporate_action_observations ADD COLUMN payable_date DATE",
        "ALTER TABLE canonical.corporate_action_observations "
        "ADD COLUMN payment_at TIMESTAMPTZ",
        "ALTER TABLE canonical.corporate_action_observations ADD COLUMN effective_date DATE",
        "ALTER TABLE canonical.corporate_action_observations ADD COLUMN expiration_date DATE",
        "ALTER TABLE canonical.corporate_action_observations ADD COLUMN terms_basis VARCHAR",
        "ALTER TABLE canonical.corporate_action_observations "
        "ADD COLUMN date_policy_content_id VARCHAR",
        "ALTER TABLE canonical.corporate_action_observations "
        "ADD COLUMN calendar_schedule_content_id VARCHAR",
        "ALTER TABLE canonical.corporate_action_observations "
        "ADD COLUMN action_fingerprint_content_id VARCHAR",
        "ALTER TABLE canonical.corporate_action_observations "
        "ADD COLUMN reference_revision_ids_json JSON DEFAULT '[]'",
        "ALTER TABLE canonical.corporate_action_observations "
        "ADD COLUMN source_terms_json JSON DEFAULT '{}'",
    ),
    (
        """CREATE TABLE {database}.research.adjustment_policies (
            adjustment_policy_id UUID NOT NULL,
            policy_version INTEGER NOT NULL CHECK (policy_version >= 1),
            qualified_name VARCHAR NOT NULL,
            definition_schema_version INTEGER NOT NULL CHECK (definition_schema_version >= 1),
            definition_content_id VARCHAR NOT NULL UNIQUE,
            definition_json JSON NOT NULL,
            created_at TIMESTAMPTZ NOT NULL,
            PRIMARY KEY (adjustment_policy_id, policy_version),
            UNIQUE (qualified_name, policy_version)
        )""",
        """CREATE TABLE {database}.research.adjustment_materializations (
            adjustment_materialization_id UUID PRIMARY KEY,
            adjustment_policy_id UUID NOT NULL,
            policy_version INTEGER NOT NULL,
            composite_snapshot_id UUID NOT NULL,
            market_database_name VARCHAR NOT NULL,
            bar_query_content_id VARCHAR NOT NULL,
            public_cutoff_policy_content_id VARCHAR NOT NULL,
            project_cutoff_at TIMESTAMPTZ,
            anchor_at TIMESTAMPTZ NOT NULL,
            action_selection_content_id VARCHAR NOT NULL,
            execution_content_id VARCHAR NOT NULL UNIQUE,
            safety_status VARCHAR NOT NULL,
            row_count BIGINT NOT NULL,
            factor_count BIGINT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL
        )""",
        """CREATE TABLE {database}.research.adjustment_factors (
            adjustment_materialization_id UUID NOT NULL,
            instrument_id UUID NOT NULL,
            effective_at TIMESTAMPTZ NOT NULL,
            factor_ordinal INTEGER NOT NULL,
            split_price_multiplier DOUBLE NOT NULL,
            cash_price_multiplier DOUBLE NOT NULL,
            volume_multiplier DOUBLE NOT NULL,
            cumulative_price_multiplier DOUBLE NOT NULL,
            cumulative_volume_multiplier DOUBLE NOT NULL,
            reference_price DOUBLE,
            corporate_action_ids_json JSON NOT NULL,
            input_revision_ids_json JSON NOT NULL,
            evidence_content_id VARCHAR NOT NULL,
            PRIMARY KEY (
                adjustment_materialization_id, instrument_id, effective_at, factor_ordinal
            )
        )""",
        """CREATE TABLE {database}.research.adjusted_bars (
            adjustment_materialization_id UUID NOT NULL,
            raw_canonical_revision_id UUID NOT NULL,
            instrument_id UUID NOT NULL,
            interval_start TIMESTAMPTZ NOT NULL,
            interval_end TIMESTAMPTZ NOT NULL,
            session_date DATE NOT NULL,
            adjusted_open DOUBLE,
            adjusted_high DOUBLE,
            adjusted_low DOUBLE,
            adjusted_close DOUBLE,
            adjusted_volume DOUBLE,
            adjusted_vwap DOUBLE,
            price_multiplier DOUBLE,
            volume_multiplier DOUBLE,
            adjustment_status VARCHAR NOT NULL,
            reason_codes_json JSON NOT NULL,
            lineage_content_id VARCHAR NOT NULL,
            PRIMARY KEY (adjustment_materialization_id, raw_canonical_revision_id)
        )""",
    ),
)

MIGRATION_8 = _step(
    8,
    "fundamental_and_economic_families",
    7,
    8,
    (),
    (
        """CREATE TABLE canonical.reports (
            report_id UUID PRIMARY KEY, issuer_id UUID NOT NULL,
            report_kind VARCHAR NOT NULL, fiscal_period_end DATE NOT NULL,
            created_catalog_sequence BIGINT NOT NULL, created_at TIMESTAMPTZ NOT NULL,
            UNIQUE (issuer_id, report_kind, fiscal_period_end)
        )""",
        """CREATE TABLE canonical.filings (
            filing_id UUID PRIMARY KEY, accession_namespace VARCHAR NOT NULL,
            normalized_accession VARCHAR NOT NULL,
            created_catalog_sequence BIGINT NOT NULL, created_at TIMESTAMPTZ NOT NULL,
            UNIQUE (accession_namespace, normalized_accession)
        )""",
        """CREATE TABLE canonical.filing_observations (
            canonical_revision_id UUID PRIMARY KEY, filing_id UUID NOT NULL,
            report_id UUID NOT NULL, issuer_id UUID NOT NULL,
            source_filing_key VARCHAR NOT NULL, form_type VARCHAR NOT NULL,
            filing_status VARCHAR NOT NULL, filing_date DATE NOT NULL,
            accepted_at TIMESTAMPTZ, report_period_start DATE,
            report_period_end DATE NOT NULL, fiscal_year INTEGER,
            fiscal_period_kind VARCHAR, is_amendment BOOLEAN NOT NULL,
            amends_filing_id UUID, taxonomy_namespace VARCHAR,
            taxonomy_version VARCHAR, document_content_id VARCHAR NOT NULL,
            document_location VARCHAR, document_redistributable BOOLEAN NOT NULL,
            source_metadata_json JSON NOT NULL
        )""",
        """CREATE TABLE canonical.fundamental_raw_facts (
            canonical_revision_id UUID PRIMARY KEY, filing_id UUID NOT NULL,
            report_id UUID NOT NULL, issuer_id UUID NOT NULL,
            taxonomy_namespace VARCHAR NOT NULL, taxonomy_version VARCHAR NOT NULL,
            source_concept_name VARCHAR NOT NULL, period_kind VARCHAR NOT NULL,
            period_start DATE, period_end DATE NOT NULL,
            period_policy_content_id VARCHAR NOT NULL, fiscal_year INTEGER,
            fiscal_period_kind VARCHAR, numeric_kind VARCHAR NOT NULL,
            value_decimal DECIMAL(38, 18), is_nil BOOLEAN NOT NULL,
            nil_reason_code VARCHAR, unit_name VARCHAR NOT NULL, currency VARCHAR,
            source_decimals INTEGER, source_precision INTEGER,
            dimensions_content_id VARCHAR NOT NULL, dimensions_json JSON NOT NULL,
            source_fact_key VARCHAR, source_metadata_json JSON NOT NULL
        )""",
        """CREATE TABLE canonical.normalized_concepts (
            normalized_concept_id UUID NOT NULL, concept_version INTEGER NOT NULL,
            qualified_name VARCHAR NOT NULL, period_kind VARCHAR NOT NULL,
            numeric_kind VARCHAR NOT NULL, canonical_unit_name VARCHAR NOT NULL,
            definition_content_id VARCHAR NOT NULL UNIQUE, definition_json JSON NOT NULL,
            created_catalog_sequence BIGINT NOT NULL,
            PRIMARY KEY (normalized_concept_id, concept_version),
            UNIQUE (qualified_name, concept_version)
        )""",
        """CREATE TABLE canonical.fundamental_mappings (
            fundamental_mapping_id UUID NOT NULL, mapping_version INTEGER NOT NULL,
            mapping_policy_name VARCHAR NOT NULL,
            source_taxonomy_namespace VARCHAR NOT NULL,
            source_taxonomy_version_pattern VARCHAR NOT NULL,
            source_concept_name VARCHAR NOT NULL, normalized_concept_id UUID NOT NULL,
            normalized_concept_version INTEGER NOT NULL,
            sign_multiplier DECIMAL(38, 18) NOT NULL,
            scale_multiplier DECIMAL(38, 18) NOT NULL,
            dimension_policy_content_id VARCHAR NOT NULL,
            applicability_json JSON NOT NULL, definition_content_id VARCHAR NOT NULL UNIQUE,
            created_catalog_sequence BIGINT NOT NULL,
            PRIMARY KEY (fundamental_mapping_id, mapping_version)
        )""",
        """CREATE TABLE canonical.fundamental_normalization_runs (
            fundamental_normalization_run_id UUID PRIMARY KEY,
            mapping_policy_content_id VARCHAR NOT NULL,
            input_catalog_sequence BIGINT NOT NULL,
            input_catalog_chain_content_id VARCHAR NOT NULL,
            execution_content_id VARCHAR NOT NULL UNIQUE,
            output_manifest_content_id VARCHAR NOT NULL, result_count BIGINT NOT NULL,
            normalized_count BIGINT NOT NULL, not_applicable_count BIGINT NOT NULL,
            unavailable_count BIGINT NOT NULL, conflict_count BIGINT NOT NULL,
            created_catalog_sequence BIGINT NOT NULL, created_at TIMESTAMPTZ NOT NULL
        )""",
        """CREATE TABLE canonical.fundamental_normalizations (
            fundamental_normalization_id UUID PRIMARY KEY,
            normalization_run_id UUID NOT NULL, raw_canonical_revision_id UUID NOT NULL,
            fundamental_mapping_id UUID NOT NULL, mapping_version INTEGER NOT NULL,
            normalized_concept_id UUID NOT NULL,
            normalized_concept_version INTEGER NOT NULL,
            normalized_value DECIMAL(38, 18), canonical_unit_name VARCHAR NOT NULL,
            normalization_status VARCHAR NOT NULL, reason_codes_json JSON NOT NULL,
            execution_content_id VARCHAR NOT NULL UNIQUE,
            created_catalog_sequence BIGINT NOT NULL, created_at TIMESTAMPTZ NOT NULL,
            UNIQUE (raw_canonical_revision_id, fundamental_mapping_id, mapping_version)
        )""",
        """CREATE TABLE canonical.estimate_measures (
            estimate_measure_id UUID NOT NULL, measure_version INTEGER NOT NULL,
            qualified_name VARCHAR NOT NULL, entity_kind VARCHAR NOT NULL,
            numeric_kind VARCHAR NOT NULL, canonical_unit_name VARCHAR NOT NULL,
            definition_content_id VARCHAR NOT NULL UNIQUE, definition_json JSON NOT NULL,
            created_catalog_sequence BIGINT NOT NULL,
            PRIMARY KEY (estimate_measure_id, measure_version),
            UNIQUE (qualified_name, measure_version)
        )""",
        """CREATE TABLE canonical.estimate_contributors (
            estimate_contributor_id UUID PRIMARY KEY, source_id UUID NOT NULL,
            source_contributor_key_content_id VARCHAR NOT NULL,
            created_catalog_sequence BIGINT NOT NULL, created_at TIMESTAMPTZ NOT NULL,
            UNIQUE (source_id, source_contributor_key_content_id)
        )""",
        """CREATE TABLE canonical.estimate_contributor_versions (
            estimate_contributor_id UUID NOT NULL, contributor_version INTEGER NOT NULL,
            display_label VARCHAR, licensing_class VARCHAR NOT NULL,
            definition_content_id VARCHAR NOT NULL UNIQUE,
            created_catalog_sequence BIGINT NOT NULL, created_at TIMESTAMPTZ NOT NULL,
            PRIMARY KEY (estimate_contributor_id, contributor_version)
        )""",
        """CREATE TABLE canonical.individual_estimates (
            canonical_revision_id UUID PRIMARY KEY, source_estimate_key VARCHAR NOT NULL,
            estimate_measure_id UUID NOT NULL, measure_version INTEGER NOT NULL,
            subject_entity_kind VARCHAR NOT NULL, subject_entity_id UUID NOT NULL,
            estimate_contributor_id UUID, target_kind VARCHAR NOT NULL,
            target_fiscal_year INTEGER, target_fiscal_period_kind VARCHAR,
            target_period_end DATE, target_report_id UUID, horizon_days INTEGER,
            target_at TIMESTAMPTZ, target_policy_content_id VARCHAR NOT NULL,
            value_decimal DECIMAL(38, 18) NOT NULL, unit_name VARCHAR NOT NULL,
            currency VARCHAR, split_basis_content_id VARCHAR,
            source_revision_label VARCHAR, source_metadata_json JSON NOT NULL
        )""",
        """CREATE TABLE canonical.estimate_consensus (
            canonical_revision_id UUID PRIMARY KEY, source_consensus_key VARCHAR NOT NULL,
            estimate_measure_id UUID NOT NULL, measure_version INTEGER NOT NULL,
            subject_entity_kind VARCHAR NOT NULL, subject_entity_id UUID NOT NULL,
            target_kind VARCHAR NOT NULL, target_fiscal_year INTEGER,
            target_fiscal_period_kind VARCHAR, target_period_end DATE,
            target_report_id UUID, horizon_days INTEGER, target_at TIMESTAMPTZ,
            target_policy_content_id VARCHAR NOT NULL, contributor_count INTEGER NOT NULL,
            mean_value DECIMAL(38, 18), median_value DECIMAL(38, 18),
            high_value DECIMAL(38, 18), low_value DECIMAL(38, 18),
            standard_deviation DECIMAL(38, 18), unit_name VARCHAR NOT NULL,
            currency VARCHAR, methodology_content_id VARCHAR NOT NULL,
            constituent_manifest_content_id VARCHAR, source_metadata_json JSON NOT NULL
        )""",
        """CREATE TABLE canonical.estimate_actuals (
            canonical_revision_id UUID PRIMARY KEY, source_actual_key VARCHAR NOT NULL,
            estimate_measure_id UUID NOT NULL, measure_version INTEGER NOT NULL,
            subject_entity_kind VARCHAR NOT NULL, subject_entity_id UUID NOT NULL,
            target_fiscal_year INTEGER, target_fiscal_period_kind VARCHAR,
            target_period_end DATE NOT NULL, value_decimal DECIMAL(38, 18) NOT NULL,
            unit_name VARCHAR NOT NULL, currency VARCHAR, filing_id UUID,
            raw_fact_revision_id UUID, fundamental_normalization_id UUID,
            actual_policy_content_id VARCHAR NOT NULL, source_metadata_json JSON NOT NULL
        )""",
        """CREATE TABLE canonical.macro_series (
            macro_series_id UUID NOT NULL, series_version INTEGER NOT NULL,
            qualified_name VARCHAR NOT NULL, frequency VARCHAR NOT NULL,
            seasonal_adjustment_status VARCHAR NOT NULL, geography_code VARCHAR NOT NULL,
            unit_name VARCHAR NOT NULL, numeric_kind VARCHAR NOT NULL,
            vintage_completeness VARCHAR NOT NULL,
            period_policy_content_id VARCHAR NOT NULL,
            definition_content_id VARCHAR NOT NULL UNIQUE, definition_json JSON NOT NULL,
            created_catalog_sequence BIGINT NOT NULL,
            PRIMARY KEY (macro_series_id, series_version),
            UNIQUE (qualified_name, series_version)
        )""",
        """CREATE TABLE canonical.macro_releases (
            macro_release_id UUID PRIMARY KEY, macro_series_id UUID NOT NULL,
            source_id UUID, source_release_key VARCHAR NOT NULL,
            created_catalog_sequence BIGINT NOT NULL, created_at TIMESTAMPTZ NOT NULL,
            UNIQUE (source_id, macro_series_id, source_release_key)
        )""",
        """CREATE TABLE canonical.macro_release_observations (
            canonical_revision_id UUID PRIMARY KEY, macro_release_id UUID NOT NULL,
            macro_series_id UUID NOT NULL, series_version INTEGER NOT NULL,
            release_at TIMESTAMPTZ NOT NULL, source_release_sequence BIGINT,
            release_manifest_content_id VARCHAR NOT NULL, source_metadata_json JSON NOT NULL
        )""",
        """CREATE TABLE canonical.macro_observations (
            canonical_revision_id UUID PRIMARY KEY, macro_series_id UUID NOT NULL,
            series_version INTEGER NOT NULL, macro_release_id UUID NOT NULL,
            macro_release_revision_id UUID NOT NULL, source_vintage_key VARCHAR NOT NULL,
            observation_period_start DATE NOT NULL,
            observation_period_end DATE NOT NULL, vintage_status VARCHAR NOT NULL,
            value_decimal DECIMAL(38, 18), is_missing BOOLEAN NOT NULL,
            missing_reason_code VARCHAR, unit_name VARCHAR NOT NULL,
            source_metadata_json JSON NOT NULL
        )""",
        """CREATE TABLE canonical.benchmarks (
            benchmark_id UUID PRIMARY KEY, qualified_name VARCHAR NOT NULL UNIQUE,
            created_catalog_sequence BIGINT NOT NULL, created_at TIMESTAMPTZ NOT NULL
        )""",
        """CREATE TABLE canonical.benchmark_versions (
            benchmark_id UUID NOT NULL, benchmark_version INTEGER NOT NULL,
            benchmark_kind VARCHAR NOT NULL, instrument_id UUID, currency VARCHAR NOT NULL,
            calendar_id UUID NOT NULL, methodology_content_id VARCHAR NOT NULL,
            licensing_class VARCHAR NOT NULL, definition_content_id VARCHAR NOT NULL UNIQUE,
            definition_json JSON NOT NULL, created_catalog_sequence BIGINT NOT NULL,
            PRIMARY KEY (benchmark_id, benchmark_version)
        )""",
        """CREATE TABLE canonical.benchmark_series_observations (
            canonical_revision_id UUID PRIMARY KEY, benchmark_id UUID NOT NULL,
            benchmark_version INTEGER NOT NULL, series_kind VARCHAR NOT NULL,
            interval_start TIMESTAMPTZ, interval_end TIMESTAMPTZ NOT NULL,
            session_date DATE, value_decimal DECIMAL(38, 18) NOT NULL,
            currency VARCHAR NOT NULL, calendar_schedule_content_id VARCHAR NOT NULL,
            source_methodology_content_id VARCHAR NOT NULL
        )""",
        """CREATE TABLE canonical.benchmark_constituents (
            canonical_revision_id UUID PRIMARY KEY, benchmark_id UUID NOT NULL,
            benchmark_version INTEGER NOT NULL, instrument_id UUID NOT NULL,
            membership_role VARCHAR NOT NULL, weight DECIMAL(38, 18),
            index_shares DECIMAL(38, 12), divisor_contribution DECIMAL(38, 12),
            valid_from TIMESTAMPTZ NOT NULL, valid_to TIMESTAMPTZ,
            methodology_content_id VARCHAR NOT NULL, source_metadata_json JSON NOT NULL
        )""",
        """CREATE TABLE canonical.risk_free_curves (
            risk_free_curve_id UUID NOT NULL, curve_version INTEGER NOT NULL,
            qualified_name VARCHAR NOT NULL, currency VARCHAR NOT NULL,
            quote_kind VARCHAR NOT NULL, compounding_kind VARCHAR NOT NULL,
            compounding_periods_per_year INTEGER, day_count_kind VARCHAR NOT NULL,
            calendar_id UUID NOT NULL, business_day_policy_content_id VARCHAR NOT NULL,
            definition_content_id VARCHAR NOT NULL UNIQUE, definition_json JSON NOT NULL,
            created_catalog_sequence BIGINT NOT NULL,
            PRIMARY KEY (risk_free_curve_id, curve_version),
            UNIQUE (qualified_name, curve_version)
        )""",
        """CREATE TABLE canonical.risk_free_points (
            canonical_revision_id UUID PRIMARY KEY, risk_free_curve_id UUID NOT NULL,
            curve_version INTEGER NOT NULL, source_release_key VARCHAR NOT NULL,
            effective_date DATE NOT NULL, release_at TIMESTAMPTZ NOT NULL,
            tenor_kind VARCHAR NOT NULL, tenor_count INTEGER NOT NULL,
            maturity_date DATE, rate_or_factor DECIMAL(38, 18) NOT NULL,
            quote_kind VARCHAR NOT NULL, compounding_kind VARCHAR NOT NULL,
            compounding_periods_per_year INTEGER, day_count_kind VARCHAR NOT NULL,
            source_curve_manifest_content_id VARCHAR NOT NULL,
            source_metadata_json JSON NOT NULL
        )""",
    ),
    (),
)

MIGRATION_9 = _step(
    9,
    "research_components_sql_and_workspaces",
    8,
    9,
    (),
    (),
    (
        "CREATE SCHEMA {database}.feature_data",
        "CREATE SCHEMA {database}.label_data",
        """CREATE TABLE {database}.research.workspace_objects (
            workspace_object_id UUID PRIMARY KEY,
            qualified_name VARCHAR NOT NULL UNIQUE,
            created_at TIMESTAMPTZ NOT NULL
        )""",
        """CREATE TABLE {database}.research.workspace_materializations (
            workspace_materialization_id UUID PRIMARY KEY,
            workspace_object_id UUID NOT NULL,
            object_version INTEGER NOT NULL CHECK (object_version >= 1),
            query_text_content_id VARCHAR NOT NULL,
            query_text VARCHAR NOT NULL,
            parameters_content_id VARCHAR NOT NULL,
            parameters_json JSON NOT NULL,
            sql_analyzer_content_id VARCHAR NOT NULL,
            sql_context_content_id VARCHAR NOT NULL,
            limits_content_id VARCHAR NOT NULL,
            dependency_manifest_content_id VARCHAR NOT NULL,
            primary_decision_dependency_ordinal INTEGER,
            lineage_completeness VARCHAR NOT NULL,
            sql_temporal_class VARCHAR NOT NULL,
            temporal_contract_kind VARCHAR NOT NULL,
            information_class VARCHAR NOT NULL,
            safety_status VARCHAR NOT NULL,
            structurally_decision_eligible BOOLEAN NOT NULL,
            execution_content_id VARCHAR NOT NULL UNIQUE,
            output_schema_content_id VARCHAR NOT NULL,
            output_relation_name VARCHAR NOT NULL UNIQUE,
            output_manifest_content_id VARCHAR NOT NULL,
            row_count BIGINT NOT NULL CHECK (row_count >= 0),
            created_at TIMESTAMPTZ NOT NULL,
            UNIQUE (workspace_object_id, object_version)
        )""",
        """CREATE TABLE {database}.research.workspace_dependencies (
            workspace_materialization_id UUID NOT NULL,
            dependency_ordinal INTEGER NOT NULL CHECK (dependency_ordinal >= 1),
            dependency_kind VARCHAR NOT NULL,
            dependency_id UUID NOT NULL,
            dependency_content_id VARCHAR NOT NULL,
            information_class VARCHAR NOT NULL,
            temporal_contract_kind VARCHAR NOT NULL,
            lineage_completeness VARCHAR NOT NULL,
            safety_status VARCHAR NOT NULL,
            PRIMARY KEY (workspace_materialization_id, dependency_ordinal),
            UNIQUE (workspace_materialization_id, dependency_content_id)
        )""",
        """CREATE TABLE {database}.research.component_definitions (
            component_definition_id UUID PRIMARY KEY,
            component_kind VARCHAR NOT NULL,
            qualified_name VARCHAR NOT NULL UNIQUE,
            created_at TIMESTAMPTZ NOT NULL
        )""",
        """CREATE TABLE {database}.research.component_versions (
            component_definition_id UUID NOT NULL,
            component_version VARCHAR NOT NULL,
            registration_sequence INTEGER NOT NULL CHECK (registration_sequence >= 1),
            definition_content_id VARCHAR NOT NULL UNIQUE,
            definition_json JSON NOT NULL,
            created_at TIMESTAMPTZ NOT NULL,
            PRIMARY KEY (component_definition_id, component_version),
            UNIQUE (component_definition_id, registration_sequence)
        )""",
        """CREATE TABLE {database}.research.component_materializations (
            component_materialization_id UUID PRIMARY KEY,
            component_definition_id UUID NOT NULL,
            component_version VARCHAR NOT NULL,
            component_kind VARCHAR NOT NULL,
            research_dataset_build_id UUID NOT NULL,
            parameters_content_id VARCHAR NOT NULL,
            execution_content_id VARCHAR NOT NULL UNIQUE,
            output_schema_content_id VARCHAR NOT NULL,
            output_manifest_content_id VARCHAR NOT NULL,
            output_relation_name VARCHAR NOT NULL UNIQUE,
            information_class VARCHAR NOT NULL,
            temporal_contract_kind VARCHAR NOT NULL,
            lineage_completeness VARCHAR NOT NULL,
            safety_status VARCHAR NOT NULL,
            structurally_decision_eligible BOOLEAN NOT NULL,
            row_count BIGINT NOT NULL CHECK (row_count >= 0),
            computed_count BIGINT NOT NULL CHECK (computed_count >= 0),
            created_at TIMESTAMPTZ NOT NULL
        )""",
        """CREATE TABLE {database}.research.temporal_conformance_results (
            temporal_conformance_result_id UUID PRIMARY KEY,
            component_definition_id UUID NOT NULL,
            component_version VARCHAR NOT NULL,
            suite_content_id VARCHAR NOT NULL,
            implementation_content_id VARCHAR NOT NULL,
            status VARCHAR NOT NULL,
            evidence_content_id VARCHAR NOT NULL,
            created_at TIMESTAMPTZ NOT NULL,
            UNIQUE (
                component_definition_id, component_version,
                suite_content_id, implementation_content_id
            )
        )""",
    ),
)

MIGRATION_10 = _step(
    10,
    "unified_feature_label_graph",
    9,
    10,
    (),
    (),
    (
        """CREATE TABLE {database}.research.component_definition_dependencies (
            component_definition_id UUID NOT NULL,
            component_version VARCHAR NOT NULL,
            input_ordinal INTEGER NOT NULL CHECK (input_ordinal >= 1),
            dependency_definition_id UUID NOT NULL,
            dependency_version VARCHAR NOT NULL,
            dependency_kind VARCHAR NOT NULL,
            dependency_output VARCHAR NOT NULL,
            PRIMARY KEY (
                component_definition_id, component_version, input_ordinal
            )
        )""",
        """CREATE TABLE {database}.research.component_materialization_dependencies (
            component_materialization_id UUID NOT NULL,
            dependency_ordinal INTEGER NOT NULL CHECK (dependency_ordinal >= 1),
            dependency_materialization_id UUID NOT NULL,
            dependency_manifest_content_id VARCHAR NOT NULL,
            PRIMARY KEY (component_materialization_id, dependency_ordinal),
            UNIQUE (
                component_materialization_id, dependency_materialization_id
            )
        )""",
    ),
)

MIGRATION_11 = _step(
    11,
    "enriched_research_dataset_bindings",
    10,
    11,
    (),
    (),
    (
        """CREATE TABLE {database}.research.research_dataset_enrichments (
            research_dataset_build_id UUID PRIMARY KEY,
            base_research_dataset_build_id UUID NOT NULL,
            dataset_role VARCHAR NOT NULL,
            information_class VARCHAR NOT NULL,
            temporal_contract_kind VARCHAR NOT NULL,
            lineage_completeness VARCHAR NOT NULL,
            safety_status VARCHAR NOT NULL,
            structurally_decision_eligible BOOLEAN NOT NULL
        )""",
        """CREATE TABLE {database}.research.research_dataset_enrichment_inputs (
            research_dataset_build_id UUID NOT NULL,
            input_ordinal INTEGER NOT NULL CHECK (input_ordinal >= 1),
            input_kind VARCHAR NOT NULL,
            component_materialization_id UUID NOT NULL,
            dependency_manifest_content_id VARCHAR NOT NULL,
            selected_outputs_json JSON NOT NULL,
            PRIMARY KEY (research_dataset_build_id, input_ordinal),
            UNIQUE (research_dataset_build_id, component_materialization_id)
        )""",
    ),
)

MIGRATION_12 = _step(
    12,
    "alpha_validation_foundation",
    11,
    12,
    (),
    (),
    (
        """CREATE TABLE {database}.analysis.validation_schemes (
            validation_scheme_id UUID PRIMARY KEY,
            qualified_name VARCHAR NOT NULL UNIQUE,
            created_at TIMESTAMPTZ NOT NULL
        )""",
        """CREATE TABLE {database}.analysis.validation_scheme_versions (
            validation_scheme_id UUID NOT NULL,
            definition_version INTEGER NOT NULL,
            definition_content_id VARCHAR NOT NULL UNIQUE,
            definition_json JSON NOT NULL,
            created_at TIMESTAMPTZ NOT NULL,
            PRIMARY KEY (validation_scheme_id, definition_version)
        )""",
        """CREATE TABLE {database}.analysis.validation_plans (
            validation_plan_id UUID PRIMARY KEY,
            validation_scheme_id UUID NOT NULL,
            definition_version INTEGER NOT NULL,
            research_dataset_build_id UUID NOT NULL,
            execution_content_id VARCHAR NOT NULL UNIQUE,
            membership_content_id VARCHAR NOT NULL,
            fold_count INTEGER NOT NULL,
            sample_count BIGINT NOT NULL,
            purged_count BIGINT NOT NULL,
            embargoed_count BIGINT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL
        )""",
        """CREATE TABLE {database}.analysis.validation_membership (
            validation_plan_id UUID NOT NULL,
            fold_index INTEGER NOT NULL,
            decision_at TIMESTAMPTZ NOT NULL,
            instrument_id UUID NOT NULL,
            validation_role VARCHAR NOT NULL,
            sample_state VARCHAR NOT NULL,
            reason_code VARCHAR NOT NULL,
            label_start_at TIMESTAMPTZ,
            label_end_at TIMESTAMPTZ,
            PRIMARY KEY (
                validation_plan_id, fold_index, decision_at, instrument_id
            )
        )""",
        """CREATE TABLE {database}.analysis.alpha_definitions (
            alpha_analysis_definition_id UUID PRIMARY KEY,
            qualified_name VARCHAR NOT NULL UNIQUE,
            created_at TIMESTAMPTZ NOT NULL
        )""",
        """CREATE TABLE {database}.analysis.alpha_definition_versions (
            alpha_analysis_definition_id UUID NOT NULL,
            definition_version INTEGER NOT NULL,
            definition_content_id VARCHAR NOT NULL UNIQUE,
            definition_json JSON NOT NULL,
            created_at TIMESTAMPTZ NOT NULL,
            PRIMARY KEY (alpha_analysis_definition_id, definition_version)
        )""",
        """CREATE TABLE {database}.analysis.alpha_results (
            alpha_analysis_result_id UUID PRIMARY KEY,
            alpha_analysis_definition_id UUID NOT NULL,
            definition_version INTEGER NOT NULL,
            research_dataset_build_id UUID NOT NULL,
            execution_content_id VARCHAR NOT NULL UNIQUE,
            output_content_id VARCHAR NOT NULL,
            created_at TIMESTAMPTZ NOT NULL
        )""",
        """CREATE TABLE {database}.analysis.alpha_metric_results (
            alpha_analysis_result_id UUID NOT NULL,
            feature_name VARCHAR NOT NULL,
            label_name VARCHAR NOT NULL,
            metric_kind VARCHAR NOT NULL,
            decision_at TIMESTAMPTZ,
            metric_state VARCHAR NOT NULL,
            estimate DOUBLE,
            observation_count BIGINT NOT NULL,
            reason_code VARCHAR,
            PRIMARY KEY (
                alpha_analysis_result_id, feature_name, label_name,
                metric_kind, decision_at
            )
        )""",
    ),
)

MIGRATIONS = (
    MIGRATION_2,
    MIGRATION_3,
    MIGRATION_4,
    MIGRATION_5,
    MIGRATION_6,
    MIGRATION_7,
    MIGRATION_8,
    MIGRATION_9,
    MIGRATION_10,
    MIGRATION_11,
    MIGRATION_12,
)


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
