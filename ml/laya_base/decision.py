"""Lazy Laya inference adapter. Not imported by any HTTP route."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any
import pandas as pd
from .config import LayaConfig
from .questions import fault_questions
from .state import telemetry_to_state

@dataclass
class LayaDecision:
    decision: str
    confidence: float
    fault_present: float
    raw: dict[str, Any]

class LayaDecisionEngine:
    def __init__(self, config: LayaConfig | None = None):
        self.config = config or LayaConfig()
        self._agent = None

    def _load(self):
        if self._agent is None:
            try:
                import laya
            except ImportError as exc:
                raise RuntimeError(
                    "Laya is not installed. Install ml/laya_base/requirements.txt."
                ) from exc
            kwargs = {"device": self.config.device}
            if self.config.subfolder:
                kwargs["subfolder"] = self.config.subfolder
            self._agent = laya.load(self.config.model_id, **kwargs)
        return self._agent

    def predict(self, df_history: pd.DataFrame) -> LayaDecision:
        state = telemetry_to_state(df_history, self.config.history_rows)
        result = self._load().predict(state, fault_questions(self.config.labels))
        answers = result["answers"]
        fault = answers["fault_type"]
        present = answers["fault_present"]
        return LayaDecision(
            decision=str(fault["choice"]),
            confidence=float(fault.get("confidence", 0.0)),
            fault_present=float(present.get("noul", 0.0)),
            raw=result,
        )
