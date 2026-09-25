"""Configuration for the isolated Laya AWS Sentinel prototype."""
from dataclasses import dataclass, field
from typing import Tuple

FAULT_LABELS: Tuple[str, ...] = (
    "NORMAL", "SENSOR_DROPOUT", "TEMPERATURE_SPIKE", "TEMPERATURE_DROP",
    "SENSOR_FREEZE", "SENSOR_DRIFT", "PRESSURE_SPIKE", "PRESSURE_DROP",
    "HUMIDITY_SPIKE", "HUMIDITY_DROP", "UNKNOWN_ANOMALY",
)

@dataclass(frozen=True)
class LayaConfig:
    model_id: str = "convaiinnovations/laya"
    subfolder: str | None = "typed-decisions"
    device: str | None = None
    question_id: str = "fault_type"
    history_rows: int = 12
    labels: Tuple[str, ...] = field(default_factory=lambda: FAULT_LABELS)
