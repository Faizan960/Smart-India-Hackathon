"""Unsupervised anomaly detector (spec section 11).

An Isolation Forest over the standardized evidence features, trained ONLY on the
chronological training split and ONLY on rows with all raw core sensors present.
Raw Isolation Forest scores are calibrated into a continuous ``anomaly_score`` in
[0, 1] (higher = more anomalous) via a logistic anchored on the *training* score
distribution — so the mapping is derived from real data, never hand-tuned to make
a demo look good.

The detector reports a score and a flag; it does NOT name a fault type (that is
the classifier's job) and does NOT by itself claim a sensor has failed.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

from .config import DEFAULT_CONFIG
from .features import to_model_matrix


def _sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(x, -60.0, 60.0)))


_SCALER_FILE = "scaler.joblib"
_MODEL_FILE = "isolation_forest.joblib"
_FEATURES_FILE = "feature_config.json"
_META_FILE = "model_metadata.json"


class AnomalyDetector:
    def __init__(self, config=None):
        self.config = config or DEFAULT_CONFIG
        self.scaler: StandardScaler | None = None
        self.model: IsolationForest | None = None
        self.features: list[str] = list(self.config.if_features)
        self.calibration: Dict[str, float] = {}
        self.metadata: Dict = {}

    # --- training ------------------------------------------------------------
    def fit(self, feat_df: pd.DataFrame) -> "AnomalyDetector":
        X, complete = to_model_matrix(feat_df, self.config, self.features)
        Xc = X[complete]
        if len(Xc) < 100:
            raise ValueError(f"too few complete rows to train ({len(Xc)})")

        self.scaler = StandardScaler().fit(Xc)
        Xs = self.scaler.transform(Xc)
        self.model = IsolationForest(
            n_estimators=self.config.if_n_estimators,
            contamination=self.config.if_contamination,
            max_samples=self.config.if_max_samples,
            random_state=self.config.if_random_state,
            n_jobs=-1,
        ).fit(Xs)

        raw = -self.model.decision_function(Xs)  # higher => more anomalous
        self._calibrate(raw)
        self.metadata = {
            "trained_utc": datetime.now(timezone.utc).isoformat(),
            "n_train_complete_rows": int(len(Xc)),
            "n_train_rows_total": int(len(X)),
            "features": self.features,
            "isolation_forest": {
                "n_estimators": self.config.if_n_estimators,
                "contamination": self.config.if_contamination,
                "max_samples": self.config.if_max_samples,
                "random_state": self.config.if_random_state,
            },
            "calibration": self.calibration,
            "train_raw_score_percentiles": {
                str(p): float(np.percentile(raw, p)) for p in (50, 90, 95, 99, 99.7)
            },
        }
        return self

    def _calibrate(self, raw: np.ndarray) -> None:
        center = float(np.percentile(raw, self.config.calib_center_pct))
        upper = float(np.percentile(raw, self.config.calib_upper_pct))
        # slope so that the upper percentile maps to ~0.88 (logit 2.0)
        scale = max((upper - center) / 2.0, 1e-6)
        self.calibration = {
            "method": "logistic_on_training_raw",
            "center": center,
            "scale": scale,
            "center_pct": self.config.calib_center_pct,
            "upper_pct": self.config.calib_upper_pct,
        }

    # --- scoring -------------------------------------------------------------
    def score(self, feat_df: pd.DataFrame) -> pd.DataFrame:
        if self.model is None or self.scaler is None:
            raise RuntimeError("detector not fitted/loaded")
        X, complete = to_model_matrix(feat_df, self.config, self.features)
        Xs = self.scaler.transform(X)
        raw = -self.model.decision_function(Xs)
        score = _sigmoid((raw - self.calibration["center"]) / self.calibration["scale"])

        out = pd.DataFrame(index=feat_df.index)
        out["raw_score"] = raw
        out["anomaly_score"] = np.where(complete, score, np.nan)
        out["is_anomaly"] = out["anomaly_score"] >= self.config.severity_warning_score
        out["core_complete"] = complete
        return out

    # --- persistence ---------------------------------------------------------
    def save(self, models_dir=None) -> Path:
        d = Path(models_dir or self.config.models_dir)
        d.mkdir(parents=True, exist_ok=True)
        joblib.dump(self.scaler, d / _SCALER_FILE)
        joblib.dump(self.model, d / _MODEL_FILE)
        with open(d / _FEATURES_FILE, "w", encoding="utf-8") as f:
            json.dump({"features": self.features, "calibration": self.calibration}, f, indent=2)
        with open(d / _META_FILE, "w", encoding="utf-8") as f:
            json.dump(self.metadata, f, indent=2)
        return d

    @classmethod
    def load(cls, models_dir=None, config=None) -> "AnomalyDetector":
        cfg = config or DEFAULT_CONFIG
        d = Path(models_dir or cfg.models_dir)
        det = cls(cfg)
        det.scaler = joblib.load(d / _SCALER_FILE)
        det.model = joblib.load(d / _MODEL_FILE)
        with open(d / _FEATURES_FILE, "r", encoding="utf-8") as f:
            fc = json.load(f)
        det.features = fc["features"]
        det.calibration = fc["calibration"]
        meta_path = d / _META_FILE
        if meta_path.exists():
            with open(meta_path, "r", encoding="utf-8") as f:
                det.metadata = json.load(f)
        return det
