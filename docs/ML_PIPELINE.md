# AWS Sentinel — Real-Data ML Pipeline (`ml/pipeline`)

A real-time sensor fault-detection intelligence layer for Automatic Weather
Stations, operating on **temperature, atmospheric pressure and relative
humidity**. It ingests real meteorological data, learns what is normal for each
station/season/hour, flags anomalies with a calibrated score, types the fault
from transparent signatures, explains *why*, and emits a Laya-typed decision
verified by an independent detector.

This package is **isolated**: nothing under `ml/pipeline/` is imported by the
existing `api/` routes, `ml/inference.py` or `ml/classifier.py`. It runs
alongside the current code and only feeds the existing `ml/laya_base` decision
layer through a thin adapter.

## Data reality (read this first)

The model is trained on **NOAA Integrated Surface Database (ISD)** composite
CSV for three Indian surface stations (`data/Raw/4398394.csv`). It is **not IMD
data** and is never represented as such. Provider-specific column names and
NOAA composite-field parsing live entirely in `data_config.yaml` +
`data_mapping.py`, so ingesting a different provider needs no change to any
modelling module.

Observed provenance (from `reports/training_summary.json`):

- 216,712 observations across stations `42071099999`, `43063099999`, `43117099999`
- Chronological split (no shuffling): train ≤ 2011-07-17, val ≤ 2013-05-20, test after
- Mixed cadence per station (3-hourly synoptic and half-hourly METAR), with gaps —
  every temporal feature is therefore wall-clock/time-based, never sample-count based.

## What it does not do

- It does **not** claim a sensor has failed from an anomaly score alone.
- It does **not** fabricate metrics, SHAP values or demo outputs.
- It does **not** call genuine extreme weather (monsoon saturation, heatwave) a fault.
- It does **not** average the Laya decision and the Isolation Forest score together.
- It does **not** train Laya on raw observations; it reuses the existing typed contract.

## Pipeline architecture (spec section 36, 10 phases)

Each phase is one focused module; every stage produces inspectable evidence, not
opaque verdicts.

| # | Concern | Module | Key output |
|---|---------|--------|-----------|
| 1 | Provider mapping | `data_mapping.py` | NOAA → standard schema |
| 2 | Load + QC report | `data_loader.py` | clean frame + quality report |
| 3 | QC flags + chronological split | `preprocessing.py` | leakage-free train/val/test |
| 4 | Diurnal baselines | `baseline.py` | robust (station,month,hour) normals |
| 5 | Thermodynamics | `physics.py` | VPD, dew point, consistency score |
| 6 | Feature engineering | `features.py` | time-based rates/rolls/tendency |
| 7 | Anomaly detection | `anomaly_detector.py` | calibrated `anomaly_score` ∈ [0,1] |
| 8 | Fault typing | `classifier.py` | typed fault + legacy label + signatures |
| — | Explainability | `explainability.py` | SHAP (or labelled fallback) attribution |
| — | Evidence fusion | `evidence.py` | severity + `fused_status` + reasons |
| — | Laya bridge | `laya_adapter.py` | typed decision + IF verification |
| 9 | Imputation + health | `imputation.py`, `health.py` | short-gap fill; rolling health |
| 10 | Runtime inference | `inference.py` | `predict_frame` / `predict_observation` |
| — | Injection + evaluation | `fault_injector.py`, `evaluator.py` | honest held-out metrics |
| — | Training entry point | `train.py` | fits + persists all artifacts |

### The detector (`anomaly_detector.py`)

An Isolation Forest over 14 standardized evidence features, trained **only** on
the chronological training split and **only** on rows with all raw core sensors
present. Raw scores are mapped to `anomaly_score ∈ [0,1]` by a logistic anchored
on the *training* score distribution (95th percentile → 0.5), so the mapping is
derived from real data, never hand-tuned. Rows missing a raw sensor are scored
`NaN` — never zero-filled into the model as if observed.

### Fault typing (`classifier.py`)

Transparent signatures assign a principled type from the taxonomy: structural
faults (dropout, freeze, physical inconsistency) are reported on their own
evidence; dynamic explanations (spike, drift, multivariate) are only asserted
where the detector actually flagged the point. A flat *temperature* run is
structurally suspicious on its own; a flat pressure/humidity plateau (common real
weather) is only called a freeze when the detector agrees.

### Evidence fusion (`evidence.py`)

Not a weighted average — a small set of inspectable rules. Every assessment
carries `severity` (NORMAL/WARNING/CRITICAL), a `fused_status`
(NORMAL/CONFIRMED/UNVERIFIED), and an explicit `reasons` list. A NORMAL verdict
never lists a phantom fault reason.

### Laya bridge (`laya_adapter.py`)

Reuses the existing `ml/laya_base` primitives — the typed `fault_type` **choice**
and `fault_present` **noul**, the state builder, `LayaDecision`, and the
verification doctrine. `run_laya` delegates to the real `LayaDecisionEngine` and
raises a clear error (never fabricates) when no checkpoint is installed;
`pipeline_decision` emits a `LayaDecision`-shaped result tagged
`source="aws_sentinel_pipeline"` so it is never misread as the Laya model's own
output. The typed decision and the Isolation Forest are combined by the
verification rule, **never averaged**.

## Measured performance

Measured on the held-out real NOAA test split with injected synthetic faults
(`python -m ml.pipeline.evaluator --seed 42`); every number here is reproduced
verbatim from `reports/evaluation.json`, not hand-entered or illustrative. The
split is 32,507 test rows, 3,986 injected fault rows across 190 injected events.

