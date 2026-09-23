"""Bridge from the LIVE weather frontend/API payload to the AWS Sentinel real-data
inference pipeline (branch ``feature/live-weather-demo``).

The dashboard polls a live weather API (OpenWeatherMap in the current development
configuration), normalizes each reading in the browser (``src/data/normalizer.js``)
and keeps a rolling per-station history in ``localStorage``. This module adapts
that history -- a list of plain observation dicts -- into the canonical Sentinel
schema and calls :class:`ml.pipeline.inference.SentinelInference`, returning the
pipeline's own structured result plus a couple of backward-compatible aliases the
existing dashboard already reads.

Design notes:
  * OpenWeather/frontend-specific field handling lives HERE, never in the core ML
    modules -- the dependency direction is adapter -> pipeline, never the reverse,
    so ``ml/pipeline`` stays isolated (nothing in the pipeline imports this).
  * The live station ids (e.g. ``DL-001``) are development locations, NOT the NOAA
    stations the model was trained on, so they have no station-specific trained
    baseline. The pipeline already falls back to its global climatology for an
    unknown station; ``baseline_source`` makes that explicit rather than silently
    pretending a Delhi feed maps to a trained NOAA station.
  * Missing/late core sensors are NEVER fabricated. An incomplete latest reading
    yields ``anomaly_score = None`` (the pipeline's missing-data guard), never a
    zero-filled or invented score.
  * The result is strictly JSON-safe (no NaN/Infinity) so it survives
    ``json.dumps(..., allow_nan=False)`` in the serverless handler.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

import pandas as pd

from .config import DEFAULT_CONFIG, STANDARD_COLUMNS
from .inference import SentinelInference, get_default_engine

# Trailing observations fed to the scorer by default. The Sentinel temporal
# features are wall-clock based (3h/24h windows, 3h pressure tendency), so more
# history resolves them better; this only bounds payload / compute per call.
LIVE_HISTORY_ROWS = 300

# Placeholder station id when the caller supplies none (kept obviously non-NOAA).
DEFAULT_LIVE_STATION = "LIVE-0001"

# incoming (browser-normalized) field -> accepted source keys, most-preferred first
_FIELD_ALIASES: Dict[str, tuple] = {
    "temperature": ("temperature", "temperatureC", "temp"),
    "humidity": ("humidity", "humidityPct", "rh"),
    "pressure": ("pressure", "pressureHpa", "mslp"),
    "wind_speed": ("wind_speed", "windSpeed", "wind"),
    "latitude": ("latitude", "lat"),
    "longitude": ("longitude", "lon", "lng"),
}
_TIMESTAMP_KEYS = ("timestamp", "observedAt", "receivedAt", "time")
_EPOCH_KEYS = ("observedEpoch", "receivedEpoch", "lastUpdatedEpoch", "dt")

def _num(value: Any) -> float:
    """Coerce to float; None / non-numeric / non-finite -> NaN (never fabricated)."""
    if value is None:
        return float("nan")
    try:
        f = float(value)
    except (TypeError, ValueError):
        return float("nan")
    return f if math.isfinite(f) else float("nan")


def _pick(point: Dict[str, Any], names: tuple) -> Any:
    for n in names:
        if n in point and point[n] is not None:
            return point[n]
    return None


def _row_timestamp(point: Dict[str, Any]):
    """Resolve a single observation's timestamp to a tz-naive (UTC) Timestamp.

    Accepts an ISO string (preferred) or an epoch-seconds field. Returns ``NaT``
    when nothing usable is present; such rows are dropped (they cannot be ordered).
    """
    ts = _pick(point, _TIMESTAMP_KEYS)
    if ts is not None:
        t = pd.to_datetime(ts, errors="coerce", utc=True)
    else:
        epoch = _pick(point, _EPOCH_KEYS)
        if epoch is None:
            return pd.NaT
        t = pd.to_datetime(_num(epoch), unit="s", errors="coerce", utc=True)
    return pd.NaT if pd.isna(t) else t.tz_convert(None)


def normalize_live_history(history, station_id: Optional[str] = None,
                           latitude=None, longitude=None,
                           history_rows: int = LIVE_HISTORY_ROWS, config=None) -> pd.DataFrame:
    """Convert a list of browser-normalized live observations into the canonical
    Sentinel schema (``STANDARD_COLUMNS``).

    Selection / renaming only: core sensor values are copied verbatim (a missing
    reading stays ``NaN``), never imputed or zero-filled -- so a genuine data gap
    remains evidence for dropout/health. Rows without a resolvable timestamp are
    dropped, the remainder sorted chronologically, and the last ``history_rows``
    kept. A per-call ``station_id``/coords apply to every row (the browser history
    points do not carry them).
    """
    config = config or DEFAULT_CONFIG
    sid = str(station_id) if station_id not in (None, "") else DEFAULT_LIVE_STATION
    rows: List[Dict[str, Any]] = []
    for point in (history or []):
        if not isinstance(point, dict):
            continue
        lat = latitude if latitude is not None else _pick(point, _FIELD_ALIASES["latitude"])
        lon = longitude if longitude is not None else _pick(point, _FIELD_ALIASES["longitude"])
        rows.append({
            "timestamp": _row_timestamp(point),
            "station_id": sid,
            "latitude": _num(lat),
            "longitude": _num(lon),
            "temperature": _num(_pick(point, _FIELD_ALIASES["temperature"])),
            "humidity": _num(_pick(point, _FIELD_ALIASES["humidity"])),
            "pressure": _num(_pick(point, _FIELD_ALIASES["pressure"])),
            "wind_speed": _num(_pick(point, _FIELD_ALIASES["wind_speed"])),
        })

    df = pd.DataFrame(rows, columns=list(STANDARD_COLUMNS))
    if df.empty:
        return df
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df = df[df["timestamp"].notna()].sort_values("timestamp").reset_index(drop=True)
    if history_rows and len(df) > int(history_rows):
        df = df.iloc[-int(history_rows):].reset_index(drop=True)
    return df


def trained_stations(baselines: Dict) -> set:
    """Station ids that have a station-specific trained baseline (else -> global)."""
    ids: set = set()
    try:
        s = baselines.get("s", {})
        for sensor in ("temperature", "humidity", "pressure"):
            ids |= set(s.get(sensor, {}).get("median", {}).keys())
    except Exception:
        return set()
    return ids


def baseline_source(station_id, baselines) -> str:
    """'station_specific' if the id was in the training data, else 'global_fallback'.

    Surfaced so the UI/JSON never implies a live OpenWeatherMap location has a real
    historical NOAA baseline when it does not.
    """
    return "station_specific" if str(station_id) in trained_stations(baselines) else "global_fallback"

def assess_live(history, station_id: Optional[str] = None, latitude=None, longitude=None,
                engine: Optional[SentinelInference] = None,
                history_rows: int = LIVE_HISTORY_ROWS) -> Dict[str, Any]:
    """Assess the latest live observation for one station through Sentinel.

    Returns the pipeline's structured :meth:`SentinelInference.predict_observation`
    result, enriched (never overwritten) with:
      * ``confidence``      -- backward-compatible alias of ``fault_confidence``;
      * ``data_complete``   -- whether the latest reading could be scored;
      * ``baseline_source`` -- 'station_specific' vs 'global_fallback';
      * ``n_history``       -- rows actually used.
    Strictly JSON-safe. An empty/timestamp-less payload returns a safe degraded
    state rather than raising.
    """
    engine = engine or get_default_engine()
    sid = str(station_id) if station_id not in (None, "") else DEFAULT_LIVE_STATION
    df = normalize_live_history(history, sid, latitude, longitude, history_rows, engine.config)
    if df.empty:
        return _degraded(sid, "no observations with a usable timestamp were provided")

    result = engine.predict_observation(df, station_id=sid)
    # Enrichment only -- pipeline semantics (score/severity/fault_type) are untouched.
    result["confidence"] = result.get("fault_confidence")
    result["data_complete"] = result.get("anomaly_score") is not None
    result["baseline_source"] = baseline_source(sid, engine.baselines)
    result["n_history"] = int(len(df))
    return result


def _degraded(station_id: str, reason: str) -> Dict[str, Any]:
    """Safe, fully-null assessment when there is not enough data to score anything.

    Mirrors the pipeline's incomplete-data contract: no fabricated score, no
    confirmed fault, strictly JSON-safe -- the UI stays functional and honest.
    """
    return {
        "station_id": station_id,
        "timestamp": None,
        "anomaly_score": None,
        "is_anomaly": False,
        "severity": "UNKNOWN",
        "fault_type": "NORMAL",
        "fault_confidence": 0.0,
        "confidence": 0.0,
        "legacy_label": "NORMAL",
        "fault_present": 0.0,
        "fused_status": "NORMAL",
        "reasons": [f"insufficient live history: {reason}"],
        "explanation": {"method": None, "score": None, "base_value": None,
                        "top_features": [], "summary": "No assessment: " + reason},
        "laya_decision": {"decision": "NORMAL", "confidence": 0.0,
                          "fault_present": 0.0, "source": "aws_sentinel_pipeline"},
        "verification": {"laya_decision": "NORMAL", "verification_status": "NORMAL",
                         "isolation_forest_anomaly": False, "isolation_forest_score": None},
        "health": {"station_id": station_id, "health_status": "UNKNOWN",
                   "n_observations": 0, "dominant_fault_in_range": "NORMAL"},
        "data_complete": False,
        "baseline_source": "global_fallback",
        "n_history": 0,
    }


