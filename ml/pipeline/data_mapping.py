"""Configurable NOAA -> standard-schema column mapping (spec sections 2 & 3).

Keeps provider-specific column names and NOAA composite-field parsing OUT of the
ML code. Edit ``data_config.yaml`` to ingest a different provider without
touching any modelling module.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
import yaml

DEFAULT_MAPPING_PATH = Path(__file__).with_name("data_config.yaml")


@dataclass
class CompositeField:
    target: str
    column: str
    part: int
    scale: float
    missing: tuple


@dataclass
class DataMapping:
    dataset: Dict[str, Any]
    direct: Dict[str, str]
    composite: List[CompositeField]
    humidity_method: Optional[str]
    humidity_direct_column: Optional[str]
    accept_report_types: Optional[List[str]]
    min_rows_per_station: int = 500
    log: List[str] = field(default_factory=list)


def load_mapping(path: str | Path = DEFAULT_MAPPING_PATH) -> DataMapping:
    with open(path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    composite = [
        CompositeField(
            target=name,
            column=spec["column"],
            part=int(spec.get("part", 0)),
            scale=float(spec.get("scale", 1.0)),
            missing=tuple(spec.get("missing", [])),
        )
        for name, spec in (cfg.get("composite") or {}).items()
    ]
    humidity = cfg.get("humidity") or {}
    qc = cfg.get("quality_control") or {}
    return DataMapping(
        dataset=cfg.get("dataset") or {},
        direct=cfg.get("direct") or {},
        composite=composite,
        humidity_method=humidity.get("method"),
        humidity_direct_column=humidity.get("direct_column"),
        accept_report_types=qc.get("accept_report_types"),
        min_rows_per_station=int(qc.get("min_rows_per_station", 500)),
    )


def _parse_composite(series: pd.Series, spec: CompositeField) -> pd.Series:
    """Extract spec.part from a NOAA composite string, scale it, drop sentinels."""

    def one(value: Any):
        if not isinstance(value, str) or value == "":
            return np.nan
        parts = value.split(",")
        if spec.part >= len(parts):
            return np.nan
        token = parts[spec.part].strip()
        try:
            iv = int(token)
        except ValueError:
            try:
                return float(token) / spec.scale
            except ValueError:
                return np.nan
        if iv in spec.missing:
            return np.nan
        return iv / spec.scale

    return series.map(one)


def apply_mapping(raw: pd.DataFrame, mapping: DataMapping) -> pd.DataFrame:
    """Extract standard + metadata columns from a raw NOAA dataframe.

    Humidity is NOT derived here (the loader does that via physics, per the
    configured method). Missing source columns are logged, not fatal.
    """
    out = pd.DataFrame(index=raw.index)
    log: List[str] = []

    for target, src in mapping.direct.items():
        if src in raw.columns:
            out[target] = raw[src]
        else:
            out[target] = np.nan
            log.append(f"direct source column '{src}' (-> '{target}') not found")

    for spec in mapping.composite:
        if spec.column in raw.columns:
            out[spec.target] = _parse_composite(raw[spec.column], spec)
        else:
            out[spec.target] = np.nan
            log.append(f"composite source column '{spec.column}' (-> '{spec.target}') not found")

    mapping.log = log
    return out
