"""Signature-based fault typing (spec sections 12-14).

Consumes the evidence-feature frame plus the anomaly score and assigns a
*principled* fault type from the general taxonomy (config.FAULT_TYPES) using
transparent, inspectable signatures — never an opaque label. Each decision is
backed by a concrete piece of evidence (a data gap, a stuck run, a physics
violation, a CUSUM excursion, ...), and confidences are monotonic functions of
that evidence, so nothing is fabricated.

It also emits a ``legacy_label`` from the existing project vocabulary (the same
set used by ml/classifier.py and ml/laya_base) so downstream API/UI contracts
keep working unchanged.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict

import numpy as np
import pandas as pd

from .baseline import DEV_COLS
from .config import CORE_SENSORS, DEFAULT_CONFIG, SENSOR_RESOLUTION
from .preprocessing import infer_sampling_seconds

# legacy vocabulary (matches ml/laya_base/config.py FAULT_LABELS) --------------
LEGACY_LABELS = (
    "NORMAL", "SENSOR_DROPOUT", "TEMPERATURE_SPIKE", "TEMPERATURE_DROP",
    "SENSOR_FREEZE", "SENSOR_DRIFT", "PRESSURE_SPIKE", "PRESSURE_DROP",
    "HUMIDITY_SPIKE", "HUMIDITY_DROP", "UNKNOWN_ANOMALY",
)
_SENSOR_LEGACY = {"temperature": ("TEMPERATURE_SPIKE", "TEMPERATURE_DROP"),
                  "pressure": ("PRESSURE_SPIKE", "PRESSURE_DROP"),
                  "humidity": ("HUMIDITY_SPIKE", "HUMIDITY_DROP")}
_THRESH_FILE = "classifier_config.json"


def fit_thresholds(feat_train: pd.DataFrame, config=None) -> Dict:
    """Learn per-sensor rate-of-change thresholds from TRAINING data (percentiles
    of |rate|). Persisted so inference uses the exact same thresholds."""
    config = config or DEFAULT_CONFIG
    hi = max(config.rate_percentiles)
    thr = {}
    for sensor in CORE_SENSORS:
        r = feat_train[f"{_pfx(sensor)}_rate"].abs().replace([np.inf, -np.inf], np.nan).dropna()
        thr[sensor] = float(np.percentile(r, hi)) if len(r) else np.nan
    return {"rate_abs_threshold": thr, "rate_percentile": hi}


def save_thresholds(thresholds: Dict, models_dir=None, config=None) -> Path:
    cfg = config or DEFAULT_CONFIG
    d = Path(models_dir or cfg.models_dir)
    d.mkdir(parents=True, exist_ok=True)
    p = d / _THRESH_FILE
    with open(p, "w", encoding="utf-8") as f:
        json.dump(thresholds, f, indent=2)
    return p


def load_thresholds(models_dir=None, config=None) -> Dict:
    cfg = config or DEFAULT_CONFIG
    p = Path(models_dir or cfg.models_dir) / _THRESH_FILE
    if not p.exists():
        return {"rate_abs_threshold": {s: np.inf for s in CORE_SENSORS}, "rate_percentile": None}
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def _pfx(sensor: str) -> str:
    return {"temperature": "temp", "humidity": "humidity", "pressure": "pressure"}[sensor]


def _consecutive_true(mask: np.ndarray) -> np.ndarray:
    """Length of the current run of True values ending at each position."""
    out = np.zeros(len(mask), dtype=int)
    run = 0
    for i, v in enumerate(mask):
        run = run + 1 if v else 0
        out[i] = run
    return out


def _flat_span_hours(frozen: np.ndarray, dt_hours: np.ndarray) -> np.ndarray:
    """Wall-clock duration of the current flat run ending at each row.

    Freeze is judged by DURATION, not sample count, so a high-cadence station
    (many identical half-hourly samples during a calm night) is not mistaken for a
    stuck sensor the way a fixed-count rule would.
    """
    out = np.zeros(len(frozen))
    cur = 0.0
    for i in range(len(frozen)):
        if frozen[i] and np.isfinite(dt_hours[i]):
            cur += dt_hours[i]
        else:
            cur = 0.0
        out[i] = cur
    return out


def _station_signatures(g: pd.DataFrame, thresholds: Dict, config) -> pd.DataFrame:
    """Compute inspectable fault signatures for one station (sorted by time)."""
    g = g.reset_index(drop=True)
    n = len(g)
    rate_thr = thresholds.get("rate_abs_threshold", {})

    # --- dropout: an over-long gap in EXPECTED cadence, or an expected sensor
    # going missing. A station that structurally never reports a variable (e.g.
    # METAR stations without sea-level pressure) is NOT a dropout — we gate on the
    # 75th-percentile cadence so a mixed 0.5h/3h station is not flagged wholesale.
    dt = g["dt_hours"].to_numpy(dtype=float)
    pos = dt[np.isfinite(dt) & (dt > 0)]
    typical = float(np.percentile(pos, 75)) if pos.size else np.nan
    gap = (np.nan_to_num(dt, nan=0.0) > config.dropout_gap_factor * typical) if np.isfinite(typical) else np.zeros(n, bool)
    expected = [s for s in CORE_SENSORS if g[s].notna().mean() >= 0.5]
    missing_expected = g[expected].isna().any(axis=1).to_numpy() if expected else np.zeros(n, bool)
    g["sig_gap"] = gap
    g["sig_missing_expected"] = missing_expected
    g["sig_dropout"] = gap | missing_expected

    freeze_span = np.zeros((n, len(CORE_SENSORS)))
    spike = np.zeros((n, len(CORE_SENSORS)), bool)
    spike_rate = np.zeros((n, len(CORE_SENSORS)))
    drift = np.zeros((n, len(CORE_SENSORS)), bool)
    drift_mag = np.zeros((n, len(CORE_SENSORS)))
    devs = np.zeros((n, len(CORE_SENSORS)))
    dt_h = g["dt_hours"].to_numpy(dtype=float)

    for j, sensor in enumerate(CORE_SENSORS):
        vals = g[sensor].to_numpy(dtype=float)
        d = np.abs(np.diff(vals, prepend=np.nan))
        frozen = np.isfinite(d) & (d <= SENSOR_RESOLUTION[sensor])
        if sensor == "humidity":
            # RH pinned at 100% (fog / monsoon saturation) or 0% is REAL weather,
            # not a stuck sensor — never let a saturation plateau look like a freeze.
            at_bound = np.isfinite(vals) & ((vals >= 99.5) | (vals <= 0.5))
            frozen = frozen & ~at_bound
        span = _flat_span_hours(frozen, dt_h)
        freeze_span[:, j] = span if sensor in expected else 0.0  # ignore unreported sensors

        z = np.nan_to_num(g[DEV_COLS[sensor]].to_numpy(dtype=float), nan=0.0)
        devs[:, j] = z
        sp = np.zeros(n); sn = np.zeros(n); k = config.drift_cusum_k
        for i in range(1, n):
            sp[i] = max(0.0, sp[i - 1] + z[i] - k)
            sn[i] = min(0.0, sn[i - 1] + z[i] + k)
        mag = np.maximum(sp, -sn)
        drift_mag[:, j] = mag
        drift[:, j] = mag > config.drift_cusum_h

        r = g[f"{_pfx(sensor)}_rate"].to_numpy(dtype=float)
        thr = rate_thr.get(sensor)
        thr = np.inf if thr is None or not np.isfinite(thr) else float(thr)
        big = np.isfinite(r) & (np.abs(r) > thr)
        r_next = np.append(r[1:], np.nan)
        reversal = big & np.isfinite(r_next) & (np.abs(r_next) > thr) & (np.sign(r) != np.sign(r_next))
        prov = np.zeros(n, bool)
        prov[-1] = big[-1]  # latest point: provisional (no future sample to confirm recovery)
        spike[:, j] = reversal | prov
        spike_rate[:, j] = np.where(np.isfinite(r), r, 0.0)

    sensors = np.array(CORE_SENSORS)
    fj = np.argmax(freeze_span, axis=1)
    g["sig_freeze_span"] = freeze_span[np.arange(n), fj]
    g["sig_freeze"] = g["sig_freeze_span"].to_numpy() >= config.freeze_min_hours
    g["sig_freeze_sensor"] = np.where(g["sig_freeze"], sensors[fj], None)

    sj = np.argmax(np.where(spike, np.abs(spike_rate), -1.0), axis=1)
    g["sig_spike"] = spike.any(axis=1)
    g["sig_spike_sensor"] = np.where(g["sig_spike"], sensors[sj], None)
    g["sig_spike_dir"] = np.where(g["sig_spike"], np.sign(spike_rate[np.arange(n), sj]), 0.0)

    dj = np.argmax(drift_mag, axis=1)
    g["sig_drift"] = drift.any(axis=1)
    g["sig_drift_mag"] = drift_mag[np.arange(n), dj]
    g["sig_drift_sensor"] = np.where(g["sig_drift"], sensors[dj], None)

    g["sig_physical"] = g["thermo_inconsistency"].fillna(False).to_numpy() if "thermo_inconsistency" in g else False

    aj = np.argmax(np.abs(devs), axis=1)
    g["dominant_sensor"] = sensors[aj]
    g["dominant_dev"] = devs[np.arange(n), aj]
    g["max_abs_dev"] = np.abs(devs).max(axis=1)
    g["n_sensors_off"] = (np.abs(devs) > 3.0).sum(axis=1)
    return g


def _legacy_label(ftype: str, sensor, direction: float) -> str:
    if ftype == "NORMAL":
        return "NORMAL"
    if ftype == "SENSOR_DROPOUT":
        return "SENSOR_DROPOUT"
    if ftype == "SENSOR_FREEZE":
        return "SENSOR_FREEZE"
    if ftype == "CALIBRATION_DRIFT":
        return "SENSOR_DRIFT"
    if ftype == "TRANSIENT_SPIKE" and sensor in _SENSOR_LEGACY:
        up, down = _SENSOR_LEGACY[sensor]
        return up if direction >= 0 else down
    return "UNKNOWN_ANOMALY"  # PHYSICAL_INCONSISTENCY, MULTIVARIATE_ANOMALY, UNKNOWN, unmapped spike


def classify_faults(feat_df: pd.DataFrame, anomaly_df: pd.DataFrame, thresholds=None,
                    config=None) -> pd.DataFrame:
    """Assign a fault type + confidence + legacy label to every row.

    Structural signatures (dropout, freeze, physical inconsistency) are reported
    on their own evidence; spike/drift/multivariate are reported when the
    signature fires. Confidence is a transparent function of the triggering
    evidence — deliberately hedged, never a fabricated certainty.
    """
    config = config or DEFAULT_CONFIG
    thresholds = thresholds or {}
    parts = [_station_signatures(g, thresholds, config)
             for _sid, g in feat_df.groupby("station_id", sort=False)]
    sig = pd.concat(parts, ignore_index=True)

    score = anomaly_df["anomaly_score"].reindex(sig.index).to_numpy(dtype=float)
    score = np.nan_to_num(score, nan=0.0)
    is_anom = score >= config.severity_warning_score
    n = len(sig)

    ftype = np.full(n, "NORMAL", dtype=object)
    conf = np.clip(1.0 - score, 0.0, 1.0)  # default: confidence that it is NORMAL
    assigned = np.zeros(n, dtype=bool)

    def _assign(mask, label, values):
        m = mask.to_numpy() if isinstance(mask, pd.Series) else np.asarray(mask)
        m = m & ~assigned
        ftype[m] = label
        conf[m] = np.clip(values, 0.0, 0.97)[m] if isinstance(values, np.ndarray) else values
        assigned[m] = True

    gap = sig["sig_gap"].to_numpy()
    miss_exp = sig["sig_missing_expected"].to_numpy()
    drop_conf = np.where(miss_exp, 0.85, 0.70)
    freeze_span = sig["sig_freeze_span"].to_numpy()
    freeze_conf = np.clip(0.5 + 0.03 * (freeze_span - config.freeze_min_hours), 0.5, 0.95)
    thermo = sig.get("thermo_inconsistency_score", pd.Series(np.zeros(n))).fillna(0.0).to_numpy()
    phys_conf = np.clip(0.5 + 0.5 * thermo, 0.5, 0.95)
    spike_conf = np.clip(0.5 + 0.45 * score, 0.5, 0.95)
    drift_conf = np.clip(0.5 + 0.1 * (sig["sig_drift_mag"].to_numpy() / config.drift_cusum_h - 1.0), 0.5, 0.95)

    # Structural / physical evidence is reported on its own (the detector can miss
    # a plausible-looking frozen value or a physics violation). Dynamic anomaly
    # *explanations* (spike / drift / multivariate) are only asserted where the
    # Isolation Forest actually flagged the point — the classifier says WHY an
    # anomaly occurred, it does not invent anomalies the detector never saw.
    # A flat temperature is structurally suspicious (air temp always has a diurnal
    # cycle), so a long flat temperature run is reported on its own. A flat
    # pressure or humidity plateau is common real weather, so those are only called
    # a freeze when the detector also flags the point.
    temp_freeze = (sig["sig_freeze_sensor"].to_numpy() == "temperature") & sig["sig_freeze"].to_numpy()
    freeze_gate = sig["sig_freeze"].to_numpy() & (temp_freeze | is_anom)
    _assign(sig["sig_dropout"], "SENSOR_DROPOUT", drop_conf)
    _assign(sig["sig_physical"].astype(bool), "PHYSICAL_INCONSISTENCY", phys_conf)
    _assign(freeze_gate, "SENSOR_FREEZE", freeze_conf)
    # a genuinely multi-sensor anomaly is more specific than assuming a single
    # sensor spiked or drifted, so it is resolved first among the dynamic types
    _assign(is_anom & (sig["n_sensors_off"].to_numpy() >= 2), "MULTIVARIATE_ANOMALY", np.clip(score, 0.0, 0.97))
    _assign(is_anom & sig["sig_spike"].to_numpy(), "TRANSIENT_SPIKE", spike_conf)
    _assign(is_anom & sig["sig_drift"].to_numpy(), "CALIBRATION_DRIFT", drift_conf)
    _assign(is_anom, "UNKNOWN_ANOMALY", np.clip(score, 0.0, 0.97))

    out = pd.DataFrame(index=feat_df.index)
    out["fault_type"] = ftype
    out["fault_confidence"] = np.round(conf, 4)
    # dominant sensor / direction for legacy mapping
    spike_sensor = sig["sig_spike_sensor"].to_numpy()
    dom_sensor = sig["dominant_sensor"].to_numpy()
    dom_dir = np.sign(sig["dominant_dev"].to_numpy())
    spike_dir = sig["sig_spike_dir"].to_numpy()
    legacy = []
    for i in range(n):
        if ftype[i] == "TRANSIENT_SPIKE":
            legacy.append(_legacy_label(ftype[i], spike_sensor[i], spike_dir[i]))
        else:
            legacy.append(_legacy_label(ftype[i], dom_sensor[i], dom_dir[i]))
    out["legacy_label"] = legacy
    out["dominant_sensor"] = dom_sensor
    for c in ("sig_dropout", "sig_freeze", "sig_spike", "sig_drift", "sig_physical",
              "sig_freeze_span", "sig_drift_mag", "max_abs_dev", "n_sensors_off"):
        out[c] = sig[c].to_numpy()
    return out


