from __future__ import annotations
 
import warnings
 
import numpy as np
import pandas as pd
 
try:
    from sklearn.ensemble import ExtraTreesRegressor, RandomForestRegressor
 
    SKLEARN_AVAILABLE = True
except ImportError:  # keeps the API alive even if scikit-learn is missing
    SKLEARN_AVAILABLE = False
 
 
COLUMNS = ["date", "modal_price"]
 
MIN_ML_MONTHS = 16          # below this, trees have too few rows to learn from
SEASONAL_MIN_MONTHS = 30    # need >= 2.5 years before using seasonal features
MAX_GAP_MONTHS = 2          # longer gaps cut the series (we never invent data)
MAX_MONTHLY_MOVE = 0.20     # one month may not move the price by more than ~20 %
RANGE_MARGIN = 0.35         # forecast stays within observed log-range +/- 35 %
BACKTEST_ORIGINS = 10
BACKTEST_HORIZON = 6
MIN_TRAIN_ROWS = 8
RANDOM_STATE = 42
 
LAST_RUN_INFO: dict = {}    # details of the most recent forecast (for logging / debugging)
 
 
# ============================================================
# Series preparation
# ============================================================
 
def _prepare_series(history: pd.DataFrame) -> pd.Series:
    """Monthly price series with a continuous month index (short gaps interpolated)."""
    data = history.copy()
    data["date"] = pd.to_datetime(data["date"], errors="coerce")
    data["modal_price"] = pd.to_numeric(data["modal_price"], errors="coerce")
    data = data.dropna(subset=COLUMNS)
    data = data[data["modal_price"] > 0]
    if data.empty:
        return pd.Series(dtype=float)
 
    data["date"] = data["date"].dt.to_period("M").dt.to_timestamp()
    series = data.groupby("date")["modal_price"].mean().sort_index()
 
    # Keep only the latest stretch with no gap longer than MAX_GAP_MONTHS.
    months = (series.index.year * 12 + series.index.month).to_numpy()
    breaks = np.where(np.diff(months) > MAX_GAP_MONTHS + 1)[0]
    if len(breaks):
        series = series.iloc[breaks[-1] + 1:]
 
    full_index = pd.date_range(series.index[0], series.index[-1], freq="MS")
    series = series.reindex(full_index).interpolate(method="linear")
    return series.astype(float)
 
 
def _clip_outliers(log_values: np.ndarray) -> np.ndarray:
    """Clip extreme spikes (data-entry errors) using a wide IQR fence in log space."""
    if len(log_values) < 8:
        return log_values
    q1, q3 = np.percentile(log_values, [25, 75])
    iqr = q3 - q1
    if iqr == 0:
        return log_values
    return np.clip(log_values, q1 - 3 * iqr, q3 + 3 * iqr)
 
 
# ============================================================
# Feature engineering
# ============================================================
 
def _seasonal_index(x: np.ndarray, months: np.ndarray) -> dict[int, float]:
    """Average log-deviation of each calendar month from its trailing 12-month mean."""
    deviations: dict[int, list[float]] = {}
    for i in range(11, len(x)):
        deviations.setdefault(int(months[i]), []).append(x[i] - x[i - 11:i + 1].mean())
    return {m: float(np.mean(v)) for m, v in deviations.items()}
 
 
def _features(x: np.ndarray, months: np.ndarray, next_month: int, seasonal: bool) -> list[float]:
    """Features describing the history `x` (log prices, with calendar `months`) used to predict the next change."""
    last = x[-1]
    diffs = np.diff(x)
    row = [
        diffs[-1],                              # last month's move
        diffs[-2],
        diffs[-3],
        last - x[-3:].mean(),                   # distance from short / medium / long averages
        last - x[-6:].mean(),
        last - x[-min(12, len(x)):].mean(),
        diffs[-6:].std(),                       # recent volatility
        x[-3:].mean() - x[-6:-3].mean(),        # 3-month trend
    ]
    if seasonal:
        index = _seasonal_index(x, months)
        row += [
            np.sin(2 * np.pi * next_month / 12),
            np.cos(2 * np.pi * next_month / 12),
            x[-12] - last,                      # price a year ago (same calendar month) vs now
            index.get(next_month, 0.0),         # usual seasonal high/low of the coming month
            index.get(int(months[-1]), 0.0),    # ... and of the current month
        ]
    return row
 
 
def _build_training_set(x: np.ndarray, months: np.ndarray, seasonal: bool):
    start = 12 if seasonal else 6
    rows, targets, weights = [], [], []
    for t in range(start, len(x)):
        rows.append(_features(x[:t], months[:t], months[t], seasonal))
        targets.append(x[t] - x[t - 1])
        weights.append(0.5 ** ((len(x) - 1 - t) / 12))      # recent months matter more
    return np.array(rows), np.array(targets), np.array(weights)
 
 
