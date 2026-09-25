"""Convert AWS telemetry into a deterministic Laya state representation."""
from __future__ import annotations
import json
from typing import Any
import pandas as pd
from .config import FAULT_LABELS

REQUIRED_COLUMNS = ("timestamp", "temperature", "humidity", "pressure", "wind_speed")

def _clean_value(value: Any) -> Any:
    if pd.isna(value):
        return None
    if hasattr(value, "item"):
        return value.item()
    return value

def telemetry_to_state(df_history: pd.DataFrame, history_rows: int = 12) -> dict:
    missing = [c for c in REQUIRED_COLUMNS if c not in df_history.columns]
    if missing:
        raise ValueError(f"Missing telemetry columns: {missing}")
    if df_history.empty:
        raise ValueError("Telemetry history cannot be empty.")
    df = df_history.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df = df.sort_values("timestamp").tail(history_rows)
    rows = []
    for _, row in df.iterrows():
        ts = None if pd.isna(row["timestamp"]) else row["timestamp"].isoformat()
        rows.append({
            "timestamp": ts,
            "temperature": _clean_value(row["temperature"]),
            "humidity": _clean_value(row["humidity"]),
            "pressure": _clean_value(row["pressure"]),
            "wind_speed": _clean_value(row["wind_speed"]),
        })
    return {
        "task": "automatic_weather_station_sensor_fault_detection",
        "current_observation": rows[-1],
        "recent_observations": rows,
        "expected_fault_labels": list(FAULT_LABELS),
    }

def state_to_text(state: dict) -> str:
    return json.dumps(state, separators=(",", ":"), ensure_ascii=False)
