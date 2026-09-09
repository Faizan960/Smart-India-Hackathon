# SIH26073 — AWS Anomaly Detection Prototype

Working MVP for "AI/ML-Based Intelligent Anomaly Detection for Automatic
Weather Stations (AWS)" — Ministry of Earth Sciences.

## Run it

```
pip install pandas numpy --break-system-packages   # if not already installed
python3 pipeline.py
```

This will:
1. Generate a synthetic 2-station AWS stream (temperature/pressure/humidity,
   5-min intervals, ~5 days) with injected spikes, freezes, drift, dropouts,
   and cross-sensor inconsistencies, each with ground-truth labels.
2. Run the data-quality gate + hybrid anomaly detector ensemble.
3. Fuse signals into anomaly type / severity / confidence / plain-English reason.
4. Score sensor health per station.
5. Evaluate against ground truth (precision/recall/F1/false-alert rate).
6. Write `data/pipeline_output.csv` and `data/dashboard_payload.json`.

## Current benchmark (synthetic data)

| Metric | Value |
|---|---|
| Precision | 78.7% |
| Recall | 48.2% |
| F1 | 0.60 |
| False alert rate | 5.1% |

Per fault type recall: freeze 100%, dropout 100%, cross-sensor 100%, spike 75%,
**drift 25%** (hardest type — gradual drift is inherently the toughest to
separate from natural diurnal variation; worth the most engineering time
before the internal round).

## Files

- `data_gen.py` — synthetic AWS stream + anomaly injection + ground truth
- `quality.py` — structural data-quality gate (missing/frozen/out-of-range)
- `detectors.py` — 3 independent detectors: statistical z-score, temporal
  drift, multivariate (cross-sensor) consistency
- `fusion.py` — combines detector signals into type/severity/confidence + a
  human-readable explanation (this is your "explainability" story for judges)
- `health.py` — rolling sensor-health score + degradation trend
- `pipeline.py` — orchestrates everything + evaluation + dashboard JSON export

## Next steps toward a full MVP

1. **Real data**: swap `data_gen.py` for actual IMD/MoES AWS historical data
   if the sponsor provides it — the pipeline interface (a DataFrame with
   timestamp/station_id/temperature_c/pressure_hpa/humidity_pct) stays the same.
2. **Improve drift detection**: current recall is weak (25%) — consider a
   CUSUM (cumulative sum) test or a proper seasonal-decomposition baseline
   instead of the simple short-vs-long rolling mean.
3. **Live dashboard**: `pipeline.py` already exports `dashboard_payload.json`
   in a shape ready for a live-replay dashboard (time series + alerts +
   health trend + incident timeline).
4. **Edge deployment stretch goal**: only attempt after the cloud pipeline is
   stable, per the evaluation weighting (Energy/Deployability are 10% each,
   Innovation/Accuracy are 25%/20% — don't over-invest early).
