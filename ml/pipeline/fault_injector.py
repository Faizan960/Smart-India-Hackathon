"""Synthetic fault injection for honest evaluation (spec sections 13 & 26).

Injects KNOWN faults into clean holdout data so detection can be measured against
ground truth. This is the only place synthetic corruption is allowed, and it is
used purely to score the detector/classifier — never to fabricate a result. Every
injected event is recorded (type, sensor, window, magnitude) so the evaluator can
compute real precision / recall / latency.

Injections are seeded and reproducible.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from .config import CORE_SENSORS, DEFAULT_CONFIG, SENSOR_BOUNDS

# default number of events per fault type and their window sizes
DEFAULT_PLAN: Dict[str, Dict] = {
    "SENSOR_DROPOUT": {"n": 30, "window_hours": (6, 24)},
    "SENSOR_FREEZE": {"n": 30, "window_hours": (8, 24)},
    "TRANSIENT_SPIKE": {"n": 40, "window_hours": (0, 0)},  # single reading
    "CALIBRATION_DRIFT": {"n": 30, "window_hours": (72, 168), "sigma": (5.0, 9.0)},
    "PHYSICAL_INCONSISTENCY": {"n": 30, "window_hours": (1, 6)},
    "MULTIVARIATE_ANOMALY": {"n": 30, "window_hours": (3, 9), "sigma": (4.0, 6.0)},
}
_INJECTABLE_SENSORS = ("temperature", "pressure")  # freeze/spike/drift target these


@dataclass
class _Event:
    event_id: int
    station_id: str
    fault_type: str
    sensor: str
    start_ts: pd.Timestamp
    end_ts: pd.Timestamp
    n_rows: int
    magnitude: float


def _robust_sigma(x: np.ndarray) -> float:
    x = x[np.isfinite(x)]
    if x.size < 5:
        return 1.0
    med = np.median(x)
    mad = np.median(np.abs(x - med))
    return float(max(1.4826 * mad, 1e-6))


def _clip(sensor: str, arr: np.ndarray) -> np.ndarray:
    lo, hi = SENSOR_BOUNDS[sensor]
    return np.clip(arr, lo, hi)


def _pick_window(rng, idx: np.ndarray, n_rows: int) -> np.ndarray:
    """Choose a contiguous block of ``n_rows`` positions from a station's index."""
    if len(idx) <= n_rows:
        return idx
    start = int(rng.integers(0, len(idx) - n_rows))
    return idx[start:start + n_rows]


def inject_faults(clean_df: pd.DataFrame, config=None, seed: int = 42,
                  plan: Optional[Dict] = None):
    """Inject reproducible, labelled faults into clean data.

    Returns ``(corrupted_df, events_df)``. ``corrupted_df`` carries ground-truth
    columns ``injected_fault`` (type or 'NORMAL'), ``injected_sensor`` and
    ``event_id``. Values are kept within physical bounds (except the deliberate
    supersaturation of PHYSICAL_INCONSISTENCY) so detection must rely on context,
    not a trivial range check.
    """
    config = config or DEFAULT_CONFIG
    plan = plan or DEFAULT_PLAN
    rng = np.random.default_rng(seed)

    df = clean_df.sort_values(["station_id", "timestamp"]).reset_index(drop=True).copy()
    df["injected_fault"] = "NORMAL"
    df["injected_sensor"] = None
    df["event_id"] = -1

    station_pos: Dict[str, np.ndarray] = {}
    station_int: Dict[str, float] = {}
    station_sigma: Dict[str, Dict[str, float]] = {}
    for sid, g in df.groupby("station_id"):
        station_pos[sid] = g.index.to_numpy()
        dt = g["timestamp"].diff().dt.total_seconds().to_numpy() / 3600.0
        dt = dt[np.isfinite(dt) & (dt > 0)]
        station_int[sid] = float(np.median(dt)) if dt.size else 1.0
        station_sigma[sid] = {s: _robust_sigma(g[s].to_numpy(dtype=float)) for s in CORE_SENSORS}

    stations = list(station_pos.keys())
    events: List[_Event] = []
    eid = 0

    def _rows_for_hours(sid, hours):
        return max(1, int(round(hours / max(station_int[sid], 1e-6))))

    for ftype, spec in plan.items():
        for _ in range(int(spec.get("n", 0))):
            sid = stations[int(rng.integers(0, len(stations)))]
            wlo, whi = spec.get("window_hours", (1, 6))
            n_rows = 1 if whi == 0 else _rows_for_hours(sid, float(rng.uniform(wlo, whi)))
            win = _pick_window(rng, station_pos[sid], n_rows)
            if len(win) == 0:
                continue
            eid += 1
            mag = _apply_event(df, rng, ftype, win, spec, station_sigma[sid])
            events.append(_Event(eid, str(sid), ftype, str(df.loc[win[0], "injected_sensor"]),
                                 df.loc[win[0], "timestamp"], df.loc[win[-1], "timestamp"],
                                 len(win), float(mag)))
            df.loc[win, "event_id"] = eid

    return df, pd.DataFrame([e.__dict__ for e in events])


def _apply_event(df, rng, ftype, win, spec, sigma) -> float:
    """Corrupt ``df`` in place over positions ``win``; tag ground truth; return
    the injected magnitude (natural units)."""
    df.loc[win, "injected_fault"] = ftype

    if ftype == "SENSOR_DROPOUT":
        df.loc[win, list(CORE_SENSORS)] = np.nan
        df.loc[win, "injected_sensor"] = "all"
        return float(len(win))

    if ftype == "PHYSICAL_INCONSISTENCY":
        # RH sensor over-reading past saturation — a real fault mode, left
        # un-clipped so the thermodynamic consistency check can see it.
        df.loc[win, "humidity"] = float(rng.uniform(108.0, 125.0))
        df.loc[win, "injected_sensor"] = "humidity"
        return 115.0

    if ftype == "MULTIVARIATE_ANOMALY":
        k = float(rng.uniform(*spec.get("sigma", (4.0, 6.0))))
        for s in CORE_SENSORS:
            base = df.loc[win, s].to_numpy(dtype=float)
            sign = 1.0 if rng.random() < 0.5 else -1.0
            df.loc[win, s] = _clip(s, base + sign * k * sigma[s])
        df.loc[win, "injected_sensor"] = "multi"
        return k

    sensor = _INJECTABLE_SENSORS[int(rng.integers(0, len(_INJECTABLE_SENSORS)))]
    if df.loc[win, sensor].notna().mean() < 0.5:
        sensor = "temperature"
    df.loc[win, "injected_sensor"] = sensor
    base = df.loc[win, sensor].to_numpy(dtype=float)
    sig = sigma[sensor]

    if ftype == "SENSOR_FREEZE":
        held = base[0] if np.isfinite(base[0]) else float(np.nanmedian(base))
        df.loc[win, sensor] = held
        return 0.0

    if ftype == "TRANSIENT_SPIKE":
        sign = 1.0 if rng.random() < 0.5 else -1.0
        offset = sign * max(8.0 * sig, 6.0 if sensor == "temperature" else 12.0)
        df.loc[win, sensor] = _clip(sensor, base + offset)
        return float(offset)

    if ftype == "CALIBRATION_DRIFT":
        k = float(rng.uniform(*spec.get("sigma", (5.0, 9.0))))
        ramp = np.linspace(0.0, k * sig, len(win))
        sign = 1.0 if rng.random() < 0.5 else -1.0
        df.loc[win, sensor] = _clip(sensor, base + sign * ramp)
        return float(sign * k * sig)

    return 0.0
