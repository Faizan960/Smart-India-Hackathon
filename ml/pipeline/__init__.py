"""AWS Sentinel real-data ML pipeline.

Isolated package: nothing here is imported by the existing ``api/`` routes,
``ml/inference.py`` or ``ml/classifier.py``. It adds a real-meteorological-data
training, detection, explanation and decision pipeline alongside the current
synthetic baseline, and only feeds the existing ``ml/laya_base`` decision layer.
"""
from .config import (
    DEFAULT_CONFIG,
    FAULT_TYPES,
    PipelineConfig,
    STANDARD_COLUMNS,
)

__all__ = ["PipelineConfig", "DEFAULT_CONFIG", "FAULT_TYPES", "STANDARD_COLUMNS"]
