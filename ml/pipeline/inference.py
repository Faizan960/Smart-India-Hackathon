"""Runtime inference entry point for the AWS Sentinel real-data pipeline
(spec section 36, phase 10).

Ties the trained artifacts together for live use: build features -> score with the
Isolation Forest -> type the fault -> explain -> fuse inspectable evidence ->
emit a Laya-typed decision (via the existing contract) verified by the detector,
plus rolling sensor health. Everything returned is computed from real model
outputs and hedged; nothing is hard-coded (spec section 35).

This module is isolated: it is NOT imported by ``api/`` or the production
``ml/inference.py`` and does not alter them.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

import numpy as np
import pandas as pd

from .anomaly_detector import AnomalyDetector
from .baseline import load_baselines
from .classifier import classify_faults, load_thresholds
from .config import CORE_SENSORS, DEFAULT_CONFIG
from .evidence import fuse_frame
from .explainability import Explainer
from .features import build_features
from .health import rolling_health, station_health_summary
from .laya_adapter import fuse_with_detector, pipeline_decision


class SentinelInference:
    """Loads trained artifacts once and serves predictions for telemetry frames."""

    def __init__(self, config=None, models_dir=None, baselines_path=None):
        self.config = config or DEFAULT_CONFIG
        md = Path(models_dir or self.config.models_dir)
        self.baselines = load_baselines(Path(baselines_path or (md / "baselines.json")))
        self.detector = AnomalyDetector.load(md, self.config)
        self.thresholds = load_thresholds(md, self.config)
        self.explainer = Explainer(self.detector, self.config)

    def _prepare(self, df: pd.DataFrame):
        """features -> anomaly scores -> fault classification for a telemetry frame."""
        feat = build_features(df, baselines=self.baselines, config=self.config)
        anom = self.detector.score(feat)
        cls = classify_faults(feat, anom, self.thresholds, self.config)
        return feat, anom, cls

    def predict_frame(self, df: pd.DataFrame, explain: bool = False) -> pd.DataFrame:
        """Batch scoring: one tidy assessment row per input observation.

        Returns a frame (indexed like the built features) with the score, severity,
        typed fault, fused status and rolling health status. Explanations are
        included per-row only when ``explain=True`` (SHAP over many rows is costly).
        """
        feat, anom, cls = self._prepare(df)
        expl = self.explainer.explain(feat, anom) if explain else None
        fused = fuse_frame(feat, anom, cls, explanations=expl, config=self.config)
        health = rolling_health(feat, anom, self.config)["health_status"]

        out = pd.DataFrame(index=feat.index)
        out["station_id"] = feat["station_id"].to_numpy()
        out["timestamp"] = feat["timestamp"].to_numpy()
        out["anomaly_score"] = anom["anomaly_score"].to_numpy()
        out["is_anomaly"] = anom["is_anomaly"].to_numpy()
        for col in ("severity", "fused_status", "fault_type", "fault_confidence",
                    "legacy_label", "fault_present", "structural_fault", "reasons"):
            out[col] = fused[col].to_numpy()
        out["health_status"] = health.to_numpy()
        if expl is not None:
            out["explanation"] = [e.get("summary") for e in expl]
        return out

    def predict_observation(self, history_df: pd.DataFrame,
                            station_id: Optional[str] = None) -> Dict:
        """Rich assessment of the LATEST observation in a station's recent history.

        ``history_df`` must hold enough recent rows for one station to compute
        rates and rolling features. Returns a hedged, fully-sourced result dict
        including the Isolation Forest score, typed fault, SHAP explanation, fused
        evidence, the Laya-typed decision (verified by the detector) and health.
        """
        df = history_df
        if station_id is not None:
            df = df[df["station_id"] == station_id]
        if df is None or df.empty:
            raise ValueError("history_df has no rows for the requested station")

        feat, anom, cls = self._prepare(df)
        ts = pd.to_datetime(feat["timestamp"], errors="coerce")
        if not ts.notna().any():
            raise ValueError("no valid timestamps in history")
        last_i = ts.idxmax()

        expl = self.explainer.explain(feat.loc[[last_i]], anom.loc[[last_i]])
        fused = fuse_frame(feat.loc[[last_i]], anom.loc[[last_i]], cls.loc[[last_i]],
                           explanations=expl, config=self.config)
        assessment = fused.iloc[0].to_dict()
        decision = pipeline_decision(assessment)
        verification = fuse_with_detector(decision, anom.loc[last_i].to_dict())

        sid = feat.loc[last_i, "station_id"]
        summ = station_health_summary(feat, anom, cls, self.config)
        hrow = summ[summ["station_id"] == sid]
        health = hrow.iloc[0].to_dict() if len(hrow) else {}
        # keep the result strictly JSON-serializable: the summary carries a pandas
        # Timestamp for the latest window, which json.dumps cannot encode.
        lt = health.get("latest_timestamp")
        if lt is not None:
            health["latest_timestamp"] = None if pd.isna(lt) else pd.Timestamp(lt).isoformat()

        return {
            "station_id": str(sid),
            "timestamp": None if pd.isna(ts.loc[last_i]) else ts.loc[last_i].isoformat(),
            "anomaly_score": assessment["anomaly_score"],
            "is_anomaly": bool(anom.loc[last_i, "is_anomaly"]) if pd.notna(anom.loc[last_i, "is_anomaly"]) else False,
            "severity": assessment["severity"],
            "fault_type": assessment["fault_type"],
            "fault_confidence": assessment["fault_confidence"],
            "legacy_label": assessment["legacy_label"],
            "fault_present": assessment["fault_present"],
            "fused_status": assessment["fused_status"],
            "reasons": assessment["reasons"],
            "explanation": expl[0],
            "laya_decision": {
                "decision": decision.decision, "confidence": decision.confidence,
                "fault_present": decision.fault_present, "source": decision.raw.get("source"),
            },
            "verification": verification,
            "health": health,
        }

    def predict_latest_complete(self, history_df: pd.DataFrame,
                                station_id: Optional[str] = None,
                                history_rows: int = 300) -> Dict:
        """Assess the latest *scoreable* observation for a station.

        Real streaming telemetry frequently ends on an incomplete reading (a core
        sensor value has not arrived yet), and :meth:`predict_observation`
        correctly refuses to fabricate an Isolation Forest score for such a row.
        For interactive testing/demo you usually want the most recent row that CAN
        be scored: this trims to the trailing window ending at the latest complete
        observation (see :func:`latest_complete_window`) and assesses that point.

        This does NOT drop or impute incomplete rows from the dataset — it only
        chooses which recent window to hand to the scorer, so missing observations
        remain intact evidence for dropout and health. For live telemetry, keep
        calling :meth:`predict_observation` (the actual-latest-row contract).
        """
        window = latest_complete_window(history_df, station_id, history_rows, self.config)
        return self.predict_observation(window, station_id=station_id)


def latest_complete_window(history_df: pd.DataFrame, station_id: Optional[str] = None,
                           history_rows: int = 300, config=None) -> pd.DataFrame:
    """Trailing window ending at the latest observation with all core sensors present.

    Returns the last ``history_rows`` rows (for a single station, sorted by time)
    up to and including the most recent row whose ``temperature``, ``humidity`` and
    ``pressure`` are all present — enough preceding context for the rate/rolling
    features to resolve. Raises ``ValueError`` if the station has no complete
    observation, or if more than one station is present and ``station_id`` is not
    given (to avoid scoring across stations).

    Selection only; it never mutates, imputes or discards data from the dataset.
    """
    config = config or DEFAULT_CONFIG
    df = history_df
    if station_id is not None:
        df = df[df["station_id"] == station_id]
    if df is None or df.empty:
        raise ValueError("history_df has no rows for the requested station")
    if df["station_id"].nunique() > 1:
        raise ValueError("latest_complete_window needs a single station; pass station_id")

    df = df.sort_values("timestamp").reset_index(drop=True)
    present = df[list(CORE_SENSORS)].notna().all(axis=1).to_numpy()
    if not present.any():
        sid = station_id if station_id is not None else df["station_id"].iloc[0]
        raise ValueError(f"station {sid} has no observation with all core sensors present")
    last_pos = int(np.flatnonzero(present).max())
    start = max(0, last_pos - int(history_rows) + 1)
    return df.iloc[start:last_pos + 1].copy()


_DEFAULT_ENGINE: Optional[SentinelInference] = None


def get_default_engine(config=None) -> SentinelInference:
    """Lazily construct and cache a default inference engine."""
    global _DEFAULT_ENGINE
    if _DEFAULT_ENGINE is None:
        _DEFAULT_ENGINE = SentinelInference(config)
    return _DEFAULT_ENGINE


def predict_observation(history_df: pd.DataFrame, station_id: Optional[str] = None,
                        config=None) -> Dict:
    """Module-level convenience over :class:`SentinelInference`."""
    return get_default_engine(config).predict_observation(history_df, station_id)


def _auto_station(frame: pd.DataFrame, history_rows: int, config) -> Optional[str]:
    """First station (sorted) that has an observation with all core sensors present."""
    for sid in sorted(frame["station_id"].astype(str).unique()):
        try:
            latest_complete_window(frame, sid, history_rows, config)
            return sid
        except ValueError:
            continue
    return None


def main(argv=None) -> int:
    """CLI: assess the latest observation for a station from raw NOAA data.

    By default it scores the latest COMPLETE observation (so a developer can test a
    real reading without hand-building a window that happens to end on an incomplete
    row). ``--allow-incomplete`` assesses the ACTUAL latest row instead, exercising
    the streaming contract: a missing core sensor yields a null score, never a
    fabricated one. Output is strict JSON (no ``default=str``) — proving the public
    result carries no NaN/Infinity.
    """
    import argparse
    import json

    from .data_loader import load_dataset

    ap = argparse.ArgumentParser(
        description="Assess the latest observation for a station from raw NOAA data")
    ap.add_argument("--input", nargs="+", required=True, help="raw CSV/CSV.GZ/Parquet path(s)")
    ap.add_argument("--station", default=None,
                    help="station id (default: first station with a complete observation)")
    ap.add_argument("--models-dir", default=None, help="trained artifacts dir (default: config)")
    ap.add_argument("--history-rows", type=int, default=300,
                    help="trailing observations fed to the scorer for rate/rolling context")
    ap.add_argument("--allow-incomplete", action="store_true",
                    help="assess the ACTUAL latest row (streaming semantics) even if a core "
                         "sensor is missing; its score is then reported as null, never fabricated")
    args = ap.parse_args(argv)

    engine = SentinelInference(models_dir=args.models_dir)
    frame = load_dataset(args.input, config=engine.config).frame
    if frame.empty:
        raise SystemExit("no rows loaded from --input")

    stations = sorted(frame["station_id"].astype(str).unique())
    station = str(args.station) if args.station is not None else None
    if station is not None and station not in stations:
        raise SystemExit(f"station {station} not found; available: {stations}")
    if station is None:
        station = _auto_station(frame, args.history_rows, engine.config)
        if station is None and args.allow_incomplete and stations:
            station = stations[0]
    if station is None:
        raise SystemExit("no station has an observation with all core sensors present; "
                         "use --allow-incomplete to assess the latest (unscored) reading")

    if args.allow_incomplete:
        one = frame[frame["station_id"].astype(str) == station]
        result = engine.predict_observation(one, station_id=station)
    else:
        result = engine.predict_latest_complete(frame, station_id=station,
                                                 history_rows=args.history_rows)

    # Strict JSON (no default=str): if this raises, the public result contained a
    # non-serializable value (e.g. NaN) — a real contract failure, surfaced not hidden.
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