**Headline (event level):** recall **0.9121** — 166 of 182 scoreable injected
events were flagged. This is the operational question that matters: *did the
station raise the fault at all, and promptly?*

**Row level:** precision 0.5549, recall 0.3954, F1 0.4618 (tp 1576, fp 1264,
fn 2410). Row-level recall is deliberately lower than event-level recall: the
detector is tuned to catch an event, not to light up every row inside a slow,
hours-long drift. The false-positive rate on non-injected rows is at most
**0.0443** (1264 / 28521) — an *upper* bound, since unlabelled real rows may
themselves contain genuine sensor issues.

Per-fault, on detected rows (`row_recall` = fraction of injected rows flagged;
`typing` = fraction of *those* given the right fault type):

| Fault | row_recall | typing | median latency |
|-------|-----------:|-------:|---------------:|
| SENSOR_DROPOUT | 1.00 | 1.00 | 0 h |
| PHYSICAL_INCONSISTENCY | 1.00 | 0.99 | 0 h |
| TRANSIENT_SPIKE | 0.78 | 0.71 | 0 h |
| SENSOR_FREEZE | 0.58 | 0.94 | 6 h |
| MULTIVARIATE_ANOMALY | 0.48 | 0.83 | 0 h |
| CALIBRATION_DRIFT | 0.27 | 0.39 | 27 h |

Honest caveats (spec section 35):

- **Calibration drift is the hardest case, and the numbers say so.** A slow offset
  on top of a diurnal baseline looks much like slowly shifting real weather, so
  row-recall is only 0.27 and median latency is 27 h — a drift is only detectable
  once its offset grows large. Of its detected rows, 419 are typed SENSOR_FREEZE
  rather than CALIBRATION_DRIFT (a slow ramp can present a locally flat window),
  which is why its typing accuracy is 0.39. This is disclosed, not tuned away.
- **Structural faults are near-perfect** (dropout, physical inconsistency: 1.00
  row-recall) because they are read off their own raw evidence, not off a learned
  score — dropout is caught structurally even though a missing sensor scores NaN.
- These are **injected synthetic faults**, a proxy for real hardware failures;
  treat them as indicative, not as a field-validated failure-detection rate.

## Running

Train (fits baselines, detector, thresholds; writes `models/sentinel/` + reports):

```bash
python -m ml.pipeline.train --input data/Raw/4398394.csv
```

Evaluate on held-out test data with injected synthetic faults (honest metrics):

```bash
python -m ml.pipeline.evaluator --seed 42
```

Runtime inference from Python:

```python
import pandas as pd
from ml.pipeline.inference import SentinelInference

engine = SentinelInference()                     # loads models/sentinel/ once
frame = engine.predict_frame(telemetry_df)       # one assessment row per observation
obs = engine.predict_observation(history_df,     # rich dict for the latest reading
                                 station_id="42071099999")
```

`telemetry_df` uses the standard schema: `timestamp, station_id, latitude,
longitude, temperature, humidity, pressure, wind_speed` (wind_speed is auxiliary,
carried only to satisfy the existing Laya state contract).

Or straight from a raw NOAA file, via the CLI:

```bash
python -m ml.pipeline.inference --input data/Raw/4398394.csv --station 42071099999
```

By default this assesses the latest **complete** observation (the most recent row
whose temperature, humidity and pressure are all present), so you always see a
scored reading. Real streaming telemetry often ends on an incomplete row — a
sensor value simply has not arrived yet — and the pipeline **refuses to fabricate
a score** for such a row; pass `--allow-incomplete` to assess the actual latest
row instead and watch it return `anomaly_score: null` (never a made-up number).
For live streaming use `predict_observation` directly (it always assesses the
true latest row); `predict_latest_complete` is the testing/demo convenience that
skips a trailing incomplete row. Neither drops or imputes data — a missing reading
stays intact as evidence for dropout and health.

## Outputs

`predict_frame` → a tidy frame: `anomaly_score, is_anomaly, severity,
fused_status, fault_type, fault_confidence, legacy_label, fault_present,
structural_fault, reasons, health_status` (+ `explanation` when `explain=True`).

`predict_observation` → a JSON-serializable dict for the latest reading: the
score, typed fault, hedged SHAP explanation, fused evidence, the pipeline-sourced
Laya-typed decision, the detector verification, and rolling station health. The
result is **strictly** JSON-safe: when a core sensor is missing the score cannot
be computed, so `anomaly_score`, `explanation.score` and
`verification.isolation_forest_score` are `null` (never `NaN`, never fabricated).

The `health` block reports two distinct dimensions — do not conflate them:

- `health_status` — overall *recent* station health (HEALTHY / WATCH / DEGRADED /
  CRITICAL / UNKNOWN), from the rolling anomaly rate over the trailing window.
- `dominant_fault_in_range` — the most frequent typed fault *signature* over the
  history supplied. A station can be `HEALTHY` now yet show a historical dominant
  fault (e.g. `CALIBRATION_DRIFT`); the two answer different questions and are
  independent of whether the current observation could be scored.

## Testing

```bash
python -m pytest tests/ml -q
```

The suite is hermetic — it generates a small seeded synthetic multi-station frame
and trains a tiny model in a temp directory, so it needs neither the real NOAA
CSV nor the committed artifacts. It covers thermodynamics, leakage-free
splitting, baselines, feature/matrix invariants, detector calibration &
persistence, every classifier gating/priority rule, evidence-fusion honesty, the
Laya typed contract, imputation invariants, health status, and end-to-end
inference (including strict JSON serialization).


