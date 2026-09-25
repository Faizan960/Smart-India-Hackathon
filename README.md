# AWS Sentinel — SIH 26073

**AI/ML-Based Intelligent Anomaly Detection for Automatic Weather Stations (AWS)**

AWS Sentinel is a web-based telemetry monitoring and machine-learning anomaly detection system for Automatic Weather Stations. It combines historical and live meteorological observations with an **unsupervised Isolation Forest model**, temporal/rolling feature engineering, fault classification, anomaly injection, and real-time visualization.

Built for **Smart India Hackathon 2026 — Problem Statement SIH26073**.

---

## 1. Problem Statement

### SIH26073 — AI/ML-Based Intelligent Anomaly Detection for Automatic Weather Stations

Automatic Weather Stations continuously produce observations such as:

- Temperature
- Relative humidity
- Atmospheric pressure
- Wind speed

Sensor failures and abnormal telemetry can appear as:

- Sudden spikes or drops
- Frozen/stuck readings
- Gradual sensor drift
- Missing values / sensor dropout
- Unusual combinations of otherwise plausible readings

AWS Sentinel identifies abnormal observations and provides an ML-assisted fault classification through a serverless inference pipeline.

---

## 2. Current System Status

This repository contains a **working MVP with an implemented ML inference pipeline**.

### Currently implemented

- Historical weather-data ingestion
- Live weather-data polling
- Unified time-series construction
- Browser-side telemetry caching
- Time-series deduplication
- Rolling and temporal feature extraction
- Scikit-Learn Isolation Forest anomaly detection
- StandardScaler preprocessing
- Fault-type classification
- Controlled anomaly injection for demonstrations
- Real-time anomaly results through a Python serverless endpoint
- Dashboard visualization using Chart.js
- Graceful fallback to a Z-score detector when the ML endpoint is unavailable

### Current ML training approach

The current model is **unsupervised Isolation Forest**.

Training currently:

1. Generates deterministic healthy telemetry for a representative station.
2. Extracts temporal and rolling statistical features.
3. Handles incomplete feature values.
4. Fits a StandardScaler.
5. Trains an IsolationForest.
6. Saves the scaler and model with Joblib.
7. The serverless inference API loads those artifacts and scores incoming observations.

The current training dataset is **synthetic healthy telemetry** used to establish a reproducible normal-behaviour baseline for the prototype.

The project does **not** claim to be trained on a large labelled national IMD AWS dataset. The architecture is designed so real historical AWS data can replace or augment the prototype training data later.

---

## 3. High-Level Architecture

~~~text
                 HISTORICAL DATA
                 Open-Meteo
                      |
                      v
              +----------------+
              | Data Pipeline  |
              +-------+--------+
                      |
LIVE DATA             v
OpenWeatherMap --> Unified Telemetry
                      |
                      v
              +-------------------+
              | Feature Extraction|
              +---------+---------+
                        |
                        v
              +-------------------+
              | StandardScaler    |
              +---------+---------+
                        |
                        v
              +-------------------+
              | Isolation Forest  |
              | ML Anomaly Model  |
              +---------+---------+
                        |
                        v
              +-------------------+
              | Fault Classifier  |
              +---------+---------+
                        |
                        v
       +----------------+----------------+
       |                                 |
       v                                 v
 Anomaly Score                    Fault Type / Confidence
       |                                 |
       +----------------+----------------+
                        |
                        v
                 Web Dashboard
                        |
                        v
              Controlled Fault Injection
~~~

---

## 4. Frontend

The frontend is intentionally lightweight.

### Technologies

- HTML5
- CSS3
- Vanilla JavaScript (ES6+)
- Chart.js

The application uses native browser APIs and ES modules rather than React, Vue, or Angular.

A custom reactive store manages:

- Live polling state
- Historical telemetry
- Cached observations
- ML synchronization
- Dashboard state

Chart.js provides telemetry visualization across multiple time windows.

---

## 5. Data Pipeline

AWS Sentinel currently combines two weather-data sources for development and demonstration.

### Historical telemetry — Open-Meteo

- Retrieves historical weather observations.
- Current implementation retrieves up to approximately 30 days / 744 hourly observations.
- Historical data is cached in browser localStorage.
- Cache duration is approximately 2 hours.

### Live telemetry — OpenWeatherMap

- Current live weather-data provider for the prototype.
- Frontend periodically requests current observations.
- API key is kept server-side through the backend proxy.

### Timeline handling

Weather providers may return repeated or slowly changing observation timestamps.

AWS Sentinel therefore maintains:

- observedEpoch — timestamp supplied by the provider.
- receivedEpoch — time at which the application received the observation.

