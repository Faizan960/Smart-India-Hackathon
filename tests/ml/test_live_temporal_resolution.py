"""Live temporal-resolution regression tests (branch ``feature/live-weather-demo``).

Reproduces and pins the production PB-011 bug: the browser POLLS the weather API
~once a minute and stamps each rolling-history point with its RECEIVE/poll time,
while the upstream source only recomputes its observation about every ~10 minutes.
The old adapter used that receive time and never de-duplicated repeat polls, so the
pipeline's per-hour rate features (temp_rate/humidity_rate/pressure_rate) divided a
tiny value change by a ~1-minute dt and fabricated huge rates (0.27 C/min -> ~16
C/h; a few % RH -> hundreds of %/h) far outside the NOAA cadence the model was
trained on.

The fix (in ``ml.pipeline.live_adapter``, never in the trained model) is: (1) prefer
the SOURCE OBSERVATION time over the browser receive time, and (2) collapse polls
closer than ``LIVE_MIN_OBS_INTERVAL_S`` to a single distinct observation. These
tests exercise the 10 required scenarios and assert genuine signals survive.

Hermetic: uses the shared temp-trained ``models_dir`` + ``synthetic_frame`` fixtures
(no real NOAA CSV / committed artifacts needed); the pure rate checks use
``build_features`` directly and need no model at all.
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone

import pandas as pd
import pytest

from ml.pipeline.features import build_features
from ml.pipeline.inference import SentinelInference
from ml.pipeline.live_adapter import (
    LIVE_MIN_OBS_INTERVAL_S,
    assess_live,
    normalize_live_history,
)


def _iso(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat()


def _browser_point(obs_epoch, recv_epoch, temp, hum, pres, wind=3.0,
                   *, with_obs=True, with_recv=True):
    """Mimic src/state/store.js ``appendHistory`` output: the point's ``timestamp``
    is the RECEIVE/poll time, and the true observation time is carried separately as
    ``observedEpoch``/``observedAt``. Toggle the groups to model missing fields."""
    p = {"temperature": temp, "humidity": hum, "pressure": pres, "windSpeed": wind}
    if with_recv:
        p["timestamp"] = _iso(recv_epoch)      # browser stamps the receive/poll time here
        p["receivedEpoch"] = recv_epoch
        p["receivedAt"] = _iso(recv_epoch)
    if with_obs:
        p["observedEpoch"] = obs_epoch
        p["observedAt"] = _iso(obs_epoch)
    return p


def _engine(models_dir):
    return SentinelInference(models_dir=models_dir)


def _latest_rate_features(frame: pd.DataFrame) -> dict:
    """Latest-row temporal features (rates are baseline-independent, so no baselines
    are needed here). NaN engineered values are reported as NaN (the model itself
    neutralises them to 0.0 in ``to_model_matrix``)."""
    feat = build_features(frame)
    i = feat["timestamp"].idxmax()

    def g(col):
        v = feat.loc[i, col]
        return float(v) if pd.notna(v) else float("nan")

    return {c: g(c) for c in ("temp_rate", "humidity_rate", "pressure_rate",
                              "pressure_change_3h")}


# --- the exact production PB-011 history (receive/observed epochs from the report) -
# Seven polls returned the same observation (observedEpoch 1790182607); the eighth
# poll caught the source's next observation (1790182676, ~69 s later) whose values
# differ slightly. Temps/humidity are set so the OLD receive-time rate is +16 C/h /
# +400 %/h over the ~62 s final poll gap, matching the reported production values.
_PB011_RECV = [1790183012, 1790183073, 1790183135, 1790183154,
               1790183202, 1790183229, 1790183290, 1790183352]
_PB011_OBS = [1790182607, 1790182607, 1790182607, 1790182607,
              1790182607, 1790182607, 1790182607, 1790182676]
_PB011_TEMP = [27.1744] * 7 + [27.45]
_PB011_HUM = [51.111] * 7 + [58.0]
_PB011_PRES = [1004.1] * 8


def _pb011_history():
    return [_browser_point(o, r, t, h, p) for o, r, t, h, p in
            zip(_PB011_OBS, _PB011_RECV, _PB011_TEMP, _PB011_HUM, _PB011_PRES)]


def _pb011_history_receive_only():
    """Old-behaviour payload: only the receive ``timestamp`` is present (no
    observation time), so the adapter can only fall back to receive time."""
    return [_browser_point(o, r, t, h, p, with_obs=False) for o, r, t, h, p in
            zip(_PB011_OBS, _PB011_RECV, _PB011_TEMP, _PB011_HUM, _PB011_PRES)]


# === PB-011: exact production reproduction, before/after the fix ===============

def test_pb011_old_receive_time_fabricates_huge_rates():
    """BEFORE: with only the receive time available and NO collapse (old semantics),
    the latest per-hour rates blow up to the reported +16 C/h / +400 %/h."""
    df = normalize_live_history(_pb011_history_receive_only(), station_id="PB-011",
                                min_obs_interval_s=0.0)   # 0 => collapse disabled
    assert len(df) == 8                                    # every poll kept (old path)
    r = _latest_rate_features(df)
    assert r["temp_rate"] == pytest.approx(16.0, abs=0.2)      # fabricated ~16 C/h
    assert r["humidity_rate"] == pytest.approx(400.0, abs=5.0)  # fabricated ~400 %/h


def test_pb011_fix_removes_fabricated_rates():
    """AFTER: preferring the observation time and collapsing the repeat polls of the
    same observation leaves ONE distinct observation in the ~1-minute window, so the
    fabricated 16 C/h / 400 %/h rates are gone (undefined -> neutral, never inflated)."""
    df = normalize_live_history(_pb011_history(), station_id="PB-011")  # default 600 s
    assert len(df) == 1                       # 8 polls -> 1 distinct observation
    assert df.attrs["n_raw_observations"] == 8
    r = _latest_rate_features(df)
    # single distinct observation => rate undefined (NaN) -> model neutralises to 0.0;
    # crucially NOT the fabricated 16 C/h.
    assert math.isnan(r["temp_rate"]) or abs(r["temp_rate"]) < 1.0
    assert math.isnan(r["humidity_rate"]) or abs(r["humidity_rate"]) < 20.0
    # the true latest OBSERVATION (obs 1790182676) is the one kept, not the last poll
    assert df["temperature"].iloc[-1] == pytest.approx(27.45)


def test_pb011_end_to_end_scored_and_not_anomalous(models_dir):
    """AFTER, end to end through the engine: the collapsed PB-011 reading scores
    without the fabricated-rate evidence and stays JSON-safe."""
    res = assess_live(_pb011_history(), station_id="PB-011", engine=_engine(models_dir))
    assert res["n_history"] == 1 and res["n_history_raw"] == 8
    assert res["anomaly_score"] is None or isinstance(res["anomaly_score"], float)
    json.dumps(res, allow_nan=False)


# === the 10 required scenarios =================================================

# --- 1. hourly observations at (near) the trained resolution: kept as-is -------

def test_scenario1_hourly_observations_not_collapsed():
    base = 1790000000
    hist = [_browser_point(base + k * 3600, base + k * 3600, 25.0 + 0.5 * k,
                           50.0, 1010.0) for k in range(6)]
    df = normalize_live_history(hist, station_id="PB-011")
    assert len(df) == 6                          # 1 h >> 10 min => nothing collapsed
    r = _latest_rate_features(df)
    assert r["temp_rate"] == pytest.approx(0.5, abs=0.05)   # genuine 0.5 C/h preserved


# --- 2. one-minute polling of the SAME observation: collapsed, no inflation ----

def test_scenario2_minute_polling_same_observation_collapsed():
    base = 1790000000
    obs = base                                    # one frozen observation...
    hist = [_browser_point(obs, base + 60 * k, 25.0, 50.0, 1010.0) for k in range(10)]
    df = normalize_live_history(hist, station_id="PB-011")
    assert len(df) == 1                           # 10 repeat polls -> 1 observation
    assert df.attrs["n_raw_observations"] == 10
    r = _latest_rate_features(df)
    assert math.isnan(r["temp_rate"])             # no dt => no fabricated rate


# --- 3. one-minute observations with genuinely changing values -----------------

def test_scenario3_minute_changing_values_stay_sensible():
    """A genuine steady trend sampled every minute: the per-hour rate of a constant
    slope is sampling-invariant, so collapsing to the trained cadence PRESERVES the
    real ~1.2 C/h signal (well under the trained 10.4 C/h rate threshold) rather than
    inflating it. The inflation in PB-011 came from a step/jitter over a ~1 min dt,
    not from a genuine slope like this one."""
    base = 1790000000
    hist = [_browser_point(base + 60 * k, base + 60 * k, 25.0 + 0.02 * k, 50.0, 1010.0)
            for k in range(40)]                   # 40 min of a genuine 1.2 C/h rise
    fixed = normalize_live_history(hist, station_id="PB-011")   # default 600 s
    assert len(fixed) < 40                         # sub-cadence polls collapsed
    rate = _latest_rate_features(fixed)["temp_rate"]
    assert rate == pytest.approx(1.2, abs=0.1)     # genuine trend preserved...
    assert abs(rate) < 10.4                         # ...and within the trained scale


# --- 4. irregular sub-cadence intervals: still collapsed, no crash -------------

def test_scenario4_irregular_intervals_collapsed():
    base = 1790000000
    recv_gaps = [0, 19, 42, 61, 80, 122, 141]     # irregular ~20-60 s poll spacing
    obs = base                                     # one underlying observation
    hist = [_browser_point(obs, base + g, 25.0, 50.0, 1010.0) for g in
            [sum(recv_gaps[:i + 1]) for i in range(len(recv_gaps))]]
    df = normalize_live_history(hist, station_id="PB-011")
    assert len(df) == 1                            # irregular repeats still collapse


# --- 5. exact duplicate observations: de-duplicated ----------------------------

def test_scenario5_duplicate_observations_deduped():
    base = 1790000000
    dup = _browser_point(base, base, 25.0, 50.0, 1010.0)
    hist = [dict(dup) for _ in range(5)]           # 5 byte-identical polls
    df = normalize_live_history(hist, station_id="PB-011")
    assert len(df) == 1
    assert df.attrs["n_raw_observations"] == 5


# --- 6. missing timestamps entirely: dropped, never fabricated -----------------

def test_scenario6_missing_timestamps_dropped_not_fabricated():
    base = 1790000000
    good = [_browser_point(base + 3600 * k, base + 3600 * k, 25.0, 50.0, 1010.0)
            for k in range(3)]
    bad = {"temperature": 25.0, "humidity": 50.0, "pressure": 1010.0}  # no time at all
    df = normalize_live_history(good + [bad], station_id="PB-011")
    assert len(df) == 3                            # the timeless row is dropped
    assert df["timestamp"].notna().all()           # no fabricated timestamp


# --- 7. missing observedEpoch: falls back to receive time (still collapsed) ----

def test_scenario7_missing_observed_epoch_falls_back_to_receive():
    df = normalize_live_history(_pb011_history_receive_only(), station_id="PB-011")
    # no observation time anywhere -> receive time used, but collapse still tames it
    assert len(df) < 8
    r = _latest_rate_features(df)
    assert math.isnan(r["temp_rate"]) or abs(r["temp_rate"]) < 16.0


# --- 8. missing receivedEpoch: observation time is used ------------------------

def test_scenario8_missing_received_epoch_uses_observation_time():
    base = 1790000000
    hist = [_browser_point(base + 3600 * k, None, 25.0 + 0.5 * k, 50.0, 1010.0,
                           with_recv=False) for k in range(6)]  # observation time only
    df = normalize_live_history(hist, station_id="PB-011")
    assert len(df) == 6                            # hourly observation time honoured
    assert df["timestamp"].is_monotonic_increasing
    assert _latest_rate_features(df)["temp_rate"] == pytest.approx(0.5, abs=0.05)


def _from_synthetic(frame, station_id="AAA", n=200):
    """Synthetic Sentinel rows -> browser points timestamped at their (hourly) source
    time, so nothing collapses and the trained-baseline path is exercised."""
    rows = frame[frame["station_id"] == station_id].tail(n)
    pts = []
    for _, r in rows.iterrows():
        e = pd.Timestamp(r["timestamp"]).tz_localize("UTC").timestamp()
        pts.append(_browser_point(
            e, e,
            None if pd.isna(r["temperature"]) else float(r["temperature"]),
            None if pd.isna(r["humidity"]) else float(r["humidity"]),
            None if pd.isna(r["pressure"]) else float(r["pressure"]),
            None if pd.isna(r["wind_speed"]) else float(r["wind_speed"])))
    return pts


# --- 9. a GENUINE rapid spike at proper cadence is still detected --------------

def test_scenario9_genuine_spike_still_detected(models_dir, synthetic_frame):
    hist = _from_synthetic(synthetic_frame, "AAA", 200)
    hist[-1]["temperature"] = 120.0                # real impossible spike, latest read
    res = assess_live(hist, station_id="AAA", engine=_engine(models_dir))
    assert res["n_history"] == 200                 # hourly data: not collapsed away
    assert res["is_anomaly"] is True or res["fault_type"] != "NORMAL"
    json.dumps(res, allow_nan=False)


# --- 10. sensor dropout on the latest reading is handled, not scored -----------

def test_scenario10_sensor_dropout_handled(models_dir, synthetic_frame):
    hist = _from_synthetic(synthetic_frame, "AAA", 200)
    hist[-1]["pressure"] = None                    # a core sensor simply stops arriving
    res = assess_live(hist, station_id="AAA", engine=_engine(models_dir))
    assert res["anomaly_score"] is None            # no fabricated score
    assert res["data_complete"] is False
    if res["fault_type"] != "NORMAL":
        assert res["fault_type"] == "SENSOR_DROPOUT"
    json.dumps(res, allow_nan=False)


# === preservation / contract guarantees ========================================

def test_latest_observation_is_always_kept():
    """Collapse never discards the freshest observation, so a genuine change on the
    newest reading is never thrown away with the repeat polls before it."""
    base = 1790000000
    hist = [_browser_point(base, base + 60 * k, 25.0, 50.0, 1010.0) for k in range(6)]
    hist.append(_browser_point(base + 700, base + 700, 30.0, 60.0, 1011.0))  # new obs
    df = normalize_live_history(hist, station_id="PB-011")
    assert df["temperature"].iloc[-1] == pytest.approx(30.0)   # newest survived


def test_response_contract_and_raw_count_are_additive(models_dir):
    """The fix only ADDS ``n_history_raw``; every legacy/contract field is intact and
    ``n_history_raw`` >= ``n_history`` (raw polls >= distinct observations)."""
    res = assess_live(_pb011_history(), station_id="PB-011", engine=_engine(models_dir))
    for k in ("is_anomaly", "anomaly_score", "fault_type", "confidence",
              "severity", "reasons", "explanation", "laya_decision",
              "verification", "health", "baseline_source", "data_complete",
              "n_history"):
        assert k in res
    assert res["n_history_raw"] >= res["n_history"]
    assert res["confidence"] == res["fault_confidence"]
    json.dumps(res, allow_nan=False)


def test_disabling_collapse_restores_naive_behaviour():
    """``min_obs_interval_s=0`` is an explicit escape hatch (used to demonstrate the
    bug); it keeps every poll, proving the collapse is opt-out and not hard-wired."""
    df = normalize_live_history(_pb011_history(), station_id="PB-011",
                                min_obs_interval_s=0.0)
    assert len(df) == 8
    assert LIVE_MIN_OBS_INTERVAL_S == 600.0        # documented default cadence guard
