from __future__ import annotations

from typing import Any, cast

import plotly.graph_objects as go

from persistra.viz._style import COLORWAY, color_for, styled_figure


def test_colorway_is_nonempty_list_of_strings():
    assert isinstance(COLORWAY, tuple)
    assert COLORWAY and all(isinstance(c, str) for c in COLORWAY)


def test_color_for_cycles_through_colorway():
    assert color_for(0) == COLORWAY[0]
    assert color_for(len(COLORWAY)) == COLORWAY[0]


def test_styled_figure_applies_title_and_axis_labels():
    fig = styled_figure(title="T", xaxis_title="X", yaxis_title="Y")
    assert isinstance(fig, go.Figure)
    layout = cast("Any", fig.layout)
    assert layout.title.text == "T"
    assert layout.xaxis.title.text == "X"
    assert layout.yaxis.title.text == "Y"
