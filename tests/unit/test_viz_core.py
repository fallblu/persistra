from __future__ import annotations

import json

import pytest

from persistra.errors import FigureResourceLimitError
from persistra.viz._core import finish_figure, graph_objects, reduce_xy
from persistra.viz.models import FigureConfig, FigureLimits, VisualReductionPolicy


def test_reduce_xy_policies_and_limits() -> None:
    x = list(range(10))
    y: list[float | None] = [float(value) for value in range(10)]
    strict = FigureConfig(limits=FigureLimits(max_input_rows=5))
    with pytest.raises(FigureResourceLimitError):
        reduce_xy(x, y, strict)

    every_nth = FigureConfig(
        reduction=VisualReductionPolicy.every_nth(4),
        limits=FigureLimits(max_points_per_trace=5),
    )
    reduced_x, reduced_y, evidence = reduce_xy(x, y, every_nth)
    assert reduced_x == [0, 4, 8, 9]
    assert reduced_y == [0.0, 4.0, 8.0, 9.0]
    assert evidence["policy"] == "every_nth"
    assert evidence["warning"] is not None

    sparse = FigureConfig(
        reduction=VisualReductionPolicy.min_max_envelope(2),
        limits=FigureLimits(max_points_per_trace=8),
    )
    gap_y: list[float | None] = [None, 1.0, -3.0, None, 5.0, 2.0, None, 0.0, 4.0, 1.0]
    _, envelope_y, envelope_evidence = reduce_xy(x, gap_y, sparse)
    assert -3.0 in envelope_y
    assert 5.0 in envelope_y
    assert envelope_evidence["policy"] == "min_max_envelope"

    still_too_many = FigureConfig(
        reduction=VisualReductionPolicy.every_nth(2),
        limits=FigureLimits(max_points_per_trace=3),
    )
    with pytest.raises(FigureResourceLimitError):
        reduce_xy(x, y, still_too_many)


def test_finish_figure_metadata_annotations_and_limits() -> None:
    go = graph_objects()
    figure = finish_figure(
        go.Figure(go.Scatter(x=[1, 2], y=[3.0, 4.0], name="series")),
        config=FigureConfig(title="Test figure"),
        kind="persistra.figure.test@1",
        sources={"run_record_id": "run"},
        counts={"rows": 2},
        reduction={
            "policy": "every_nth",
            "parameter": 2,
            "original_count": 4,
            "rendered_count": 2,
            "warning": "Visual reduction applied; financial values were not recomputed.",
        },
        warnings=("fidelity.finding",),
        xaxis_title="x",
        yaxis_title="y",
    )
    payload = json.loads(figure.to_json())
    metadata = payload["layout"]["meta"]
    assert metadata["figure_kind"] == "persistra.figure.test@1"
    assert "fidelity.finding" in metadata["warnings"]
    assert payload["layout"]["annotations"]

    empty = finish_figure(
        go.Figure(),
        config=FigureConfig(title="Empty"),
        kind="persistra.figure.test@1",
        sources={},
        counts={"rows": 0},
    )
    empty_payload = json.loads(empty.to_json())
    assert empty_payload["layout"]["annotations"][0]["text"] == (
        "No applicable observations"
    )

    with pytest.raises(FigureResourceLimitError):
        finish_figure(
            go.Figure(go.Scatter(x=[1], y=[1.0])),
            config=FigureConfig(
                title="Tiny budget",
                limits=FigureLimits(max_figure_json_bytes=64),
            ),
            kind="persistra.figure.test@1",
            sources={},
            counts={"rows": 1},
        )
    with pytest.raises(FigureResourceLimitError):
        finish_figure(
            go.Figure([go.Scatter(x=[1], y=[1.0]), go.Scatter(x=[1], y=[2.0])]),
            config=FigureConfig(title="Traces", limits=FigureLimits(max_traces=1)),
            kind="persistra.figure.test@1",
            sources={},
            counts={"rows": 1},
        )