# ============================================================
# Models
# ============================================================
 
def _new_forest(kind: str):
    common = dict(n_estimators=150, min_samples_leaf=2, max_features=0.7,
                  random_state=RANDOM_STATE, n_jobs=1)
    return RandomForestRegressor(**common) if kind == "random_forest" else ExtraTreesRegressor(**common)
 
 
class _TreeModel:
    """Random Forest, Extra Trees or the average of both."""
 
    def __init__(self, kind: str):
        self.kinds = ["random_forest", "extra_trees"] if kind == "rf_et_blend" else [kind]
        self.models = []
 
    def fit(self, X, y, w):
        self.models = [_new_forest(k).fit(X, y, sample_weight=w) for k in self.kinds]
        return self
 
    def predict_one(self, row) -> float:
        return float(np.mean([m.predict([row])[0] for m in self.models]))
 
 
def _recursive_forecast(model: _TreeModel, x: np.ndarray, months: np.ndarray, months_ahead: list[int], seasonal: bool) -> np.ndarray:
    lo, hi = x.min() - RANGE_MARGIN, x.max() + RANGE_MARGIN
    history, hist_months = list(x), list(months)
    for month in months_ahead:
        change = model.predict_one(_features(np.array(history), np.array(hist_months), month, seasonal))
        change = float(np.clip(change, -MAX_MONTHLY_MOVE, MAX_MONTHLY_MOVE))
        history.append(float(np.clip(history[-1] + change, lo, hi)))
        hist_months.append(month)
    return np.array(history[len(x):])
 
 
def _seasonal_naive(values: np.ndarray, periods: int) -> np.ndarray:
    """Same month last year, shifted to today's price level (half of the recent year-on-year change)."""
    x = np.log(values)
    shift = 0.5 * (x[-3:].mean() - x[-15:-12].mean())
    extended = list(x)
    for _ in range(periods):
        extended.append(extended[-12] + shift)
    return np.exp(np.array(extended[len(x):]))
 
 
def _holt_run(values: np.ndarray, alpha: float, beta: float, phi: float):
    """One pass of damped Holt smoothing. Returns (final level, final trend, one-step squared error)."""
    level, trend = float(values[0]), float(values[1] - values[0])
    sse = 0.0
    for y in values[1:]:
        sse += (float(y) - (level + phi * trend)) ** 2
        previous = level
        level = alpha * float(y) + (1 - alpha) * (level + phi * trend)
        trend = beta * (level - previous) + (1 - beta) * phi * trend
    return level, trend, sse
 
 
def _damped_trend(values: np.ndarray, periods: int, phi: float = 0.8) -> np.ndarray:
    """Damped Holt smoothing: follows the RECENT level and trend (old months fade out), and the
    trend dies out over time so the forecast cannot run away. The smoothing speed (alpha, beta)
    is chosen from the series itself: whichever predicted its own next month best."""
    if len(values) < 3:
        return np.repeat(values[-1], periods)
    best = None
    for alpha in (0.3, 0.5, 0.7, 0.9):
        for beta in (0.1, 0.3):
            level, trend, sse = _holt_run(values, alpha, beta, phi)
            if best is None or sse < best[2]:
                best = (level, trend, sse)
    level, trend, _ = best
    limit = abs(level) * 0.05                                   # at most 5 % per month
    trend = float(np.clip(trend, -limit, limit))
    return np.array([max(0.0, level + trend * sum(phi ** k for k in range(1, h + 1)))
                     for h in range(1, periods + 1)])
 
 
# ============================================================
# Backtest + selection
# ============================================================
 
def _month_numbers(index: pd.DatetimeIndex) -> np.ndarray:
    return index.month.to_numpy()
 
 
def _seasonal_holt(series: pd.Series, periods: int) -> np.ndarray:
    """Remove the yearly pattern (log-space, centred 12-month average), forecast the
    de-seasonalised level with damped Holt, then put the seasonal pattern back."""
    x = np.log(series.to_numpy())
    months = _month_numbers(series.index)
    ma = pd.Series(x).rolling(12, center=True, min_periods=12).mean()
    ma = (ma + ma.shift(-1)) / 2                       # 2x12 centred moving average
    dev = pd.Series(x - ma.to_numpy())
    idx = dev.groupby(months).mean().reindex(range(1, 13)).fillna(0.0)
    idx = idx - idx.mean()
    seasonal = idx.reindex(months).to_numpy()
    level_fc = _damped_trend(np.exp(x - seasonal), periods)
    future = pd.date_range(series.index[-1] + pd.offsets.MonthBegin(1), periods=periods, freq="MS")
    return level_fc * np.exp(idx.reindex(future.month).to_numpy())
 
 
