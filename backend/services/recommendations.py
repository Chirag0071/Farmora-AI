from typing import List

import pandas as pd


def _score_crop(df):

    if df.empty:

        return None

    df = df.copy()

    df["arrival_date"] = pd.to_datetime(
        df["arrival_date"],
        errors="coerce"
    )

    df["modal_price"] = pd.to_numeric(
        df["modal_price"],
        errors="coerce"
    )

    df = df.dropna(
        subset=[
            "arrival_date",
            "modal_price"
        ]
    )

    if df.empty:

        return None

    recent_date = df["arrival_date"].max()

    recent = df[
        df["arrival_date"]
        >= recent_date - pd.Timedelta(days=365)
    ]

    if recent.empty:

        recent = df

    average_price = (
        recent["modal_price"]
        .mean()
    )

    observations = len(recent)

    market_count = (
        recent["market"]
        .nunique()
    )

    recent_months = (
        recent
        .set_index("arrival_date")
        ["modal_price"]
        .resample("MS")
        .mean()
        .dropna()
    )

    if len(recent_months) >= 3:

        first = recent_months.iloc[
            :max(1, len(recent_months) // 2)
        ].mean()

        last = recent_months.iloc[
            len(recent_months) // 2:
        ].mean()

        trend = (
            ((last - first) / first) * 100
            if first
            else 0
        )

    else:

        trend = 0

    # Normalised practical demand score.
    score = (
        min(observations, 365) * 0.30
        + min(market_count, 20) * 5 * 0.25
        + min(average_price / 100, 100) * 0.25
        + max(min(trend, 30), -30) * 0.20
    )

    return {
        "average_price": round(
            float(average_price),
            2
        ),
        "market_count": int(
            market_count
        ),
        "observations": int(
            observations
        ),
        "trend_percent": round(
            float(trend),
            2
        ),
        "score": round(
            float(score),
            2
        )
    }


def recommend_crops(
    state,
    district,
    selected_crop,
    base_dataframe,
    max_results=8
):

    if base_dataframe.empty:

        return []

    # Use commodities available in the selected
    # district/state data.
    candidates = []

    for commodity, group in (
        base_dataframe
        .groupby("commodity")
    ):

        commodity = str(
            commodity
        ).strip()

        if not commodity:

            continue

        stats = _score_crop(
            group
        )

        if not stats:

            continue

        candidates.append({
            "crop": commodity,
            **stats
        })

    if not candidates:

        return []

    result = pd.DataFrame(
        candidates
    )

    result = result.sort_values(
        [
            "score",
            "trend_percent",
            "market_count"
        ],
        ascending=False
    )

    result = result.head(
        max_results
    )

    return result.to_dict(
        orient="records"
    )