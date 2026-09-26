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

## Keep-alive / uptime monitoring (demo)

Render Free-Tier Web Services spin down after a period of inactivity and take a
few seconds to cold-start on the next request. For a live demo you can *reduce*
the chance of a cold start by having an **external uptime monitor** poll the
liveness endpoint on a fixed interval:

```
External uptime monitor  --(GET every ~1 min)-->  https://<service>.onrender.com/health
```

- Point an external monitor at `GET https://<service>.onrender.com/health` and
  expect `200`. For this SIH demo the desired interval is **~1 minute** to keep
  idle spin-down low.
- Interval caveat: **UptimeRobot's free tier has a 5-minute minimum**, so it does
  **not** deliver the desired ~1-minute pings. If you specifically want ~1-minute
  checks, use a monitor/service that supports sub-5-minute intervals — e.g. a
  self-hosted cron (`* * * * *`), or an uptime service such as BetterStack or
  Cronitor on a plan that allows ~1-minute checks. (GitHub Actions `schedule` is
  also ~5-minute-minimum and best-effort, so it is not reliable for 1-minute pings.)
- `GET /health` is deliberately cheap: **no auth, no ML inference, no weather-API
  call, no database**. It returns `200` with
  `{"status": ..., "model_loaded": <bool>, "service": "aws-sentinel-inference"}`
  as long as the process is up (the model reference is cached at startup, so the
  check does not reload anything).
- Do **not** rely on the dashboard/browser to keep the service awake: a browser
  `setInterval` stops when the tab is closed or throttled in the background, so it
  is not a dependable keep-alive. The dashboard is not responsible for uptime.

> **Limitation:** this only *reduces* idle spin-down for a demo/development
> setup — it does **not** guarantee the service never sleeps. Render's free tier
> enforces its own limits (e.g. monthly running-hours caps) and may change its
> policies; pinging is subject to those current policies. For a guaranteed
> always-on service, use a paid Render instance.
