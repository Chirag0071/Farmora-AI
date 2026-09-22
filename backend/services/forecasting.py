import numpy as np
import pandas as pd

from sklearn.ensemble import RandomForestRegressor


FEATURES = [
    "year",
    "month",
    "month_sin",
    "month_cos",
    "lag_1",
    "lag_2",
    "lag_3",
    "lag_6",
    "lag_12",
    "rolling_3",
    "rolling_6",
    "rolling_12",
]


def create_features(df):

    data = df.copy()

    data["date"] = pd.to_datetime(
        data["date"]
    )

    data = (
        data
        .sort_values("date")
        .drop_duplicates("date")
        .reset_index(drop=True)
    )

    data["year"] = data["date"].dt.year

    data["month"] = data["date"].dt.month

    data["month_sin"] = np.sin(
        2 * np.pi * data["month"] / 12
    )

    data["month_cos"] = np.cos(
        2 * np.pi * data["month"] / 12
    )

    data["lag_1"] = data["modal_price"].shift(1)
    data["lag_2"] = data["modal_price"].shift(2)
    data["lag_3"] = data["modal_price"].shift(3)
    data["lag_6"] = data["modal_price"].shift(6)
    data["lag_12"] = data["modal_price"].shift(12)

    data["rolling_3"] = (
        data["modal_price"]
        .shift(1)
        .rolling(3)
        .mean()
    )

    data["rolling_6"] = (
        data["modal_price"]
        .shift(1)
        .rolling(6)
        .mean()
    )

    data["rolling_12"] = (
        data["modal_price"]
        .shift(1)
        .rolling(12)
        .mean()
    )

    return data


def _linear_forecast(history, periods):

    history = history.copy()

    history["date"] = pd.to_datetime(
        history["date"]
    )

    history = history.dropna(
        subset=["modal_price"]
    )

    if history.empty:

        return pd.DataFrame(
            columns=[
                "date",
                "modal_price"
            ]
        )

    if len(history) == 1:

        value = float(
            history["modal_price"].iloc[-1]
        )

        future_dates = pd.date_range(
            history["date"].iloc[-1]
            + pd.offsets.MonthBegin(1),
            periods=periods,
            freq="MS"
        )

        return pd.DataFrame({
            "date": future_dates,
            "modal_price": [value] * periods
        })

    x = np.arange(
        len(history)
    )

    y = history["modal_price"].values

    slope, intercept = np.polyfit(
        x,
        y,
        1
    )

    future_x = np.arange(
        len(history),
        len(history) + periods
    )

    predictions = (
        slope * future_x
        + intercept
    )

    predictions = np.maximum(
        predictions,
        0
    )

    future_dates = pd.date_range(
        history["date"].iloc[-1]
        + pd.offsets.MonthBegin(1),
        periods=periods,
        freq="MS"
    )

    return pd.DataFrame({
        "date": future_dates,
        "modal_price": predictions
    })


def forecast_prices(
    monthly_history,
    periods=12
):

    if monthly_history.empty:

        return pd.DataFrame(
            columns=[
                "date",
                "modal_price"
            ]
        )

    history = monthly_history.copy()

    history["date"] = pd.to_datetime(
        history["date"]
    )

    history = (
        history
        .sort_values("date")
        .drop_duplicates("date")
        .reset_index(drop=True)
    )

    # Not enough data for all lag features.
    if len(history) < 18:

        return _linear_forecast(
            history,
            periods
        )

    feature_data = create_features(
        history
    )

    train = feature_data.dropna(
        subset=FEATURES + ["modal_price"]
    )

    if len(train) < 12:

        return _linear_forecast(
            history,
            periods
        )

    model = RandomForestRegressor(
        n_estimators=400,
        max_depth=12,
        min_samples_leaf=2,
        random_state=42,
        n_jobs=-1
    )

    model.fit(
        train[FEATURES],
        train["modal_price"]
    )

    working = history.copy()

    predictions = []

    for _ in range(periods):

        next_date = (
            working["date"].iloc[-1]
            + pd.offsets.MonthBegin(1)
        )

        values = working[
            "modal_price"
        ].tolist()

        if len(values) >= 12:

            lag_12 = values[-12]

        else:

            lag_12 = values[0]

        row = {
            "date": next_date,
            "modal_price": np.nan
        }

        temp = pd.concat(
            [
                working,
                pd.DataFrame([row])
            ],
            ignore_index=True
        )

        temp["year"] = (
            temp["date"].dt.year
        )

        temp["month"] = (
            temp["date"].dt.month
        )

        temp["month_sin"] = np.sin(
            2 * np.pi * temp["month"] / 12
        )

        temp["month_cos"] = np.cos(
            2 * np.pi * temp["month"] / 12
        )

        temp["lag_1"] = (
            temp["modal_price"]
            .shift(1)
        )

        temp["lag_2"] = (
            temp["modal_price"]
            .shift(2)
        )

        temp["lag_3"] = (
            temp["modal_price"]
            .shift(3)
        )

        temp["lag_6"] = (
            temp["modal_price"]
            .shift(6)
        )

        temp["lag_12"] = (
            temp["modal_price"]
            .shift(12)
        )

        temp["rolling_3"] = (
            temp["modal_price"]
            .shift(1)
            .rolling(3)
            .mean()
        )

        temp["rolling_6"] = (
            temp["modal_price"]
            .shift(1)
            .rolling(6)
            .mean()
        )

        temp["rolling_12"] = (
            temp["modal_price"]
            .shift(1)
            .rolling(12)
            .mean()
        )

        latest = temp.iloc[-1]

        X = pd.DataFrame(
            [{
                feature: latest[feature]
                for feature in FEATURES
            }]
        )

        if X.isna().any().any():

            return _linear_forecast(
                history,
                periods
            )

        prediction = float(
            model.predict(X)[0]
        )

        prediction = max(
            0,
            prediction
        )

        predictions.append({
            "date": next_date,
            "modal_price": prediction
        })

        working = pd.concat(
            [
                working,
                pd.DataFrame(
                    [{
                        "date": next_date,
                        "modal_price": prediction
                    }]
                )
            ],
            ignore_index=True
        )

    return pd.DataFrame(
        predictions
    )