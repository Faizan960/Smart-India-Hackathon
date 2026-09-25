"""Import smoke test: every pipeline module must import cleanly.

Guards against syntax errors, broken imports and accidental hard dependencies in
the isolated ``ml.pipeline`` package.
"""
from __future__ import annotations

import importlib

import pytest

_MODULES = [
    "ml.pipeline",
    "ml.pipeline.config",
    "ml.pipeline.data_mapping",
    "ml.pipeline.data_loader",
    "ml.pipeline.physics",
    "ml.pipeline.preprocessing",
    "ml.pipeline.baseline",
    "ml.pipeline.features",
    "ml.pipeline.anomaly_detector",
    "ml.pipeline.classifier",
    "ml.pipeline.explainability",
    "ml.pipeline.evidence",
    "ml.pipeline.laya_adapter",
    "ml.pipeline.imputation",
    "ml.pipeline.health",
    "ml.pipeline.inference",
    "ml.pipeline.evaluator",
    "ml.pipeline.fault_injector",
    "ml.pipeline.train",
]


@pytest.mark.parametrize("name", _MODULES)
def test_module_imports(name):
    assert importlib.import_module(name) is not None
