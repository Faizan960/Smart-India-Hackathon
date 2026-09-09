"""
Synthetic Automatic Weather Station (AWS) data generator.

Simulates realistic temperature (C), pressure (hPa), and relative humidity (%)
streams for one or more stations, with a diurnal (day/night) cycle plus noise,
and injects labeled anomalies so we can measure detector precision/recall
against ground truth (SIH26073 MVP requirement: "Replay a realistic AWS
stream... inject spikes, freezes, drift, dropouts and cross-sensor
inconsistencies").
"""

import numpy as np
import pandas as pd

RNG = np.random.default_rng(42)

# Physically plausible bounds for a mid-latitude Indian AWS station
BOUNDS = {
    "temperature_c": (-10.0, 55.0),
    "pressure_hpa": (870.0, 1085.0),
    "humidity_pct": (0.0, 100.0),
}


def _diurnal_temperature(hours: np.ndarray, base: float = 27.0, amplitude: float = 6.0) -> np.ndarray:
    """Simple sinusoidal day/night temperature cycle, peak ~3pm."""
    phase = (hours - 15.0) / 24.0 * 2 * np.pi
    return base + amplitude * np.cos(phase)


def generate_station_stream(
    station_id: str,
    n_points: int = 2000,
    freq_minutes: int = 5,
    start: str = "2026-01-01",
) -> pd.DataFrame:
    """Generate a clean baseline stream for one station, then inject anomalies."""
    timestamps = pd.date_range(start=start, periods=n_points, freq=f"{freq_minutes}min")
    hours = timestamps.hour + timestamps.minute / 60.0

    temperature = _diurnal_temperature(hours) + RNG.normal(0, 0.4, n_points)
    # pressure drifts slowly (synoptic-scale) + small noise
    pressure = 1013.0 + np.cumsum(RNG.normal(0, 0.02, n_points)) + RNG.normal(0, 0.15, n_points)
    # humidity anti-correlated with temperature (roughly), clipped to [10,95]
    humidity = np.clip(75 - 1.4 * (temperature - 27) + RNG.normal(0, 2.5, n_points), 10, 95)

    df = pd.DataFrame(
        {
            "timestamp": timestamps,
            "station_id": station_id,
            "temperature_c": temperature,
            "pressure_hpa": pressure,
            "humidity_pct": humidity,
        }
    )

    # ground-truth anomaly labels, default "normal"
    df["gt_anomaly_type"] = "normal"
    df["gt_is_anomaly"] = False

    df = _inject_spike(df)
    df = _inject_freeze(df)
    df = _inject_drift(df)
    df = _inject_dropout(df)
    df = _inject_cross_sensor_inconsistency(df)

    return df


def _mark(df, idx, label):
    df.loc[idx, "gt_anomaly_type"] = label
    df.loc[idx, "gt_is_anomaly"] = True
    return df


def _inject_spike(df, n_events=3, width=1):
    """Sudden single-point sensor spike (e.g. transient electrical fault)."""
    n = len(df)
    for _ in range(n_events):
        start = RNG.integers(200, n - 50)
        idx = range(start, start + width)
        col = RNG.choice(["temperature_c", "pressure_hpa"])
        magnitude = RNG.choice([1, -1]) * RNG.uniform(15, 25)
        df.loc[idx, col] = df.loc[idx, col] + magnitude
        df = _mark(df, idx, "spike")
    return df


def _inject_freeze(df, n_events=2, min_len=25, max_len=60):
    """Sensor 'stuck-at' a constant value (frozen reading) — common hardware fault."""
    n = len(df)
    for _ in range(n_events):
        start = RNG.integers(200, n - 100)
        length = RNG.integers(min_len, max_len)
        idx = range(start, start + length)
        col = RNG.choice(["humidity_pct", "temperature_c"])
        stuck_value = df.loc[start, col]
        df.loc[idx, col] = stuck_value
        df = _mark(df, idx, "freeze")
    return df


def _inject_drift(df, n_events=2, length=150):
    """Slow linear sensor drift (miscalibration) — hardest to detect, builds gradually."""
    n = len(df)
    for _ in range(n_events):
        start = RNG.integers(200, n - length - 10)
        idx = range(start, start + length)
        col = RNG.choice(["pressure_hpa", "temperature_c"])
        ramp = np.linspace(0, RNG.choice([1, -1]) * RNG.uniform(6, 12), length)
        df.loc[idx, col] = df.loc[idx, col].values + ramp
        df = _mark(df, idx, "drift")
    return df


def _inject_dropout(df, n_events=3, min_len=5, max_len=20):
    """Missing readings (communication/power dropout)."""
    n = len(df)
    for _ in range(n_events):
        start = RNG.integers(200, n - 50)
        length = RNG.integers(min_len, max_len)
        idx = range(start, start + length)
        col = RNG.choice(["temperature_c", "pressure_hpa", "humidity_pct"])
        df.loc[idx, col] = np.nan
        df = _mark(df, idx, "dropout")
    return df


def _inject_cross_sensor_inconsistency(df, n_events=2, length=20):
    """Physically implausible combination: e.g. high temp + high humidity + falling
    pressure with no correlation — a fault type only visible when comparing sensors,
    not from any single sensor in isolation."""
    n = len(df)
    for _ in range(n_events):
        start = RNG.integers(200, n - length - 10)
        idx = range(start, start + length)
        # force humidity to spike opposite to what temperature implies
        df.loc[idx, "humidity_pct"] = np.clip(
            df.loc[idx, "humidity_pct"].values + RNG.uniform(35, 45), 0, 100
        )
        df = _mark(df, idx, "cross_sensor_inconsistency")
    return df


def generate_multi_station(station_ids, **kwargs) -> pd.DataFrame:
    frames = [generate_station_stream(sid, **kwargs) for sid in station_ids]
    return pd.concat(frames, ignore_index=True)


if __name__ == "__main__":
    df = generate_multi_station(["AWS_DELHI_01", "AWS_PUNE_02"], n_points=1500)
    df.to_csv("data/synthetic_aws_stream.csv", index=False)
    print(df["gt_anomaly_type"].value_counts())
    print(f"Total rows: {len(df)}")
