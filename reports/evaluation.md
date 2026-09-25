# AWS Sentinel — ML Evaluation (injected faults on real holdout data)

- Test rows: **39,004**  |  injected rows: **3,994**  |  events: **190**
- Row-level detection: precision **0.5287**, recall **0.4427**, F1 **0.4819**
- Event-level recall: **0.9176** (167/182 events)
- False-positive rate on non-injected rows (UPPER BOUND — real data has genuine outliers): **0.045**

## Per-fault detection & typing

| Fault | injected | detected | row recall | typing acc (of detected) |
|---|---:|---:|---:|---:|
| SENSOR_DROPOUT | 353 | 353 | 1.0 | 1.0 |
| SENSOR_FREEZE | 367 | 198 | 0.5395 | 0.9646 |
| TRANSIENT_SPIKE | 36 | 29 | 0.8056 | 0.7241 |
| CALIBRATION_DRIFT | 3004 | 1019 | 0.3392 | 0.3768 |
| PHYSICAL_INCONSISTENCY | 97 | 97 | 1.0 | 0.9691 |
| MULTIVARIATE_ANOMALY | 137 | 72 | 0.5255 | 0.7778 |

## Detection latency (windowed faults)

| Fault | detected events | median latency (h) | mean latency (h) |
|---|---:|---:|---:|
| SENSOR_DROPOUT | 30 | 0.0 | 0.0 |
| SENSOR_FREEZE | 19 | 6.0 | 5.5 |
| TRANSIENT_SPIKE | 29 | 0.0 | 0.0 |
| CALIBRATION_DRIFT | 30 | 15.5 | 25.8 |
| PHYSICAL_INCONSISTENCY | 29 | 0.0 | 0.0 |
| MULTIVARIATE_ANOMALY | 30 | 0.0 | 0.317 |
