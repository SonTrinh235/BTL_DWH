"""Tiện ích giao diện dùng chung: bảng màu, style biểu đồ, KPI."""
import plotly.graph_objects as go
import streamlit as st

# Bảng màu phân loại (thứ tự cố định) và dãy tuần tự một tông xanh
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#6250d6"]
SEQ_BLUE = [[0.0, "#e8f1fc"], [0.35, "#8fbcf0"], [0.7, "#2a78d6"], [1.0, "#0d3b78"]]
STATUS_ICON = {"urgent": "🔴", "action": "🟠", "watch": "🟡", "ok": "🟢"}


def style(fig: go.Figure, height: int = 380, legend: bool = True) -> go.Figure:
    """Style nhất quán: lưới nhạt, không viền thừa, legend nằm ngang phía trên."""
    fig.update_layout(
        height=height, margin=dict(l=8, r=8, t=36, b=8), showlegend=legend,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, title_text=""),
        font=dict(size=13), hoverlabel=dict(font_size=13),
    )
    fig.update_xaxes(showgrid=False, title_standoff=8)
    fig.update_yaxes(gridcolor="rgba(128,128,128,0.2)", zeroline=False)
    return fig


def chart(fig: go.Figure, **kw) -> None:
    st.plotly_chart(style(fig, **kw), width="stretch")


def kpi_row(items: list[tuple[str, str, str | None]]) -> None:
    cols = st.columns(len(items))
    for c, (label, value, hint) in zip(cols, items):
        c.metric(label, value, help=hint)
