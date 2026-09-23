"""Thermodynamic features (spec section 9).

Magnus/Tetens formulation. All functions are vectorised and NaN-safe. These
produce SUPPORTING EVIDENCE (a thermodynamic consistency score and an
inconsistency flag) — not verdicts. Genuine near-saturation (fog, monsoon) is
NOT treated as impossible; only clear violations degrade the consistency score.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# Magnus coefficients over water (valid roughly -40..+50 C).
_A = 17.625
_B = 243.04  # degrees C


def saturation_vapor_pressure(temp_c):
    """Saturation vapour pressure es(T) in hPa. es(0 C) = 6.1094 hPa."""
    t = np.asarray(temp_c, dtype=float)
    return 6.1094 * np.exp(_A * t / (_B + t))


def actual_vapor_pressure(temp_c, rh_pct):
    """Actual vapour pressure e = RH/100 * es(T), in hPa."""
    rh = np.asarray(rh_pct, dtype=float)
    return rh / 100.0 * saturation_vapor_pressure(temp_c)


def vapor_pressure_deficit(temp_c, rh_pct):
    """Vapour pressure deficit VPD = es - e, in hPa (>= 0 physically)."""
    es = saturation_vapor_pressure(temp_c)
    rh = np.asarray(rh_pct, dtype=float)
    return es * (1.0 - rh / 100.0)


def dewpoint_to_rh(temp_c, dew_c):
    """Relative humidity (%) from temperature and dew point via Magnus.

    Values are returned un-clipped so upstream QC can see supersaturation as
    evidence; callers that need a display value should clip to [0, 100].
    """
    t = np.asarray(temp_c, dtype=float)
    td = np.asarray(dew_c, dtype=float)
    gamma_t = _A * t / (_B + t)
    gamma_td = _A * td / (_B + td)
    return 100.0 * np.exp(gamma_td - gamma_t)


def rh_to_dewpoint(temp_c, rh_pct):
    """Dew point (deg C) implied by temperature and RH via Magnus."""
    t = np.asarray(temp_c, dtype=float)
    rh = np.clip(np.asarray(rh_pct, dtype=float), 1e-3, 200.0)
    gamma = np.log(rh / 100.0) + _A * t / (_B + t)
    return _B * gamma / (_A - gamma)


def thermodynamic_features(df: pd.DataFrame) -> pd.DataFrame:
    """Append es_hpa, vpd, dew_point_calc, thermo_consistency,
    thermo_inconsistency_score (0..1, higher = worse) and a thermo_inconsistency
    boolean. Rows missing temperature or humidity get NaN/False."""
    out = df.copy()
    t = out["temperature"].astype(float)
    rh = out["humidity"].astype(float)
    valid = t.notna() & rh.notna()

    out["es_hpa"] = pd.Series(saturation_vapor_pressure(t), index=out.index).where(t.notna())
    out["vpd"] = pd.Series(vapor_pressure_deficit(t, rh), index=out.index).where(valid)
    out["dew_point_calc"] = pd.Series(rh_to_dewpoint(t, rh), index=out.index).where(valid)

    # Physical checks: RH should not exceed ~100% and dew point should not exceed
    # air temperature. Small margins are tolerated (measurement noise near
    # saturation is common and real).
    rh_excess = (rh - 100.0).clip(lower=0)
    dp_excess = (out["dew_point_calc"] - t).clip(lower=0)
    consistency = 1.0 / (1.0 + 0.2 * rh_excess.fillna(0) + 0.5 * dp_excess.fillna(0))

    out["thermo_consistency"] = consistency.where(valid)
    out["thermo_inconsistency_score"] = (1.0 - consistency).clip(0, 1).where(valid)
    out["thermo_inconsistency"] = ((rh_excess > 2.0) | (dp_excess > 0.5)).where(valid, False)
    return out
