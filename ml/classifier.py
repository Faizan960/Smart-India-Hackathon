import pandas as pd

def classify_fault(df_history, anomaly_result):
    """
    Determines the specific fault type based on the anomaly result and recent history.
    """
    if not anomaly_result.get("is_anomaly", False):
        return {"fault_type": "NORMAL", "confidence": 1.0}
    
    current = df_history.iloc[-1]
    history_no_current = df_history.iloc[:-1]
    
    if len(history_no_current) < 3:
        return {"fault_type": "UNKNOWN_ANOMALY", "confidence": 0.5}
        
    # Temporal histories
    temp_hist = history_no_current['temperature'].dropna()
    
    # 1. Missing data check (Sensor Dropout)
    if pd.isna(current.get('temperature')) or pd.isna(current.get('humidity')):
        return {"fault_type": "SENSOR_DROPOUT", "confidence": 0.99}
        
    mean_temp = temp_hist.mean()
    std_temp = temp_hist.std()
    if pd.isna(std_temp) or std_temp == 0:
        std_temp = 0.1
    
    # 2. Temperature Spike / Drop
    z_temp = (current['temperature'] - mean_temp) / std_temp
    if z_temp > 4:
        return {"fault_type": "TEMPERATURE_SPIKE", "confidence": min(0.99, 0.5 + abs(z_temp)/20)}
    elif z_temp < -4:
        return {"fault_type": "TEMPERATURE_DROP", "confidence": min(0.99, 0.5 + abs(z_temp)/20)}
        
    # 3. Sensor Freeze
    if len(temp_hist) >= 4:
        last_temps = list(temp_hist[-4:]) + [current['temperature']]
        if len(set(last_temps)) == 1:
            return {"fault_type": "SENSOR_FREEZE", "confidence": 0.95}
            
    # 4. Sensor Drift
    # Check if there's a monotonic increase or decrease over the last N readings
    if len(temp_hist) >= 5:
        last_temps = list(temp_hist[-5:]) + [current['temperature']]
        diffs = [last_temps[i] - last_temps[i-1] for i in range(1, len(last_temps))]
        if all(d > 0.1 for d in diffs) or all(d < -0.1 for d in diffs):
            return {"fault_type": "SENSOR_DRIFT", "confidence": 0.85}

    # 5. Pressure / Humidity checks
    pres_hist = history_no_current['pressure'].dropna()
    hum_hist = history_no_current['humidity'].dropna()
    
    if not pd.isna(current.get('pressure')) and len(pres_hist) > 0:
        z_pres = (current['pressure'] - pres_hist.mean()) / (pres_hist.std() or 0.1)
        if abs(z_pres) > 4:
            return {"fault_type": "PRESSURE_SPIKE" if z_pres > 0 else "PRESSURE_DROP", "confidence": 0.8}
            
    if not pd.isna(current.get('humidity')) and len(hum_hist) > 0:
        z_hum = (current['humidity'] - hum_hist.mean()) / (hum_hist.std() or 0.1)
        if abs(z_hum) > 4:
            return {"fault_type": "HUMIDITY_SPIKE" if z_hum > 0 else "HUMIDITY_DROP", "confidence": 0.8}
            
    # Default fallback
    return {"fault_type": "UNKNOWN_ANOMALY", "confidence": 0.6}
