"""Inspectable evidence fusion (spec sections 17 & 35).

Combines the pipeline's independent signals for each observation — the calibrated
Isolation Forest anomaly score, the classifier's principled fault type, the raw
structural signatures, and (optionally) the SHAP explanation — into a single
transparent assessment. This is deliberately NOT an opaque weighted average: the
fused status is a small set of inspectable rules and every assessment carries the
explicit list of reasons that produced it, so a reviewer can audit each call.

Structural faults (a data dropout, a stuck sensor, a physics violation) are
treated as meaningful in their own right even when the statistical score is low
or undefined — but nothing here upgrades a bare anomaly score into a claim that a
sensor has failed (spec section 35). Wording stays hedged.
"""
from __future__ import annotations

from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from .config import DEFAULT_CONFIG

# structural / dynamic signature column -> hedged human reason
_SIG_REASON = {
    "sig_dropout": "expected sensor missing or an over-long reporting gap (probable data dropout)",
    "sig_freeze": "a flat reading run beyond the freeze duration threshold (possible stuck sensor)",
    "sig_physical": "relative humidity / dew-point thermodynamically inconsistent (possible RH fault)",
    "sig_spike": "a large rate-of-change spike with rapid reversal (possible transient spike)",
    "sig_drift": "a sustained one-sided deviation from baseline (possible calibration drift)",
}
_STRUCTURAL = ("sig_dropout", "sig_freeze", "sig_physical")

def _severity(score: float, fault_type: str, structural: bool, config) -> str:
    """Map evidence to NORMAL / WARNING / CRITICAL using ONLY config thresholds.

    A fired structural signature is meaningful even when the statistical score is
    low or NaN (e.g. a dropout has no score), so it floors severity at WARNING.
    """
    if np.isfinite(score):
        if score >= config.severity_critical_score:
            return "CRITICAL"
        if score >= config.severity_warning_score:
            return "WARNING"
    if structural and fault_type != "NORMAL":
        return "WARNING"
    return "NORMAL"


def fuse_observation(*, anomaly_score: float, is_anomaly: bool, core_complete: bool,
                     fault_type: str, fault_confidence: float, legacy_label: str,
                     signatures: Dict[str, bool], explanation: Optional[Dict] = None,
                     config=None) -> Dict:
    """Fuse one observation's signals into an inspectable assessment dict."""
    config = config or DEFAULT_CONFIG
    structural = any(bool(signatures.get(k)) for k in _STRUCTURAL)
    severity = _severity(anomaly_score, fault_type, structural, config)

    # Reasons are surfaced only for a non-normal assessment, and dynamic
    # explanations (spike/drift, SHAP) only when the detector actually flagged the
    # point — so a NORMAL verdict never lists a phantom fault (spec section 35).
    reasons: List[str] = []
    if severity != "NORMAL":
        if fault_type != "NORMAL":
            reasons.append(f"classifier: {fault_type.replace('_', ' ').lower()} "
                           f"(confidence {fault_confidence:.2f})")
        for key in ("sig_dropout", "sig_freeze", "sig_physical"):
            if signatures.get(key):
                reasons.append(_SIG_REASON[key])
        if is_anomaly:
            for key in ("sig_spike", "sig_drift"):
                if signatures.get(key):
                    reasons.append(_SIG_REASON[key])
            if explanation and explanation.get("top_features"):
                reasons.append("detector evidence: "
                               + "; ".join(f["text"] for f in explanation["top_features"]))
    reasons = reasons or ["no anomalous evidence"]

    # fault_present in [0,1] — transparent, not an opaque blend. A data gap is
    # itself a probable fault even though the statistical score is undefined.
    if not core_complete and signatures.get("sig_dropout"):
        fault_present = 0.8
    elif np.isfinite(anomaly_score):
        fault_present = float(anomaly_score)
    else:
        fault_present = 0.0

    # deterministic status mirroring the ml/laya_base verification doctrine:
    # a typed fault is CONFIRMED only when an independent signal agrees.
    if severity == "NORMAL":
        status = "NORMAL"
    elif is_anomaly or structural:
        status = "CONFIRMED"
    else:
        status = "UNVERIFIED"

    return {
        "severity": severity,
        "fused_status": status,
        "fault_type": fault_type,
        "fault_confidence": round(float(fault_confidence), 4),
        "legacy_label": legacy_label,
        "anomaly_score": None if not np.isfinite(anomaly_score) else round(float(anomaly_score), 4),
        "fault_present": round(float(fault_present), 4),
        "structural_fault": bool(structural),
        "reasons": reasons or ["no anomalous evidence"],
    }


def fuse_frame(feat_df: pd.DataFrame, anomaly_df: pd.DataFrame, class_df: pd.DataFrame,
               explanations: Optional[List[Dict]] = None, config=None) -> pd.DataFrame:
    """Vectorised wrapper: one fused assessment row per observation.

    All three inputs are indexed on ``feat_df.index`` (as produced by the detector
    and classifier), so they are aligned by reindexing rather than by position.
    """
    config = config or DEFAULT_CONFIG
    idx = feat_df.index
    score = anomaly_df["anomaly_score"].reindex(idx).to_numpy(dtype=float)
    is_anom = anomaly_df["is_anomaly"].reindex(idx).fillna(False).to_numpy(dtype=bool)
    complete = anomaly_df["core_complete"].reindex(idx).fillna(False).to_numpy(dtype=bool)
    ftype = class_df["fault_type"].reindex(idx).to_numpy()
    fconf = class_df["fault_confidence"].reindex(idx).to_numpy(dtype=float)
    legacy = class_df["legacy_label"].reindex(idx).to_numpy()
    sig_cols = [c for c in ("sig_dropout", "sig_freeze", "sig_spike", "sig_drift", "sig_physical")
                if c in class_df.columns]
    sigs = {c: class_df[c].reindex(idx).fillna(False).to_numpy(dtype=bool) for c in sig_cols}

    rows: List[Dict] = []
    for i in range(len(idx)):
        signatures = {c: bool(sigs[c][i]) for c in sig_cols}
        expl = explanations[i] if explanations is not None and i < len(explanations) else None
        rows.append(fuse_observation(
            anomaly_score=score[i], is_anomaly=bool(is_anom[i]), core_complete=bool(complete[i]),
            fault_type=str(ftype[i]),
            fault_confidence=float(fconf[i]) if np.isfinite(fconf[i]) else 0.0,
            legacy_label=str(legacy[i]), signatures=signatures, explanation=expl, config=config))
    return pd.DataFrame(rows, index=idx)
