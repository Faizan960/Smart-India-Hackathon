import pandas as pd
import numpy as np
from datetime import datetime, timedelta

def generate_healthy_telemetry(station_id, start_time, n_points=4000, interval_minutes=5):
    """
    Generates realistic, physically plausible healthy telemetry data.
    """
    np.random.seed(42) # Deterministic for reproducible SIH demo
    
    timestamps = [start_time + timedelta(minutes=i*interval_minutes) for i in range(n_points)]
    
    # Base variations
    time_arr = np.arange(n_points)
    daily_cycle = np.sin(time_arr * interval_minutes * 2 * np.pi / (24 * 60))
    
    # Temperature: Daily cycle + smooth noise
    base_temp = 25.0
    temp = base_temp + 6.0 * daily_cycle + np.random.normal(0, 0.5, n_points)
    
    # Humidity: Inverse to temperature + smooth noise
    base_humidity = 60.0
    humidity = base_humidity - 15.0 * daily_cycle + np.random.normal(0, 2.0, n_points)
    humidity = np.clip(humidity, 0, 100)
    
    # Pressure: Slow variation
    pressure_cycle = np.sin(time_arr * interval_minutes * 2 * np.pi / (72 * 60)) # 3 day cycle
    pressure = 1010 + 5.0 * pressure_cycle + np.random.normal(0, 0.2, n_points)
    
    # Wind: Irregular but positive
    wind_speed = np.abs(5.0 + 3.0 * np.sin(time_arr / 50) + np.random.normal(0, 1.5, n_points))
    
    df = pd.DataFrame({
        "timestamp": timestamps,
        "station_id": station_id,
        "temperature": temp,
        "humidity": humidity,
        "pressure": pressure,
        "wind_speed": wind_speed
    })
    
    return df
