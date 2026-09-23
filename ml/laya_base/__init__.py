"""Optional Laya integration for AWS Sentinel.

This package is isolated from the existing inference path.
Nothing in api/ imports it yet.
"""
from .decision import LayaDecisionEngine
from .verification import verify_laya_decision
__all__ = ["LayaDecisionEngine", "verify_laya_decision"]
