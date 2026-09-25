"""Direct API smoke test for the Sentinel FastAPI backend (stdlib only, no deps).

Exercises ``POST /inference`` (and ``GET /health``) against a RUNNING server with
the existing live-payload shape, over the 5 scenarios requested for this cutover:
  1. normal history          -> scored, NORMAL, verification carries real IF fields
  2. missing sensor value    -> data_complete False, anomaly_score null (no fabrication)
  3. empty history           -> 400 (preserves the previous endpoint's behaviour)
  4. temperature spike       -> flagged, non-NORMAL, severity WARNING/CRITICAL
  5. sensor dropout (gap)    -> unscoreable latest reading handled honestly

It only READS the responses and asserts the real pipeline executed (it never
fabricates values). Uses REAL artifacts via the running server.

Usage:  python sentinel_api/smoke_test.py [BASE_URL]
        BASE_URL defaults to http://127.0.0.1:8000 (env SENTINEL_BASE_URL also read).
Exit code 0 = all scenarios passed their assertions.
"""
from __future__ import annotations

import json
import math
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone


def _history(n: int = 72):
    """A plausible hourly rolling history (camelCase windSpeed, like the browser)."""
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    pts = []
    for i in range(n):
        t = now - timedelta(hours=(n - 1 - i))
        pts.append({
            "timestamp": t.isoformat(),
            "temperature": round(25.0 + 3.0 * math.sin(i / 6.0), 2),
            "humidity": round(60.0 + 8.0 * math.cos(i / 5.0), 2),
            "pressure": round(1010.0 + 2.0 * math.sin(i / 8.0), 2),
            "windSpeed": round(3.0 + 1.0 * math.sin(i / 4.0), 2),
        })
    return pts

def _post(base, payload):
    req = urllib.request.Request(
        base.rstrip("/") + "/inference",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8") or "{}")


def _get(base, path):
    with urllib.request.urlopen(base.rstrip("/") + path, timeout=30) as r:
        return r.status, json.loads(r.read().decode("utf-8"))


def _strict(obj):
    """Assert the payload is strictly JSON-safe (no NaN/Infinity slipped through)."""
    json.dumps(obj, allow_nan=False)


def _show(tag, status, body):
    v = (body or {}).get("verification") or {}
    laya = (body or {}).get("laya_decision") or {}
    health = (body or {}).get("health") or {}
    print(f"\n=== {tag} (HTTP {status}) ===")
    if "error" in (body or {}):
        print("  error:", body["error"])
        return
    print(f"  is_anomaly={body.get('is_anomaly')} anomaly_score={body.get('anomaly_score')} "
          f"fault_type={body.get('fault_type')} confidence={body.get('confidence')}")
    print(f"  severity={body.get('severity')} fused_status={body.get('fused_status')} "
          f"data_complete={body.get('data_complete')} baseline_source={body.get('baseline_source')}")
    print(f"  verification: if_anomaly={v.get('isolation_forest_anomaly')} "
          f"if_score={v.get('isolation_forest_score')} decision_source={v.get('decision_source')}")
    print(f"  laya_decision: decision={laya.get('decision')} confidence={laya.get('confidence')} "
          f"source={laya.get('source')}")
    print(f"  health: status={health.get('health_status')} "
          f"dominant={health.get('dominant_fault_in_range')}")

def main() -> int:
    base = (sys.argv[1] if len(sys.argv) > 1 else
            os.environ.get("SENTINEL_BASE_URL", "http://127.0.0.1:8000"))
    print(f"Testing Sentinel API at {base}")
    failures = []

    # GET /health
    hs, hb = _get(base, "/health")
    print(f"\n=== GET /health (HTTP {hs}) ===\n  {hb}")
    if hs != 200 or not hb.get("model_loaded"):
        failures.append("health: model not loaded")

    # 1. normal ------------------------------------------------------------
    s, b = _post(base, {"history": _history(), "station_id": "DL-001"})
    _show("1. normal history", s, b); _strict(b)
    v = b.get("verification") or {}
    laya = b.get("laya_decision") or {}
    if s != 200: failures.append("normal: not 200")
    if not isinstance(b.get("anomaly_score"), (int, float)): failures.append("normal: score not numeric")
    if not isinstance(v.get("isolation_forest_score"), (int, float)): failures.append("normal: IF score missing")
    if v.get("decision_source") != "aws_sentinel_pipeline": failures.append("normal: decision_source wrong")
    if laya.get("decision") is None or laya.get("confidence") is None: failures.append("normal: laya fields missing")
    if b.get("data_complete") is not True: failures.append("normal: data_complete not True")

    # 2. missing sensor value ---------------------------------------------
    h = _history(); h[-1]["pressure"] = None
    s, b = _post(base, {"history": h, "station_id": "DL-001"})
    _show("2. missing sensor value", s, b); _strict(b)
    if s != 200: failures.append("missing: not 200")
    if b.get("anomaly_score") is not None: failures.append("missing: score not null")
    if b.get("data_complete") is not False: failures.append("missing: data_complete not False")

    # 3. empty history -----------------------------------------------------
    s, b = _post(base, {"history": [], "station_id": "DL-001"})
    _show("3. empty history", s, b); _strict(b)
    if s != 400: failures.append("empty: expected 400")

    # 4. temperature spike -------------------------------------------------
    h = _history(); h[-1]["temperature"] = 120.0
    s, b = _post(base, {"history": h, "station_id": "DL-001"})
    _show("4. temperature spike", s, b); _strict(b)
    if s != 200: failures.append("spike: not 200")
    if not (b.get("is_anomaly") or b.get("fault_type") != "NORMAL"): failures.append("spike: not flagged")
    if b.get("severity") not in ("WARNING", "CRITICAL"): failures.append("spike: severity not raised")

    # 5. sensor dropout (sustained gap on the latest readings) -------------
    h = _history()
    for j in range(1, 5):
        h[-j]["pressure"] = None
    s, b = _post(base, {"history": h, "station_id": "DL-001"})
    _show("5. sensor dropout", s, b); _strict(b)
    if s != 200: failures.append("dropout: not 200")
    if b.get("data_complete") is not False: failures.append("dropout: data_complete not False")

    print("\n" + ("=" * 52))
    if failures:
        print("FAILED:", *(f"\n  - {f}" for f in failures))
        return 1
    print("ALL SCENARIOS PASSED (real artifacts, strict JSON, no fabrication).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


