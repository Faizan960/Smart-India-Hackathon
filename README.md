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

## Live IMD Integration

The frontend dashboard is now integrated directly with the official India Meteorological Department AWS API.

- **Official Source**: India Meteorological Department AWS API
- **Endpoint**: `https://api.imd.gov.in/api/v1/aws_data`
- **Prototype Station**: NDL (Lodi Road, New Delhi)

### Connection Modes
The application supports several data-fetching modes to handle network unreliability:
1. **LIVE**: Successfully fetched the latest real-time observation from IMD.
2. **CACHED**: If IMD is unreachable, the application falls back to the most recent successful observation stored locally.
3. **ERROR**: No live observation could be reached and no cache exists.
4. **DEMO**: Uses synthetic data for demonstration purposes (clearly labeled in the UI).

### Local History & Anomaly Limitations
The IMD endpoint provides current observations only, not complete historical time series. To enable anomaly detection, the application implements **local observation history**. 
Every 5 minutes, it collects and persists the live observation locally (up to 288 points, approx. 24 hours). 

**Important Constraints**:
- The application does not claim to have historical IMD coverage from before it was started. It only plots observations it has actively collected.
- Statistical anomaly detection (e.g., Z-Score for spikes) requires at least 6 consecutive observations. The anomaly engine will not force or fabricate anomalies on startup; it waits until a sufficient local baseline is established.
