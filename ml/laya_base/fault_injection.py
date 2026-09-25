"""Controlled fault injection for Laya training data."""
from __future__ import annotations
import numpy as np
import pandas as pd
from .config import FAULT_LABELS

def inject_fault(df: pd.DataFrame, fault_type: str, seed: int = 42) -> pd.DataFrame:
    if fault_type not in FAULT_LABELS:
        raise ValueError(f"Unsupported fault type: {fault_type}")
    if len(df) < 6:
        raise ValueError("At least 6 observations are required.")
    out = df.copy()
    out["timestamp"] = pd.to_datetime(out["timestamp"], errors="coerce")
    rng = np.random.default_rng(seed)
    idx = out.index[-1]
    if fault_type == "NORMAL":
        return out
    if fault_type == "SENSOR_DROPOUT":
        out.loc[idx, ["temperature", "humidity"]] = np.nan
    elif fault_type in ("TEMPERATURE_SPIKE", "TEMPERATURE_DROP"):
        base = out["temperature"].iloc[:-1].dropna()
        sigma = float(base.std()) if len(base) > 2 else 1.0
        delta = max(8.0, 5.0 * sigma)
        out.loc[idx, "temperature"] = float(base.mean() + (delta if fault_type.endswith("SPIKE") else -delta))
    elif fault_type == "SENSOR_FREEZE":
        out.loc[out.index[-5:], "temperature"] = float(out["temperature"].iloc[-2])
    elif fault_type == "SENSOR_DRIFT":
        start = float(out["temperature"].iloc[-6])
        out.loc[out.index[-6:], "temperature"] = np.linspace(start, start + 5.0, 6)
    elif fault_type in ("PRESSURE_SPIKE", "PRESSURE_DROP"):
        base = out["pressure"].iloc[:-1].dropna()
        sigma = float(base.std()) if len(base) > 2 else 1.0
        delta = max(12.0, 5.0 * sigma)
        out.loc[idx, "pressure"] = float(base.mean() + (delta if fault_type.endswith("SPIKE") else -delta))
    elif fault_type in ("HUMIDITY_SPIKE", "HUMIDITY_DROP"):
        base = out["humidity"].iloc[:-1].dropna()
        sigma = float(base.std()) if len(base) > 2 else 1.0
        delta = max(30.0, 5.0 * sigma)
        out.loc[idx, "humidity"] = float(np.clip(base.mean() + (delta if fault_type.endswith("SPIKE") else -delta), 0, 100))
    elif fault_type == "UNKNOWN_ANOMALY":
        out.loc[idx, "temperature"] = float(out["temperature"].iloc[-2] + rng.choice([-10.0, 10.0]))
        out.loc[idx, "pressure"] = float(out["pressure"].iloc[-2] + rng.choice([-20.0, 20.0]))
    return out
