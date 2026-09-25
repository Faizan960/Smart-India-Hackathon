# AWS Sentinel — ML Pipeline Deliverables

A summary of what was built for the sensor fault-detection intelligence layer
(SIH 26073), what is verified, and what the honest measured numbers are. Nothing
here is fabricated: every metric is reproduced verbatim from the committed
`reports/*.json` artifacts, and every claim is traceable to a module or test.

## What was delivered

A real-data ML pipeline living entirely in `ml/pipeline/` — an **isolated**
subpackage that runs alongside the existing code and touches the legacy
`api/`, `ml/inference.py` and `ml/classifier.py` in no way. It ingests real
meteorological observations, learns per-station/season/hour normals, flags
anomalies with a calibrated score, types the fault from transparent signatures,
explains why, and emits a Laya-typed decision verified by an independent detector.

The 10-phase architecture (spec section 36) is documented in
[docs/ML_PIPELINE.md](../docs/ML_PIPELINE.md). This report covers the supporting
deliverables built on top of that pipeline:

- **`tests/ml/`** — a hermetic pytest suite (see below).
- **[docs/ML_PIPELINE.md](../docs/ML_PIPELINE.md)** — architecture, usage, and
  measured-performance documentation.
- **`requirements.txt`** — pinned additions (PyYAML, pyarrow, shap, pytest).
- **`.gitignore`** — excludes raw/processed/injected data and `*.joblib` artifacts.

## Data provenance (honesty statement)

The model is trained on **NOAA Integrated Surface Database (ISD)** composite CSV
for three Indian surface stations (`data/Raw/4398394.csv`). It is **not IMD data**
and is never represented as such (spec section 2). Observed provenance, verbatim
from `reports/training_summary.json`:

- 216,712 observations across stations `42071099999`, `43063099999`, `43117099999`
- Chronological split (no shuffling): train ends `2011-07-17`, val ends `2013-05-20`
- 151,698 train / 32,507 val / 32,507 test rows; 87,917 complete training rows
- Logistic score calibration anchored on the *training* raw-score distribution
  (95th percentile → 0.5), so the mapping is derived from data, never hand-tuned.

## Test suite

`python -m pytest tests/ml -q` → **75 passed** (~9 s), verified this session.

The suite is fully hermetic: it generates a small seeded synthetic multi-station
frame and trains a tiny model in a temp directory, so it depends on neither the
git-ignored NOAA CSV nor the committed `models/sentinel/` artifacts. 12 test
modules (+ `conftest.py`) cover:

- thermodynamics (`test_physics`) — es/VPD/dew-point identities, supersaturation flag
- leakage-free chronological split (`test_preprocessing`) and QC flags
- robust diurnal baselines (`test_baseline`) — structure, clipping, save/load
- feature/matrix invariants (`test_features`) — completeness, finiteness, rates
- detector calibration & persistence (`test_detector`) — bounds, NaN-on-incomplete
- every classifier gating/priority rule (`test_classifier`) — freeze gate, priority
- evidence-fusion honesty (`test_evidence`) — no phantom reasons on NORMAL
- the Laya typed contract (`test_laya_adapter`) — never averages, honest failure
- imputation invariants (`test_imputation`) — short-gap fill, long/leading gaps left
- rolling health status (`test_health`)
- end-to-end inference (`test_inference`) — schema, ranges, strict JSON serialization
- import smoke over all 19 `ml.pipeline.*` modules (`test_imports`)

## Measured performance

Measured on the held-out real NOAA test split with injected synthetic faults
(`python -m ml.pipeline.evaluator --seed 42`); numbers verbatim from
`reports/evaluation.json`. Split: 32,507 test rows, 3,986 injected fault rows,
190 injected events.

- **Event-level recall 0.9121** (166 / 182 scoreable events) — the headline
  operational metric: did the station raise the fault at all, and promptly?
- Row-level: precision 0.5549, recall 0.3954, F1 0.4618 (tp 1576 / fp 1264 / fn 2410).
- False-positive rate on non-injected rows ≤ **0.0443** (1264 / 28521) — an
  *upper* bound, since unlabelled real rows may contain genuine sensor issues.

Per-fault (row_recall / typing accuracy of detected / median latency):

| Fault | row_recall | typing | median latency |
|-------|-----------:|-------:|---------------:|
| SENSOR_DROPOUT | 1.00 | 1.00 | 0 h |
| PHYSICAL_INCONSISTENCY | 1.00 | 0.99 | 0 h |
| TRANSIENT_SPIKE | 0.78 | 0.71 | 0 h |
| SENSOR_FREEZE | 0.58 | 0.94 | 6 h |
| MULTIVARIATE_ANOMALY | 0.48 | 0.83 | 0 h |
| CALIBRATION_DRIFT | 0.27 | 0.39 | 27 h |

Honest caveats (spec section 35): calibration drift is the hardest case — a slow
offset resembles slowly shifting real weather, so its row-recall is 0.27, median
latency 27 h, and 419 of its detected rows are typed SENSOR_FREEZE (a slow ramp
can look locally flat). Structural faults (dropout, physical inconsistency) reach
1.00 row-recall because they are read off raw evidence, not a learned score. The
injected faults are a proxy for real hardware failure — treat the numbers as
indicative, not as a field-validated failure-detection rate.

## Files delivered

```
ml/pipeline/            19 modules (isolated; see docs/ML_PIPELINE.md table)
tests/ml/               conftest.py + 12 test modules (hermetic, 75 tests)
docs/ML_PIPELINE.md     architecture, usage, measured performance
reports/                training_summary.json, evaluation.json, DELIVERABLES.md
models/sentinel/        trained artifacts (detector, thresholds, baselines)
requirements.txt        pinned deps (PyYAML, pyarrow, shap, pytest added)
.gitignore              excludes data/Raw|processed|injected + *.joblib
```

## Reproduce

```bash
python -m ml.pipeline.train --input data/Raw/4398394.csv   # fit + write models/reports
python -m ml.pipeline.evaluator --seed 42                  # honest held-out metrics
python -m pytest tests/ml -q                               # 75 hermetic tests
```

## Constraints honored

- **Git isolation** — all work is on `feature/aws-sentinel-real-ml`; nothing was
  committed to, merged into, or reset on `main`, and no history was rewritten.
- **No false claims (section 35)** — no hard-coded demo outputs; metrics and
  provenance are read verbatim from `reports/*.json`; language is hedged.
- **Laya contract (section 18)** — the adapter reuses the existing `ml/laya_base`
  typed `fault_type` choice + `fault_present` noul; Laya is never trained on raw
  observations and its decision is never averaged with the Isolation Forest.

