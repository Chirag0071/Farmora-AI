# backend/services/recommendations.py

import pandas as pd

from backend.services.agmarknet import (
    fetch_agmarknet,
    records_to_dataframe,
    AGMARKNETError
)


def _score_crop(df):

    if df.empty:
        return None

    data = df.copy()

    data["arrival_date"] = pd.to_datetime(
        data["arrival_date"],
        errors="coerce"
    )

    data["modal_price"] = pd.to_numeric(
        data["modal_price"],
        errors="coerce"
    )

    data = data.dropna(
        subset=[
            "arrival_date",
            "modal_price"
        ]
    )

    if data.empty:
        return None

    latest_date = (
        data["arrival_date"].max()
    )

    recent = data[
        data["arrival_date"]
        >= latest_date -
        pd.Timedelta(days=365)
    ]

    if recent.empty:
        recent = data

    average_price = float(
        recent["modal_price"].mean()
    )

    observations = len(
        recent
    )

    market_count = int(
        recent["market"].nunique()
    )

    monthly = (
        recent
        .set_index("arrival_date")
        ["modal_price"]
        .resample("MS")
        .mean()
        .dropna()
    )

    trend = 0.0

    if len(monthly) >= 3:

        middle = max(
            1,
            len(monthly) // 2
        )

        first = float(
            monthly.iloc[:middle].mean()
        )

        last = float(
            monthly.iloc[middle:].mean()
        )

        if first > 0:

            trend = (
                (last - first)
                / first
            ) * 100

    # --------------------------------------------------------
    # Market-activity score
    # --------------------------------------------------------

    score = (

        min(
            observations,
            365
        ) * 0.30

        +

        min(
            market_count,
            20
        ) * 5 * 0.25

        +

        min(
            average_price / 100,
            100
        ) * 0.25

        +

        max(
            min(trend, 30),
            -30
        ) * 0.20
    )

    return {

        "average_price":
            round(
                average_price,
                2
            ),

        "market_count":
            market_count,

        "observations":
            observations,

        "trend_percent":
            round(
                trend,
                2
            ),

        "score":
            round(
                score,
                2
            )
    }


def get_crop_suggestions(
    state,
    district,
    selected_crop=None,
    max_results=8
):

    records = fetch_agmarknet(
        state=state,
        district=district,
        commodity=None
    )

    df = records_to_dataframe(
        records
    )

    if df.empty:

        raise AGMARKNETError(
            f"No market data found for "
            f"{district}, {state}."
        )

    candidates = []

    for commodity, group in (
        df.groupby("commodity")
    ):

        commodity = str(
            commodity
        ).strip()

        if not commodity:
            continue

        if (
            selected_crop
            and commodity.lower()
            == selected_crop.lower()
        ):
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