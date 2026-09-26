"""Second-stage Laya -> existing Isolation Forest verification."""
from __future__ import annotations
from typing import Any
import pandas as pd
from .decision import LayaDecisionEngine

def verify_laya_decision(df_history: pd.DataFrame, laya_engine: LayaDecisionEngine, anomaly_result: dict[str, Any]) -> dict[str, Any]:
    laya = laya_engine.predict(df_history)
    is_anomaly = bool(anomaly_result.get("is_anomaly", False))
    if laya.decision == "NORMAL":
        status = "NORMAL"
    elif is_anomaly:
        status = "CONFIRMED"
    else:
        status = "UNVERIFIED"
    return {
        "laya_decision": laya.decision,
        "laya_confidence": laya.confidence,
        "laya_fault_probability": laya.fault_present,
        "isolation_forest_anomaly": is_anomaly,
        "isolation_forest_score": anomaly_result.get("anomaly_score"),
        "verification_status": status,
        "laya_raw": laya.raw,
    }
