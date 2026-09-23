"""Bridge from the AWS Sentinel pipeline to the EXISTING Laya typed contract
(spec section 18).

This adapter does NOT invent a new Laya API and does NOT replace the adapter in
``ml/laya_base/``. It reuses that package's own primitives — the typed
``fault_type`` **choice** and ``fault_present`` **noul** questions, the
deterministic state builder, the ``LayaDecision`` dataclass and the Laya ->
Isolation-Forest verification doctrine — and simply lets this pipeline speak the
same vocabulary.

Two paths are offered:
  * ``run_laya`` delegates to the real ``LayaDecisionEngine`` when a Laya
    checkpoint is installed (the genuine learned-decision path); it raises a clear
    error rather than fabricating a decision when Laya is absent.
  * ``pipeline_decision`` emits a ``LayaDecision``-shaped typed decision derived
    from THIS pipeline's evidence. Its ``raw`` payload is tagged
    ``source='aws_sentinel_pipeline'`` so it is never misrepresented as the Laya
    model's output (spec section 35).

Both are verified against the independent Isolation Forest exactly as
``ml/laya_base/verification.py`` prescribes — the two signals are never averaged.
"""
from __future__ import annotations

import math
from typing import Any, Dict, Optional

import pandas as pd

from ml.laya_base.config import FAULT_LABELS, LayaConfig
from ml.laya_base.decision import LayaDecision, LayaDecisionEngine
from ml.laya_base.questions import fault_questions
from ml.laya_base.state import REQUIRED_COLUMNS, telemetry_to_state

def _with_required_columns(df: pd.DataFrame) -> pd.DataFrame:
    """wind_speed is auxiliary here but required by the Laya state contract; add it
    as NaN (rendered null) when absent so the existing builder is satisfied."""
    out = df.copy()
    for col in REQUIRED_COLUMNS:
        if col not in out.columns:
            out[col] = float("nan")
    return out


def to_laya_state(df_history: pd.DataFrame, laya_config: Optional[LayaConfig] = None) -> dict:
    """Shape a canonical observation frame into the EXISTING Laya state dict."""
    laya_config = laya_config or LayaConfig()
    return telemetry_to_state(_with_required_columns(df_history), laya_config.history_rows)


def laya_questions(laya_config: Optional[LayaConfig] = None) -> dict:
    """The EXISTING typed question schema (choice + noul), unchanged."""
    laya_config = laya_config or LayaConfig()
    return fault_questions(laya_config.labels)


def pipeline_decision(assessment: Dict, laya_config: Optional[LayaConfig] = None) -> LayaDecision:
    """Build a typed ``LayaDecision`` from this pipeline's fused evidence.

    The pipeline's ``legacy_label`` is already in the Laya ``FAULT_LABELS``
    vocabulary, so it becomes the typed **choice**; ``fault_confidence`` is the
    choice confidence and ``fault_present`` is the **noul**. Tagged pipeline-sourced
    so it is never presented as the Laya model's own decision.
    """
    label = str(assessment.get("legacy_label", "NORMAL"))
    if label not in FAULT_LABELS:
        label = "UNKNOWN_ANOMALY" if assessment.get("fault_type", "NORMAL") != "NORMAL" else "NORMAL"
    return LayaDecision(
        decision=label,
        confidence=float(assessment.get("fault_confidence", 0.0) or 0.0),
        fault_present=float(assessment.get("fault_present", 0.0) or 0.0),
        raw={
            "source": "aws_sentinel_pipeline",
            "note": "typed decision derived from pipeline evidence, not the Laya model",
            "fault_type": assessment.get("fault_type"),
            "severity": assessment.get("severity"),
            "reasons": assessment.get("reasons"),
        },
    )


def _json_safe_score(value: Any) -> Optional[float]:
    """Coerce a numeric anomaly score to a strictly JSON-safe value.

    Strict JSON has no ``NaN``/``Infinity`` tokens, so the public inference
    contract reports ``None`` (null) for an unavailable score rather than a
    special float. A finite value passes through verbatim — it is never rounded
    or blended (spec section 18) — and ``None``/``NaN``/``inf`` all become ``None``.
    """
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def fuse_with_detector(decision: LayaDecision, anomaly_result: Dict[str, Any]) -> Dict[str, Any]:
    """Verify a typed decision against the independent Isolation Forest.

    Mirrors ``ml/laya_base/verification.verify_laya_decision`` exactly: the two
    signals are NEVER averaged. The detector only confirms (or leaves unverified) a
    non-normal typed decision; a NORMAL decision stays NORMAL.
    """
    is_anomaly = bool(anomaly_result.get("is_anomaly", False))
    if decision.decision == "NORMAL":
        status = "NORMAL"
    elif is_anomaly:
        status = "CONFIRMED"
    else:
        status = "UNVERIFIED"
    source = decision.raw.get("source", "laya") if isinstance(decision.raw, dict) else "laya"
    return {
        "laya_decision": decision.decision,
        "laya_confidence": decision.confidence,
        "laya_fault_probability": decision.fault_present,
        "isolation_forest_anomaly": is_anomaly,
        "isolation_forest_score": _json_safe_score(anomaly_result.get("anomaly_score")),
        "verification_status": status,
        "decision_source": source,
    }


def run_laya(df_history: pd.DataFrame, laya_config: Optional[LayaConfig] = None,
             engine: Optional[LayaDecisionEngine] = None) -> LayaDecision:
    """Delegate to the REAL ``LayaDecisionEngine`` (needs an installed checkpoint).

    Propagates the engine's ``RuntimeError`` unchanged when Laya is not installed —
    it never fabricates a learned decision.
    """
    laya_config = laya_config or LayaConfig()
    engine = engine or LayaDecisionEngine(laya_config)
    return engine.predict(_with_required_columns(df_history))
