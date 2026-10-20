"""Stacked column chart of past, present and forecast prices (Plotly)."""

import pandas as pd
import plotly.graph_objects as go

COLORS = {
    "Past": "#4da3ff",
    "Present": "#ffb703",
    "Future": "#2ecc71",
}


def build_price_3d_chart(history, present, forecast):
    """Stacked column chart: one column per month, stacked by period.

    history / forecast: DataFrames with date, modal_price.
    present: dict with date, modal_price (latest observed price) or None.
    (Function name kept so result.py does not need to change.)
    """

    categories = []
    values = {"Past": [], "Present": [], "Future": []}

    def add(label, text, price):
        categories.append(text)
        for key in values:
            values[key].append(price if key == label else 0)

    if history is not None and not history.empty:
        for _, r in history.sort_values("date").iterrows():
            add("Past", f"{pd.Timestamp(r['date']):%b %y}", float(r["modal_price"]))

    if present:
        add("Present", f"Now ({pd.Timestamp(present['date']):%d %b %y})", float(present["modal_price"]))

    if forecast is not None and not forecast.empty:
        for _, r in forecast.sort_values("date").iterrows():
            add("Future", f"{pd.Timestamp(r['date']):%b %y}", float(r["modal_price"]))

    if not categories:
        return None

    fig = go.Figure()

    for label in ("Past", "Present", "Future"):
        if not any(values[label]):
            continue
        fig.add_trace(go.Bar(
            x=categories,
            y=values[label],
            name=label,
            marker_color=COLORS[label],
            # hide zero segments from the tooltip
            hovertemplate=f"{label}<br>%{{x}}<br>₹%{{y:,.0f}}/qtl<extra></extra>",
        ))

    fig.update_layout(
        barmode="stack",
        height=480,
        margin=dict(l=10, r=10, t=30, b=10),
        paper_bgcolor="rgba(10,12,17,0.78)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="white"),
        legend=dict(orientation="h", y=1.08, x=0),
        xaxis=dict(type="category", tickangle=-45, gridcolor="rgba(255,255,255,0.1)"),
        yaxis=dict(title="Modal price (₹/qtl)", gridcolor="rgba(255,255,255,0.15)", rangemode="tozero"),
    )
    return fig


def build_market_map(locations):
    """pydeck map with a red dot per market; hovering shows the market name.

    locations: DataFrame with market, lat, lon.
    """

    import pydeck as pdk

    data = locations[["market", "lat", "lon"]].copy()
    data["lat"] = data["lat"].astype(float)
    data["lon"] = data["lon"].astype(float)

    span = max(data["lat"].max() - data["lat"].min(), data["lon"].max() - data["lon"].min(), 0.01)
    zoom = 12 if span < 0.05 else 10 if span < 0.3 else 9 if span < 0.6 else 8 if span < 1.2 else 7 if span < 3 else 5

    dots = pdk.Layer(
        "ScatterplotLayer",
        data=data,
        get_position="[lon, lat]",
        get_fill_color=[255, 0, 0, 230],
        get_radius=900,
        radius_min_pixels=7,
        radius_max_pixels=14,
        pickable=True,
        auto_highlight=True,
    )

    return pdk.Deck(
        layers=[dots],
        initial_view_state=pdk.ViewState(
            latitude=float(data["lat"].mean()),
            longitude=float(data["lon"].mean()),
            zoom=zoom,
        ),
        map_style="light",
        tooltip={"html": "<b>{market}</b>"},
    )