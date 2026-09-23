"""Shared fixtures for the AWS Sentinel pipeline tests.

These tests are HERMETIC: they never touch the real NOAA CSV or the committed
``models/sentinel`` artifacts. Instead a small, physically-consistent, seeded
synthetic multi-station frame is generated in-memory and a tiny Isolation Forest
is trained on it inside a temp directory. That keeps the suite fast, deterministic
and independent of any large data / model files (which are git-ignored).
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# Put the repo root on sys.path so ``import ml.pipeline...`` resolves regardless
# of where pytest is invoked from (ml is a namespace package at the repo root).
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _make_station(sid: str, lat: float, lon: float, start: str,
                  periods: int, freq_h: int, seed: int) -> pd.DataFrame:
    """A single station's physically-consistent diurnal series.

    Humidity is anti-correlated with temperature and kept below saturation, so a
    dew point implied by (T, RH) stays under the air temperature -> the clean data
    carries no thermodynamic inconsistency and reads as NORMAL to the detector.
    """
    rng = np.random.default_rng(seed)
    ts = pd.date_range(start, periods=periods, freq=f"{freq_h}h")
    hours = ts.hour + ts.minute / 60.0
    doy = ts.dayofyear.to_numpy(dtype=float)
    temp = (20.0
            + 8.0 * np.sin(2 * np.pi * (hours - 9) / 24.0)
            + 6.0 * np.sin(2 * np.pi * (doy - 80) / 365.0)
            + rng.normal(0.0, 0.7, periods))
    hum = np.clip(70.0 - 1.5 * (temp - 20.0) + rng.normal(0.0, 4.0, periods), 15.0, 98.0)
    press = 1011.0 + 3.0 * np.sin(2 * np.pi * doy / 365.0) + rng.normal(0.0, 0.8, periods)
    wind = np.clip(rng.normal(3.0, 1.2, periods), 0.0, None)
    return pd.DataFrame({
        "timestamp": ts,
        "station_id": sid,
        "latitude": lat,
        "longitude": lon,
        "temperature": np.round(temp, 1),
        "humidity": np.round(hum, 0),
        "pressure": np.round(press, 1),
        "wind_speed": np.round(wind, 1),
    })


@pytest.fixture(scope="session")
def synthetic_frame() -> pd.DataFrame:
    """Two stations with different cadences (hourly + 3-hourly) in one frame."""
    a = _make_station("AAA", 28.5, 77.1, "2021-01-01", periods=2400, freq_h=1, seed=1)
    b = _make_station("BBB", 19.1, 72.9, "2021-01-01", periods=900, freq_h=3, seed=2)
    df = pd.concat([a, b], ignore_index=True)
    return df.sort_values(["station_id", "timestamp"]).reset_index(drop=True)


@pytest.fixture(scope="session")
def split(synthetic_frame):
    from ml.pipeline.preprocessing import chronological_split
    return chronological_split(synthetic_frame)


@pytest.fixture(scope="session")
def baselines(split):
    from ml.pipeline.baseline import compute_baselines
    train, _val, _test = split
    return compute_baselines(train)


@pytest.fixture(scope="session")
def feat_train(split, baselines):
    from ml.pipeline.features import build_features
    train, _val, _test = split
    return build_features(train, baselines=baselines)


@pytest.fixture(scope="session")
def detector(feat_train):
    from ml.pipeline.anomaly_detector import AnomalyDetector
    return AnomalyDetector().fit(feat_train)


@pytest.fixture(scope="session")
def thresholds(feat_train):
    from ml.pipeline.classifier import fit_thresholds
    return fit_thresholds(feat_train)


@pytest.fixture(scope="session")
def models_dir(tmp_path_factory, detector, thresholds, baselines):
    """A temp models dir holding saved detector + thresholds + baselines, so the
    end-to-end SentinelInference can be exercised without the committed artifacts."""
    from ml.pipeline.baseline import save_baselines
    from ml.pipeline.classifier import save_thresholds
    d = tmp_path_factory.mktemp("sentinel_models")
    detector.save(d)
    save_thresholds(thresholds, d)
    save_baselines(baselines, d / "baselines.json")
    return d


@pytest.fixture(scope="session")
def feat_all(synthetic_frame, baselines):
    from ml.pipeline.features import build_features
    return build_features(synthetic_frame, baselines=baselines)


@pytest.fixture(scope="session")
def anom_all(feat_all, detector):
    return detector.score(feat_all)


@pytest.fixture(scope="session")
def cls_all(feat_all, anom_all, thresholds):
    from ml.pipeline.classifier import classify_faults
    return classify_faults(feat_all, anom_all, thresholds)
