"""Honest evaluation harness (spec sections 26 & 34).

Injects known faults into the clean holdout split, runs the real trained
detector + classifier over the corrupted data, and measures detection against
ground truth: precision / recall / F1, per-fault recall, a confusion matrix and
detection latency. Every number is computed from actual model outputs — nothing
is hard-coded. Results are written to reports/evaluation.json and .md.

Note on "false positives": the clean holdout is REAL data and contains genuine
outliers, so flags on non-injected rows are an UPPER BOUND on false positives,
not proof of error. This is stated in the report rather than hidden.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict

import numpy as np
import pandas as pd

from .anomaly_detector import AnomalyDetector
from .baseline import load_baselines
from .classifier import classify_faults, load_thresholds
from .config import DEFAULT_CONFIG, FAULT_TYPES
from .fault_injector import inject_faults
from .features import build_features


def _prf(tp: int, fp: int, fn: int) -> Dict[str, float]:
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {"precision": round(precision, 4), "recall": round(recall, 4), "f1": round(f1, 4),
            "tp": int(tp), "fp": int(fp), "fn": int(fn)}


def evaluate(clean_test_df: pd.DataFrame, models_dir=None, baselines_path=None,
             config=None, seed: int = 42) -> Dict:
    """Run the full injected-fault evaluation and return a metrics dict."""
    config = config or DEFAULT_CONFIG
    models_dir = Path(models_dir or config.models_dir)
    baselines_path = Path(baselines_path or (models_dir / "baselines.json"))

    baselines = load_baselines(baselines_path)
    detector = AnomalyDetector.load(models_dir, config)
    thresholds = load_thresholds(models_dir, config)

    corrupted, events = inject_faults(clean_test_df, config, seed=seed)
    feat = build_features(corrupted, baselines=baselines, config=config)
    # align ground-truth (build_features re-sorts by station,timestamp identically)
    gt = corrupted.sort_values(["station_id", "timestamp"]).reset_index(drop=True)
    anom = detector.score(feat)
    cls = classify_faults(feat, anom, thresholds, config).reset_index(drop=True)

    ev = pd.DataFrame({
        "station_id": gt["station_id"].to_numpy(),
        "timestamp": gt["timestamp"].to_numpy(),
        "injected_fault": gt["injected_fault"].to_numpy(),
        "event_id": gt["event_id"].to_numpy(),
        "pred_fault": cls["fault_type"].to_numpy(),
        "anomaly_score": anom["anomaly_score"].to_numpy(),
    })
    ev["gt_flag"] = ev["injected_fault"] != "NORMAL"
    ev["pred_flag"] = ev["pred_fault"] != "NORMAL"

    metrics = {"seed": seed, "n_test_rows": int(len(ev)),
               "n_injected_rows": int(ev["gt_flag"].sum()),
               "n_events": int((events["event_id"] > 0).sum()) if len(events) else 0}
    metrics["detection_row_level"] = _row_detection(ev)
    metrics["detection_event_level"] = _event_detection(ev)
    metrics["per_fault"] = _per_fault(ev)
    metrics["confusion_matrix"] = _confusion(ev)
    metrics["latency"] = _latency(ev)
    metrics["false_positive_upper_bound"] = _fp_bound(ev)
    metrics["injected_event_counts"] = (events["fault_type"].value_counts().to_dict() if len(events) else {})
    return metrics


def _row_detection(ev: pd.DataFrame) -> Dict:
    tp = int((ev["gt_flag"] & ev["pred_flag"]).sum())
    fp = int((~ev["gt_flag"] & ev["pred_flag"]).sum())
    fn = int((ev["gt_flag"] & ~ev["pred_flag"]).sum())
    return _prf(tp, fp, fn)


def _event_detection(ev: pd.DataFrame) -> Dict:
    e = ev[ev["event_id"] > 0]
    if e.empty:
        return {"n_events": 0, "detected": 0, "recall": 0.0}
    detected = e.groupby("event_id")["pred_flag"].any()
    return {"n_events": int(len(detected)), "detected": int(detected.sum()),
            "recall": round(float(detected.mean()), 4)}


def _per_fault(ev: pd.DataFrame) -> Dict:
    out: Dict[str, Dict] = {}
    for ftype in FAULT_TYPES:
        if ftype == "NORMAL":
            continue
        rows = ev[ev["injected_fault"] == ftype]
        if rows.empty:
            continue
        detected = rows["pred_flag"]
        typed = rows.loc[detected, "pred_fault"] == ftype
        out[ftype] = {
            "injected_rows": int(len(rows)),
            "detected_rows": int(detected.sum()),
            "row_recall": round(float(detected.mean()), 4),
            "typing_accuracy_of_detected": round(float(typed.mean()), 4) if detected.sum() else 0.0,
            "detected_as": rows.loc[detected, "pred_fault"].value_counts().to_dict(),
        }
    return out


def _confusion(ev: pd.DataFrame) -> Dict:
    ct = pd.crosstab(ev["injected_fault"], ev["pred_fault"])
    return {str(idx): {str(c): int(v) for c, v in row.items()} for idx, row in ct.iterrows()}


def _latency(ev: pd.DataFrame) -> Dict:
    per_type: Dict[str, list] = {}
    for eid, g in ev[ev["event_id"] > 0].groupby("event_id"):
        g = g.sort_values("timestamp")
        ftype = g["injected_fault"].iloc[0]
        flagged = g[g["pred_flag"]]
        if flagged.empty:
            continue
        first = flagged.index[0]
        samples = int(g.index.get_loc(first))
        hours = float((g.loc[first, "timestamp"] - g["timestamp"].iloc[0]) / np.timedelta64(1, "h"))
        per_type.setdefault(ftype, []).append((samples, hours))
    summary = {}
    for ftype, vals in per_type.items():
        s = np.array([v[0] for v in vals]); h = np.array([v[1] for v in vals])
        summary[ftype] = {
            "detected_events": int(len(vals)),
            "median_latency_samples": float(np.median(s)),
            "median_latency_hours": round(float(np.median(h)), 3),
            "mean_latency_hours": round(float(np.mean(h)), 3),
        }
    return summary


def _fp_bound(ev: pd.DataFrame) -> Dict:
    ni = ev[~ev["gt_flag"]]
    flagged = int(ni["pred_flag"].sum())
    return {"non_injected_rows": int(len(ni)), "flagged": flagged,
            "rate_upper_bound": round(flagged / len(ni), 4) if len(ni) else 0.0}


def write_reports(metrics: Dict, reports_dir=None, config=None) -> Path:
    config = config or DEFAULT_CONFIG
    d = Path(reports_dir or config.reports_dir)
    d.mkdir(parents=True, exist_ok=True)
    with open(d / "evaluation.json", "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2, default=str)

    det = metrics["detection_row_level"]
    lines = [
        "# AWS Sentinel — ML Evaluation (injected faults on real holdout data)",
        "",
        f"- Test rows: **{metrics['n_test_rows']:,}**  |  injected rows: **{metrics['n_injected_rows']:,}**  |  events: **{metrics['n_events']}**",
        f"- Row-level detection: precision **{det['precision']}**, recall **{det['recall']}**, F1 **{det['f1']}**",
        f"- Event-level recall: **{metrics['detection_event_level']['recall']}** "
        f"({metrics['detection_event_level']['detected']}/{metrics['detection_event_level']['n_events']} events)",
        f"- False-positive rate on non-injected rows (UPPER BOUND — real data has genuine outliers): "
        f"**{metrics['false_positive_upper_bound']['rate_upper_bound']}**",
        "",
        "## Per-fault detection & typing",
        "",
        "| Fault | injected | detected | row recall | typing acc (of detected) |",
        "|---|---:|---:|---:|---:|",
    ]
    for ftype, m in metrics["per_fault"].items():
        lines.append(f"| {ftype} | {m['injected_rows']} | {m['detected_rows']} | "
                     f"{m['row_recall']} | {m['typing_accuracy_of_detected']} |")
    lines += ["", "## Detection latency (windowed faults)", "",
              "| Fault | detected events | median latency (h) | mean latency (h) |",
              "|---|---:|---:|---:|"]
    for ftype, m in metrics["latency"].items():
        lines.append(f"| {ftype} | {m['detected_events']} | {m['median_latency_hours']} | {m['mean_latency_hours']} |")
    lines.append("")
    with open(d / "evaluation.md", "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return d


if __name__ == "__main__":
    import argparse

    from .data_loader import load_dataset
    from .preprocessing import chronological_split

    ap = argparse.ArgumentParser(description="Evaluate the Sentinel detector on injected faults")
    ap.add_argument("--input", nargs="+", required=True, help="raw CSV/CSV.GZ/Parquet path(s)")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    df = load_dataset(args.input).frame
    _, _, test = chronological_split(df)
    metrics = evaluate(test, seed=args.seed)
    out = write_reports(metrics)
    det = metrics["detection_row_level"]
    print(f"Detection F1={det['f1']} recall={det['recall']} precision={det['precision']}")
    print(f"Event recall={metrics['detection_event_level']['recall']}")
    print(f"Reports written to {out}")

