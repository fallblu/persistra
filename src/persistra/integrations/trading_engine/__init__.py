"""Build, run, import, and analyze deterministic trading-engine replays."""

from persistra.integrations.trading_engine.analysis import (
    ExecutionAnalysisPolicy,
    ExecutionAnalysisResult,
    ExecutionComparisonPolicy,
    ExecutionComparisonResult,
    InitialEquitySource,
    TurnoverDenominator,
    analyze_execution,
    compare_execution,
)
from persistra.integrations.trading_engine.journal import read_journal
from persistra.integrations.trading_engine.model import (
    BarClockPolicy,
    EngineRunResult,
    ExecutionInstrument,
    ExecutionPolicy,
    ExecutionReplayResult,
    JournalEvent,
    RiskPolicy,
    RunCompletion,
    ScenarioBar,
    SizingPolicy,
    TargetDecision,
    TradingEngineProcessError,
    TradingEngineScenario,
)
from persistra.integrations.trading_engine.runner import run_scenario
from persistra.integrations.trading_engine.scenario import (
    build_scenario,
    read_scenario,
    scenario_from_json,
    scenario_to_json,
    write_scenario,
)

__all__ = [
    "BarClockPolicy",
    "EngineRunResult",
    "ExecutionAnalysisPolicy",
    "ExecutionAnalysisResult",
    "ExecutionComparisonPolicy",
    "ExecutionComparisonResult",
    "ExecutionInstrument",
    "ExecutionPolicy",
    "ExecutionReplayResult",
    "InitialEquitySource",
    "JournalEvent",
    "RiskPolicy",
    "RunCompletion",
    "ScenarioBar",
    "SizingPolicy",
    "TargetDecision",
    "TradingEngineProcessError",
    "TradingEngineScenario",
    "TurnoverDenominator",
    "analyze_execution",
    "build_scenario",
    "compare_execution",
    "read_journal",
    "read_scenario",
    "run_scenario",
    "scenario_from_json",
    "scenario_to_json",
    "write_scenario",
]
