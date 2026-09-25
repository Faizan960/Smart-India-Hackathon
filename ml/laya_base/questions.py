"""Typed Laya question schema for AWS Sentinel."""
from .config import FAULT_LABELS

def fault_questions(labels=None) -> dict:
    labels = tuple(labels or FAULT_LABELS)
    return {
        "fault_type": {
            "type": "choice",
            "instructions": (
                "Classify the current automatic weather station telemetry into exactly one "
                "fault category. Use NORMAL when recent telemetry is consistent with healthy "
                "sensor behavior. Use UNKNOWN_ANOMALY when abnormal behavior exists but no "
                "listed fault category is sufficiently supported."
            ),
            "criteria": {label: label.replace("_", " ").lower() for label in labels},
        },
        "fault_present": {
            "type": "noul",
            "instructions": (
                "Does the current automatic weather station telemetry indicate a sensor or "
                "measurement fault rather than normal operation?"
            ),
            "criteria": {
                "true": "a sensor or telemetry fault is present",
                "false": "telemetry is normal",
            },
        },
    }