This prevents repeated provider timestamps from collapsing the live time-series.

---

## 6. Machine Learning Pipeline

The ML pipeline is implemented in Python.

### Model

**Scikit-Learn Isolation Forest**

Isolation Forest is used as an unsupervised anomaly detector. It learns the structure of the normal training distribution and identifies observations that are isolated from that distribution.

### Preprocessing

- Pandas
- NumPy
- StandardScaler
- Joblib

### Feature engineering

The current feature extractor generates **14 model features**.

#### Raw meteorological features

- Temperature
- Humidity
- Pressure
- Wind speed

#### Temporal features

- Hour-of-day sine encoding
- Hour-of-day cosine encoding

These encode the daily cycle without treating adjacent hours across midnight as distant values.

#### Rolling features

For each meteorological variable:

- Rolling mean
- Rolling standard deviation

The current rolling window is **12 observations**, corresponding to approximately one hour when observations arrive at 5-minute intervals.

### Feature vector

~~~text
temperature
humidity
pressure
wind_speed

hour_sin
hour_cos

temperature_rolling_mean
temperature_rolling_std

humidity_rolling_mean
humidity_rolling_std

pressure_rolling_mean
pressure_rolling_std

wind_speed_rolling_mean
wind_speed_rolling_std
~~~

---

## 7. Model Training

Training implementation:

~~~text
ml/train.py
~~~

Training process:

~~~text
Generate Healthy Telemetry
        |
        v
Feature Extraction
        |
        v
Missing-value Handling
        |
        v
StandardScaler
        |
        v
IsolationForest
        |
        v
Joblib Model Artifacts
~~~

### Current training configuration

- 10,000 generated healthy observations
- Deterministic random seed
- StandardScaler preprocessing
- IsolationForest
- 100 estimators
- contamination = 0.01
- random_state = 42

The synthetic generator models:

- Temperature daily variation
- Humidity variation inversely related to temperature
- Slow pressure variation
- Irregular positive wind speed

This provides a reproducible healthy baseline for the current prototype.

---

## 8. Real-Time Inference

