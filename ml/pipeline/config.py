"""Central, overridable configuration for the AWS Sentinel real-data ML pipeline.

Every tunable number lives here so the ML modules never hard-code magic values.
Override by constructing ``PipelineConfig(**overrides)``; the NOAA column mapping
is configured separately in ``data_config.yaml`` (see ``data_mapping.py``).

This package is fully isolated: nothing under ``ml/pipeline`` is imported by the
existing ``api/`` routes, ``ml/inference.py``, or ``ml/classifier.py``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Tuple

# Repo root: ml/pipeline/config.py -> ml/pipeline -> ml -> <repo>
REPO_ROOT = Path(__file__).resolve().parents[2]

# --- canonical internal schema ------------------------------------------------
CORE_SENSORS: Tuple[str, ...] = ("temperature", "humidity", "pressure")
# wind_speed is auxiliary: not a core anomaly variable, but carried through so the
# existing ml/laya_base state contract (which requires it) can be satisfied.
AUX_SENSORS: Tuple[str, ...] = ("wind_speed",)
STANDARD_COLUMNS: Tuple[str, ...] = (
    "timestamp", "station_id", "latitude", "longitude", *CORE_SENSORS, *AUX_SENSORS,
)

# --- fault taxonomy (spec section 13) -----------------------------------------
# General, principled fault types produced by ml/pipeline/classifier.py.
FAULT_TYPES: Tuple[str, ...] = (
    "NORMAL",
    "SENSOR_DROPOUT",
    "SENSOR_FREEZE",
    "TRANSIENT_SPIKE",
    "CALIBRATION_DRIFT",
    "PHYSICAL_INCONSISTENCY",
    "MULTIVARIATE_ANOMALY",
    "UNKNOWN_ANOMALY",
)

# Physically plausible bounds per sensor (hard range check only — NOT used to call
# genuine extreme weather a fault). Mid-latitude Indian surface station envelope.
SENSOR_BOUNDS: Dict[str, Tuple[float, float]] = {
    "temperature": (-30.0, 60.0),
    "humidity": (0.0, 100.0),
    "pressure": (850.0, 1090.0),
    "wind_speed": (0.0, 120.0),
}

# Sensor resolution / noise floor: two readings closer than this are "identical"
# for freeze detection (avoids requiring exact variance == 0).
SENSOR_RESOLUTION: Dict[str, float] = {
    "temperature": 0.1,
    "humidity": 1.0,
    "pressure": 0.1,
    "wind_speed": 0.1,
}


@dataclass
class PipelineConfig:
    """All pipeline knobs. Serializable via ``dataclasses.asdict``."""

    # paths -------------------------------------------------------------------
    models_dir: Path = REPO_ROOT / "models" / "sentinel"
    reports_dir: Path = REPO_ROOT / "reports"
    processed_dir: Path = REPO_ROOT / "data" / "processed"
    injected_dir: Path = REPO_ROOT / "data" / "injected"

    # chronological split (spec section 4) — no random shuffling ---------------
    train_frac: float = 0.70
    val_frac: float = 0.15
    # test_frac is the remainder (0.15)
    explicit_split: Dict[str, Tuple[str, str]] | None = None  # {"train": (start,end), ...}

    # diurnal baseline (spec section 6) ---------------------------------------
    baseline_keys: Tuple[str, ...] = ("station_id", "month", "hour")
    baseline_min_samples: int = 5  # below this, fall back to coarser grouping
    zscore_clip: float = 12.0  # clip robust z-scores to a sane range

    # temporal / rolling features (spec section 7) — TIME-based, interval-aware
    rolling_windows: Tuple[str, ...] = ("3h", "24h")
    min_periods_frac: float = 0.3  # min fraction of expected samples in a window

    # rate-of-change (spec section 8) — thresholds are LEARNED, these are the
    # percentiles used to derive per-station rate thresholds from training data
    rate_percentiles: Tuple[float, ...] = (99.0, 99.9)

    # pressure tendency (spec section 10) -------------------------------------
    pressure_tendency_windows: Tuple[str, ...] = ("3h",)

    # isolation forest (spec section 11) --------------------------------------
    if_n_estimators: int = 200
    if_contamination: str | float = "auto"
    if_max_samples: str | int = "auto"
    if_random_state: int = 42
    # score calibration: raw IF scores -> anomaly_score in [0,1] via a logistic
    # anchored on the TRAINING score distribution (no fabricated thresholds).
    calib_center_pct: float = 95.0  # training percentile mapped to score 0.5
    calib_upper_pct: float = 99.7   # training percentile used to set the slope

    # freeze / dropout / spike / drift (spec section 13) ----------------------
    freeze_min_run: int = 5          # consecutive near-identical readings (legacy reference)
    freeze_min_hours: float = 6.0    # wall-clock span of a flat run to suspect a freeze
    freeze_long_hours: float = 12.0  # a flat run this long is suspicious on its own
    dropout_gap_factor: float = 3.0  # gap > factor * typical interval => dropout gap
    spike_recovery_window: str = "3h"
    drift_cusum_k: float = 0.5       # CUSUM slack (in robust-sigma units)
    drift_cusum_h: float = 5.0       # CUSUM decision threshold

    # spatial consistency (spec section 15) -----------------------------------
    spatial_radius_km: float = 300.0
    spatial_min_neighbors: int = 1

    # severity thresholds (spec section 19) — anomaly_score in [0,1] ----------
    severity_warning_score: float = 0.55
    severity_critical_score: float = 0.80

    # sensor health (spec section 22) — rolling window + rate thresholds ------
    health_window: str = "24h"
    health_watch_anomaly_rate: float = 0.05
    health_degraded_anomaly_rate: float = 0.15
    health_critical_anomaly_rate: float = 0.35

    # imputation (spec section 21) — only SHORT interior gaps are filled, and
    # every filled value is flagged so it is never presented as a real reading.
    impute_max_gap_hours: float = 6.0

    # explainability (spec section 16) ----------------------------------------
    shap_top_features: int = 3

    # feature list actually fed to the Isolation Forest. Kept explicit so the
    # model and inference always agree, and so redundant features can be dropped.
    if_features: Tuple[str, ...] = (
        "temperature", "humidity", "pressure",
        "temp_dev_baseline", "humidity_dev_baseline", "pressure_dev_baseline",
        "temp_rate", "humidity_rate", "pressure_rate",
        "temp_roll_std_3h", "pressure_roll_std_3h",
        "vpd", "thermo_inconsistency_score",
        "pressure_change_3h",
    )

    def ensure_dirs(self) -> None:
        for d in (self.models_dir, self.reports_dir, self.processed_dir, self.injected_dir):
            Path(d).mkdir(parents=True, exist_ok=True)


DEFAULT_CONFIG = PipelineConfig()
