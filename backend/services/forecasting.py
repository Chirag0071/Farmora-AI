"""Dependency-light price forecasting baseline (no scikit-learn required)."""
import numpy as np
import pandas as pd

def linear_forecast(history: pd.DataFrame, periods: int = 12) -> pd.DataFrame:
    columns = ["date", "modal_price"]
    if history is None or history.empty or periods <= 0:
        return pd.DataFrame(columns=columns)
    data = history.copy()
    data["date"] = pd.to_datetime(data["date"], errors="coerce")
    data["modal_price"] = pd.to_numeric(data["modal_price"], errors="coerce")
    data = data.dropna(subset=columns).sort_values("date").drop_duplicates("date")
    if data.empty:
        return pd.DataFrame(columns=columns)
    values = data["modal_price"].astype(float).to_numpy()
    last_date = data["date"].iloc[-1]
    future_dates = pd.date_range(last_date + pd.offsets.MonthBegin(1), periods=periods, freq="MS")
    if len(values) < 3:
        predictions = np.repeat(values[-1], periods)
    else:
        # Fit only the latest 12 observations and damp the trend to avoid runaway extrapolation.
        recent = values[-min(12, len(values)):]
        slope = float(np.polyfit(np.arange(len(recent)), recent, 1)[0])
        slope = float(np.clip(slope, -max(abs(values[-1]) * 0.15, 1), max(abs(values[-1]) * 0.15, 1)))
        predictions = [max(0.0, values[-1] + slope * sum(0.8 ** k for k in range(i + 1))) for i in range(periods)]
    return pd.DataFrame({"date": future_dates, "modal_price": np.round(predictions, 2)})

def forecast_prices(monthly_history: pd.DataFrame, periods: int = 12) -> pd.DataFrame:
    """Generate an explicitly approximate forecast from observed monthly prices."""
    return linear_forecast(monthly_history, periods)
