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

# Minimum spacing (seconds) between two *distinct* live observations. The dashboard
# POLLS the weather API ~once a minute, but the upstream source (OpenWeatherMap)
# only recomputes its observation roughly every ~10 minutes, so the same physical
# observation is delivered on many consecutive polls. The Sentinel temporal
# features (temp_rate/humidity_rate/pressure_rate, pressure_change_3h) were trained
# on NOAA observations at their true observation cadence (~0.5h METAR to 3h
# synoptic); computing a per-hour rate over a ~1-minute poll gap divides a tiny
# value change by a tiny dt and fabricates a huge rate (0.27 C/min -> ~16 C/h) the
# model never saw. Polls closer than this are collapsed to a single observation
# (see _collapse_to_observations) so live rates stay on the trained scale. 10 min
# matches OpenWeatherMap's real update cadence; anything finer is polling/cache
# jitter, not a new measurement. Overridable per call (mainly for tests).
LIVE_MIN_OBS_INTERVAL_S = 600.0

# incoming (browser-normalized) field -> accepted source keys, most-preferred first
_FIELD_ALIASES: Dict[str, tuple] = {
    "temperature": ("temperature", "temperatureC", "temp"),
    "humidity": ("humidity", "humidityPct", "rh"),
    "pressure": ("pressure", "pressureHpa", "mslp"),
    "wind_speed": ("wind_speed", "windSpeed", "wind"),
    "latitude": ("latitude", "lat"),
    "longitude": ("longitude", "lon", "lng"),
}
# Timestamp source priority. The browser stamps each rolling-history point's
# ``timestamp`` with its RECEIVE/poll time (see src/state/store.js appendHistory,
# which advances the timestamp every poll so the live chart animates even when the
# provider's own observation time has not changed). The physical OBSERVATION time
# is carried separately (observedEpoch/observedAt). Rate features are only physically
# meaningful against observation time, so observation-time keys are resolved FIRST
# and the receive/poll time is a last resort -- never silently treated as the
# measurement time when a real observation time is present.
_OBS_TIME_KEYS = ("observedAt",)                                # ISO observation time
_OBS_EPOCH_KEYS = ("observedEpoch", "lastUpdatedEpoch", "dt")   # epoch-seconds observation time
_RECV_TIME_KEYS = ("timestamp", "time", "receivedAt")           # ISO receive/poll time (fallback)
_RECV_EPOCH_KEYS = ("receivedEpoch", "fetchedAtEpoch")          # epoch-seconds receive time (fallback)

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

    Prefers the source OBSERVATION time (observedAt/observedEpoch/...) over the
    browser RECEIVE/poll time (timestamp/receivedEpoch/...), trying an ISO string
    then an epoch-seconds field within each group. Returns ``NaT`` when nothing
    usable is present; such rows are dropped (they cannot be ordered) -- never
    fabricated.
    """
    for keys, is_epoch in ((_OBS_TIME_KEYS, False), (_OBS_EPOCH_KEYS, True),
                           (_RECV_TIME_KEYS, False), (_RECV_EPOCH_KEYS, True)):
        raw = _pick(point, keys)
        if raw is None:
            continue
        t = (pd.to_datetime(_num(raw), unit="s", errors="coerce", utc=True) if is_epoch
             else pd.to_datetime(raw, errors="coerce", utc=True))
        if pd.notna(t):
            return t.tz_convert(None)
    return pd.NaT


def _collapse_to_observations(df: pd.DataFrame, min_obs_interval_s: float) -> pd.DataFrame:
    """Collapse repeat polls / sub-cadence jitter into DISTINCT observations.

    ``df`` must already be sorted ascending by observation timestamp (ties in input
    poll order). Walking backwards from the most recent observation, a row is kept
    only when it is at least ``min_obs_interval_s`` before the last kept one; rows
    closer than that -- repeat polls or cache jitter of the same underlying
    observation -- are dropped, keeping the freshest. The latest observation is
    ALWAYS kept, so a genuine change on the newest reading is never discarded.

    This is pure *selection* of real rows: nothing is interpolated, averaged,
    resampled onto a fixed grid, or invented. It exists so the pipeline's per-hour
    rate features are computed over true observation-time gaps at (near) the trained
    cadence instead of over the ~1-minute browser poll interval -- see
    :data:`LIVE_MIN_OBS_INTERVAL_S`.
    """
    n = len(df)
    if n <= 1 or not (min_obs_interval_s and min_obs_interval_s > 0):
        return df
    ts = df["timestamp"]
    tol = pd.Timedelta(seconds=float(min_obs_interval_s))
    keep = [n - 1]
    anchor = ts.iloc[n - 1]
    for i in range(n - 2, -1, -1):
        if anchor - ts.iloc[i] >= tol:
            keep.append(i)
            anchor = ts.iloc[i]
    keep.sort()
    return df.iloc[keep].reset_index(drop=True)


def normalize_live_history(history, station_id: Optional[str] = None,
                           latitude=None, longitude=None,
                           history_rows: int = LIVE_HISTORY_ROWS, config=None,
                           min_obs_interval_s: float = LIVE_MIN_OBS_INTERVAL_S) -> pd.DataFrame:
    """Convert a list of browser-normalized live observations into the canonical
    Sentinel schema (``STANDARD_COLUMNS``).

    Selection / renaming only: core sensor values are copied verbatim (a missing
    reading stays ``NaN``), never imputed or zero-filled -- so a genuine data gap
    remains evidence for dropout/health. Each row is timestamped by its true source
    OBSERVATION time when available (falling back to the browser receive/poll time);
    rows without a resolvable timestamp are dropped. The remainder is sorted
    chronologically and then collapsed to DISTINCT observations spaced at least
    ``min_obs_interval_s`` apart (repeat polls of the same observation are removed;
    set to 0 to disable), and the last ``history_rows`` are kept. A per-call
    ``station_id``/coords apply to every row (the browser history points do not
    carry them). The returned frame's ``.attrs['n_raw_observations']`` records how
    many valid-timestamp rows existed before collapsing.
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
    # stable sort by OBSERVATION time; ties keep input (poll) order so that when one
    # observation time is polled repeatedly the freshest poll wins on collapse.
    df = df[df["timestamp"].notna()].sort_values("timestamp", kind="stable").reset_index(drop=True)
    n_raw = int(len(df))
    # Collapse repeat polls / sub-cadence jitter to true distinct observations, so
    # the pipeline's per-hour rates are computed over real observation-time gaps
    # rather than the ~1-minute browser poll interval (never fabricates a reading).
    df = _collapse_to_observations(df, min_obs_interval_s)
    if history_rows and len(df) > int(history_rows):
        df = df.iloc[-int(history_rows):].reset_index(drop=True)
    df.attrs["n_raw_observations"] = n_raw
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
                history_rows: int = LIVE_HISTORY_ROWS,
                min_obs_interval_s: float = LIVE_MIN_OBS_INTERVAL_S) -> Dict[str, Any]:
    """Assess the latest live observation for one station through Sentinel.

    Returns the pipeline's structured :meth:`SentinelInference.predict_observation`
    result, enriched (never overwritten) with:
      * ``confidence``      -- backward-compatible alias of ``fault_confidence``;
      * ``data_complete``   -- whether the latest reading could be scored;
      * ``baseline_source`` -- 'station_specific' vs 'global_fallback';
      * ``n_history``       -- DISTINCT observations actually scored (after collapsing
                               repeat polls, see :func:`normalize_live_history`);
      * ``n_history_raw``   -- raw poll rows received before collapsing (additive).
    Strictly JSON-safe. An empty/timestamp-less payload returns a safe degraded
    state rather than raising.
    """
    engine = engine or get_default_engine()
    sid = str(station_id) if station_id not in (None, "") else DEFAULT_LIVE_STATION
    df = normalize_live_history(history, sid, latitude, longitude, history_rows,
                                engine.config, min_obs_interval_s)
    if df.empty:
        return _degraded(sid, "no observations with a usable timestamp were provided")

    n_raw = int(df.attrs.get("n_raw_observations", len(df)))
    result = engine.predict_observation(df, station_id=sid)
    # Enrichment only -- pipeline semantics (score/severity/fault_type) are untouched.
    result["confidence"] = result.get("fault_confidence")
    result["data_complete"] = result.get("anomaly_score") is not None
    result["baseline_source"] = baseline_source(sid, engine.baselines)
    result["n_history"] = int(len(df))
    result["n_history_raw"] = n_raw
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
        "n_history_raw": 0,
    }


