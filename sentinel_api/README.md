# AWS Sentinel — Inference Backend (FastAPI, Render)

The Sentinel real-data ML inference path, extracted from the Vercel Python
function into a dedicated FastAPI service deployable to Render via Docker. It is a
**thin HTTP wrapper only** — all ML logic stays in `ml/pipeline` and is reached
through `ml.pipeline.live_adapter.assess_live`. No retraining, no CSV reads at
request time; the trained `models/sentinel/` artifacts load once at startup.

```
Frontend (Vercel)  --VITE_SENTINEL_API_URL-->  FastAPI /inference (Render)
                                                   -> assess_live()
                                                   -> SentinelInference
                                                   -> Isolation Forest -> classify
                                                   -> evidence fusion -> Laya/JEV
                                                   -> SHAP/explanation -> health -> JSON
```

## Endpoints
- `GET /health` — liveness + `model_loaded`.
- `POST /inference` — body `{ "history": [...], "station_id"?, "latitude"?, "longitude"? }`.
  Empty `history` → `400` (matches the previous endpoint). Response is strictly
  JSON-safe (`allow_nan=False`); an unscoreable reading yields `anomaly_score: null`.

## Run locally
```bash
uvicorn sentinel_api.main:app --reload --port 8000   # from the repo root
python sentinel_api/smoke_test.py http://127.0.0.1:8000
```

## Docker
```bash
docker build -t aws-sentinel-api -f sentinel_api/Dockerfile .
docker run --rm -p 8000:8000 -e FRONTEND_ORIGIN="https://<your-app>.vercel.app" aws-sentinel-api
```

## Environment
- `PORT` — provided by Render; the server binds `0.0.0.0:$PORT` (default 8000).
- `FRONTEND_ORIGIN` — allowed CORS origin(s), comma-separated (the Vercel frontend
  origin). `localhost` dev origins and `*.vercel.app` are always allowed.
- This backend does **not** call OpenWeatherMap; that key stays with the existing
  Node weather functions on Vercel.

## Deploy to Render (Docker Web Service)
1. Push this branch to the remote.
2. Render → New → **Web Service** → connect the repo/branch.
3. Runtime **Docker**; Dockerfile path `sentinel_api/Dockerfile`; context = repo root.
4. Health check path `/health`.
5. Env var `FRONTEND_ORIGIN=https://<your-app>.vercel.app`.
6. Deploy, then set `VITE_SENTINEL_API_URL=https://<service>.onrender.com` on the
   Vercel project so the frontend calls this service.
