"""
Sensor-health scoring: a rolling "how much do we trust this station right now"
score, plus a simple degradation trend (is it getting worse over time). This is
distinct from any single anomaly alert — a station could have zero anomalies
right now but a rising rate of flags over the last few hours, which is exactly
the kind of early-warning signal the PS calls for.
"""

import numpy as np
import pandas as pd


def compute_health(df: pd.DataFrame, window: int = 48) -> pd.DataFrame:
    """health_score in [0,1]: 1 = perfectly healthy, 0 = fully anomalous over window.
    window=48 points * 5min = 4 hours."""
    out = df.copy()
    out["health_score"] = 1.0
    out["health_trend"] = 0.0

    for station, g in out.groupby("station_id"):
        anomaly_rate = g["pred_is_anomaly"].astype(float).rolling(window, min_periods=window // 4).mean()
        score = (1 - anomaly_rate).fillna(1.0)
        out.loc[g.index, "health_score"] = score.values

        # trend = slope of health score over the last `window` points (simple linear fit)
        trend = score.rolling(window, min_periods=window // 2).apply(_slope, raw=True)
        out.loc[g.index, "health_trend"] = trend.fillna(0).values

    return out


def _slope(y: np.ndarray) -> float:
    x = np.arange(len(y))
    if len(y) < 2 or np.all(y == y[0]):
        return 0.0
    return np.polyfit(x, y, 1)[0]
