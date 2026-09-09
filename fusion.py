"""
Fusion layer: turns raw quality flags + detector flags into a single
judge-readable anomaly record: type, severity, confidence, and a plain-English
reason. This is the "explainability" piece called out in the PS evaluation
weights (Explainability 10%) -- an alert is only useful if a human can see
*why* the system raised it.
"""

import numpy as np
import pandas as pd

SENSOR_COLS = ["temperature_c", "pressure_hpa", "humidity_pct"]


def classify_row(row) -> dict:
    """Decide anomaly type/severity/confidence/reason for a single row based on
    which underlying signals fired. Priority order matters: structural quality
    issues (missing/frozen) are unambiguous and get classified first; then
    statistical/temporal/multivariate signals, which can overlap and need
    a confidence blend."""

    # --- structural (data quality) anomalies: high confidence, deterministic ---
    if row["q_missing"]:
        return _record("dropout", "high", 0.95, "Sensor reading missing (no data received).")
    if row["q_frozen"]:
        return _record(
            "freeze", "high", 0.9, "Sensor value has not changed across a long run of readings — likely a stuck/frozen sensor."
        )
    if row["q_out_of_range"]:
        return _record(
            "out_of_range", "high", 0.95, "Reading falls outside physically plausible bounds for this station."
        )

    # --- behavioral anomalies from the hybrid detector ensemble ---
    fired = []
    if row.get("flag_statistical"):
        fired.append("statistical")
    if row.get("flag_temporal"):
        fired.append("temporal")
    if row.get("flag_multivariate"):
        fired.append("multivariate")

    if not fired:
        return _record("normal", "none", 0.0, "No anomaly detected.")

    # more detectors agreeing = higher confidence
    confidence = min(0.5 + 0.2 * len(fired), 0.95)

    if "multivariate" in fired and "statistical" not in fired and "temporal" not in fired:
        atype = "cross_sensor_inconsistency"
        reason = "Humidity and temperature readings are inconsistent with the expected physical relationship between them."
        severity = "medium"
    elif "temporal" in fired and "statistical" not in fired:
        atype = "drift"
        reason = "Short-term average has diverged gradually from the long-term baseline — consistent with sensor drift/miscalibration."
        severity = "medium"
    elif "statistical" in fired:
        atype = "spike"
        reason = _spike_reason(row)
        severity = "high" if len(fired) >= 2 else "medium"
    else:
        atype = "unclassified"
        reason = "Multiple weak signals fired without a clear dominant pattern."
        severity = "low"

    return _record(atype, severity, confidence, reason)


def _spike_reason(row) -> str:
    culprits = [c for c in SENSOR_COLS if row.get(f"flag_stat_{c}")]
    if not culprits:
        return "Statistical deviation detected."
    zvals = {c: row.get(f"z_{c}", 0.0) for c in culprits}
    worst = max(zvals, key=lambda c: abs(zvals[c]))
    return f"{worst.replace('_', ' ')} deviates {abs(zvals[worst]):.1f} standard deviations from its recent rolling baseline."


def _record(atype, severity, confidence, reason):
    return {"pred_anomaly_type": atype, "pred_severity": severity, "pred_confidence": confidence, "pred_reason": reason}


def fuse(df: pd.DataFrame) -> pd.DataFrame:
    records = df.apply(classify_row, axis=1, result_type="expand")
    out = pd.concat([df, records], axis=1)
    out["pred_is_anomaly"] = out["pred_anomaly_type"] != "normal"
    return out
