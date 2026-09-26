"""AWS Sentinel -- FastAPI inference backend (Render Web Service).

Thin HTTP wrapper around the EXISTING real-data Sentinel pipeline. It does NOT
re-implement any ML logic: every request is delegated to
``ml.pipeline.live_adapter.assess_live`` -> ``SentinelInference`` (Isolation
Forest + fault classification + evidence fusion + Laya/JEV decision + SHAP /
labelled-fallback explanation + rolling health).

Model artifacts in ``models/sentinel/`` are loaded ONCE at startup and reused; no
NOAA CSV is read and nothing is trained during a request.

Endpoints:
    GET  /health     -> liveness + whether the model artifacts loaded
    POST /inference  -> assess the latest live observation (existing payload shape)

Run (local, from repo root):  uvicorn sentinel_api.main:app --reload --port 8000
Run (Docker, WORKDIR here):   uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}
"""
from __future__ import annotations

import json
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel

# Make the repo-root packages (``ml``) importable whether this module is launched
# as ``sentinel_api.main`` (from the repo root) or as ``main`` (WORKDIR=sentinel_api
# inside the container). Mirrors api/inference.py's path handling.
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from ml.pipeline.inference import get_default_engine  # noqa: E402
from ml.pipeline.live_adapter import assess_live  # noqa: E402


def _allowed_origins() -> List[str]:
    """CORS allow-list: common localhost dev origins plus the production frontend.

    ``FRONTEND_ORIGIN`` (set on Render) is the deployed Vercel origin and may be a
    comma-separated list. A ``*.vercel.app`` regex is also allowed (below) so Vercel
    preview deployments work without reconfiguring the backend for each one.
    """
    origins: List[str] = [
        "http://localhost:3000", "http://127.0.0.1:3000",   # `vercel dev`
        "http://localhost:5173", "http://127.0.0.1:5173",   # vite dev, if ever added
        "http://localhost:8000", "http://127.0.0.1:8000",
    ]
    for raw in os.environ.get("FRONTEND_ORIGIN", "").split(","):
        origin = raw.strip().rstrip("/")
        if origin and origin not in origins:
            origins.append(origin)
    return origins


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Warm the model ONCE at startup so the first request is not slow. Never fatal:
    if the artifacts are missing the real error is surfaced again per request."""
    try:
        get_default_engine()
        print("[sentinel_api] model artifacts loaded at startup", file=sys.stderr)
    except Exception as exc:  # pragma: no cover - surfaced again on /inference
        print(f"[sentinel_api] model warm-up deferred: {exc}", file=sys.stderr)
    yield


app = FastAPI(title="AWS Sentinel Inference API", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins(),
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)

class InferenceRequest(BaseModel):
    """The existing dashboard payload (unchanged). ``history`` is the browser's
    rolling list of normalized observations; station id / coords are top-level."""
    model_config = {"extra": "ignore"}

    history: List[Dict[str, Any]] = []
    station_id: Optional[str] = None
    stationId: Optional[str] = None  # camelCase alias some callers send
    latitude: Optional[float] = None
    longitude: Optional[float] = None


def _safe_json(data: Dict[str, Any]) -> Response:
    """Serialize with ``allow_nan=False`` so a NaN/Infinity can never reach the
    client -- an unavailable score stays ``null``, never fabricated. Mirrors the
    strict guarantee the previous Vercel handler enforced."""
    body = json.dumps(data, allow_nan=False).encode("utf-8")
    return Response(content=body, media_type="application/json; charset=utf-8")


@app.get("/health")
def health() -> Dict[str, Any]:
    """Liveness for Render's health check + whether the trained artifacts loaded."""
    model_loaded = False
    try:
        eng = get_default_engine()
        model_loaded = bool(eng and eng.detector and eng.detector.model is not None)
    except Exception as exc:  # pragma: no cover - reported, never fatal
        return {"status": "degraded", "model_loaded": False,
                "service": "aws-sentinel-inference", "detail": str(exc)}
    return {"status": "ok" if model_loaded else "degraded",
            "model_loaded": model_loaded, "service": "aws-sentinel-inference"}


@app.get("/")
def root() -> Dict[str, Any]:
    return {"service": "aws-sentinel-inference",
            "endpoints": ["GET /health", "POST /inference"]}

@app.post("/inference")
def inference(req: InferenceRequest) -> Response:
    """Assess the latest live observation through the real Sentinel pipeline.

    Empty history is rejected with 400 (preserving the previous endpoint's
    behaviour, so the frontend's heuristic fallback engages exactly as before).
    A non-empty payload is delegated verbatim to ``assess_live`` -- the same code
    path validated by ``tests/ml`` and the CLI -- and the pipeline's own decision
    (score / severity / fault_type / Laya / verification) is returned untouched.
    """
    history = req.history if isinstance(req.history, list) else []
    if len(history) == 0:
        return _safe_json_error(400, "Missing history data")

    try:
        result = assess_live(
            history,
            station_id=req.station_id or req.stationId,
            latitude=req.latitude,
            longitude=req.longitude,
        )
    except Exception as exc:  # pragma: no cover - defensive; real errors surfaced
        return _safe_json_error(500, f"Inference error: {exc}")

    return _safe_json(result)


def _safe_json_error(code: int, message: str) -> Response:
    body = json.dumps({"error": message}, allow_nan=False).encode("utf-8")
    return Response(content=body, status_code=code,
                    media_type="application/json; charset=utf-8")



