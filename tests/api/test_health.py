"""Basic tests for the AWS Sentinel backend liveness endpoint.

These exercise ONLY the lightweight ``GET /health`` route that an external uptime
monitor polls to reduce Render idle spin-down. The endpoint runs no ML inference,
makes no weather-API call and touches no database, so the tests stay fast and do
not depend on live data. ``degraded`` is accepted alongside ``ok`` so the suite
passes even in an environment where the trained model artifacts are absent — a
liveness probe must still return 200 while the process is up.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from sentinel_api.main import app


def test_health_returns_200_without_auth():
    """Liveness: an unauthenticated GET with no body returns HTTP 200."""
    with TestClient(app) as client:
        resp = client.get("/health")
    assert resp.status_code == 200


def test_health_payload_shape():
    """Body advertises the service, a coarse status, and a boolean readiness flag."""
    with TestClient(app) as client:
        body = client.get("/health").json()
    assert body["service"] == "aws-sentinel-inference"
    assert body["status"] in {"ok", "degraded"}
    assert isinstance(body["model_loaded"], bool)
