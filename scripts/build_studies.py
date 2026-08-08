"""Build deterministic, output-free notebooks from reviewable source cells."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from textwrap import dedent
from typing import Literal, NamedTuple


class Cell(NamedTuple):
    """One source cell before notebook serialization."""

    kind: Literal["markdown", "code"]
    source: str


def markdown(source: str) -> Cell:
    """Create one normalized Markdown source cell."""
    return Cell("markdown", dedent(source).strip())


def code(source: str) -> Cell:
    """Create one normalized Python source cell."""
    return Cell("code", dedent(source).strip())


def serialize_notebook(name: str, cells: list[Cell]) -> str:
    """Serialize one stable version-4 notebook with no execution artifacts."""
    slug = name.split("_", 1)[0]
    serialized = []
    for position, cell in enumerate(cells, 1):
        base = {
            "cell_type": cell.kind,
            "id": f"study-{slug}-{position:02d}",
            "metadata": {},
            "source": cell.source,
        }
        if cell.kind == "code":
            base.update({"execution_count": None, "outputs": []})
        serialized.append(base)
    notebook = {
        "cells": serialized,
        "metadata": {
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            },
            "language_info": {"name": "python", "version": "3.12"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    return json.dumps(notebook, indent=1, ensure_ascii=False) + "\n"


def write_notebook(name: str, cells: list[Cell], *, check: bool) -> None:
    """Write one notebook or fail if its committed serialization is stale."""
    target = Path(__file__).resolve().parents[1] / "studies" / name
    serialized = serialize_notebook(name, cells)
    if check:
        if not target.is_file() or target.read_text(encoding="utf-8") != serialized:
            raise SystemExit(f"{target}: regenerate with scripts/build_studies.py")
        return
    target.write_text(serialized, encoding="utf-8")


def growth_inflation_notebook() -> list[Cell]:
    """Return the growth-and-inflation quadrant study."""
    return [
        markdown(
            r"""
            # Growth and inflation quadrants

            This notebook asks how a fixed set of liquid cross-asset proxies behaves after four
            combinations of real-time industrial-production growth and consumer-price inflation.
            It is a descriptive regime study, not a causal model, forecast, or trading strategy.

            The hypothesis and thresholds were recorded in `studies/README.md` before live
            execution. The committed notebook contains no saved provider values or outputs.
            Running it retrieves live Alpha Vantage and FRED or ALFRED data into a temporary
            directory, builds every table and figure in memory, and removes the raw responses.

            **Primary protocol.** A decision is the last common ETF trading session in a complete
            calendar month. Information must have been available at least one calendar day before
            that close. The unit of analysis is one decision month. The primary horizon is the
            next calendar month. The four primary estimands are average two-factor contrasts:
            high minus lower inflation for `GLD` and `DBC`, and contracting minus expanding
            growth for `SPY` and `IEF`. The other factor and its interaction remain in each model.
            One-month simultaneous intervals control this four-contrast family; longer horizons,
            threshold sweeps, and latest-revised comparisons are exploratory.
            """
        ),
        code(
            """
            import matplotlib.pyplot as plt
            import pandas as pd

            from studies._support import (
                CORE_SYMBOLS,
                STUDY_START,
                acquire_latest_series,
                acquire_monthly_prices,
                acquire_vintage_histories,
                assert_component_periods_match,
                build_point_in_time_levels,
                classification_transition_table,
                compare_statistics,
                configure_plots,
                factorial_contrast_statistics,
                familywise_primary_intervals,
                feature_provenance_summary,
                forward_labels,
                latest_revised_year_over_year,
                momentum_baseline,
                open_live_session,
                plot_coverage,
                plot_feature_comparison,
                plot_normalized_prices,
                plot_regime_contrasts,
                plot_regime_distributions,
                plot_regime_means,
                plot_regime_timeline,
                plot_revision_gap,
                plot_sample_sizes,
                plot_sensitivity_heatmap,
                point_in_time_year_over_year,
                regime_statistics,
                regime_style,
                simultaneous_interval_family,
                study_run_manifest,
                temporal_factorial_stability,
                unconditional_statistics,
                validate_study_outputs,
            )

            configure_plots()
            pd.set_option("display.max_columns", 20)
            session = open_live_session()
            """
        ),
        markdown(
            r"""
            ## Pre-analysis protocol and universe

            `SPY`, `IEF`, `GLD`, `DBC`, and `UUP` represent equities, intermediate Treasuries,
            gold, broad commodities, and the United States dollar. Adjusted closes account for
            distributions and splits according to the provider's adjustment method. Month-end
            sampling reduces unequal holiday calendars to one common decision frequency.

            `CPIAUCSL` measures the consumer price level and `INDPRO` measures industrial output.
            Both are revised. Their values therefore need an availability interval as well as an
            observation period. The one-day operational lag is conservative: a release that
            becomes available on a decision date is not used until the next calendar day.

            Adjusted ETF closes are total-return proxies, not executable transaction prices. The
            code acquires one year of price history before the analysis window so the twelve-month
            momentum baseline exists on the first eligible outcome date. It rejects missing or
            duplicate calendar months and common closes too far from month end. Raw responses and
            normalized objects also round-trip through a temporary DuckDB database. That storage
            check is part of the end-to-end path and disappears when the session closes.
            """
        ),
        code(
            """
            price_history, market_provenance = acquire_monthly_prices(session, CORE_SYMBOLS)
            prices = price_history.loc[STUDY_START:]
            series_ids = ("CPIAUCSL", "INDPRO")
            histories = acquire_vintage_histories(session, series_ids, prices.index)
            latest = acquire_latest_series(session, series_ids)
            staleness = {series_id: pd.Timedelta(days=62) for series_id in series_ids}
            point_in_time = build_point_in_time_levels(
                histories,
                prices.index,
                staleness,
            )
            feature_provenance = feature_provenance_summary(point_in_time)
            manifest = study_run_manifest(
                prices,
                series_ids=series_ids,
                thresholds="growth=0%; inflation=3%",
                staleness=staleness,
            )
            display(manifest, market_provenance, feature_provenance)
            """
        ),
        markdown(
            r"""
            ## Coverage is part of the result

            A long price history does not guarantee a complete joint panel. ETF inception dates,
            missing sessions, release schedules, explicit missing macro observations, and the
            staleness ceiling can all remove decisions. The first panel below shows provider
            history depth. The second reports the share of decision dates with an admissible
            macro version. Sparse coverage is not filled or silently replaced with an older
            nonmissing observation.

            Three dates have different jobs. The **observation period** says which month the
            level describes. `available_from` and `available_through` define the source version's
            historical validity interval. `retrieved_at` records when this execution obtained the
            response. A row is admissible only when the lagged decision cutoff lies inside its
            availability interval and its observation age is below the declared ceiling.
            """
        ),
        code(
            """
            figure, _ = plot_coverage(market_provenance, feature_provenance)
            plt.show()
            plt.close(figure)
            """
        ),
        markdown(
            r"""
            ## From source levels to point-in-time features

            For decision date \(d\), the code selects one complete vintage snapshot known at the
            information cutoff. If \(x_{d,t}\) is the level for its newest admissible source month
            \(t\), the feature is \(100(x_{d,t}/x_{d,t-12}-1)\). Numerator and denominator come
            from one coherent vintage and exact observation months, not values captured on two
            different decision dates. This matters when benchmark revisions rebase a level path.

            Component provenance records expected and actual periods, availability intervals,
            source definition fields, and retrieval time. The latest-revised comparison preserves
            those exact component periods and swaps in today's values. It isolates revision
            substitution rather than inventing an earlier release date or changing the window.

            The plot is diagnostic. A visible gap shows where retrospective history differs from
            the feature available at the time; agreement does not prove that the timing policy was
            unnecessary.
            """
        ),
        code(
            """
            point_yoy_result = point_in_time_year_over_year(histories, point_in_time)
            latest_yoy_result = latest_revised_year_over_year(point_in_time, latest)
            point_yoy = point_yoy_result.frame
            latest_yoy = latest_yoy_result.frame
            point_features = point_yoy.rename(
                columns={"CPIAUCSL": "CPI inflation", "INDPRO": "Industrial production growth"}
            )
            latest_features = latest_yoy.set_axis(point_features.columns, axis="columns")
            figure, _ = plot_feature_comparison(
                point_features,
                latest_features,
                tuple(point_features.columns),
            )
            plt.show()
            plt.close(figure)
            """
        ),
        markdown(
            r"""
            ## Hypothesis and regime construction

            The primary rules are fixed before outcome analysis. Inflation is high at or above
            three percent. Industrial-production growth is contracting at or below zero. The
            Cartesian product yields four named quadrants. These boundaries are transparent and
            interpretable, but they are not natural laws. Later sensitivity analysis evaluates a
            complete nearby grid rather than choosing the threshold that looks best.

            `GLD` and `DBC` are the focal inflation assets; `SPY` and `IEF` are the focal growth
            assets. “Focal” does not claim that their effects rank above every other ETF. For each
            outcome, an effect-coded saturated model uses growth, inflation, and their interaction.
            The inflation coefficient averages the high-minus-lower simple effect equally across
            expanding and contracting states; the growth coefficient averages across inflation
            states. This factorial estimand prevents unequal composition of the other macro
            dimension from masquerading as the focal effect.

            The timeline and phase portrait expose persistence and sparse quadrants before any
            outcome statistic is read. Adjacent months in one uninterrupted state form one episode,
            so a month count is not an independent-event count.
            """
        ),
        code(
            """
            def growth_inflation_regime(
                features: pd.DataFrame,
                *,
                inflation_boundary: float = 3.0,
                growth_boundary: float = 0.0,
            ) -> pd.Series:
                inflation = features["CPIAUCSL"]
                growth = features["INDPRO"]
                valid = inflation.notna() & growth.notna()
                state = pd.Series(pd.NA, index=features.index, dtype="string")
                state.loc[valid & growth.gt(growth_boundary) & inflation.lt(inflation_boundary)] = (
                    "expanding / lower inflation"
                )
                state.loc[valid & growth.gt(growth_boundary) & inflation.ge(inflation_boundary)] = (
                    "expanding / high inflation"
                )
                state.loc[valid & growth.le(growth_boundary) & inflation.lt(inflation_boundary)] = (
                    "contracting / lower inflation"
                )
                state.loc[valid & growth.le(growth_boundary) & inflation.ge(inflation_boundary)] = (
                    "contracting / high inflation"
                )
                return state

            def inflation_state(
                features: pd.DataFrame,
                boundary: float = 3.0,
            ) -> pd.Series:
                values = features["CPIAUCSL"]
                valid = features[["CPIAUCSL", "INDPRO"]].notna().all(axis=1)
                state = pd.Series(pd.NA, index=features.index, dtype="string")
                state.loc[valid & values.lt(boundary)] = "lower inflation"
                state.loc[valid & values.ge(boundary)] = "high inflation"
                return state

            def growth_state(
                features: pd.DataFrame,
                boundary: float = 0.0,
            ) -> pd.Series:
                values = features["INDPRO"]
                valid = features[["CPIAUCSL", "INDPRO"]].notna().all(axis=1)
                state = pd.Series(pd.NA, index=features.index, dtype="string")
                state.loc[valid & values.gt(boundary)] = "expanding"
                state.loc[valid & values.le(boundary)] = "contracting"
                return state

            point_regimes = growth_inflation_regime(point_yoy)
            latest_regimes = growth_inflation_regime(latest_yoy)
            point_inflation_states = inflation_state(point_yoy)
            point_growth_states = growth_state(point_yoy)
            display(point_regimes.value_counts(dropna=False).rename("decision count"))
            figure, _ = plot_regime_timeline(
                point_yoy["CPIAUCSL"],
                point_regimes,
                title="Real-time inflation with growth-inflation quadrant markers",
                ylabel="Year-over-year percent change",
                boundaries=(3.0,),
            )
            plt.show()
            plt.close(figure)

            figure, axis = plt.subplots(figsize=(9, 6.5))
            for regime in (
                "expanding / lower inflation",
                "expanding / high inflation",
                "contracting / lower inflation",
                "contracting / high inflation",
            ):
                color, marker = regime_style(regime)
                selected = point_regimes.eq(regime).fillna(False)
                axis.scatter(
                    point_yoy.loc[selected, "INDPRO"],
                    point_yoy.loc[selected, "CPIAUCSL"],
                    label=regime,
                    marker=marker,
                    color=color,
                    alpha=0.75,
                )
            axis.axvline(0, color="#333333", linestyle="--", linewidth=0.9)
            axis.axhline(3, color="#333333", linestyle="--", linewidth=0.9)
            axis.set(
                title="Real-time growth-inflation phase portrait",
                xlabel="Industrial-production year-over-year growth (percent)",
                ylabel="Consumer-price year-over-year inflation (percent)",
            )
            axis.legend(ncol=2)
            figure.tight_layout()
            plt.show()
            plt.close(figure)
            """
        ),
        markdown(
            r"""
            ## Future labels and conventional baselines

            The price panel is passed to `persistra.research.forward_returns`, which returns a
            dedicated label object and records the end date of every horizon. No forward return
            enters the feature frame. The final one, three, or twelve rows remain missing when a
            complete future horizon is unavailable.

            Two baselines discourage regime storytelling. The unconditional table asks whether
            a regime adds information beyond the same macro-eligible sample. The trailing
            twelve-month price momentum split is a conventional asset-only time-series comparison
            using information observable at the same decision date. The normalized-price plot
            provides historical context but is not a simulated portfolio.

            For price \(P_d\), an \(h\)-month label is \(R_{d,h}=P_{d+h}/P_d-1\). Each label
            stores its actual ending close. Live checks require its calendar period to be exactly
            \(h\) months after the start, so a missing month cannot silently lengthen the outcome.
            Terminal labels remain missing rather than using a shorter horizon.
            """
        ),
        code(
            """
            labels = forward_labels(prices)
            eligible = point_regimes.notna()
            unconditional = unconditional_statistics(labels, eligible=eligible)
            momentum = momentum_baseline(price_history, labels, eligible=eligible)
            display(unconditional, momentum)
            figure, _ = plot_normalized_prices(prices)
            plt.show()
            plt.close(figure)
            """
        ),
        markdown(
            r"""
            ## Conditional summaries and uncertainty

            Each descriptive row reports observed count, outcome-eligible episode count, coverage,
            mean simple return, horizon-return standard deviation, positive-return share, and a
            pointwise two-sided interval. One-month annualized volatility is a separate column.
            The Bartlett-kernel heteroskedasticity-and-autocorrelation-consistent (HAC) bandwidth
            is the larger of the overlap floor \(h-1\) and a predeclared automatic time-series
            rule. It can address covariance beyond mechanical
            overlap, but remains a normal large-sample approximation.

            The one-month summary also exercises Persistra's regime summarizer, including its
            episode-aware drawdown calculation. The four primary one-month factorial contrasts
            receive Bonferroni simultaneous intervals. Gray means only that a result falls below
            the display rule of twelve outcomes per side, six per factorial cell, and two
            outcome-eligible episodes per side; it does not guarantee reliable inference.
            Secondary horizons and sensitivity families remain exploratory. First/second-half and
            leave-one-episode-out tables expose fragility without redefining the primary estimate.
            """
        ),
        code(
            """
            point_statistics = regime_statistics(labels, point_regimes)
            latest_statistics = regime_statistics(labels, latest_regimes)
            inflation_contrasts = factorial_contrast_statistics(
                labels,
                point_inflation_states,
                point_growth_states,
                treated="high inflation",
                reference="lower inflation",
                adjustment_levels=("contracting", "expanding"),
                assets=("GLD", "DBC"),
            )
            growth_contrasts = factorial_contrast_statistics(
                labels,
                point_growth_states,
                point_inflation_states,
                treated="contracting",
                reference="expanding",
                adjustment_levels=("high inflation", "lower inflation"),
                assets=("SPY", "IEF"),
            )
            primary_contrasts = familywise_primary_intervals(
                pd.concat([inflation_contrasts, growth_contrasts], ignore_index=True)
            )
            display(point_statistics, primary_contrasts)
            figure, _ = plot_regime_means(
                point_statistics,
                title="Growth-inflation quadrants and one-month outcomes",
            )
            plt.show()
            plt.close(figure)

            figure, _ = plot_regime_contrasts(
                primary_contrasts,
                title="Predeclared one-month boundary contrasts",
            )
            plt.show()
            plt.close(figure)
            """
        ),
        markdown(
            r"""
            ## Distributions, episodes, and sample size

            Conditional means can be dominated by a few crisis months. Box plots retain the
            middle spread and skew without displaying every raw observation, while the count plot
            makes rare quadrants unmistakable. Neither plot makes months independent: adjacent
            decisions can belong to the same macro episode, and the same shock can influence
            several horizons and assets.
            """
        ),
        code(
            """
            figure, _ = plot_regime_distributions(
                labels[1],
                point_regimes,
                assets=("SPY", "IEF", "GLD", "DBC"),
                title="One-month outcome distributions by quadrant",
            )
            plt.show()
            plt.close(figure)

            figure, _ = plot_sample_sizes(point_statistics)
            plt.show()
            plt.close(figure)
            """
        ),
        markdown(
            r"""
            ## Sensitivity without threshold shopping

            Two one-dimensional sweeps preserve the factorial estimand. Inflation boundaries of
            2.5, 3.0, and 3.5 percent are evaluated for `GLD` and `DBC` while the primary growth
            factor remains in the model. Growth boundaries of -1, 0, and 1 percent are evaluated
            for `SPY` and `IEF` while the primary inflation factor remains. This is not a Cartesian
            search for the best diagonal quadrant.

            The long table retains counts, outcome-eligible episodes, HAC errors, and intervals.
            One exploratory Bonferroni family covers every displayed threshold-asset effect.
            Cells below the minimum-data display rule are explicitly marked and masked in the
            two feature-specific heatmaps; they are not zero effects. Separate panels avoid
            implying that nonfocal feature-asset pairs were estimated. Visual stability is a
            robustness diagnostic, not a new specification-selection rule.
            """
        ),
        code(
            """
            sensitivity_rows = []
            for boundary in (2.5, 3.0, 3.5):
                table = factorial_contrast_statistics(
                    {1: labels[1]},
                    inflation_state(point_yoy, boundary),
                    point_growth_states,
                    treated="high inflation",
                    reference="lower inflation",
                    adjustment_levels=("contracting", "expanding"),
                    assets=("GLD", "DBC"),
                )
                table.insert(0, "boundary", boundary)
                table.insert(0, "feature", "inflation")
                sensitivity_rows.append(table)
            for boundary in (-1.0, 0.0, 1.0):
                table = factorial_contrast_statistics(
                    {1: labels[1]},
                    growth_state(point_yoy, boundary),
                    point_inflation_states,
                    treated="contracting",
                    reference="expanding",
                    adjustment_levels=("high inflation", "lower inflation"),
                    assets=("SPY", "IEF"),
                )
                table.insert(0, "boundary", boundary)
                table.insert(0, "feature", "growth")
                sensitivity_rows.append(table)
            sensitivity_table = simultaneous_interval_family(
                pd.concat(sensitivity_rows, ignore_index=True),
                family_id="growth-inflation threshold family",
            )
            inflation_rows = sensitivity_table.loc[sensitivity_table["feature"].eq("inflation")]
            inflation_sensitivity = inflation_rows.pivot(
                index="boundary", columns="asset", values="mean_difference"
            ).where(
                inflation_rows.pivot(
                    index="boundary", columns="asset", values="meets_display_threshold"
                )
            )
            growth_rows = sensitivity_table.loc[sensitivity_table["feature"].eq("growth")]
            growth_sensitivity = growth_rows.pivot(
                index="boundary", columns="asset", values="mean_difference"
            ).where(
                growth_rows.pivot(
                    index="boundary", columns="asset", values="meets_display_threshold"
                )
            )
            display(sensitivity_table, inflation_sensitivity, growth_sensitivity)
            figure, _ = plot_sensitivity_heatmap(
                inflation_sensitivity,
                title="Inflation-boundary effects for focal inflation assets",
                color_label="Difference in one-month mean return",
            )
            plt.show()
            plt.close(figure)

            figure, _ = plot_sensitivity_heatmap(
                growth_sensitivity,
                title="Growth-boundary effects for focal growth assets",
                color_label="Difference in one-month mean return",
            )
            plt.show()
            plt.close(figure)
            """
        ),
        markdown(
            r"""
            ## Latest-revised bias diagnostic

            The latest-revised classification is deliberately wrong for historical decisions.
            Comparing it with the point-in-time summary shows whether revisions change membership
            or conditional means. The revision-gap plot stays in
            the diagnostic layer: future revisions never become features in the primary analysis.

            A small difference is a finding about these series and dates, not permission to ignore
            availability in other research.

            The transition table includes an explicit unclassified state. It separates boundary
            crossings from dates lost to component availability. The conditional-summary
            comparison is therefore a total revision-plus-availability diagnostic; it is not the
            primary factorial estimate. The stability table belongs to robustness: it reports
            first/second-half and leave-one-episode-out estimates using only real-time regimes.
            """
        ),
        code(
            """
            revision_comparison = compare_statistics(point_statistics, latest_statistics)
            classification_changes = classification_transition_table(
                point_regimes,
                latest_regimes,
            )
            inflation_stability = temporal_factorial_stability(
                labels,
                point_inflation_states,
                point_growth_states,
                treated="high inflation",
                reference="lower inflation",
                adjustment_levels=("contracting", "expanding"),
                assets=("GLD", "DBC"),
            )
            growth_stability = temporal_factorial_stability(
                labels,
                point_growth_states,
                point_inflation_states,
                treated="contracting",
                reference="expanding",
                adjustment_levels=("high inflation", "lower inflation"),
                assets=("SPY", "IEF"),
            )
            factorial_stability = pd.concat(
                [inflation_stability, growth_stability], ignore_index=True
            )
            display(revision_comparison, classification_changes, factorial_stability)
            figure, _ = plot_revision_gap(
                point_yoy["CPIAUCSL"],
                latest_yoy["CPIAUCSL"],
                title="Consumer-price inflation revision substitution gap",
            )
            plt.show()
            plt.close(figure)
            """
        ),
        markdown(
            r"""
            ## Limitations and adversarial checks

            The ETF universe is selected with current knowledge and begins after every core proxy
            exists. It embeds survivorship and product-design choices. Adjusted closes omit
            transaction costs, taxes, spreads, and executable decision timing. Macro staleness and
            monthly sampling simplify intramonth release mechanics. Regime observations cluster,
            confidence intervals are approximate, and many assets, horizons, quadrants, and
            sensitivity cells create multiple-testing risk.

            The final code asserts alignment, provenance completeness, positive prices, separate
            labels, multiple regimes, nonempty summaries, and finite observed means. These checks
            protect mechanics, not the economic hypothesis.

            Current FRED definition metadata are attached to historical vintage rows, so the
            notebook cannot prove that every old benchmark definition was unchanged. Within-vintage
            ratios avoid cross-vintage level arithmetic, but benchmark changes remain part of the
            diagnostic. See the [ALFRED real-time-period guide](https://fred.stlouisfed.org/docs/api/fred/realtime_period.html),
            [Alpha Vantage API documentation](https://www.alphavantage.co/documentation/), and
            Newey and West's [HAC covariance paper](https://doi.org/10.2307/1913610).
            """
        ),
        code(
            """
            audit = validate_study_outputs(
                prices,
                point_in_time,
                labels,
                point_regimes,
                point_statistics,
                expected_regimes=frozenset(
                    {
                        "expanding / lower inflation",
                        "expanding / high inflation",
                        "contracting / lower inflation",
                        "contracting / high inflation",
                    }
                ),
                transformed=point_yoy_result,
            )
            assert_component_periods_match(point_yoy_result, latest_yoy_result)
            assert set(point_in_time.frame.columns).isdisjoint(labels[1].frame.columns)
            matched = point_in_time.provenance["available_from"].notna()
            assert point_in_time.provenance.loc[matched, "available_from"].le(
                point_in_time.provenance.loc[matched, "decision_date"] - pd.Timedelta(days=1)
            ).all()
            display(audit)
            session.close()
            """
        ),
        markdown(
            r"""
            ## Interpretation after execution

            Read coverage and counts before means, then compare intervals, distributions, the
            unconditional and momentum baselines, the complete sensitivity grid, and the
            latest-revised diagnostic. Retain null, unstable, and contrary results. Any observed
            association describes this fixed sample; it is not causal evidence or proof of a
            profitable allocation rule.
            """
        ),
    ]


def labor_notebook() -> list[Cell]:
    """Return the labor-deterioration study."""
    return [
        markdown(
            r"""
            # Real-time labor-market deterioration

            This notebook asks how cross-asset outcomes differ after a real-time unemployment
            deterioration alert. The alert is Sahm-rule-like, but it is calculated directly from
            the vintage unemployment rate and is not the official recession indicator.

            The design was fixed before results were retrieved. Live outputs are temporary. The
            committed notebook explains the method without storing provider observations,
            figures, tables, or empirical conclusions.

            **Primary protocol.** Each unit is the last common ETF trading session of a complete
            month, and the information cutoff is one calendar day earlier. The treatment is a
            deterioration alert; the reference is no alert; the primary horizon is one calendar
            month. The four primary outcomes are `SPY`, `DBC`, `TLT`, and the paired return spread
            `TLT-SHY`. Expected directions are negative for the two risk-asset contrasts and
            positive for the Treasury contrasts. Bonferroni intervals cover this one-month family.
            Longer horizons, alternative alert boundaries, revised history, and stability splits
            are exploratory.
            """
        ),
        code(
            """
            import matplotlib.pyplot as plt
            import pandas as pd

            from studies._support import (
                CORE_SYMBOLS,
                STUDY_START,
                acquire_latest_series,
                acquire_monthly_prices,
                acquire_vintage_histories,
                assert_component_periods_match,
                build_point_in_time_levels,
                classification_transition_table,
                combined_outcome_labels,
                compare_statistics,
                configure_plots,
                familywise_primary_intervals,
                feature_provenance_summary,
                forward_labels,
                latest_revised_counterpart,
                latest_revised_labor_deterioration,
                momentum_baseline,
                open_live_session,
                plot_coverage,
                plot_feature_comparison,
                plot_normalized_prices,
                plot_regime_contrasts,
                plot_regime_distributions,
                plot_regime_means,
                plot_regime_timeline,
                plot_revision_gap,
                plot_sample_sizes,
                plot_sensitivity_heatmap,
                point_in_time_labor_deterioration,
                regime_contrast_statistics,
                regime_statistics,
                return_spread_labels,
                simultaneous_interval_family,
                study_run_manifest,
                temporal_contrast_stability,
                unconditional_statistics,
                validate_study_outputs,
            )

            configure_plots()
            pd.set_option("display.max_columns", 20)
            session = open_live_session()
            """
        ),
        markdown(
            r"""
            ## Hypothesis, assets, and source series

            The core cross-asset proxies are extended with `TLT` and `SHY`. The additions separate
            long- and short-duration Treasury behavior when labor conditions weaken. The fixed ETF
            set is liquid and interpretable, but it is not survivorship-free.

            `UNRATE` is a monthly, seasonally adjusted unemployment rate that can be revised. The
            hypothesis is that equity and commodity outcomes are weaker, and high-quality bond
            outcomes stronger, after an alert. This is an association hypothesis. Labor releases
            do not cause every subsequent market move, and an alert is not a deterministic market
            timing signal.

            `TLT-SHY` is a within-date difference of two forward returns, not the difference of
            separately estimated tables. It retains the covariance between long- and short-duration
            Treasuries and directly asks whether maturity exposure behaves differently during an
            alert. `IEF` remains visible as an intermediate-duration reference. Adjusted closes
            capture provider adjustments but omit spreads, taxes, and any execution rule.
            """
        ),
        code(
            """
            symbols = (*CORE_SYMBOLS, "TLT", "SHY")
            price_history, market_provenance = acquire_monthly_prices(session, symbols)
            prices = price_history.loc[STUDY_START:]
            histories = acquire_vintage_histories(session, ("UNRATE",), prices.index)
            latest = acquire_latest_series(session, ("UNRATE",))
            staleness = {"UNRATE": pd.Timedelta(days=62)}
            point_in_time = build_point_in_time_levels(
                histories,
                prices.index,
                staleness,
            )
            latest_levels = latest_revised_counterpart(point_in_time, latest)
            feature_provenance = feature_provenance_summary(point_in_time)
            manifest = study_run_manifest(
                prices,
                series_ids=("UNRATE",),
                thresholds="labor alert=0.5 percentage points",
                staleness=staleness,
            )
            display(manifest, market_provenance, feature_provenance)
            """
        ),
        markdown(
            r"""
            ## Coverage and release staleness

            Month-end decisions often use an unemployment observation for an earlier reference
            month because the current month's survey has not been released. That is correct
            point-in-time behavior. The maximum-staleness rule permits ordinary publication delay
            but rejects a feature if releases stop arriving. Missing or deleted source values stay
            missing rather than falling back to a more favorable older observation.

            Observation month, source availability, and retrieval time are distinct. The code
            selects only a version whose daily availability interval contains the lagged cutoff.
            It rejects matches older than 62 days. Market and macro results are saved to and
            reloaded from a temporary DuckDB database before analysis, verifying the storage
            boundary without publishing a snapshot. The coverage table should be read before the
            signal because a valid current level does not guarantee all 15 required source months.
            """
        ),
        code(
            """
            figure, _ = plot_coverage(market_provenance, feature_provenance)
            plt.show()
            plt.close(figure)
            """
        ),
        markdown(
            r"""
            ## Point-in-time unemployment versus latest-revised history

            Persistra selects the source version whose availability interval contains the lagged
            decision date. The counterfactual latest-revised view retains the same selected
            observation month and substitutes today's value. That comparison isolates revisions;
            it does not pretend the observation itself was published earlier.

            The level plot is an audit of information timing. Small visual differences can still
            matter near a fixed alert threshold, so classification changes are examined later.
            """
        ),
        code(
            """
            point_levels = point_in_time.frame.rename(columns={"UNRATE": "Unemployment rate"})
            revised_levels = latest_levels.set_axis(point_levels.columns, axis="columns")
            figure, _ = plot_feature_comparison(
                point_levels,
                revised_levels,
                ("Unemployment rate",),
            )
            plt.show()
            plt.close(figure)
            """
        ),
        markdown(
            r"""
            ## Alert construction

            At each decision, the code opens one as-of unemployment vintage and requests 15 exact,
            consecutive observation months. Let \(u_{d,t}\) be the unemployment rate for source
            month \(t\) in the vintage known at cutoff \(d\), and let
            \(m_{d,t}=(u_{d,t}+u_{d,t-1}+u_{d,t-2})/3\). The signal is
            \(m_{d,t}-\min(m_{d,t-1},\ldots,m_{d,t-12})\). The current mean is excluded from its
            own baseline by construction. An alert begins at 0.5 percentage points.

            This resembles the intuition of the Sahm rule but is deliberately calculated from the
            selected `UNRATE` vintage and is not the official indicator. The component plot shows
            the latest level, current three-month mean, and prior twelve-month low so the reader
            can audit what moves the gap. Exact source-month provenance prevents repeated decision
            rows from standing in for distinct labor observations.
            """
        ),
        code(
            """
            def labor_regime(signal: pd.Series, *, boundary: float = 0.5) -> pd.Series:
                regime = pd.Series(pd.NA, index=signal.index, dtype="string")
                regime.loc[signal.notna() & signal.lt(boundary)] = "no alert"
                regime.loc[signal.notna() & signal.ge(boundary)] = "deterioration alert"
                return regime

            point_signal_result = point_in_time_labor_deterioration(
                histories["UNRATE"], point_in_time
            )
            latest_signal_result = latest_revised_labor_deterioration(
                point_in_time, latest["UNRATE"]
            )
            point_signal = point_signal_result.frame["UNRATE"]
            latest_signal = latest_signal_result.frame["UNRATE"]
            point_regimes = labor_regime(point_signal)
            latest_regimes = labor_regime(latest_signal)
            display(point_regimes.value_counts(dropna=False).rename("decision count"))
            figure, _ = plot_regime_timeline(
                point_signal,
                point_regimes,
                title="Real-time labor deterioration signal",
                ylabel="Percentage-point increase",
                boundaries=(0.5,),
            )
            plt.show()
            plt.close(figure)

            component_values = (
                point_signal_result.provenance.loc[
                    point_signal_result.provenance["view"].eq("point-in-time")
                ]
                .pivot(index="decision_date", columns="component", values="value")
                .astype("Float64")
            )
            ordered_components = [f"month_{offset}" for offset in range(-14, 1)]
            smoothed = (
                component_values[ordered_components]
                .T.rolling(3, min_periods=3)
                .mean()
                .T
            )
            labor_components = pd.DataFrame(
                {
                    "latest unemployment rate": component_values["month_0"],
                    "current three-month mean": smoothed["month_0"],
                    "prior twelve-month low": smoothed[
                        [f"month_{offset}" for offset in range(-12, 0)]
                    ].min(axis=1),
                }
            )
            figure, axis = plt.subplots(figsize=(12, 5.5))
            for column, style in zip(
                labor_components.columns,
                ("-", "--", ":"),
                strict=True,
            ):
                axis.plot(
                    labor_components.index,
                    labor_components[column],
                    label=column,
                    linestyle=style,
                )
            axis.set(
                title="Components of the real-time labor alert",
                ylabel="Unemployment rate (percentage points)",
            )
            axis.legend()
            figure.tight_layout()
            plt.show()
            plt.close(figure)
            """
        ),
        markdown(
            r"""
            ## Labels and baselines

            One-, three-, and twelve-month forward returns are separate label objects with explicit
            end dates. The notebook never joins a future label into the unemployment feature
            panel. The unconditional baseline shows the macro-eligible distribution. A trailing
            twelve-month price-momentum split supplies a familiar asset-only time-series baseline
            that does not depend on macro revisions.

            Normalized prices are context, not a backtest. There are no portfolio weights,
            rebalancing rules, costs, or claims about investability.

            Forward return \(R_{d,h}=P_{d+h}/P_d-1\) lives in a typed label object with an actual
            ending close. The calendar period of that close must be exactly \(h\) months after the
            decision. The unconditional baseline is restricted to dates with a valid labor state.
            A one-year price warm-up makes the momentum split available from the beginning of the
            analysis window, so differences are not driven by a hidden baseline burn-in.
            """
        ),
        code(
            """
            labels = forward_labels(prices)
            eligible = point_regimes.notna()
            unconditional = unconditional_statistics(labels, eligible=eligible)
            momentum = momentum_baseline(price_history, labels, eligible=eligible)
            display(unconditional, momentum)
            figure, _ = plot_normalized_prices(prices)
            plt.show()
            plt.close(figure)
            """
        ),
        markdown(
            r"""
            ## Uncertainty and conditional summaries

            The summaries retain counts, coverage, means, volatility, positive shares, and
            heteroskedasticity-and-autocorrelation-consistent (HAC) intervals. The horizon-aware
            lag addresses overlap in multi-month labels but cannot
            create independent alert episodes. The one-month maximum drawdown resets when an
            alert changes or an observation is missing, preventing disconnected alert periods
            from being compounded as one path.

            Interpret wide or overlapping intervals as uncertainty, not as evidence that two
            economic states are equivalent.

            The explicit alert-minus-no-alert estimator is a regression contrast whose HAC score
            remains aligned to the full monthly calendar. Its bandwidth is at least \(h-1\) for
            overlapping labels and may be longer under the automatic rule. Descriptive regime-mean
            intervals are pointwise. Only the four predeclared one-month contrasts use simultaneous
            Bonferroni intervals. The minimum-data flag requires twelve outcomes and two
            outcome-eligible episodes on each side; it is a display threshold, not proof that a
            two-episode normal approximation is trustworthy. Leave-one-episode-out estimates are
            essential context when alerts cluster.
            """
        ),
        code(
            """
            point_statistics = regime_statistics(labels, point_regimes)
            latest_statistics = regime_statistics(labels, latest_regimes)
            directional_contrasts = regime_contrast_statistics(
                labels,
                point_regimes,
                treated="deterioration alert",
                reference="no alert",
                assets=("SPY", "DBC", "TLT"),
            )
            duration_labels = return_spread_labels(
                labels, {"TLT minus SHY": ("TLT", "SHY")}
            )
            duration_contrast = regime_contrast_statistics(
                duration_labels,
                point_regimes,
                treated="deterioration alert",
                reference="no alert",
            )
            primary_contrasts = familywise_primary_intervals(
                pd.concat([directional_contrasts, duration_contrast], ignore_index=True)
            )
            display(point_statistics, primary_contrasts)
            figure, _ = plot_regime_means(
                point_statistics,
                title="Labor deterioration and one-month outcomes",
            )
            plt.show()
            plt.close(figure)

            figure, _ = plot_regime_contrasts(
                primary_contrasts,
                title="Predeclared labor-alert contrasts",
            )
            plt.show()
            plt.close(figure)
            """
        ),
        markdown(
            r"""
            ## Distribution shape and rare episodes

            Labor alerts are expected to cluster around a limited number of stress episodes.
            Means can therefore conceal skew, outliers, and unequal sample sizes. The box plots
            compare the central distributions for risk assets and Treasury durations. The count
            chart shows whether an apparent difference rests on a small alert sample.

            Removing outliers after seeing them would change the analysis plan, so the numerical
            summaries retain every finite provider observation.

            Box plots show quartiles and whiskers while retaining every tail observation as a
            plotted flier. They are not density estimates. The companion bars distinguish outcome
            months from contiguous labor episodes after unavailable labels are masked. This avoids
            counting a terminal alert episode that contributes no return as inferential support.
            """
        ),
        code(
            """
            figure, _ = plot_regime_distributions(
                labels[1],
                point_regimes,
                assets=("SPY", "DBC", "TLT", "SHY"),
                title="One-month outcomes with and without a labor alert",
            )
            plt.show()
            plt.close(figure)

            figure, _ = plot_sample_sizes(point_statistics)
            plt.show()
            plt.close(figure)
            """
        ),
        markdown(
            r"""
            ## Sensitivity to the alert boundary

            The predeclared boundaries are 0.3, 0.5, and 0.7 percentage points. For every asset,
            the heatmap reports the one-month mean during alerts minus the mean without an alert.
            It displays the full asset-by-threshold family instead of selecting the most favorable
            asset or boundary. A stable pattern should survive nearby definitions; a fragile one
            is a limitation to report.

            Every threshold produces a long contrast table with counts, episode counts, HAC errors,
            and nominal intervals. One exploratory Bonferroni family is then recomputed across the
            complete threshold-by-asset display. Gray or masked cells fail the predeclared
            minimum-data rule; they are neither zero nor evidence of no association.
            """
        ),
        code(
            """
            sensitivity_rows = []
            for boundary in (0.3, 0.5, 0.7):
                table = regime_contrast_statistics(
                    {1: labels[1]},
                    labor_regime(point_signal, boundary=boundary),
                    treated="deterioration alert",
                    reference="no alert",
                    assets=symbols,
                )
                table.insert(0, "boundary", boundary)
                sensitivity_rows.append(table)
            sensitivity_table = simultaneous_interval_family(
                pd.concat(sensitivity_rows, ignore_index=True),
                family_id="labor threshold family",
            )
            sensitivity = sensitivity_table.pivot(
                index="boundary", columns="asset", values="mean_difference"
            ).where(
                sensitivity_table.pivot(
                    index="boundary", columns="asset", values="meets_display_threshold"
                )
            )
            display(sensitivity_table, sensitivity)
            figure, _ = plot_sensitivity_heatmap(
                sensitivity,
                title="Alert-minus-no-alert mean return across fixed boundaries",
                color_label="Difference in one-month mean return",
            )
            plt.show()
            plt.close(figure)
            """
        ),
        markdown(
            r"""
            ## Latest-revised classification bias

            Revision effects enter through two channels: the level can change, and a small change
            can move a decision across the alert boundary. The comparison table preserves both
            membership and mean differences. The plotted signal gap is retrospective and remains
            outside the primary feature set.

            Agreement between real-time and latest-revised labels in this sample would be a
            legitimate negative result, not a reason to omit the comparison.

            Latest-revised signal components use the exact same 15 source months as the real-time
            signal. The classification cross-tab includes unclassified dates, so availability
            changes are not hidden inside a mean difference. The first/second-half and
            leave-one-episode-out table uses the real-time classification only and should be read
            as temporal robustness, not as evidence about revision bias.
            """
        ),
        code(
            """
            revision_comparison = compare_statistics(point_statistics, latest_statistics)
            classification_changes = classification_transition_table(
                point_regimes,
                latest_regimes,
            )
            stability_labels = combined_outcome_labels(
                labels,
                assets=("SPY", "DBC", "TLT"),
                spreads={"TLT minus SHY": ("TLT", "SHY")},
            )
            stability = temporal_contrast_stability(
                stability_labels,
                point_regimes,
                treated="deterioration alert",
                reference="no alert",
            )
            display(revision_comparison, classification_changes, stability)
            figure, _ = plot_revision_gap(
                point_signal,
                latest_signal,
                title="Labor-signal revision substitution gap",
            )
            plt.show()
            plt.close(figure)
            """
        ),
        markdown(
            r"""
            ## Limitations and executable review

            The alert is monthly, release-lagged, and based on a single national series. It ignores
            intramonth information, labor-force composition, and other recession evidence. The
            contemporary ETF universe has inception and survivorship bias. Returns exclude costs,
            spreads, taxes, and implementation delay. Alert months cluster, secondary horizons
            overlap, normal intervals are approximate, and repeated assets and thresholds raise
            multiple-testing risk.

            Mechanical assertions verify causal availability, label separation, alignment,
            finite outputs, and provenance coverage. They do not certify the hypothesis.

            The 0.5-point rule is a research definition, not an official recession declaration.
            The [real-time Sahm indicator page](https://fred.stlouisfed.org/release?rid=456) gives
            context for the official concept, while the
            [ALFRED guide](https://fred.stlouisfed.org/docs/api/fred/realtime_period.html) explains
            historical information sets. The HAC intervals follow the covariance construction in
            [Newey and West (1987)](https://doi.org/10.2307/1913610). These references motivate the
            concepts; they do not validate this ETF association design.
            """
        ),
        code(
            """
            audit = validate_study_outputs(
                prices,
                point_in_time,
                labels,
                point_regimes,
                point_statistics,
                expected_regimes=frozenset({"no alert", "deterioration alert"}),
                transformed=point_signal_result,
            )
            assert_component_periods_match(point_signal_result, latest_signal_result)
            assert set(point_in_time.frame.columns).isdisjoint(labels[1].frame.columns)
            matched = point_in_time.provenance["available_from"].notna()
            assert point_in_time.provenance.loc[matched, "available_from"].le(
                point_in_time.provenance.loc[matched, "decision_date"] - pd.Timedelta(days=1)
            ).all()
            display(audit)
            session.close()
            """
        ),
        markdown(
            r"""
            ## Interpretation after execution

            Begin with coverage, alert counts, and episode concentration. Compare full
            distributions and uncertainty with both baselines, then inspect threshold stability
            and latest-revised classification changes. Keep results that are null, unstable, or
            opposite the hypothesis. The notebook measures association only; it does not establish
            recession timing, causality, or a profitable defensive rotation.
            """
        ),
    ]


def yield_curve_notebook() -> list[Cell]:
    """Return the Treasury yield-curve inversion study."""
    return [
        markdown(
            r"""
            # Treasury yield-curve inversion

            This notebook asks how cross-asset outcomes differ after the ten-year minus two-year
            Treasury spread is inverted at a month-end decision date. Inversion is an observable
            market-rate state, not a deterministic recession forecast or causal intervention.

            The hypothesis, zero boundary, lag policy, staleness rule, outcomes, and sensitivity
            grid were fixed before live results. Committed cells retain no provider values or
            outputs; live data and figures exist only in the executing process.

            **Primary protocol.** The unit is the last common ETF trading session in a complete
            month. The primary spread must be available at least one calendar day before that
            close. Inverted is the treatment, noninverted is the reference, and the primary
            horizon is one calendar month. The four two-sided primary outcomes are `SPY`, `TLT`,
            `TLT-SHY`, and `TLT-IEF`; “two-sided” predeclares a difference without a directional
            sign. Bonferroni intervals cover this family. Other assets, longer horizons,
            thresholds, timing policies, and revision views are exploratory.
            """
        ),
        code(
            """
            import matplotlib.pyplot as plt
            import pandas as pd

            from studies._support import (
                CORE_SYMBOLS,
                STUDY_START,
                acquire_latest_series,
                acquire_monthly_prices,
                acquire_vintage_histories,
                assert_feature_panel_timing,
                build_point_in_time_levels,
                classification_transition_table,
                combined_outcome_labels,
                compare_statistics,
                configure_plots,
                familywise_primary_intervals,
                feature_provenance_summary,
                forward_labels,
                latest_revised_counterpart,
                momentum_baseline,
                open_live_session,
                plot_coverage,
                plot_feature_comparison,
                plot_normalized_prices,
                plot_regime_contrasts,
                plot_regime_distributions,
                plot_regime_means,
                plot_regime_timeline,
                plot_revision_gap,
                plot_sample_sizes,
                plot_sensitivity_heatmap,
                regime_contrast_statistics,
                regime_statistics,
                return_spread_labels,
                simultaneous_interval_family,
                study_run_manifest,
                temporal_contrast_stability,
                unconditional_statistics,
                validate_study_outputs,
            )

            configure_plots()
            pd.set_option("display.max_columns", 20)
            session = open_live_session()
            """
        ),
        markdown(
            r"""
            ## Hypothesis, universe, and maturity exposure

            The fixed core universe is extended with `TLT` and `SHY` so long- and short-duration
            Treasury outcomes can be compared with `IEF`. `SPY`, `GLD`, `DBC`, and `UUP` retain
            broader cross-asset context. These ETFs are current products selected with hindsight;
            their joint history is not a reconstructed investable universe.

            `T10Y2Y` is the ten-year Treasury constant-maturity rate minus the two-year rate. The
            hypothesis is that inversion is associated with different subsequent equity and
            Treasury-duration outcomes. The study does not assume which month a recession begins
            or that the spread alone has stable forecast value.

            `TLT-SHY` and `TLT-IEF` subtract forward returns on the same dates. They preserve
            common rate shocks and directly measure whether added maturity exposure changes the
            inversion contrast. The ETF products have evolving duration and holdings, so these
            are maturity-exposure proxies rather than constant-maturity bonds.
            """
        ),
        code(
            """
            symbols = (*CORE_SYMBOLS, "TLT", "SHY")
            price_history, market_provenance = acquire_monthly_prices(session, symbols)
            prices = price_history.loc[STUDY_START:]
            histories = acquire_vintage_histories(
                session,
                ("T10Y2Y",),
                prices.index,
                selected_view_series=frozenset({"T10Y2Y"}),
            )
            latest = acquire_latest_series(session, ("T10Y2Y",))
            staleness = {"T10Y2Y": pd.Timedelta(days=7)}
            point_in_time = build_point_in_time_levels(
                histories,
                prices.index,
                staleness,
                latest_nonmissing_series=frozenset({"T10Y2Y"}),
            )
            latest_levels = latest_revised_counterpart(point_in_time, latest)
            feature_provenance = feature_provenance_summary(point_in_time)
            manifest = study_run_manifest(
                prices,
                series_ids=("T10Y2Y",),
                thresholds="primary inversion=spread below 0 percentage points",
                staleness=staleness,
            )
            display(manifest, market_provenance, feature_provenance)
            """
        ),
        markdown(
            r"""
            ## Selected historical views and coverage

            The daily spread is requested through three bounded sets of historical views: the
            actual common-close dates and their one- and two-day cutoffs. This covers every cutoff
            used by the timing grid without requesting an unbounded history. Combined provenance
            retains the exact cutoff sets and query retrieval times. Persistra applies the chosen
            operational lag and selects the newest nonmissing observation no more than seven days
            old.

            The staleness allowance covers weekends and ordinary market holidays. A longer outage
            produces a missing feature instead of carrying an obsolete rate forward.

            FRED represents some daily holidays as explicit missing observations. For this daily
            market series only, the study removes those rows and searches backward for the latest
            valid spread; monthly macro studies do not use that fallback. Normalized market and
            rate results also round-trip through temporary DuckDB storage before analysis.

            Separate bounded requests can repeat one revision with a query-scoped interval end.
            The combiner requires every economic field to agree, orders the distinct selected
            revision starts, and assigns each inclusive interval through the day before the next
            start; the last selected revision remains open. This reconstruction is sufficient for
            the exact cutoff set queried here and is not presented as a complete daily archive.
            """
        ),
        code(
            """
            figure, _ = plot_coverage(market_provenance, feature_provenance)
            plt.show()
            plt.close(figure)
            """
        ),
        markdown(
            r"""
            ## Point-in-time rate information

            Treasury market series are revised less extensively than many macro releases, but
            point-in-time selection still matters: corrections, publication timing, weekends, and
            retrieval-date history are distinct concepts. The latest-revised diagnostic preserves
            the observation selected in real time and substitutes the current value for that same
            date.

            If the two paths overlap, that is an empirical property of this series and window. It
            does not justify applying latest history to a revised labor, inflation, or GDP series.
            """
        ),
        code(
            """
            point_spread = point_in_time.frame.rename(columns={"T10Y2Y": "10y minus 2y spread"})
            revised_spread = latest_levels.set_axis(point_spread.columns, axis="columns")
            figure, _ = plot_feature_comparison(
                point_spread,
                revised_spread,
                ("10y minus 2y spread",),
            )
            plt.show()
            plt.close(figure)
            """
        ),
        markdown(
            r"""
            ## Regime rule and timing convention

            The primary regime is inverted when the admissible spread is below zero and
            noninverted otherwise. Zero is a predeclared economic boundary, not a fitted cut point.
            The price at decision month end and the lagged spread are both known before any
            forward label begins. The timeline displays duration and clustering of inversion
            episodes, which determine effective sample diversity.

            A positive subsequent return in an inverted month does not mean inversion caused that
            return, and a negative return does not invalidate the yield curve as a macro signal.

            The primary state uses the strict rule \(s_d<0\), where \(s_d\) is the latest valid
            spread known at the lagged cutoff. Zero belongs to the noninverted reference state.
            The timeline makes uninterrupted inversion episodes visible; the later maturity-profile
            plot then compares `SHY`, `IEF`, and `TLT` without treating their months as independent
            macro events.
            """
        ),
        code(
            """
            def curve_regime(spread: pd.Series, *, boundary: float = 0.0) -> pd.Series:
                regime = pd.Series(pd.NA, index=spread.index, dtype="string")
                regime.loc[spread.notna() & spread.lt(boundary)] = "inverted"
                regime.loc[spread.notna() & spread.ge(boundary)] = "noninverted"
                return regime

            def curve_threshold_state(spread: pd.Series, boundary: float) -> pd.Series:
                regime = pd.Series(pd.NA, index=spread.index, dtype="string")
                regime.loc[spread.notna() & spread.lt(boundary)] = "below boundary"
                regime.loc[spread.notna() & spread.ge(boundary)] = "at or above boundary"
                return regime

            point_regimes = curve_regime(point_in_time.frame["T10Y2Y"])
            latest_regimes = curve_regime(latest_levels["T10Y2Y"])
            display(point_regimes.value_counts(dropna=False).rename("decision count"))
            figure, _ = plot_regime_timeline(
                point_in_time.frame["T10Y2Y"],
                point_regimes,
                title="Point-in-time Treasury spread and inversion states",
                ylabel="Percentage points",
                boundaries=(0.0,),
            )
            plt.show()
            plt.close(figure)
            """
        ),
        markdown(
            r"""
            ## Forward labels and time-series baselines

            Persistra builds one-, three-, and twelve-month forward returns as label objects whose
            ending dates are explicit. The macro feature cannot access them. Secondary horizons
            overlap, while the primary one-month horizon does not overlap on monthly decisions.

            The unconditional baseline establishes ordinary asset behavior over the same sample.
            The twelve-month momentum baseline asks whether a conventional price-only state is at
            least as descriptive as inversion. Normalized adjusted closes provide context without
            constructing a strategy or charging transaction costs.

            An \(h\)-month label is \(P_{d+h}/P_d-1\), and its stored ending close must fall
            exactly \(h\) calendar months after the decision. Both baselines use dates with a valid
            primary curve state. A one-year price warm-up supplies trailing momentum at the start
            of the analysis window; normalized prices remain context rather than a backtest.
            """
        ),
        code(
            """
            labels = forward_labels(prices)
            eligible = point_regimes.notna()
            unconditional = unconditional_statistics(labels, eligible=eligible)
            momentum = momentum_baseline(price_history, labels, eligible=eligible)
            display(unconditional, momentum)
            figure, _ = plot_normalized_prices(prices)
            plt.show()
            plt.close(figure)
            """
        ),
        markdown(
            r"""
            ## Association estimates and uncertainty

            The table reports every asset and horizon rather than highlighting the largest
            difference. Means are accompanied by horizon-aware
            heteroskedasticity-and-autocorrelation-consistent (HAC) intervals, counts, coverage,
            volatility, and positive shares. One-month drawdown is calculated within contiguous
            regime episodes so separated inversions are not compounded into one artificial path.

            These estimates share macro episodes and market shocks. Confidence intervals quantify
            sampling uncertainty under an approximation; they do not solve structural instability
            or the multiple comparisons across assets and horizons.

            Treated-minus-reference contrasts use a full-calendar HAC score series. The bandwidth
            is at least the overlap floor and may be longer under the fixed automatic rule. The
            four primary one-month outcomes receive Bonferroni simultaneous intervals; descriptive
            group means remain pointwise, and longer horizons are exploratory. A gray contrast has
            fewer than twelve outcomes or two outcome-eligible episodes on a side. That minimum is
            only a display rule, especially because two episodes do not make normal inference
            dependable. First/second-half and leave-one-episode-out estimates expose this risk.
            """
        ),
        code(
            """
            point_statistics = regime_statistics(labels, point_regimes)
            latest_statistics = regime_statistics(labels, latest_regimes)
            directional_contrasts = regime_contrast_statistics(
                labels,
                point_regimes,
                treated="inverted",
                reference="noninverted",
                assets=("SPY", "TLT"),
            )
            duration_labels = return_spread_labels(
                labels,
                {
                    "TLT minus SHY": ("TLT", "SHY"),
                    "TLT minus IEF": ("TLT", "IEF"),
                },
            )
            duration_contrasts = regime_contrast_statistics(
                duration_labels,
                point_regimes,
                treated="inverted",
                reference="noninverted",
            )
            primary_contrasts = familywise_primary_intervals(
                pd.concat([directional_contrasts, duration_contrasts], ignore_index=True)
            )
            display(point_statistics, primary_contrasts)
            figure, _ = plot_regime_means(
                point_statistics,
                title="Yield-curve state and one-month outcomes",
            )
            plt.show()
            plt.close(figure)

            figure, _ = plot_regime_contrasts(
                primary_contrasts,
                title="Predeclared inversion contrasts",
            )
            plt.show()
            plt.close(figure)

            duration_order = ("SHY", "IEF", "TLT")
            duration_rows = point_statistics.loc[
                point_statistics["horizon_months"].eq(1)
                & point_statistics["asset"].isin(duration_order)
            ]
            figure, axis = plt.subplots(figsize=(9, 5.2))
            for regime, marker in (("inverted", "o"), ("noninverted", "s")):
                means = (
                    duration_rows.loc[duration_rows["regime"].eq(regime)]
                    .set_index("asset")
                    .reindex(duration_order)["mean_return"]
                )
                axis.plot(
                    duration_order,
                    means,
                    label=regime,
                    marker=marker,
                )
            axis.axhline(0, color="#333333", linewidth=0.9)
            axis.set(
                title="Treasury maturity response by curve state",
                xlabel="Increasing maturity exposure",
                ylabel="One-month mean simple return",
            )
            axis.yaxis.set_major_formatter(plt.matplotlib.ticker.PercentFormatter(1.0))
            axis.legend()
            figure.tight_layout()
            plt.show()
            plt.close(figure)
            """
        ),
        markdown(
            r"""
            ## Outcome distributions and episode counts

            Treasury duration is central to this question, so the distribution plot compares
            equities with intermediate, long, and short Treasuries. Box plots show dispersion and
            asymmetry that a mean can hide. The separate count chart makes the imbalance between
            inverted and noninverted decisions visible.

            No observation is removed because it looks exceptional. Crisis outcomes are part of
            the phenomenon under study and must remain in both tables and figures.
            """
        ),
        code(
            """
            figure, _ = plot_regime_distributions(
                labels[1],
                point_regimes,
                assets=("SPY", "IEF", "TLT", "SHY"),
                title="One-month outcomes by yield-curve state",
            )
            plt.show()
            plt.close(figure)

            figure, _ = plot_sample_sizes(point_statistics)
            plt.show()
            plt.close(figure)
            """
        ),
        markdown(
            r"""
            ## Sensitivity to boundary and operational lag

            The fixed grid crosses boundaries of -0.25, 0, and 0.25 percentage points with lags of
            zero, one, and two days. Each cell is the `TLT` one-month mean below the boundary minus
            its mean at or above the boundary. “Inverted” is reserved for the zero-boundary primary
            rule. Rebuilding the feature panel for every lag ensures the
            sensitivity test changes information availability rather than shifting a completed
            feature after the fact.

            The zero-day row is an explicitly optimistic, noncausal look-ahead diagnostic. FRED's
            day-resolution availability cannot prove a same-day spread preceded the ETF close, so
            that row is excluded from admissible timing conclusions. One day is the primary causal
            policy and two days is conservative. Every panel undergoes an availability assertion.
            The long table retains counts, episodes, HAC errors, and intervals; one exploratory
            Bonferroni family covers all nine cells before the heatmap masks rows below the display
            threshold. No cell becomes a replacement primary specification.
            """
        ),
        code(
            """
            sensitivity_rows = []
            lag_labels = {
                0: "0 — optimistic same-day diagnostic",
                1: "1 — primary causal policy",
                2: "2 — conservative policy",
            }
            for lag_days in (0, 1, 2):
                panel = build_point_in_time_levels(
                    histories,
                    prices.index,
                    {"T10Y2Y": pd.Timedelta(days=7)},
                    publication_lag=pd.Timedelta(days=lag_days),
                    latest_nonmissing_series=frozenset({"T10Y2Y"}),
                )
                assert_feature_panel_timing(panel)
                matched = panel.provenance["available_from"].notna()
                assert panel.provenance.loc[matched, "available_from"].le(
                    panel.provenance.loc[matched, "decision_date"]
                    - pd.Timedelta(days=lag_days)
                ).all()
                for boundary in (-0.25, 0.0, 0.25):
                    regimes = curve_threshold_state(panel.frame["T10Y2Y"], boundary)
                    table = regime_contrast_statistics(
                        {1: labels[1]},
                        regimes,
                        treated="below boundary",
                        reference="at or above boundary",
                        assets=("TLT",),
                    )
                    table.insert(0, "boundary", boundary)
                    table.insert(0, "lag_policy", lag_labels[lag_days])
                    sensitivity_rows.append(table)
            sensitivity_table = simultaneous_interval_family(
                pd.concat(sensitivity_rows, ignore_index=True),
                family_id="yield-curve lag and threshold family",
            )
            sensitivity = sensitivity_table.pivot(
                index="lag_policy", columns="boundary", values="mean_difference"
            ).where(
                sensitivity_table.pivot(
                    index="lag_policy",
                    columns="boundary",
                    values="meets_display_threshold",
                )
            )
            display(sensitivity_table, sensitivity)
            figure, _ = plot_sensitivity_heatmap(
                sensitivity,
                title="Long-Treasury contrast across timing policies",
                color_label="Difference in one-month mean return",
            )
            plt.show()
            plt.close(figure)
            """
        ),
        markdown(
            r"""
            ## Latest-revised diagnostic

            The comparison is retained even if this market-rate series has few revisions. It
            records membership differences, conditional-mean changes, and the source-value gap.
            The purpose is to demonstrate the same temporal discipline used for more heavily
            revised series, including the possibility of a materially negative finding about
            revision bias here.

            The current series is never substituted into the primary regime classification.

            The classification table includes an unclassified state, so missing-to-present
            transitions are visible. The first/second-half and leave-one-episode-out table is a
            real-time robustness diagnostic, not part of the revision comparison. A small revision
            gap for this rate series would not weaken the need for vintage discipline elsewhere.
            """
        ),
        code(
            """
            revision_comparison = compare_statistics(point_statistics, latest_statistics)
            classification_changes = classification_transition_table(
                point_regimes,
                latest_regimes,
            )
            stability_labels = combined_outcome_labels(
                labels,
                assets=("SPY", "TLT"),
                spreads={
                    "TLT minus SHY": ("TLT", "SHY"),
                    "TLT minus IEF": ("TLT", "IEF"),
                },
            )
            stability = temporal_contrast_stability(
                stability_labels,
                point_regimes,
                treated="inverted",
                reference="noninverted",
            )
            display(revision_comparison, classification_changes, stability)
            figure, _ = plot_revision_gap(
                point_in_time.frame["T10Y2Y"],
                latest_levels["T10Y2Y"],
                title="Treasury-spread revision substitution gap",
            )
            plt.show()
            plt.close(figure)
            """
        ),
        markdown(
            r"""
            ## Limitations and execution checks

            The spread is one curve measure sampled monthly. It ignores the full yield curve,
            term-premium estimates, inflation expectations, policy surprises, and intramonth
            dynamics. ETF duration and composition change. If the live sample contains few
            independent inversion episodes, month counts overstate event diversity. Outcomes
            overlap at longer horizons, and many asset-horizon
            comparisons increase false-discovery risk. Returns omit implementation costs.

            The final audit checks positivity, alignment, provenance completeness, distinct label
            objects, multiple regimes, and finite summaries. Availability assertions enforce the
            one-day lag but cannot prove economic interpretation.

            For background, FRED defines
            [`T10Y2Y`](https://fred.stlouisfed.org/series/T10Y2Y) as the ten-year minus two-year
            constant-maturity spread. The New York Fed's
            [yield-curve guide](https://www.newyorkfed.org/research/capital_markets/ycfaq.htm)
            illustrates why a term spread may be studied while also warning that a curve model is
            not an official forecast. The exact maturity pair there differs from this notebook,
            so it is conceptual context rather than validation.
            """
        ),
        code(
            """
            audit = validate_study_outputs(
                prices,
                point_in_time,
                labels,
                point_regimes,
                point_statistics,
                expected_regimes=frozenset({"inverted", "noninverted"}),
            )
            assert set(point_in_time.frame.columns).isdisjoint(labels[1].frame.columns)
            matched = point_in_time.provenance["available_from"].notna()
            assert point_in_time.provenance.loc[matched, "available_from"].le(
                point_in_time.provenance.loc[matched, "decision_date"] - pd.Timedelta(days=1)
            ).all()
            display(audit)
            session.close()
            """
        ),
        markdown(
            r"""
            ## Interpretation after execution

            Inspect coverage and inversion episode counts first. Compare the entire distribution
            with unconditional and price-momentum baselines, then examine uncertainty, the full
            timing grid, and the latest-revised diagnostic. Preserve weak, unstable, or contrary
            evidence. The notebook reports historical association; it does not certify recession
            forecasts, market timing, causality, or strategy profitability.
            """
        ),
    ]


def inflation_momentum_notebook() -> list[Cell]:
    """Return the inflation acceleration and deceleration study."""
    return [
        markdown(
            r"""
            # Inflation acceleration and deceleration

            This notebook asks how inflation-sensitive assets behave after six-month changes in
            real-time inflation momentum. It distinguishes the inflation rate from its direction
            of change: a high but falling rate is economically different from a low but rising
            rate.

            Thresholds, series, horizons, and baselines were predeclared. Live provider values and
            rendered results remain temporary; the committed narrative explains concepts and
            procedures without asserting an observed result.

            **Primary protocol.** The unit is the last common ETF trading session of a complete
            month, with a one-calendar-day information lag. Acceleration is the treatment,
            deceleration the reference, and one month the primary horizon. Outcomes are the paired
            return spreads `TIP-IEF`, `DBC-IEF`, and `GLD-IEF`. Their contrasts are differences in
            acceleration-minus-deceleration effects relative to nominal intermediate Treasuries,
            so they directly operationalize “differ more.” Bonferroni intervals cover these three
            primary outcomes. The stable state is descriptive; longer horizons, headline/core
            sweeps, and revised history are exploratory.
            """
        ),
        code(
            """
            import matplotlib.pyplot as plt
            import pandas as pd

            from studies._support import (
                CORE_SYMBOLS,
                STUDY_START,
                acquire_latest_series,
                acquire_monthly_prices,
                acquire_vintage_histories,
                assert_component_periods_match,
                build_point_in_time_levels,
                classification_transition_table,
                compare_statistics,
                configure_plots,
                feature_provenance_summary,
                forward_labels,
                latest_revised_inflation_momentum,
                latest_revised_year_over_year,
                momentum_baseline,
                open_live_session,
                plot_coverage,
                plot_feature_comparison,
                plot_normalized_prices,
                plot_regime_contrasts,
                plot_regime_distributions,
                plot_regime_means,
                plot_regime_timeline,
                plot_revision_gap,
                plot_sample_sizes,
                plot_sensitivity_heatmap,
                point_in_time_inflation_momentum,
                point_in_time_year_over_year,
                regime_contrast_statistics,
                regime_statistics,
                regime_style,
                return_spread_labels,
                simultaneous_interval_family,
                study_run_manifest,
                temporal_contrast_stability,
                unconditional_statistics,
                validate_study_outputs,
            )

            configure_plots()
            pd.set_option("display.max_columns", 20)
            session = open_live_session()
            """
        ),
        markdown(
            r"""
            ## Hypothesis, inflation measures, and assets

            `CPIAUCSL` is the primary headline consumer-price index. `CPILFESL`, which excludes
            food and energy, is a predeclared measure sensitivity rather than a replacement
            chosen after seeing results. Both series are revised and require vintage selection.

            `TIP` extends the core asset set because inflation-linked Treasury principal responds
            to measured inflation, while its market price also reflects real yields and duration.
            The hypothesis is expressed through within-date spreads rather than comparing two
            independent tables. A `TIP-IEF` outcome, for example, subtracts the two forward returns
            before estimating the acceleration contrast and therefore preserves their covariance.
            This is not a claim of inflation hedging at every horizon. TreasuryDirect's
            [TIPS overview](https://www.treasurydirect.gov/marketable-securities/tips/) explains
            inflation-adjusted principal, while market-price returns also reflect real yields,
            duration, liquidity, and ETF mechanics.
            """
        ),
        code(
            """
            symbols = (*CORE_SYMBOLS, "TIP")
            price_history, market_provenance = acquire_monthly_prices(session, symbols)
            prices = price_history.loc[STUDY_START:]
            series_ids = ("CPIAUCSL", "CPILFESL")
            histories = acquire_vintage_histories(session, series_ids, prices.index)
            latest = acquire_latest_series(session, series_ids)
            staleness = {series_id: pd.Timedelta(days=62) for series_id in series_ids}
            point_in_time = build_point_in_time_levels(
                histories,
                prices.index,
                staleness,
            )
            feature_provenance = feature_provenance_summary(point_in_time)
            manifest = study_run_manifest(
                prices,
                series_ids=series_ids,
                thresholds="headline momentum band=±0.25 percentage points",
                staleness=staleness,
            )
            display(manifest, market_provenance, feature_provenance)
            """
        ),
        markdown(
            r"""
            ## Coverage before transformation

            Inflation momentum needs four historical source components even though it produces one
            value per decision. A matched current level does not guarantee that all exact comparison
            months exist inside the same vintage. The coverage figure describes current-level
            matching; component provenance and later regime counts reveal transformation coverage.
            Because the transform opens the historical snapshot at each decision, it does not need
            eighteen earlier decision rows or mix values captured on different dates.

            No interpolation fills missing releases, and a deleted latest observation remains
            missing under Persistra's point-in-time contract.

            Observation period, source availability interval, and retrieval time have separate
            meanings. The lagged decision cutoff must fall inside the source version's availability
            interval, and the current observation must be no more than 62 days old. Market and CPI
            objects round-trip through a temporary DuckDB database before analysis.
            """
        ),
        code(
            """
            figure, _ = plot_coverage(market_provenance, feature_provenance)
            plt.show()
            plt.close(figure)
            """
        ),
        markdown(
            r"""
            ## Point-in-time inflation rates

            For each decision \(d\), year-over-year inflation is calculated within one as-of
            vintage as \(100(C_{d,t}/C_{d,t-12}-1)\). The numerator and denominator are exact source
            months from the same historical snapshot, not two entries on a decision-date sequence.
            The latest-revised comparison uses today's values for those identical source periods.
            This keeps the release calendar and staleness policy fixed while exposing revision
            substitution.

            Every component carries source identity, availability, frequency, unit, seasonal
            adjustment, and retrieval provenance. The final audit checks that the point-in-time and
            revised calculations requested the same economic months.

            Headline and core inflation can diverge because volatile food and energy prices enter
            only the headline measure. Neither series is treated as a direct forecast of asset
            returns.
            """
        ),
        code(
            """
            point_rate_result = point_in_time_year_over_year(histories, point_in_time)
            latest_rate_result = latest_revised_year_over_year(point_in_time, latest)
            point_inflation = point_rate_result.frame
            latest_inflation = latest_rate_result.frame
            point_rates = point_inflation.rename(
                columns={"CPIAUCSL": "Headline inflation", "CPILFESL": "Core inflation"}
            )
            latest_rates = latest_inflation.set_axis(point_rates.columns, axis="columns")
            figure, _ = plot_feature_comparison(
                point_rates,
                latest_rates,
                tuple(point_rates.columns),
            )
            plt.show()
            plt.close(figure)
            """
        ),
        markdown(
            r"""
            ## Momentum and regime definition

            Inflation momentum is the current year-over-year rate minus the year-over-year rate
            for the source month six months earlier. All four levels—\(C_t\), \(C_{t-12}\),
            \(C_{t-6}\), and \(C_{t-18}\)—come from one vintage known at the decision cutoff. Thus
            \(M_d=100(C_t/C_{t-12}-1)-100(C_{t-6}/C_{t-18}-1)\). A value above 0.25 percentage
            points is acceleration, below -0.25 is
            deceleration, and the middle band is stable. The band avoids classifying negligible
            changes as distinct macro states.

            The primary regime uses headline inflation. Core inflation is reserved for sensitivity.
            The timeline shows how smooth macro states can cluster; it also reveals that a
            count of months can exaggerate the number of independent episodes.

            The phase portrait makes level and momentum separate axes. A high inflation rate can
            be decelerating, and a lower rate can be accelerating. Neither the six-month difference
            nor the stable band imposes a separate persistence requirement.
            """
        ),
        code(
            """
            def momentum_regime(momentum: pd.Series, *, band: float = 0.25) -> pd.Series:
                regime = pd.Series(pd.NA, index=momentum.index, dtype="string")
                regime.loc[momentum.notna() & momentum.gt(band)] = "accelerating"
                regime.loc[momentum.notna() & momentum.lt(-band)] = "decelerating"
                regime.loc[momentum.notna() & momentum.between(-band, band, inclusive="both")] = (
                    "stable"
                )
                return regime

            point_momentum_result = point_in_time_inflation_momentum(
                histories, point_in_time
            )
            latest_momentum_result = latest_revised_inflation_momentum(
                point_in_time, latest
            )
            point_momentum = point_momentum_result.frame
            latest_momentum = latest_momentum_result.frame
            point_regimes = momentum_regime(point_momentum["CPIAUCSL"])
            latest_regimes = momentum_regime(latest_momentum["CPIAUCSL"])
            display(point_regimes.value_counts(dropna=False).rename("decision count"))
            figure, _ = plot_regime_timeline(
                point_momentum["CPIAUCSL"],
                point_regimes,
                title="Real-time headline inflation momentum",
                ylabel="Six-month change in year-over-year inflation",
                boundaries=(-0.25, 0.25),
            )
            plt.show()
            plt.close(figure)

            figure, axis = plt.subplots(figsize=(9, 6))
            for regime in ("accelerating", "stable", "decelerating"):
                color, marker = regime_style(regime)
                selected = point_regimes.eq(regime).fillna(False)
                axis.scatter(
                    point_inflation.loc[selected, "CPIAUCSL"],
                    point_momentum.loc[selected, "CPIAUCSL"],
                    label=regime,
                    color=color,
                    marker=marker,
                    alpha=0.75,
                )
            axis.axhline(0, color="#333333", linewidth=0.9)
            axis.set(
                title="Inflation level and momentum occupy different states",
                xlabel="Headline year-over-year inflation (percent)",
                ylabel="Six-month inflation-rate change (percentage points)",
            )
            axis.legend()
            figure.tight_layout()
            plt.show()
            plt.close(figure)
            """
        ),
        markdown(
            r"""
            ## Outcomes and conventional baselines

            Forward returns over one, three, and twelve decision months are calculated only after
            the macro panel is complete. Each label retains its horizon end date and remains in a
            different typed object. The final incomplete horizons stay missing.

            The unconditional baseline represents ordinary behavior over the same dates. The
            trailing twelve-month momentum split is a conventional time-series comparator for
            each asset. Normalized prices show scale and crisis context but do not simulate
            switching between inflation states.

            For price \(P_d\), \(R_{d,h}=P_{d+h}/P_d-1\), and the stored ending close must fall
            exactly \(h\) calendar months after the decision. The unconditional table is restricted
            to valid headline states. One year of pre-analysis prices supplies trailing momentum
            on the first study date. The relative-return labels subtract assets only after their
            calendars and horizons are aligned.
            """
        ),
        code(
            """
            labels = forward_labels(prices)
            eligible = point_regimes.notna()
            unconditional = unconditional_statistics(labels, eligible=eligible)
            momentum = momentum_baseline(price_history, labels, eligible=eligible)
            display(unconditional, momentum)
            figure, _ = plot_normalized_prices(prices)
            plt.show()
            plt.close(figure)
            """
        ),
        markdown(
            r"""
            ## Regime summaries and uncertainty

            Counts and coverage accompany all conditional moments. A horizon-aware
            heteroskedasticity-and-autocorrelation-consistent (HAC) interval accounts for the
            mechanical overlap of multi-month outcomes, while the one-month
            Persistra summary supplies annualized volatility and episode-aware drawdown. The
            interval is approximate and does not make clustered inflation episodes independent.

            The HAC bandwidth is the larger of \(h-1\) and a predeclared automatic rule. Group-mean
            intervals are pointwise; Bonferroni intervals cover only the three primary one-month
            relative-return contrasts. A gray point falls below twelve outcomes or two
            outcome-eligible episodes on a side. That display rule does not make two episodes
            sufficient for confident normal inference, so first/second-half and
            leave-one-episode-out estimates remain central robustness evidence.

            The complete table is the result family. Individual asset-state differences should be
            judged against the unconditional and price-momentum baselines and the many comparisons
            performed.
            """
        ),
        code(
            """
            point_statistics = regime_statistics(labels, point_regimes)
            latest_statistics = regime_statistics(labels, latest_regimes)
            relative_labels = return_spread_labels(
                labels,
                {
                    "TIP minus IEF": ("TIP", "IEF"),
                    "DBC minus IEF": ("DBC", "IEF"),
                    "GLD minus IEF": ("GLD", "IEF"),
                },
            )
            primary_contrasts = regime_contrast_statistics(
                relative_labels,
                point_regimes,
                treated="accelerating",
                reference="decelerating",
            )
            display(point_statistics, primary_contrasts)
            figure, _ = plot_regime_means(
                point_statistics,
                title="Inflation momentum and one-month outcomes",
            )
            plt.show()
            plt.close(figure)

            figure, _ = plot_regime_contrasts(
                primary_contrasts,
                title="Inflation-sensitive assets relative to nominal Treasuries",
            )
            plt.show()
            plt.close(figure)
            """
        ),
        markdown(
            r"""
            ## Distributions and state balance

            Inflation-sensitive assets can respond asymmetrically to shocks, real-yield changes,
            and energy moves. Box plots therefore accompany means for `TIP`, `DBC`, `GLD`, and
            nominal Treasuries. The count chart shows whether acceleration, stability, and
            deceleration have adequate outcome coverage.

            Extreme months are economically relevant and remain included. The plots are
            descriptive and do not justify a post hoc winsorization rule.

            Box plots retain all tail points but summarize quartiles rather than a full density.
            Sample bars separately report outcome months and contiguous macro episodes after
            masking unavailable labels. The headline/core agreement matrix is topic-specific: it
            reveals whether changing the inflation measure changes state membership before any
            outcome comparison is interpreted.
            """
        ),
        code(
            """
            figure, _ = plot_regime_distributions(
                labels[1],
                point_regimes,
                assets=("TIP", "DBC", "GLD", "IEF"),
                title="One-month outcomes by headline inflation momentum",
            )
            plt.show()
            plt.close(figure)

            figure, _ = plot_sample_sizes(point_statistics)
            plt.show()
            plt.close(figure)
            """
        ),
        markdown(
            r"""
            ## Sensitivity to the neutral band and inflation measure

            The predeclared bands are 0.10, 0.25, and 0.50 percentage points. The primary heatmap
            reports acceleration-minus-deceleration one-month contrasts for `TIP-IEF`, `DBC-IEF`,
            and `GLD-IEF` under every headline and core band. This repeats exactly the primary
            estimand instead of comparing an alternate raw summary table. It prevents a measure or
            band from being selected solely because it produces a larger contrast.

            The long table retains counts, outcome-eligible episodes, HAC errors, and intervals.
            One exploratory Bonferroni family covers all measure-by-band-by-spread cells. The
            heatmap is zero-centered and masks cells below the minimum-data display rule; the
            underlying table still distinguishes missing estimation from an effect near zero.
            """
        ),
        code(
            """
            sensitivity_rows = []
            for measure in ("CPIAUCSL", "CPILFESL"):
                for band in (0.10, 0.25, 0.50):
                    regimes = momentum_regime(point_momentum[measure], band=band)
                    table = regime_contrast_statistics(
                        {1: relative_labels[1]},
                        regimes,
                        treated="accelerating",
                        reference="decelerating",
                    )
                    table.insert(0, "band", band)
                    table.insert(0, "measure", measure)
                    sensitivity_rows.append(table)
            sensitivity_table = simultaneous_interval_family(
                pd.concat(sensitivity_rows, ignore_index=True),
                family_id="inflation measure and threshold family",
            )
            sensitivity = sensitivity_table.pivot(
                index=["measure", "band"], columns="asset", values="mean_difference"
            ).where(
                sensitivity_table.pivot(
                    index=["measure", "band"],
                    columns="asset",
                    values="meets_display_threshold",
                )
            )
            core_regimes = momentum_regime(point_momentum["CPILFESL"])
            measure_agreement = classification_transition_table(
                point_regimes,
                core_regimes,
            )
            display(sensitivity_table, sensitivity, measure_agreement)
            figure, _ = plot_sensitivity_heatmap(
                sensitivity,
                title="Headline and core acceleration-minus-deceleration contrasts",
                color_label="Difference in one-month mean return",
            )
            plt.show()
            plt.close(figure)

            figure, axis = plt.subplots(figsize=(7.5, 5.5))
            agreement_image = axis.imshow(measure_agreement.to_numpy(), cmap="Blues")
            axis.set(
                title="Headline and core momentum classification agreement",
                xlabel="Core classification",
                ylabel="Headline classification",
                xticks=range(len(measure_agreement.columns)),
                yticks=range(len(measure_agreement.index)),
                xticklabels=measure_agreement.columns,
                yticklabels=measure_agreement.index,
            )
            for row in range(len(measure_agreement.index)):
                for column in range(len(measure_agreement.columns)):
                    axis.text(
                        column,
                        row,
                        int(measure_agreement.iloc[row, column]),
                        ha="center",
                        va="center",
                    )
            figure.colorbar(agreement_image, ax=axis, label="Decision count")
            figure.tight_layout()
            plt.show()
            plt.close(figure)
            """
        ),
        markdown(
            r"""
            ## Latest-revised bias diagnostic

            Revised levels can change both year-over-year rates and six-month momentum. The
            comparison reports regime membership and conditional-mean differences when today's
            revisions are substituted into historical decisions. The plotted gap focuses on the
            headline momentum feature and remains a retrospective diagnostic.

            Material agreement or disagreement is retained without changing the primary feature
            definition or threshold.

            Latest-revised momentum uses the exact same four component months as each real-time
            decision. The transition table includes unclassified states, so availability changes
            are visible. The stability table is separate: it evaluates the real-time relative-return
            contrast across halves and after leaving out each contiguous episode.
            """
        ),
        code(
            """
            revision_comparison = compare_statistics(point_statistics, latest_statistics)
            classification_changes = classification_transition_table(
                point_regimes,
                latest_regimes,
            )
            stability = temporal_contrast_stability(
                relative_labels,
                point_regimes,
                treated="accelerating",
                reference="decelerating",
            )
            display(revision_comparison, classification_changes, stability)
            figure, _ = plot_revision_gap(
                point_momentum["CPIAUCSL"],
                latest_momentum["CPIAUCSL"],
                title="Headline inflation-momentum revision substitution gap",
            )
            plt.show()
            plt.close(figure)
            """
        ),
        markdown(
            r"""
            ## Limitations and live assertions

            CPI is not an investor-specific consumption basket, and `TIP` returns reflect real
            yields, duration, liquidity, and index mechanics as well as inflation accrual. Monthly
            decisions omit release-time reactions. The fixed ETF universe has inception and
            survivorship bias. Outcomes omit costs and taxes. Persistent regimes reduce effective
            sample size, longer labels overlap, normal intervals are approximate, and the asset,
            horizon, band, and inflation-measure family creates multiple-testing risk.

            Execution assertions cover temporal availability, alignment, provenance, finite
            summaries, and feature-label separation. They do not validate an economic story.

            CPI is a revised index and current series-definition metadata do not prove historical
            definition stability. Within-vintage arithmetic reduces that risk. The
            [ALFRED real-time guide](https://fred.stlouisfed.org/docs/api/fred/realtime_period.html)
            explains information vintages, while the
            [Treasury TIPS page](https://www.treasurydirect.gov/marketable-securities/tips/)
            explains principal indexation. Neither source implies that an ETF return must track
            the inflation feature over a one-month market horizon.
            """
        ),
        code(
            """
            audit = validate_study_outputs(
                prices,
                point_in_time,
                labels,
                point_regimes,
                point_statistics,
                expected_regimes=frozenset({"accelerating", "stable", "decelerating"}),
                transformed=point_momentum_result,
            )
            assert_component_periods_match(point_rate_result, latest_rate_result)
            assert_component_periods_match(point_momentum_result, latest_momentum_result)
            assert set(point_in_time.frame.columns).isdisjoint(labels[1].frame.columns)
            matched = point_in_time.provenance["available_from"].notna()
            assert point_in_time.provenance.loc[matched, "available_from"].le(
                point_in_time.provenance.loc[matched, "decision_date"] - pd.Timedelta(days=1)
            ).all()
            display(audit)
            session.close()
            """
        ),
        markdown(
            r"""
            ## Interpretation after execution

            Read feature coverage and regime counts before conditional means. Compare uncertainty
            and distributions with both baselines, then inspect the complete band grid, the core
            sensitivity, and latest-revised changes. Preserve null, unstable, and contrary
            findings. These are historical associations, not proof that an asset is a reliable
            inflation hedge or that the regimes support a profitable strategy.
            """
        ),
    ]


def revision_risk_notebook() -> list[Cell]:
    """Return the macroeconomic revision-risk study."""
    return [
        markdown(
            r"""
            # Macroeconomic revision risk

            This notebook asks whether classifying growth with today's revised history materially
            changes the cross-asset differences obtained from information available in real time.
            Revisions are treated as retrospective diagnostics, never as contemporaneously
            observable features.

            The real-GDP threshold, payroll sensitivity, outcomes, and baselines were fixed before
            execution. No observed provider values, tables, plots, or conclusions are saved in the
            committed notebook.

            **Primary protocol.** The decision is the last common ETF trading session of a complete
            month, using macro information available one calendar day earlier. Faster GDP growth is
            the treatment, slower growth the reference, and one month the primary horizon. For each
            core ETF, the primary revision estimand is the **signed** latest-revised
            faster-minus-slower contrast minus the signed point-in-time contrast on dates classified
            in both views. No direction is predeclared. Bonferroni intervals cover the five-asset
            family. A total revision-plus-availability estimate, longer horizons, GDP thresholds,
            payrolls, and temporal splits are exploratory. “Cleaner” or absolute separation is not
            claimed.
            """
        ),
        code(
            """
            import matplotlib.pyplot as plt
            import pandas as pd

            from studies._support import (
                CORE_SYMBOLS,
                STUDY_START,
                acquire_latest_series,
                acquire_monthly_prices,
                acquire_vintage_histories,
                assert_component_periods_match,
                assert_revision_change_identities,
                build_point_in_time_levels,
                classification_change_summary,
                classification_transition_table,
                compare_statistics,
                component_availability_summary,
                configure_plots,
                feature_provenance_summary,
                forward_labels,
                latest_revised_year_over_year,
                momentum_baseline,
                open_live_session,
                plot_coverage,
                plot_feature_comparison,
                plot_normalized_prices,
                plot_regime_contrasts,
                plot_regime_distributions,
                plot_regime_means,
                plot_regime_timeline,
                plot_revision_contrast_change,
                plot_revision_gap,
                plot_sample_sizes,
                plot_sensitivity_heatmap,
                point_in_time_year_over_year,
                regime_contrast_statistics,
                regime_statistics,
                regime_style,
                revision_contrast_change,
                simultaneous_interval_family,
                study_run_manifest,
                temporal_revision_change_stability,
                unconditional_statistics,
                validate_study_outputs,
            )

            configure_plots()
            pd.set_option("display.max_columns", 20)
            session = open_live_session()
            """
        ),
        markdown(
            r"""
            ## Hypothesis, series, and fixed market universe

            `GDPC1` is quarterly real gross domestic product. It is the primary series because
            benchmark revisions can alter the historical growth path. `PAYEMS` is monthly payroll
            employment and supplies a higher-frequency sensitivity. Both are revised and both are
            selected through ALFRED availability intervals.

            The core ETF universe spans equities, intermediate Treasuries, gold, commodities, and
            the dollar. The hypothesis is that latest-revised classification can change the signed
            faster-minus-slower return contrast. A second estimate restricts both views to the same
            classified dates, while availability transitions are reported separately. A contrary,
            near-zero, or unavailable change remains informative about this sample.

            Real GDP is a chain-type quantity measure, so benchmark updates can revise long spans
            and reference years. Payroll employment measures a different monthly concept; it is a
            sensitivity, not a validation target. The live normalized objects round-trip through a
            temporary DuckDB database before any transformation.
            """
        ),
        code(
            """
            price_history, market_provenance = acquire_monthly_prices(session, CORE_SYMBOLS)
            prices = price_history.loc[STUDY_START:]
            series_ids = ("GDPC1", "PAYEMS")
            histories = acquire_vintage_histories(session, series_ids, prices.index)
            latest = acquire_latest_series(session, series_ids)
            staleness = {
                "GDPC1": pd.Timedelta(days=150),
                "PAYEMS": pd.Timedelta(days=62),
            }
            point_in_time = build_point_in_time_levels(
                histories,
                prices.index,
                staleness,
                observation_date_columns={"GDPC1": "period_end"},
            )
            feature_provenance = feature_provenance_summary(point_in_time)
            manifest = study_run_manifest(
                prices,
                series_ids=series_ids,
                thresholds="GDP growth=2%; payroll sensitivity=0%",
                staleness=staleness,
            )
            display(manifest, market_provenance, feature_provenance)
            """
        ),
        markdown(
            r"""
            ## Unequal frequency and stale releases

            Monthly decisions do not turn quarterly GDP into monthly information. Between GDP
            releases, the newest admissible observation is carried only within a 150-day
            staleness ceiling, and provenance records the matched observation age. Payrolls use a
            shorter ceiling. The coverage plot exposes these policies rather than hiding them
            behind forward filling.

            GDP observation age is measured from the derived quarter end, not the quarter start.
            This allows the 150-day ceiling to span ordinary release spacing without turning the
            sample into release months only. The cutoff must still lie inside the selected version's
            availability interval. Observation period, availability, and this execution's retrieval
            time remain separate provenance fields.

            ETF inception and missing provider sessions affect the market panel independently of
            macro release coverage. Joint outcome counts are examined later.
            """
        ),
        code(
            """
            figure, _ = plot_coverage(market_provenance, feature_provenance)
            plt.show()
            plt.close(figure)
            """
        ),
        markdown(
            r"""
            ## Real-time and latest-revised growth paths

            Year-over-year growth is calculated within one complete vintage known at each decision.
            For newest source quarter \(t\), GDP growth is
            \(100(G_{d,t}/G_{d,t-4}-1)\); the exact year-ago quarter comes from the same snapshot.
            Payroll growth analogously uses exact source months \(t\) and \(t-12\). Repeated monthly
            decisions can refer to the same quarterly observation, but they never substitute twelve
            decision rows for four source quarters.

            Today's revised counterpart keeps the exact component periods and substitutes current
            values. Component provenance records actual period, availability, source identity,
            definition fields, and retrieval time. This avoids arithmetic across two benchmark
            vintages while making component availability changes auditable.

            Plotting both GDP and payroll growth distinguishes the primary quarterly feature from
            the monthly sensitivity before any return grouping occurs.
            """
        ),
        code(
            """
            point_growth_result = point_in_time_year_over_year(histories, point_in_time)
            latest_growth_result = latest_revised_year_over_year(point_in_time, latest)
            point_growth = point_growth_result.frame
            latest_growth = latest_growth_result.frame
            point_features = point_growth.rename(
                columns={"GDPC1": "Real GDP growth", "PAYEMS": "Payroll growth"}
            )
            latest_features = latest_growth.set_axis(point_features.columns, axis="columns")
            figure, _ = plot_feature_comparison(
                point_features,
                latest_features,
                tuple(point_features.columns),
            )
            plt.show()
            plt.close(figure)
            """
        ),
        markdown(
            r"""
            ## Primary classification and leakage boundary

            Faster real-GDP growth is above two percent year over year; slower growth is at or
            below two percent. The threshold is fixed and intentionally broader than a recession
            rule. It yields an interpretable growth comparison without claiming that a particular
            rate is structurally optimal.

            The point-in-time classification is the only primary regime. Later revisions are
            evaluation information, analogous to a label: they can describe how a past conclusion
            changed but cannot enter the decision-date feature.
            """
        ),
        code(
            """
            def growth_regime(growth: pd.Series, *, boundary: float = 2.0) -> pd.Series:
                regime = pd.Series(pd.NA, index=growth.index, dtype="string")
                regime.loc[growth.notna() & growth.gt(boundary)] = "faster growth"
                regime.loc[growth.notna() & growth.le(boundary)] = "slower growth"
                return regime

            point_regimes = growth_regime(point_growth["GDPC1"])
            latest_regimes = growth_regime(latest_growth["GDPC1"])
            display(point_regimes.value_counts(dropna=False).rename("decision count"))
            figure, _ = plot_regime_timeline(
                point_growth["GDPC1"],
                point_regimes,
                title="Point-in-time real-GDP growth classification",
                ylabel="Year-over-year percent change",
                boundaries=(2.0,),
            )
            plt.show()
            plt.close(figure)

            figure, axis = plt.subplots(figsize=(7, 7))
            valid = point_growth["GDPC1"].notna() & latest_growth["GDPC1"].notna()
            for regime in ("faster growth", "slower growth"):
                color, marker = regime_style(regime)
                selected = valid & point_regimes.eq(regime).fillna(False)
                axis.scatter(
                    point_growth.loc[selected, "GDPC1"],
                    latest_growth.loc[selected, "GDPC1"],
                    label=regime,
                    marker=marker,
                    color=color,
                    alpha=0.75,
                )
            combined = pd.concat(
                [point_growth.loc[valid, "GDPC1"], latest_growth.loc[valid, "GDPC1"]]
            )
            limits = (combined.min(), combined.max())
            axis.plot(limits, limits, color="#333333", linestyle="--", linewidth=1)
            axis.set_xlim(limits)
            axis.set_ylim(limits)
            axis.set_aspect("equal", adjustable="box")
            axis.set(
                title="Real-time and latest-revised GDP growth",
                xlabel="Point-in-time year-over-year growth (percent)",
                ylabel="Latest-revised year-over-year growth (percent)",
            )
            axis.legend()
            figure.tight_layout()
            plt.show()
            plt.close(figure)
            """
        ),
        markdown(
            r"""
            ## Separated outcomes and baselines

            One-, three-, and twelve-month asset returns are computed only from the Alpha Vantage
            price panel and stored in typed label objects. The final incomplete horizons remain
            missing, and each label carries its ending date. Macro features and asset labels have
            disjoint columns and construction paths.

            Unconditional outcomes and a trailing twelve-month price-momentum split provide two
            conventional benchmarks. Normalized closes show market history but do not represent a
            regime-switching portfolio.

            The return label is \(R_{d,h}=P_{d+h}/P_d-1\) and stores its actual ending close. Live
            checks require an exact \(h\)-calendar-month period offset and leave terminal outcomes
            missing. Both baselines use point-in-time GDP-regime-eligible dates. One year of earlier
            prices supplies the twelve-month momentum feature at the first analysis date.
            """
        ),
        code(
            """
            labels = forward_labels(prices)
            eligible = point_regimes.notna()
            unconditional = unconditional_statistics(labels, eligible=eligible)
            momentum = momentum_baseline(price_history, labels, eligible=eligible)
            display(unconditional, momentum)
            figure, _ = plot_normalized_prices(prices)
            plt.show()
            plt.close(figure)
            """
        ),
        markdown(
            r"""
            ## Conditional summaries and uncertainty

            The primary table contains the complete asset-by-regime-by-horizon family. Counts,
            coverage, means, horizon-return dispersion, positive shares,
            heteroskedasticity-and-autocorrelation-consistent (HAC) standard errors, confidence
            bounds,
            and one-month episode-aware drawdowns remain visible. Longer-horizon overlap is
            reflected in the minimum bandwidth, while an automatic rule permits additional serial
            covariance. One-month annualized volatility is reported in a separate column.

            Descriptive group intervals are pointwise. The five primary signed revision changes use
            Bonferroni simultaneous intervals, paired through aligned influence series so the
            covariance between the two classifications is retained. The display rule requires
            twelve outcomes and two outcome-eligible episodes per side; it is not a claim that two
            episodes make normal inference adequate. First/second-half and leave-one-episode-out
            results remain necessary context.

            Comparing the latest-revised table with the primary table is a specification-bias
            audit. It is not an invitation to use the revised table as a historical strategy.
            """
        ),
        code(
            """
            point_statistics = regime_statistics(labels, point_regimes)
            latest_statistics = regime_statistics(labels, latest_regimes)
            point_contrasts = regime_contrast_statistics(
                labels,
                point_regimes,
                treated="faster growth",
                reference="slower growth",
                assets=CORE_SYMBOLS,
            )
            total_revision_change = revision_contrast_change(
                labels,
                point_regimes,
                latest_regimes,
                treated="faster growth",
                reference="slower growth",
            )
            common_sample_revision_change = revision_contrast_change(
                labels,
                point_regimes,
                latest_regimes,
                treated="faster growth",
                reference="slower growth",
                common_classified_only=True,
            )
            display(
                point_statistics,
                point_contrasts,
                total_revision_change,
                common_sample_revision_change,
            )
            figure, _ = plot_regime_means(
                point_statistics,
                title="Real-time GDP growth and one-month outcomes",
            )
            plt.show()
            plt.close(figure)

            figure, _ = plot_regime_contrasts(
                point_contrasts,
                title="Real-time faster-minus-slower growth contrasts",
            )
            plt.show()
            plt.close(figure)

            figure, _ = plot_revision_contrast_change(
                common_sample_revision_change,
                title="Signed contrast change on dates classified in both views",
            )
            plt.show()
            plt.close(figure)
            """
        ),
        markdown(
            r"""
            ## Distributions and effective sample size

            Growth regimes cluster through expansions, slowdowns, and contractions. A large count
            of monthly decisions can therefore reflect fewer independent macro episodes. Box
            plots show the distribution behind each mean, while the count chart exposes state
            imbalance and incomplete forward horizons.

            Provider observations are retained as received after validation. No outlier is removed
            because it weakens or strengthens the predeclared hypothesis.

            Box plots show quartiles and retain every tail point. Count bars distinguish monthly
            outcomes from contiguous, outcome-eligible GDP episodes. Repeating one quarterly state
            over several monthly decisions can still make effective information diversity smaller
            than either number suggests, which is why leave-one-episode-out estimates are shown.
            """
        ),
        code(
            """
            figure, _ = plot_regime_distributions(
                labels[1],
                point_regimes,
                assets=("SPY", "IEF", "GLD", "DBC"),
                title="One-month outcomes by real-time GDP growth state",
            )
            plt.show()
            plt.close(figure)

            figure, _ = plot_sample_sizes(point_statistics)
            plt.show()
            plt.close(figure)
            """
        ),
        markdown(
            r"""
            ## Threshold and payroll sensitivity

            The GDP grid uses boundaries of zero, one, two, and three percent. Every cell reports
            the faster-minus-slower one-month mean for one core asset. The separate payroll
            sensitivity classifies positive versus nonpositive year-over-year employment growth.
            Both analyses are displayed in full; neither is selected by return magnitude.

            A pattern that depends on one GDP boundary or disappears with payroll growth is a
            fragility to report, not a prompt for another search.

            The GDP threshold table retains counts, episode counts, HAC errors, and intervals, and
            one exploratory Bonferroni family covers all twenty threshold-asset cells. Masked cells
            fail the minimum-data display rule; they do not mean zero. Payroll repeats both the
            total revision-plus-availability change and the common-classified-date signed change,
            so the monthly sensitivity tests the revision-risk question rather than merely showing
            another regime table.
            """
        ),
        code(
            """
            sensitivity_rows = []
            for boundary in (0.0, 1.0, 2.0, 3.0):
                regimes = growth_regime(point_growth["GDPC1"], boundary=boundary)
                table = regime_contrast_statistics(
                    {1: labels[1]},
                    regimes,
                    treated="faster growth",
                    reference="slower growth",
                    assets=CORE_SYMBOLS,
                )
                table.insert(0, "boundary", boundary)
                sensitivity_rows.append(table)
            sensitivity_table = simultaneous_interval_family(
                pd.concat(sensitivity_rows, ignore_index=True),
                family_id="GDP threshold family",
            )
            sensitivity = sensitivity_table.pivot(
                index="boundary", columns="asset", values="mean_difference"
            ).where(
                sensitivity_table.pivot(
                    index="boundary", columns="asset", values="meets_display_threshold"
                )
            )
            payroll_regimes = growth_regime(point_growth["PAYEMS"], boundary=0.0)
            latest_payroll_regimes = growth_regime(latest_growth["PAYEMS"], boundary=0.0)
            payroll_statistics = regime_statistics(labels, payroll_regimes)
            payroll_revision_change = revision_contrast_change(
                labels,
                payroll_regimes,
                latest_payroll_regimes,
                treated="faster growth",
                reference="slower growth",
            )
            common_payroll_revision_change = revision_contrast_change(
                labels,
                payroll_regimes,
                latest_payroll_regimes,
                treated="faster growth",
                reference="slower growth",
                common_classified_only=True,
            )
            display(
                sensitivity_table,
                sensitivity,
                payroll_statistics,
                payroll_revision_change,
                common_payroll_revision_change,
            )
            figure, _ = plot_sensitivity_heatmap(
                sensitivity,
                title="Faster-minus-slower contrasts across GDP boundaries",
                color_label="Difference in one-month mean return",
            )
            plt.show()
            plt.close(figure)
            """
        ),
        markdown(
            r"""
            ## Revision magnitude and classification instability

            The latest-revised diagnostic measures changes in selected growth values, regime
            membership, sample counts, and conditional means. A classification cross-tab makes
            boundary crossings explicit. The revision-gap figure shows the retrospective GDP
            growth difference without feeding it back into the feature panel.

            The hypothesis concerns whether revised history changes descriptive conclusions. It
            does not claim that future revision direction can be traded.

            “Signed contrast change” is defined as
            \((\bar R_F-\bar R_S)_{latest}-(\bar R_F-\bar R_S)_{real\ time}\). It is not the change
            in absolute magnitude. Aligned influence contributions retain covariance between the
            two classifications. The primary common-sample table requires a classification in both
            views. A separate total table allows component availability to change, while the
            component summary, reclassification denominator and rate, and unclassified transition
            cells identify that channel explicitly. The plotted simultaneous intervals use the
            common-sample version.
            """
        ),
        code(
            """
            revision_comparison = compare_statistics(point_statistics, latest_statistics)
            classification_changes = classification_transition_table(
                point_regimes,
                latest_regimes,
            )
            classification_summary = classification_change_summary(
                point_regimes,
                latest_regimes,
            )
            component_availability = component_availability_summary(
                point_growth_result,
                latest_growth_result,
            )
            revision_diagnostics = pd.DataFrame(
                {
                    "point-in-time growth": point_growth["GDPC1"],
                    "latest-revised growth": latest_growth["GDPC1"],
                    "classification changed": point_regimes.ne(latest_regimes),
                }
            )
            stability = temporal_revision_change_stability(
                labels,
                point_regimes,
                latest_regimes,
                treated="faster growth",
                reference="slower growth",
                assets=CORE_SYMBOLS,
            )
            display(
                revision_comparison,
                classification_changes,
                classification_summary,
                component_availability,
                total_revision_change,
                common_sample_revision_change,
                revision_diagnostics,
                stability,
            )
            figure, _ = plot_revision_gap(
                point_growth["GDPC1"],
                latest_growth["GDPC1"],
                title="Real-GDP growth revision substitution gap",
            )
            plt.show()
            plt.close(figure)
            """
        ),
        markdown(
            r"""
            ## Limitations and adversarial assertions

            Quarterly GDP is released with delay and revised through annual and benchmark cycles.
            A monthly decision grid repeats quarterly information. Payroll employment captures a
            different concept and is not a validation target for GDP. The ETF universe has
            inception, fixed-selection, and survivorship bias. Returns exclude costs, taxes, and
            executable release timing. Overlapping labels, clustered growth regimes, approximate
            intervals, and the full asset-horizon-threshold family create multiple-testing risk.

            Live assertions verify temporal availability, provenance completeness, label
            separation, index alignment, multiple regimes, and finite outputs.

            Current FRED definition fields are applied to historical vintage rows and cannot prove
            that old benchmark metadata were unchanged. Within-vintage ratios avoid mixing two
            definitions, but revision interpretation still includes methodological updates. BEA's
            [GDP release information](https://www.bea.gov/news/gdp-release-additional-information)
            explains advance, second, third, annual, and comprehensive updates. The
            [BEA methodology index](https://www.bea.gov/resources/methodologies) provides deeper
            national-account concepts. ALFRED supplies historical information sets; none of these
            sources makes revisions observable at the earlier market decision.
            """
        ),
        code(
            """
            audit = validate_study_outputs(
                prices,
                point_in_time,
                labels,
                point_regimes,
                point_statistics,
                expected_regimes=frozenset({"faster growth", "slower growth"}),
                transformed=point_growth_result,
            )
            assert_component_periods_match(point_growth_result, latest_growth_result)
            assert_revision_change_identities(
                labels,
                point_regimes,
                treated="faster growth",
                reference="slower growth",
            )
            assert set(point_in_time.frame.columns).isdisjoint(labels[1].frame.columns)
            matched = point_in_time.provenance["available_from"].notna()
            assert point_in_time.provenance.loc[matched, "available_from"].le(
                point_in_time.provenance.loc[matched, "decision_date"] - pd.Timedelta(days=1)
            ).all()
            display(audit)
            session.close()
            """
        ),
        markdown(
            r"""
            ## Interpretation after execution

            Start with matched observation ages, feature coverage, and regime counts. Compare
            point-in-time distributions and uncertainty with both baselines, then inspect the full
            GDP grid, payroll sensitivity, classification cross-tab, and revised-history changes.
            Preserve negative and unstable evidence. This notebook studies revision-sensitive
            association; it does not prove causality, forecast skill, or strategy profitability.
            """
        ),
    ]


def main() -> None:
    """Build the complete notebook suite."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail when a committed notebook differs from its reviewable source",
    )
    arguments = parser.parse_args()
    notebooks = {
        "01_growth_inflation_quadrants.ipynb": growth_inflation_notebook(),
        "02_labor_deterioration.ipynb": labor_notebook(),
        "03_yield_curve_inversion.ipynb": yield_curve_notebook(),
        "04_inflation_momentum.ipynb": inflation_momentum_notebook(),
        "05_revision_risk.ipynb": revision_risk_notebook(),
    }
    for name, cells in notebooks.items():
        write_notebook(name, cells, check=arguments.check)


if __name__ == "__main__":
    main()
