"""
Orchestrates the full pipeline: generate -> quality gate -> detectors ->
fusion -> health scoring -> evaluation against injected ground truth.
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd

from data_gen import generate_multi_station
from quality import run_quality_gate
from detectors import run_all_detectors
from fusion import fuse
from health import compute_health


def run_pipeline(station_ids, n_points=1500) -> pd.DataFrame:
    df = generate_multi_station(station_ids, n_points=n_points)
    df = run_quality_gate(df)
    df = run_all_detectors(df)
    df = fuse(df)
    df = compute_health(df)
    return df


def evaluate(df: pd.DataFrame) -> dict:
    """Point-level precision/recall/F1 for "is this an anomaly at all", plus a
    per-type breakdown, since the PS explicitly calls for "detection
    precision/recall/F1" and "false-alert rate" as validation metrics."""
    y_true = df["gt_is_anomaly"].astype(bool)
    y_pred = df["pred_is_anomaly"].astype(bool)

    tp = int((y_true & y_pred).sum())
    fp = int((~y_true & y_pred).sum())
    fn = int((y_true & ~y_pred).sum())
    tn = int((~y_true & ~y_pred).sum())

    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    false_alert_rate = fp / (fp + tn) if (fp + tn) else 0.0

    per_type = {}
    for atype in [t for t in df["gt_anomaly_type"].unique() if t != "normal"]:
        mask = df["gt_anomaly_type"] == atype
        detected = df.loc[mask, "pred_is_anomaly"].sum()
        total = mask.sum()
        per_type[atype] = {
            "total_points": int(total),
            "detected_points": int(detected),
            "recall": round(detected / total, 3) if total else 0.0,
        }

    return {
        "overall": {
            "precision": round(precision, 3),
            "recall": round(recall, 3),
            "f1": round(f1, 3),
            "false_alert_rate": round(false_alert_rate, 3),
            "true_positives": tp,
            "false_positives": fp,
            "false_negatives": fn,
            "true_negatives": tn,
        },
        "per_anomaly_type_recall": per_type,
    }


def build_dashboard_payload(df: pd.DataFrame, metrics: dict, station_id: str) -> dict:
    """Slim JSON payload for the dashboard artifact: one station's time series +
    alerts + health trend + incident timeline + eval metrics."""
    g = df[df["station_id"] == station_id].copy()
    g["timestamp"] = g["timestamp"].astype(str)

    series = g[["timestamp", "temperature_c", "pressure_hpa", "humidity_pct", "pred_is_anomaly", "pred_severity"]].to_dict(
        orient="records"
    )

    alerts = g[g["pred_is_anomaly"]][
        ["timestamp", "pred_anomaly_type", "pred_severity", "pred_confidence", "pred_reason"]
    ].to_dict(orient="records")

    health = g[["timestamp", "health_score", "health_trend"]].to_dict(orient="records")

    # collapse consecutive alerts of the same type into incidents
    incidents = []
    cur = None
    for row in g.itertuples():
        if row.pred_is_anomaly:
            if cur and cur["type"] == row.pred_anomaly_type and cur["end_idx"] == row.Index - 1:
                cur["end_idx"] = row.Index
                cur["end_ts"] = str(row.timestamp)
                cur["count"] += 1
            else:
                if cur:
                    incidents.append(cur)
                cur = {
                    "type": row.pred_anomaly_type,
                    "severity": row.pred_severity,
                    "start_ts": str(row.timestamp),
                    "end_ts": str(row.timestamp),
                    "end_idx": row.Index,
                    "count": 1,
                }
        else:
            if cur:
                incidents.append(cur)
                cur = None
    if cur:
        incidents.append(cur)
    for i in incidents:
        i.pop("end_idx")

    return {
        "station_id": station_id,
        "series": series,
        "alerts": alerts,
        "health": health,
        "incidents": incidents,
        "metrics": metrics,
    }


def build_dashboard_data(df: pd.DataFrame, metrics: dict, station_ids: list[str]) -> dict:
    """Build the browser replay shape for every station in the run."""
    def json_value(value):
        return None if pd.isna(value) else value

    stations = {}
    for station_id in station_ids:
        g = df[df["station_id"] == station_id]
        stations[station_id] = [
            {
                "t": str(row.timestamp),
                "temp": json_value(row.temperature_c),
                "pres": json_value(row.pressure_hpa),
                "hum": json_value(row.humidity_pct),
                "anom": bool(row.pred_is_anomaly),
                "sev": row.pred_severity,
                "type": row.pred_anomaly_type,
                "conf": json_value(row.pred_confidence),
                "reason": row.pred_reason,
                "health": json_value(row.health_score),
            }
            for row in g.itertuples(index=False)
        ]
    return {"stations": stations, "metrics": metrics}


if __name__ == "__main__":
    stations = ["AWS_DELHI_01", "AWS_PUNE_02"]
    df = run_pipeline(stations, n_points=1500)
    metrics = evaluate(df)
    print(json.dumps(metrics, indent=2))

    Path("data").mkdir(parents=True, exist_ok=True)
    df.to_csv("data/pipeline_output.csv", index=False)

    payload = build_dashboard_payload(df, metrics, stations[0])
    with open("data/dashboard_payload.json", "w") as f:
        json.dump(payload, f)
    print(f"\nDashboard payload written: {len(payload['series'])} points, {len(payload['alerts'])} alerts, {len(payload['incidents'])} incidents")

    dashboard_data = build_dashboard_data(df, metrics, stations)
    with open("data/dashboard_data.js", "w") as f:
        f.write("const AWS_DATA = ")
        json.dump(dashboard_data, f, allow_nan=False)
        f.write(";\n")
    print(f"Dashboard data written: {len(dashboard_data['stations'])} stations")
