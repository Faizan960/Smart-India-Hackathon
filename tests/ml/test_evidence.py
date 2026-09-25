"""Inspectable evidence fusion tests (spec sections 17 & 35)."""
from __future__ import annotations

import pandas as pd

from ml.pipeline.evidence import fuse_frame, fuse_observation


def _fuse(**kw):
    base = dict(
        anomaly_score=0.1, is_anomaly=False, core_complete=True,
        fault_type="NORMAL", fault_confidence=0.9, legacy_label="NORMAL",
        signatures={}, explanation=None,
    )
    base.update(kw)
    return fuse_observation(**base)


def test_normal_has_no_phantom_reasons():
    a = _fuse(anomaly_score=0.1)
    assert a["severity"] == "NORMAL"
    assert a["fused_status"] == "NORMAL"
    assert a["reasons"] == ["no anomalous evidence"]
    assert a["fault_present"] == 0.1


def test_normal_verdict_never_lists_a_dynamic_signature():
    # Incomplete row: score undefined, detector didn't flag it, classifier said
    # NORMAL -- yet a raw drift signature column is still True. The fused NORMAL
    # verdict must NOT surface a "calibration drift" reason (spec section 35).
    a = _fuse(anomaly_score=float("nan"), core_complete=False, is_anomaly=False,
              fault_type="NORMAL", signatures={"sig_drift": True})
    assert a["severity"] == "NORMAL"
    assert a["reasons"] == ["no anomalous evidence"]
    assert not any("drift" in r for r in a["reasons"])


def test_structural_dropout_warns_even_without_a_score():
    a = _fuse(anomaly_score=float("nan"), core_complete=False, is_anomaly=False,
              fault_type="SENSOR_DROPOUT", legacy_label="SENSOR_DROPOUT",
              signatures={"sig_dropout": True})
    assert a["severity"] == "WARNING"
    assert a["structural_fault"] is True
    assert a["fused_status"] == "CONFIRMED"      # structural signal is self-verifying
    assert a["fault_present"] == 0.8             # a data gap is itself probable fault
    assert a["anomaly_score"] is None
    assert any("dropout" in r for r in a["reasons"])


def test_high_score_is_critical_and_confirmed():
    a = _fuse(anomaly_score=0.85, is_anomaly=True, fault_type="UNKNOWN_ANOMALY",
              legacy_label="UNKNOWN_ANOMALY")
    assert a["severity"] == "CRITICAL"
    assert a["fused_status"] == "CONFIRMED"


def test_dynamic_reasons_only_when_detector_flags():
    # A structural freeze raises severity to WARNING without a detector flag; a raw
    # spike signature is present but must be suppressed because is_anomaly is False.
    a = _fuse(anomaly_score=float("nan"), core_complete=False, is_anomaly=False,
              fault_type="SENSOR_FREEZE", legacy_label="SENSOR_FREEZE",
              signatures={"sig_freeze": True, "sig_spike": True})
    assert a["severity"] == "WARNING"
    joined = " ".join(a["reasons"])
    assert "stuck sensor" in joined          # structural freeze reason present
    assert "transient spike" not in joined   # dynamic spike reason suppressed

    b = _fuse(anomaly_score=0.6, is_anomaly=True, fault_type="TRANSIENT_SPIKE",
              legacy_label="TEMPERATURE_SPIKE", signatures={"sig_spike": True})
    assert "transient spike" in " ".join(b["reasons"])


def test_fuse_frame_aligns_and_labels():
    feat = pd.DataFrame(index=[0, 1])
    anom = pd.DataFrame({"anomaly_score": [0.05, 0.9], "is_anomaly": [False, True],
                         "core_complete": [True, True]}, index=[0, 1])
    sig_false = [False, False]
    cls = pd.DataFrame({
        "fault_type": ["NORMAL", "UNKNOWN_ANOMALY"], "fault_confidence": [0.9, 0.9],
        "legacy_label": ["NORMAL", "UNKNOWN_ANOMALY"],
        "sig_dropout": sig_false, "sig_freeze": sig_false, "sig_spike": sig_false,
        "sig_drift": sig_false, "sig_physical": sig_false,
    }, index=[0, 1])
    out = fuse_frame(feat, anom, cls)
    assert list(out.index) == [0, 1]
    assert out["severity"].iloc[0] == "NORMAL"
    assert out["severity"].iloc[1] == "CRITICAL"
    assert out["fused_status"].iloc[1] == "CONFIRMED"
