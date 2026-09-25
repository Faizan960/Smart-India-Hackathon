# AWS Sentinel inference backend -- Render Web Service (Docker).
#
# Stable Python matching the trained artifacts: the Isolation Forest + scaler in
# models/sentinel/ are scikit-learn 1.7.2 pickles, and python:3.12-slim has clean
# wheels for the whole scientific stack (numpy/pandas/scipy/scikit-learn/joblib)
# and for shap's deps (numba/llvmlite), so nothing is compiled from source.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app

WORKDIR /app

# Runtime deps first so this layer is cached until requirements.txt changes.
COPY sentinel_api/requirements.txt /app/sentinel_api/requirements.txt
RUN pip install --no-cache-dir -r /app/sentinel_api/requirements.txt

# Copy ONLY what the inference runtime needs: the pipeline package (+ laya_base,
# imported by laya_adapter), the trained artifacts, and the API. Training data
# (data/), reports/, tests/, notebooks and the frontend are excluded via
# .dockerignore, so no NOAA CSV or dev artifact is ever baked into the image.
COPY ml/ /app/ml/
COPY models/sentinel/ /app/models/sentinel/
COPY sentinel_api/ /app/sentinel_api/

WORKDIR /app/sentinel_api

EXPOSE 8000

# Liveness (local docker run; Render uses its own health check path -> /health).
HEALTHCHECK --interval=30s --timeout=5s --start-period=45s --retries=3 \
  CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('PORT','8000')+'/health').read()" || exit 1

# Render injects $PORT; default 8000 locally. Must bind 0.0.0.0. main.py adds the
# repo root (/app) to sys.path so `import ml...` resolves with WORKDIR here.
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
