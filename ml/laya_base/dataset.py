"""Build JSONL training cases for Laya from telemetry windows."""
from __future__ import annotations
import json
from pathlib import Path
import pandas as pd
from .config import FAULT_LABELS
from .fault_injection import inject_fault
from .questions import fault_questions
from .state import telemetry_to_state

def build_case(df_window: pd.DataFrame, label: str, case_id: str) -> dict:
    questions = fault_questions()
    return {
        "id": case_id,
        "workflow": "aws_sensor_fault_detection",
        "state": json.dumps(telemetry_to_state(df_window)),
        "questions": json.dumps(questions),
        "gold": json.dumps({
            "fault_type": {
                "label": label,
                "probabilities": {name: 1.0 if name == label else 0.0 for name in FAULT_LABELS},
            },
            "fault_present": {
                "label": "false" if label == "NORMAL" else "true",
                "probabilities": {
                    "false": 1.0 if label == "NORMAL" else 0.0,
                    "true": 0.0 if label == "NORMAL" else 1.0,
                },
            },
        }),
    }

def build_jsonl(df: pd.DataFrame, output_path: str | Path, stride: int = 12, max_windows: int | None = None) -> int:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with output_path.open("w", encoding="utf-8") as f:
        for end in range(12, len(df) + 1, stride):
            if max_windows is not None and count >= max_windows:
                break
            window = df.iloc[end - 12:end].copy()
            base_id = f"aws-window-{end:06d}"
            for label_index, label in enumerate(FAULT_LABELS):
                faulty = inject_fault(window, label, seed=end + label_index)
                f.write(json.dumps(build_case(faulty, label, f"{base_id}-{label.lower()}"), ensure_ascii=False) + "\n")
                count += 1
    return count
