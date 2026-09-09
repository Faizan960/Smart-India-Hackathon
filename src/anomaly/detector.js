
// Frontend Anomaly Engine

// History store for baseline calculations
const history = {};

function getHistory(stationId, sensor) {
    const key = `${stationId}_${sensor}`;
    if (!history[key]) history[key] = [];
    return history[key];
}

export function detectAnomalies(sensorData) {
    const anomalies = [];
    const sensors = ['temperature', 'humidity', 'pressure', 'windSpeed'];
    
    // Add current observation to history
    sensors.forEach(sensor => {
        if (sensorData[sensor] !== undefined && sensorData[sensor] !== null) {
            const hist = getHistory(sensorData.id, sensor);
            hist.push({ val: sensorData[sensor], time: sensorData.timestamp });
            // Keep last 100 observations
            if (hist.length > 100) hist.shift();
            
            // 1. Z-Score Anomaly (SPIKE / DROP)
            if (hist.length > 10) {
                const values = hist.slice(0, hist.length - 1).map(h => h.val);
                const mean = values.reduce((a, b) => a + b, 0) / values.length;
                const variance = values.reduce((a, b) => a + Math.pow(b - mean, 2), 0) / values.length;
                const stdDev = Math.sqrt(variance) || 1; // avoid division by zero
                
                const zScore = Math.abs((sensorData[sensor] - mean) / stdDev);
                
                if (zScore > 3) {
                    anomalies.push({
                        id: crypto.randomUUID(),
                        timestamp: sensorData.timestamp,
                        stationId: sensorData.id,
                        sensor: sensor,
                        observed: sensorData[sensor],
                        expected: mean,
                        deviation: sensorData[sensor] - mean,
                        anomalyType: sensorData[sensor] > mean ? 'SPIKE' : 'DROP',
                        severity: zScore > 5 ? 'CRITICAL' : 'WARNING',
                        confidence: Math.min(0.99, 0.5 + (zScore / 10)),
                        evidence: `Z-Score of ${zScore.toFixed(1)} exceeds normal threshold.`,
                        status: 'NEW'
                    });
                }
            }
            
            // 2. Freeze Detection
            if (hist.length >= 5) {
                const recent = hist.slice(hist.length - 5).map(h => h.val);
                if (recent.every(v => v === recent[0])) {
                    anomalies.push({
                        id: crypto.randomUUID(),
                        timestamp: sensorData.timestamp,
                        stationId: sensorData.id,
                        sensor: sensor,
                        observed: sensorData[sensor],
                        expected: sensorData[sensor], // no deviation, just frozen
                        deviation: 0,
                        anomalyType: 'FREEZE',
                        severity: 'WARNING',
                        confidence: 0.85,
                        evidence: `Sensor value has not changed for 5 consecutive observations.`,
                        status: 'NEW'
                    });
                }
            }
        } else {
            // Missing Data Anomaly
            anomalies.push({
                id: crypto.randomUUID(),
                timestamp: sensorData.timestamp,
                stationId: sensorData.id,
                sensor: sensor,
                observed: null,
                expected: null,
                deviation: 0,
                anomalyType: 'MISSING_DATA',
                severity: 'CRITICAL',
                confidence: 1.0,
                evidence: `Sensor reading is null or undefined.`,
                status: 'NEW'
            });
        }
    });
    
    return anomalies;
}