def _forecast_with(name: str, series: pd.Series, periods: int, seasonal: bool) -> np.ndarray:
    """Forecast `periods` months after the end of `series` (prices, not logs)."""
    values = series.to_numpy()
    if name == "naive":
        return np.repeat(values[-1], periods)
    if name == "damped_trend":
        return _damped_trend(values, periods)
    if name == "seasonal_naive":
        return _seasonal_naive(values, periods)
    if name == "seasonal_holt":
        return _seasonal_holt(series, periods)
 
    x = _clip_outliers(np.log(values))
    months = _month_numbers(series.index)
    X, y, w = _build_training_set(x, months, seasonal)
    model = _TreeModel(name).fit(X, y, w)
    future = pd.date_range(series.index[-1] + pd.offsets.MonthBegin(1), periods=periods, freq="MS")
    log_pred = _recursive_forecast(model, x, months, list(future.month), seasonal)
    return np.exp(log_pred)
 
 
def _backtest(series: pd.Series, candidates: list[str], seasonal: bool) -> dict[str, float]:
    """Mean absolute % error of each candidate on the most recent held-out months."""
    start_rows = 12 if seasonal else 6
    first_origin = start_rows + MIN_TRAIN_ROWS
    last_origin = len(series) - 1
    origins = list(range(max(first_origin, last_origin - BACKTEST_ORIGINS + 1), last_origin + 1))
    errors = {name: [] for name in candidates}
 
    for origin in origins:
        train = series.iloc[:origin]
        actual = series.iloc[origin:origin + BACKTEST_HORIZON].to_numpy()
        steps = len(actual)
        for name in candidates:
            try:
                pred = _forecast_with(name, train, steps, seasonal)
                errors[name].append(float(np.mean(np.abs(pred - actual) / actual)) * 100)
            except Exception:  # one failed fit must not break the forecast
                continue
 
    return {name: float(np.mean(vals)) for name, vals in errors.items() if vals}
 
 
# ============================================================
# Public API
# ============================================================
 
def forecast_prices(monthly_history: pd.DataFrame, periods: int = 12) -> pd.DataFrame:
    """Forecast monthly modal prices. Always returns columns: date, modal_price."""
    global LAST_RUN_INFO
 
    if monthly_history is None or monthly_history.empty or periods <= 0:
        return pd.DataFrame(columns=COLUMNS)
 
    series = _prepare_series(monthly_history)
    if series.empty:
        return pd.DataFrame(columns=COLUMNS)
 
    n = len(series)
    future_dates = pd.date_range(series.index[-1] + pd.offsets.MonthBegin(1), periods=periods, freq="MS")
    info = {"months_used": n, "model": None, "backtest_mape": {}}
 
    if n < 3:
        predictions = np.repeat(series.iloc[-1], periods)
        info["model"] = "last_value"
 
    elif n < MIN_ML_MONTHS or not SKLEARN_AVAILABLE:
        predictions = _damped_trend(series.to_numpy(), periods)
        info["model"] = "damped_trend" if SKLEARN_AVAILABLE else "damped_trend (scikit-learn missing)"
 
    else:
        seasonal = n >= SEASONAL_MIN_MONTHS
        candidates = ["damped_trend", "random_forest", "extra_trees", "rf_et_blend"]
        if seasonal:
            candidates += ["seasonal_naive", "seasonal_holt"]
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            scores = _backtest(series, candidates + ["naive"], seasonal)
            selectable = {k: v for k, v in scores.items() if k != "naive"}
            ranked = sorted(selectable, key=selectable.get)
            best = ranked[0] if ranked else "rf_et_blend"
            predictions = _forecast_with(best, series, periods, seasonal)
            # Averaging the two best models is usually steadier than trusting one.
            if len(ranked) >= 2 and selectable[ranked[1]] <= selectable[ranked[0]] * 1.15:
                second = _forecast_with(ranked[1], series, periods, seasonal)
                predictions = (np.asarray(predictions) + np.asarray(second)) / 2
                best = f"{ranked[0]}+{ranked[1]}"
        info.update(model=best, seasonal=seasonal, backtest_mape=scores)
 
    predictions = np.maximum(np.asarray(predictions, dtype=float), 0.0)
    LAST_RUN_INFO = info
    print(f"Forecast: model={info['model']} months_used={n} backtest_MAPE%={ {k: round(v, 1) for k, v in info['backtest_mape'].items()} }")
 
    return pd.DataFrame({"date": future_dates, "modal_price": np.round(predictions, 2)})
 