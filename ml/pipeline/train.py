"""Training entrypoint for the AWS Sentinel real-data pipeline (spec section 36).

Runs the leakage-free pipeline end to end on real data:
  load -> chronological split -> diurnal baselines -> features -> Isolation Forest
  -> classifier thresholds -> (optional) injected-fault evaluation.

All artifacts are written under models/sentinel/ and reports/. Training uses ONLY
the training split; the baseline and every threshold is derived from training data
so evaluation on the future test split is honest.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .anomaly_detector import AnomalyDetector
from .baseline import compute_baselines, save_baselines
from .classifier import fit_thresholds, save_thresholds
from .config import DEFAULT_CONFIG
from .data_loader import load_dataset
from .evaluator import evaluate, write_reports
from .features import build_features
from .preprocessing import chronological_split, split_bounds


def train_pipeline(paths, config=None, seed: int = 42, run_eval: bool = True) -> dict:
    config = config or DEFAULT_CONFIG
    config.ensure_dirs()

    load = load_dataset(paths, config=config)
    df = load.frame
    train, val, test = chronological_split(df, config)
    t_end, v_end = split_bounds(df, config)

    baselines = compute_baselines(train, config)
    save_baselines(baselines, Path(config.models_dir) / "baselines.json")

    feat_train = build_features(train, baselines=baselines, config=config)
    detector = AnomalyDetector(config).fit(feat_train)
    detector.save()
    thresholds = fit_thresholds(feat_train, config)
    save_thresholds(thresholds, config=config)

    summary = {
        "trained_utc": datetime.now(timezone.utc).isoformat(),
        "input_files": [str(p) for p in (paths if isinstance(paths, (list, tuple)) else [paths])],
        "rows_total": int(len(df)),
        "rows_train": int(len(train)), "rows_val": int(len(val)), "rows_test": int(len(test)),
        "train_end": str(t_end), "val_end": str(v_end),
        "stations": sorted(df["station_id"].unique().tolist()),
        "n_train_complete_rows": detector.metadata.get("n_train_complete_rows"),
        "features": detector.features,
        "calibration": detector.calibration,
        "rate_thresholds": thresholds.get("rate_abs_threshold"),
    }
    with open(Path(config.reports_dir) / "training_summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, default=str)

    if run_eval:
        metrics = evaluate(test, config=config, seed=seed)
        write_reports(metrics, config=config)
        summary["evaluation"] = {
            "detection_f1": metrics["detection_row_level"]["f1"],
            "detection_recall": metrics["detection_row_level"]["recall"],
            "event_recall": metrics["detection_event_level"]["recall"],
        }
    return summary


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Train the AWS Sentinel real-data ML pipeline")
    ap.add_argument("--input", nargs="+", required=True, help="raw CSV/CSV.GZ/Parquet path(s)")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--no-eval", action="store_true", help="skip injected-fault evaluation")
    args = ap.parse_args()

    summary = train_pipeline(args.input, seed=args.seed, run_eval=not args.no_eval)
    print(json.dumps(summary, indent=2, default=str))