> **On branch `feature/live-weather-demo`:** `/api/inference` is bridged to the
> real-data **AWS Sentinel** pipeline (`ml/pipeline`) through the thin adapter
> `ml/pipeline/live_adapter.py`; the legacy `ml/inference.py` path below is left
> intact but is no longer what this endpoint calls. The HTTP contract is
> preserved (see [§22](#22-live-weather--sentinel-inference-integration)). The
> description in this section reflects the original prototype design.

The inference endpoint is:

~~~text
/api/inference
~~~

Implemented in:

~~~text
api/inference.py
ml/inference.py
~~~

Inference flow:

~~~text
Recent Telemetry History
          |
          v
     Pandas DataFrame
          |
          v
    Feature Extraction
          |
          v
    Last Observation
          |
          v
      StandardScaler
          |
          v
    Isolation Forest
          |
          +------------------+
          |                  |
          v                  v
     Prediction        Anomaly Score
          |                  |
          +--------+---------+
                   v
             Fault Classifier
                   |
                   v
          JSON Result → UI
~~~

The current inference result includes:

- is_anomaly
- anomaly_score
- raw_score
- fault_type
- confidence

The anomaly score is derived from the Isolation Forest score and normalized to a 0–1 range for dashboard use.

---

## 9. Fault Classification

The ML model determines whether an observation is anomalous. A secondary deterministic classifier then identifies the likely fault type using recent telemetry history.

Current classifications:

- NORMAL
- SENSOR_DROPOUT
- TEMPERATURE_SPIKE
- TEMPERATURE_DROP
- SENSOR_FREEZE
- SENSOR_DRIFT
- PRESSURE_SPIKE
- PRESSURE_DROP
- HUMIDITY_SPIKE
- HUMIDITY_DROP
- UNKNOWN_ANOMALY

Current classification logic includes:

- Missing-value detection
- Historical mean/std comparison
- Temperature z-score
- Pressure z-score
- Humidity z-score
- Repeated identical readings
- Monotonic short-term temperature movement

Therefore the current architecture is accurately described as:

**ML anomaly detection + deterministic fault classification.**

It is not a fully learned fault-classification model.

---

## 10. Controlled Anomaly Injection

AWS Sentinel includes a demo-oriented anomaly injection mechanism.

It allows controlled synthetic faults to be introduced into the telemetry stream so the complete pipeline can be demonstrated without waiting for a naturally occurring sensor failure.

~~~text
Healthy Telemetry
      |
      v
Inject Synthetic Fault
      |
      v
Feature Extraction
      |
      v
Isolation Forest
      |
      v
Anomaly Detected
      |
      v
Fault Classification
      |
      v
Dashboard Alert
~~~

Example demonstrations include sudden temperature anomalies and other abnormal telemetry patterns supported by the demo controls.

The injection mechanism is explicitly a **demo/testing feature** and is not presented as naturally occurring weather data.

---

## 11. Genuine Weather Event vs Sensor Fault

A key research direction is distinguishing a genuine meteorological event from a faulty sensor.

The current prototype provides the foundation through:

- Historical context
- Rolling features
- Multiple weather variables
- ML anomaly scoring
- Fault classification
- Controlled anomaly injection

### Implemented now

- Temporal feature engineering
- Multivariate weather inputs
- Isolation Forest anomaly detection
- Deterministic fault classification

### Future/extended ML work

- Station-specific learned baselines
- Stronger temporal sequence modelling
- Explicit cross-variable physical-consistency modelling
- Learned fault-type classification
- Sensor degradation forecasting
- Feature-attribution/explainability methods
- Training and evaluation on larger real AWS/IMD datasets

These extensions are planned directions, not claims about the current MVP.

---

## 12. Graceful Degradation

If the ML endpoint is unavailable, the dashboard can fall back to an offline Z-score heuristic detector.

~~~text
ML API Available
      |
      v
Isolation Forest inference
      |
      v
ML anomaly result

ML API Unavailable / Timeout
      |
      v
Offline Z-score heuristic
      |
      v
Fallback anomaly result
~~~

The fallback detector is **not the primary ML model**.

---

## 13. Repository Structure

~~~text
/
├── api/
│   └── inference.py
├── ml/
│   ├── train.py
│   ├── inference.py
│   ├── features.py
│   ├── classifier.py
│   ├── data_gen.py
│   └── models/
│       ├── scaler.joblib
│       └── isolation_forest.joblib
├── frontend/
│   └── ...
├── requirements.txt
├── package.json
├── vercel.json
├── .python-version
└── README.md
~~~

The frontend file organization may evolve as the MVP develops.

---

## 14. Technology Stack

### Frontend

| Technology | Purpose |
|---|---|
| HTML5 | UI structure |
| CSS3 | Styling |
| Vanilla JavaScript | Application logic |
| Chart.js | Telemetry visualization |

### Backend

| Technology | Purpose |
|---|---|
| Node.js | Weather API proxy/backend routes |
| Python 3.12 | ML inference |
| Vercel Functions | Serverless deployment |

### Machine Learning

| Technology | Version | Purpose |
|---|---:|---|
| Scikit-Learn | 1.7.2 | Isolation Forest + StandardScaler |
| Pandas | 2.3.3 | DataFrames and feature processing |
| NumPy | 2.3.5 | Numerical computation |
| Joblib | 1.5.2 | Model artifact persistence |

### Data providers

| Provider | Current role |
|---|---|
| Open-Meteo | Historical development telemetry |
| OpenWeatherMap | Live development telemetry |

These are development/demo data providers. They are not being represented as the IMD's production AWS feed.

---

## 15. Local Development

### Prerequisites

- Node.js 18+
- Python 3.12
- Vercel CLI

Install Vercel CLI:

~~~bash
npm install -g vercel
~~~

### Environment variables

Create .env.local:

~~~env
WEATHER_PROVIDER=openweathermap
OPENWEATHERMAP_API_KEY=your_owm_api_key
~~~

### Start

~~~bash
vercel dev
~~~

---

## 16. Retraining the ML Model

Train the current prototype model with:

~~~bash
python ml/train.py
~~~

Generated artifacts:

~~~text
ml/models/scaler.joblib
ml/models/isolation_forest.joblib
~~~

For future real-data training, the feature schema used during training must remain consistent with inference.

---

## 17. Deployment

The project is configured for Vercel.

~~~text
GitHub Repository
       |
       v
     Vercel
       |
       +--> Frontend
       |
       +--> Node.js API routes
       |
       +--> Python ML inference
~~~

Production environment variable:

~~~text
OPENWEATHERMAP_API_KEY
~~~

Python runtime:

~~~text
Python 3.12
~~~

---

## 18. SIH 2026 Alignment

| Requirement / capability | Status |
|---|---|
| Real-time anomaly detection | Implemented |
| Temperature anomaly detection | Implemented |
| Humidity anomaly detection | Implemented |
| Pressure anomaly detection | Implemented |
| Wind-speed feature | Implemented |
| Temporal feature engineering | Implemented |
| Rolling statistical features | Implemented |
| Multivariate input | Implemented |
| Unsupervised ML | Isolation Forest implemented |
| Confidence output | Implemented through fault classification |
| Fault-type identification | Deterministic classifier implemented |
| Anomaly injection | Implemented for demonstration |
| Historical telemetry | Implemented |
| Real-time telemetry | Implemented |
| Dashboard visualization | Implemented |
| Graceful ML fallback | Implemented |
| Learned seasonal/long-term baseline | Future extension |
| Learned physical-consistency model | Future extension |
| Learned fault classification | Future extension |
| Sensor degradation prediction | Future extension |
| Large-scale real AWS/IMD training | Future extension |
| Advanced explainability | Future extension |

---

## 19. Current MVP vs Full Production Vision

### Current MVP

~~~text
Historical + Live Telemetry
          |
          v
Feature Engineering
          |
          v
Isolation Forest
          |
          v
Fault Classification
          |
          v
Anomaly / Confidence
          |
          v
Dashboard
~~~

### Full Production Vision

~~~text
AWS Network
    |
    v
Secure Telemetry Ingestion
    |
    v
Quality Control + Feature Store
    |
    v
Station-Specific Temporal Models
    |
    v
Multivariate Consistency Analysis
    |
    v
ML Anomaly Ensemble
    |
    v
Fault Classification
    |
    v
Explainability + Confidence
    |
    v
Sensor Health / Degradation
    |
    v
Operator Dashboard + Alerts
~~~

The production vision is the next stage of development and should not be presented as already completed.

---

## 20. Project Positioning

AWS Sentinel is not a weather-forecasting system.

Its primary role is **data-quality intelligence for Automatic Weather Stations**:

> **Learn normal station behaviour → detect abnormal observations → identify likely sensor faults → provide confidence and actionable monitoring information.**

The central engineering challenge is to reduce false alarms while identifying observations that are inconsistent with the learned behaviour of the station and its telemetry context.

---

## 21. Documentation and Presentation Ground Rules

Any SIH presentation or documentation generated from this repository should use the repository as the technical source of truth.

### Present as implemented

- Isolation Forest anomaly detection
- StandardScaler preprocessing
- Temporal/rolling feature engineering
- Multivariate weather inputs
- Fault classification
- Confidence output
- Historical + live telemetry
- Controlled anomaly injection
- Dashboard visualization
- Serverless Python inference
- Graceful fallback detection

### Present as future/extended work unless implemented later

- LSTM/Transformer temporal models
- Autoencoders
- SHAP-based explanations
- Learned physical-consistency models
- Sensor degradation prediction
- Real IMD AWS production integration
- Large-scale labelled training datasets
- Production-grade automated retraining

This distinction keeps the SIH presentation technically credible and prevents the project from claiming capabilities that are not actually present in the repository.

---

## Current Production Architecture

AWS Sentinel uses a split deployment architecture. The Vercel application serves the dashboard and weather/configuration routes, while the Python Sentinel inference service runs separately on Render.

```text
                         HISTORICAL TRAINING DATA
                                  |
                                  v
                    +-----------------------------+
                    | NOAA Integrated Surface     |
                    | Database (ISD)              |
                    | Historical Weather Data     |
                    +-------------+---------------+
                                  |
                                  v
                    +-----------------------------+
                    | Data Mapping + Quality      |
                    | Control + Preprocessing     |
                    +-------------+---------------+
                                  |
                                  v
                    +-----------------------------+
                    | Station / Month / Hour      |
                    | Robust Baselines            |
                    +-------------+---------------+
                                  |
                                  |
                                  v
LIVE WEATHER       +-----------------------------+
OpenWeatherMap --->| Unified Telemetry / Live    |
                   | Adapter                     |
                   +-------------+---------------+
                                 |
                                 v
                   +-----------------------------+
                   | Feature Engineering         |
                   |                             |
                   | • Baseline Deviations       |
                   | • Temporal / Rate Features  |
                   | • Rolling Features          |
                   | • VPD / Thermodynamics      |
                   | • Pressure Tendency         |
                   +-------------+---------------+
                                 |
                                 v
                   +-----------------------------+
                   | StandardScaler              |
                   +-------------+---------------+
                                 |
                                 v
                   +-----------------------------+
                   | Isolation Forest            |
                   | ML Anomaly Detection        |
                   +-------------+---------------+
                                 |
                    +------------+-------------+
                    |                          |
                    v                          v
          +-------------------+      +----------------------+
          | Anomaly Score     |      | Fault Classification |
          | is_anomaly        |      |                      |
          +---------+---------+      | • SENSOR_DROPOUT     |
                    |                | • SENSOR_FREEZE      |
                    |                | • TRANSIENT_SPIKE    |
                    |                | • CALIBRATION_DRIFT  |
                    |                | • PHYSICAL_INCONS.   |
                    |                | • MULTIVARIATE       |
                    |                | • UNKNOWN            |
                    |                +----------+-----------+
                    |                           |
                    +-------------+-------------+
                                  |
                                  v
                    +-----------------------------+
                    | Evidence Fusion             |
                    |                             |
                    | • Severity                  |
                    | • Fused Status              |
                    | • Reasons                   |
                    +-------------+---------------+
                                  |
                                  v
                    +-----------------------------+
                    | LAYA / JEV DECISION LAYER   |
                    |                             |
                    | fault_type  -> choice       |
                    | fault_present -> noul       |
                    +-------------+---------------+
                                  |
                                  v
                    +-----------------------------+
                    | Decision Verification       |
                    |                             |
                    | Laya/JEV Decision           |
                    |          <->                |
                    | Isolation Forest Evidence  |
                    +-------------+---------------+
                                  |
                    +-------------+-------------+
                    |                           |
                    v                           v
          +-------------------+       +----------------------+
          | SHAP Explainability|       | Sensor Health       |
          |                   |       | & Imputation         |
          | Why was it        |       |                      |
          | flagged?          |       | HEALTHY / WATCH /   |
          +---------+---------+       | DEGRADED / CRITICAL  |
                    |                 +----------+-----------+
                    |                            |
                    +-------------+--------------+
                                  |
                                  v
                    +-----------------------------+
                    | FastAPI Inference API       |
                    |           Render             |
                    +-------------+---------------+
                                  |
                                  v
                    +-----------------------------+
                    | Vercel Web Dashboard        |
                    | Visualization + Alerts       |
                    +-----------------------------+
                                  |
                                  v
                    +-----------------------------+
                    | Controlled Fault Injection  |
                    |       Demo / Testing         |
                    +-----------------------------+
```

### Data-source roles

The architecture deliberately separates the three data sources:

| Source | Role |
|---|---|
| **NOAA ISD** | Historical training and evaluation data for the Sentinel ML pipeline |
| **OpenWeatherMap** | Current live weather input used for live inference |
| **Open-Meteo** | Historical development telemetry used by the frontend for charts/context |

NOAA is the current real-data training source and is **not IMD data**. OpenWeatherMap is the current live inference provider. Open-Meteo is not the source used to train the current Isolation Forest.

### Decision path

The core ML decision path is:

```text
Features
   ↓
Isolation Forest
   ↓
Fault Classification
   ↓
Evidence Fusion
   ↓
Laya / JEV Decision
   ↓
Verification
   ↓
SHAP + Health
   ↓
FastAPI / Render
   ↓
Vercel Dashboard
```

**Laya/JEV does not replace the Isolation Forest.** It is the typed decision layer around the structured Sentinel evidence. The Isolation Forest remains an independent anomaly signal used during verification.

**Controlled Fault Injection is a testing/demo path**, not a normal production data source.

## Vercel Application Layer

Vercel continues to host the production frontend from the \`main\` branch.

Vercel responsibilities:

- Frontend/dashboard
- \`/api/weather/current\`
- \`/api/weather/history\`
- \`/api/config/public\`

The Sentinel inference backend is no longer dependent on a Vercel Python function.

### Runtime Sentinel configuration

The public runtime configuration endpoint is:

\`\`\`text
GET /api/config/public
\`\`\`

The Vercel environment variable is:

\`\`\`text
VITE_SENTINEL_API_URL=https://smart-india-hackathon-pcfm.onrender.com
\`\`\`

The frontend currently uses native ES modules rather than a Vite build pipeline, so \`api/config/public.js\` exposes the configured URL to the browser at runtime.

The frontend then calls:

\`\`\`text
POST https://smart-india-hackathon-pcfm.onrender.com/inference
\`\`\`

The Render URL is a public API origin, not a secret.

---

## Render Sentinel API

The dedicated inference service lives under:

\`\`\`text
sentinel_api/
├── main.py
├── requirements.txt
├── Dockerfile
├── smoke_test.py
└── README.md
\`\`\`

\`sentinel_api/main.py\` is deliberately a thin HTTP wrapper. It delegates inference to:

\`\`\`text
ml.pipeline.live_adapter.assess_live()
\`\`\`

The service:

- Loads Sentinel model artifacts once at startup
- Exposes \`GET /health\`
- Exposes \`POST /inference\`
- Applies CORS
- Returns strict JSON
- Does not retrain the model during requests
- Does not read NOAA training CSVs during normal inference

### Docker runtime

The service uses:

\`\`\`text
python:3.12-slim
\`\`\`

The Docker build context is the repository root because the image needs:

\`\`\`text
ml/
models/sentinel/
sentinel_api/
\`\`\`

Render injects \`$PORT\`, and Uvicorn binds to \`0.0.0.0\`.

### Render environment variable

\`\`\`text
FRONTEND_ORIGIN=https://smart-india-hackathon-ebon.vercel.app
\`\`\`

---

## Real-Data AWS Sentinel ML Pipeline

The authoritative real-data implementation is under:

\`\`\`text
ml/pipeline/
\`\`\`

It operates primarily on:

- Temperature
- Atmospheric pressure
- Relative humidity

\`wind_speed\` is carried as an auxiliary field for the existing Laya state contract.

The current model is trained on historical **NOAA ISD** data, not IMD data. The current training source is:

\`\`\`text
data/Raw/4398394.csv
\`\`\`

The real-data pipeline uses chronological train/validation/test separation and wall-clock-aware temporal calculations.

### 14 detector features

\`\`\`text
temperature
humidity
pressure

temp_dev_baseline
humidity_dev_baseline
pressure_dev_baseline

temp_rate
humidity_rate
pressure_rate

temp_roll_std_3h
pressure_roll_std_3h

vpd
thermo_inconsistency_score
pressure_change_3h
\`\`\`

The trained runtime artifacts are stored in:

\`\`\`text
models/sentinel/
├── baselines.json
├── classifier_config.json
├── feature_config.json
├── isolation_forest.joblib
├── model_metadata.json
└── scaler.joblib
\`\`\`

---

## Detection and Fault Classification

### Isolation Forest

Isolation Forest is the primary unsupervised anomaly detector.

\`\`\`text
14 model features
       |
       v
StandardScaler
       |
       v
Isolation Forest
       |
       v
Raw score
       |
       v
Training-distribution calibration
       |
       v
anomaly_score [0,1]
\`\`\`

The detector supplies anomaly evidence and the anomaly flag. It does not independently prove a hardware failure.

### Fault classification

Fault classification is currently deterministic and evidence-based rather than a separately trained fault-classification model.

Canonical fault taxonomy:

\`\`\`text
NORMAL
SENSOR_DROPOUT
SENSOR_FREEZE
TRANSIENT_SPIKE
CALIBRATION_DRIFT
PHYSICAL_INCONSISTENCY
MULTIVARIATE_ANOMALY
UNKNOWN_ANOMALY
\`\`\`

The classifier uses evidence such as missing values, unexpected gaps, flat readings, rate changes, robust baseline deviations, drift signatures, thermodynamic inconsistency, and multi-sensor deviation.

---

## Evidence Fusion

Evidence fusion is an inspectable rule layer, not a weighted average of model outputs.

It produces:

\`\`\`text
severity
fused_status
reasons
\`\`\`

Severity:

\`\`\`text
NORMAL
WARNING
CRITICAL
\`\`\`

Fused status:

\`\`\`text
NORMAL
CONFIRMED
UNVERIFIED
\`\`\`

Anomaly score, severity, fault confidence, fault presence, and verification status remain separate concepts.

---

## Laya / JEV Decision Model

Laya/JEV is used as a **typed decision layer** around the Sentinel evidence. It is not the raw anomaly detector.

The existing typed contract uses:

\`\`\`text
fault_type     -> choice
fault_present  -> noul
\`\`\`

The Sentinel bridge is:

\`\`\`text
ml/pipeline/laya_adapter.py
\`\`\`

### Real Laya path

When a Laya checkpoint is installed, \`run_laya()\` delegates to the existing \`LayaDecisionEngine\`.

If Laya is not available, the implementation does not fabricate a learned result.

### Pipeline-derived typed decision

\`pipeline_decision()\` can produce a LayaDecision-shaped result from Sentinel's own evidence.

It explicitly tags the source:

\`\`\`text
source = "aws_sentinel_pipeline"
\`\`\`

This is important: a pipeline-derived typed decision must not be presented as though an external Laya model itself generated it.

### Verification

The Laya-typed decision and the independent Isolation Forest are compared by a verification rule.

They are **not averaged**.

\`\`\`text
Sentinel evidence
      |
      v
Typed decision
      |
      +----------------------+
      |                      |
      v                      v
Laya-style choice      Isolation Forest
      |                      |
      +----------+-----------+
                 |
                 v
         verification status
\`\`\`

Example response fields:

\`\`\`json
{
  "laya_decision": {
    "decision": "NORMAL",
    "confidence": 0.7652,
    "fault_present": 0.2348,
    "source": "aws_sentinel_pipeline"
  },
  "verification": {
    "laya_decision": "NORMAL",
    "laya_confidence": 0.7652,
    "laya_fault_probability": 0.2348,
    "isolation_forest_anomaly": false,
    "isolation_forest_score": 0.2347522321872649,
    "verification_status": "NORMAL",
    "decision_source": "aws_sentinel_pipeline"
  }
}
\`\`\`

The Laya-shaped presence/confidence fields are not automatically calibrated probabilities of physical sensor failure.

---

## SHAP Explainability

The Render runtime includes SHAP so deployed explanations can use the same explainability path as validated local inference.

For scored observations:

\`\`\`text
explanation.method = "shap"
\`\`\`

The explanation may contain:

- Base value
- Top contributing features
- Feature values
- Standardized values
- Contribution direction
- Human-readable feature descriptions
- Summary text

SHAP is feature attribution. It is not causal proof and is not itself a calibrated probability.

A labelled attribution fallback exists for runtimes where SHAP is unavailable.

---

## Missing Data, Imputation and Health

### Missing data

Missing core sensor values are never silently fabricated.

When the latest observation cannot be scored because a core sensor is missing:

\`\`\`text
anomaly_score = null
\`\`\`

The API uses strict JSON serialization with \`allow_nan=False\`, so \`NaN\` and \`Infinity\` are not emitted to clients.

### Imputation

Imputation is a separate continuity layer:

- Only short interior gaps are interpolated
- Leading/trailing gaps remain missing
- Over-long gaps remain missing
- Filled values are explicitly flagged
- Imputed values do not feed detector training

### Sensor health

Health tracks recent anomaly frequency and reports:

\`\`\`text
HEALTHY
WATCH
DEGRADED
CRITICAL
UNKNOWN
\`\`\`

\`health_status\` and \`dominant_fault_in_range\` represent different dimensions. Health is a maintenance-prioritisation signal, not a confirmed hardware-failure verdict.

---

## Live Data and Temporal Resolution

The live browser integration currently polls live weather roughly at minute-level intervals, while the historical NOAA training data has different and mixed cadence.

The live payload carries both:

- \`observedEpoch\` — provider-associated observation timing
- \`receivedEpoch\` — application receive timing

Therefore:

\`\`\`text
observation time != receive/poll time
\`\`\`

This temporal-resolution difference is an identified integration issue under investigation. It should not be described as fully resolved, and minute-level live rate values should not automatically be interpreted as equivalent to hourly changes without validating the timestamp semantics.

---

## Production API Contract

### \`GET /health\`

Returns service/model status.

Example:

\`\`\`json
{
  "status": "ok",
  "model_loaded": true,
  "service": "aws-sentinel-inference"
}
\`\`\`

### \`POST /inference\`

Request:

\`\`\`json
{
  "history": [],
  "station_id": "PB-011",
  "latitude": 30.901,
  "longitude": 75.8573
}
\`\`\`

Response fields include:

\`\`\`text
station_id
timestamp
anomaly_score
is_anomaly
severity
fault_type
fault_confidence
legacy_label
fault_present
fused_status
reasons
explanation
laya_decision
verification
health
confidence
data_complete
baseline_source
n_history
\`\`\`

The request carries rolling history; the API evaluates the true latest observation after normalization.

---

## Deployment Verification

The deployed Render service has been verified with the project's smoke-test client.

Verified scenarios:

\`\`\`text
1. Normal history            -> HTTP 200
2. Missing sensor value      -> HTTP 200
3. Empty history             -> HTTP 400
4. Temperature spike         -> HTTP 200
5. Sensor dropout            -> HTTP 200
\`\`\`

The deployed service returns real model outputs, Laya-shaped decision/verification fields, SHAP explanations on the tested scored path, and strict JSON.

The Vercel production dashboard has also successfully issued \`POST /inference\` requests to the Render service and received HTTP 200 responses.

These checks establish deployment/integration functionality. They are not field-validated sensor-failure accuracy.

---

## Evaluation

The real-data pipeline has been evaluated on a chronological NOAA held-out split with injected synthetic faults.

Reported metrics:

\`\`\`text
Single-station:
Detection F1      0.4618
Detection Recall  0.3954
Event Recall      0.9121

Multi-station:
Detection F1      0.4819
Detection Recall  0.4427
Precision         0.5287
Event Recall      0.9176
\`\`\`

These are pipeline evaluation results using held-out NOAA data and injected synthetic faults. They are not OpenWeatherMap field accuracy, IMD production accuracy, weather-forecast accuracy, or confirmed hardware-failure validation rates.

---

## Testing

Run the ML suite:

\`\`\`bash
python -m pytest tests/ml -q
\`\`\`

Current validated result:

\`\`\`text
97 passed
\`\`\`

Test the deployed Render API:

\`\`\`bash
python sentinel_api/smoke_test.py https://smart-india-hackathon-pcfm.onrender.com
\`\`\`

---

## Repository Structure

\`\`\`text
/
├── api/
│   ├── config/
│   │   └── public.js
│   ├── imd/
│   │   └── aws.js
│   └── weather/
│       ├── current.js
│       └── history.js
│
├── ml/
│   ├── pipeline/
│   └── laya_base/
│
├── models/
│   └── sentinel/
│
├── sentinel_api/
│   ├── Dockerfile
│   ├── README.md
│   ├── main.py
│   ├── requirements.txt
│   └── smoke_test.py
│
├── src/
│   ├── api/
│   ├── components/
│   ├── data/
│   ├── state/
│   └── ui/
│
├── tests/
│   └── ml/
│
├── docs/
│   └── ML_PIPELINE.md
│
├── .dockerignore
├── .env.example
├── vercel.json
└── README.md
\`\`\`

---

## Implemented vs Future

### Implemented

- Real-data NOAA training pipeline
- Chronological evaluation
- Robust station/month/hour baselines
- Thermodynamic evidence
- Time-based temporal features
- Isolation Forest anomaly detection
- Deterministic fault classification
- Evidence fusion
- Laya/JEV typed decision bridge
- Isolation Forest verification
- SHAP explainability
- Imputation
- Sensor health
- Controlled fault injection
- Live OpenWeatherMap integration
- FastAPI + Docker inference service
- Render deployment
- Vercel → Render production integration
- Strict JSON handling
- Heuristic fallback

### Future / extended work

- Direct production IMD AWS ingestion
- Larger field datasets
- Training data matched to high-frequency live cadence
- Learned sequence models
- Learned fault-type classification
- Stronger spatial consistency analysis
- Sensor degradation forecasting
- Automated retraining and model monitoring
- Field validation against confirmed hardware failures
- Production alerting workflows



## 22. Live Weather → Sentinel Inference Integration

On `feature/live-weather-demo`, the existing live OpenWeatherMap pipeline is
connected to the real-data **AWS Sentinel / Laya** ML pipeline (authoritatively
documented in [`docs/ML_PIPELINE.md`](docs/ML_PIPELINE.md)). This is an
*integration* — the model is **not** retrained on live data, and no second
detector or weather API is introduced.

### Data flow

~~~text
OpenWeatherMap (live) -> /api/weather/current -> browser normalizer
   -> rolling per-station history (localStorage)
   -> POST /api/inference { history, station_id, latitude, longitude }
   -> ml/pipeline/live_adapter.assess_live()
   -> SentinelInference: features -> Isolation Forest -> fault typing
        -> evidence fusion -> SHAP -> health -> Laya decision + verification
   -> strict JSON (allow_nan=False) -> existing dashboard
~~~

### Data-source roles (kept distinct)

| Role | Source |
|---|---|
| Model **training** (historical) | NOAA ISD — **not** IMD data |
| **Live inference** input | OpenWeatherMap (dev live provider) |
| Historical **dev** telemetry | Open-Meteo |
| ML detection / typing / explanation | real-data Sentinel pipeline (`ml/pipeline`) |
| Decision layer | Laya (`ml/laya_base`) |

### Honesty boundaries

- Live station ids (`DL-001`, …) are **development locations**, not IMD AWS
  station ids. Locations unknown to training use a global-climatology baseline,
  reported as `baseline_source: "global_fallback"`.
- A missing live sensor value is **never fabricated**: the reading is scored
  `anomaly_score: null` and surfaced as at most a hedged `SENSOR_DROPOUT`.
- The NOAA held-out evaluation metrics are **not** a measured OpenWeatherMap
  accuracy, and **no IMD production integration** is claimed.
- On this branch, SHAP explanations and real-data training (listed as future
  work in §21) are **implemented** in `ml/pipeline`.

### Serverless artifacts

`api/inference.py` loads `models/sentinel/**` (bundled via `vercel.json`
`includeFiles`); runtime deps are pinned in `api/requirements.txt`
(numpy / pandas / scikit-learn / joblib — SHAP optional, with a graceful
fallback). Integration tests: `tests/ml/test_live_adapter.py`
(`python -m pytest tests/ml -q`).

---

## License

Developed for **Smart India Hackathon 2026 — SIH26073**.

**Project:** AWS Sentinel  
**Problem:** AI/ML-Based Intelligent Anomaly Detection for Automatic Weather Stations
