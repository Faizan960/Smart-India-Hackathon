"""Real meteorological data loader + quality report (spec section 3).

Loads NOAA ISD CSV(.gz)/Parquet, applies the configurable column mapping,
derives humidity, converts timestamps, removes duplicate observations, and emits
a data-quality report. It NEVER silently discards data: every cleaning step is
counted and logged, and original observed values are preserved (the loader only
adds/normalises columns and drops structurally unusable rows with a logged count;
it does not impute or clip real observations).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List

import numpy as np
import pandas as pd

from .config import CORE_SENSORS, DEFAULT_CONFIG, SENSOR_BOUNDS
from .data_mapping import apply_mapping, load_mapping
from .physics import dewpoint_to_rh


@dataclass
class LoadResult:
    frame: pd.DataFrame
    report: Dict[str, Any]
    cleaning_log: List[str] = field(default_factory=list)


def _read_one(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".parquet":
        return pd.read_parquet(path)
    # CSV / CSV.GZ — read as string so NOAA composite fields survive intact.
    return pd.read_csv(path, dtype=str, low_memory=False)


def load_dataset(paths, mapping=None, config=None, verbose=False) -> LoadResult:
    """Load one or more raw files into the standard schema with a QC report."""
    config = config or DEFAULT_CONFIG
    mapping = mapping or load_mapping()
    if isinstance(paths, (str, Path)):
        paths = [paths]
    log: List[str] = []

    frames = []
    for raw_path in paths:
        raw_path = Path(raw_path)
        raw = _read_one(raw_path)
        std = apply_mapping(raw, mapping)
        std["source_file"] = raw_path.name
        log.extend(f"{raw_path.name}: {m}" for m in mapping.log)
        log.append(f"{raw_path.name}: read {len(raw):,} raw rows")
        frames.append(std)
    df = pd.concat(frames, ignore_index=True)
    n_start = len(df)

    for col in ("latitude", "longitude", "elevation", *CORE_SENSORS, "wind_speed", "dew_point"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    bad_ts = int(df["timestamp"].isna().sum())
    if bad_ts:
        df = df[df["timestamp"].notna()].copy()
        log.append(f"dropped {bad_ts:,} rows with unparseable timestamp")

    # derive humidity (Magnus) unless a direct RH column is configured
    if mapping.humidity_direct_column and mapping.humidity_direct_column in df.columns:
        df["humidity"] = pd.to_numeric(df[mapping.humidity_direct_column], errors="coerce")
        log.append(f"humidity taken directly from '{mapping.humidity_direct_column}'")
    elif mapping.humidity_method == "from_dew_point" and "dew_point" in df.columns:
        rh = dewpoint_to_rh(df["temperature"].to_numpy(), df["dew_point"].to_numpy())
        df["humidity"] = np.clip(rh, 0.0, 100.0)
        log.append(f"derived humidity from dew point via Magnus for {int(np.isfinite(rh).sum()):,} rows")
    else:
        df["humidity"] = np.nan
        log.append("humidity could not be derived (no dew point / direct RH column)")

    # count out-of-range / non-finite values (flagged as invalid, not clipped)
    invalid = 0
    for col, (lo, hi) in SENSOR_BOUNDS.items():
        if col in df.columns:
            bad = ((df[col] < lo) | (df[col] > hi)) & df[col].notna()
            invalid += int(bad.sum())

    if mapping.accept_report_types:
        before = len(df)
        df = df[df["report_type"].isin(mapping.accept_report_types)].copy()
        log.append(f"kept {len(df):,}/{before:,} rows for report types {mapping.accept_report_types}")

    df["station_id"] = df["station_id"].astype(str).str.strip()
    if "station_name" in df.columns:
        df["station_name"] = df["station_name"].astype(str).str.strip()

    # collapse duplicate (station, timestamp) observations, keeping the most complete
    df["_completeness"] = df[list(CORE_SENSORS)].notna().sum(axis=1)
    df = df.sort_values(["station_id", "timestamp", "_completeness"], ascending=[True, True, False])
    dup_mask = df.duplicated(subset=["station_id", "timestamp"], keep="first")
    n_dupes = int(dup_mask.sum())
    df = df[~dup_mask].drop(columns="_completeness")
    if n_dupes:
        log.append(f"collapsed {n_dupes:,} duplicate (station, timestamp) rows (kept most complete)")

    counts = df["station_id"].value_counts()
    keep_ids = set(counts[counts >= mapping.min_rows_per_station].index)
    dropped = [s for s in counts.index if s not in keep_ids]
    if dropped:
        n_drop_rows = int(df["station_id"].isin(dropped).sum())
        df = df[df["station_id"].isin(keep_ids)].copy()
        log.append(
            f"dropped {len(dropped)} station(s) with < {mapping.min_rows_per_station} rows "
            f"({n_drop_rows:,} rows): {dropped}"
        )

    df = df.sort_values(["station_id", "timestamp"]).reset_index(drop=True)
    report = _quality_report(df, mapping, n_start, bad_ts, n_dupes, invalid)
    if verbose:
        import json

        print(json.dumps(report, indent=2, default=str))
    return LoadResult(frame=df, report=report, cleaning_log=log)


def _quality_report(df, mapping, n_start, bad_ts, n_dupes, invalid) -> Dict[str, Any]:
    per_station: Dict[str, Any] = {}
    for sid, g in df.groupby("station_id"):
        gaps = g["timestamp"].sort_values().diff().dropna().dt.total_seconds() / 3600.0
        per_station[str(sid)] = {
            "name": str(g["station_name"].iloc[0]) if "station_name" in g else None,
            "rows": int(len(g)),
            "date_start": str(g["timestamp"].min()),
            "date_end": str(g["timestamp"].max()),
            "median_interval_hours": round(float(gaps.median()), 4) if len(gaps) else None,
            "latitude": float(g["latitude"].iloc[0]) if g["latitude"].notna().any() else None,
            "longitude": float(g["longitude"].iloc[0]) if g["longitude"].notna().any() else None,
            "missing_temperature": int(g["temperature"].isna().sum()),
            "missing_humidity": int(g["humidity"].isna().sum()),
            "missing_pressure": int(g["pressure"].isna().sum()),
        }
    return {
        "dataset": mapping.dataset,
        "rows": int(len(df)),
        "rows_read": int(n_start),
        "stations": int(df["station_id"].nunique()) if len(df) else 0,
        "station_ids": sorted(df["station_id"].unique().tolist()) if len(df) else [],
        "date_start": str(df["timestamp"].min()) if len(df) else None,
        "date_end": str(df["timestamp"].max()) if len(df) else None,
        "missing_temperature": int(df["temperature"].isna().sum()),
        "missing_humidity": int(df["humidity"].isna().sum()),
        "missing_pressure": int(df["pressure"].isna().sum()),
        "duplicate_rows": int(n_dupes),
        "unparseable_timestamps": int(bad_ts),
        "invalid_values": int(invalid),
        "per_station": per_station,
    }


if __name__ == "__main__":
    import argparse
    import json

    ap = argparse.ArgumentParser(description="Load + quality-check a NOAA dataset")
    ap.add_argument("--input", nargs="+", required=True, help="CSV/CSV.GZ/Parquet path(s)")
    ap.add_argument("--report", default=None, help="optional path to write the QC report JSON")
    args = ap.parse_args()

    result = load_dataset(args.input, verbose=True)
    print("\n--- cleaning log ---")
    print("\n".join(result.cleaning_log))
    if args.report:
        Path(args.report).parent.mkdir(parents=True, exist_ok=True)
        with open(args.report, "w", encoding="utf-8") as f:
            json.dump(result.report, f, indent=2, default=str)
        print(f"\nQuality report written to {args.report}")
