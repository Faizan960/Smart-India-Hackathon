import pandas as pd
import numpy as np

def extract_features(df):
    """
    Given a dataframe sorted by time (for a single station), 
    extracts rolling and temporal features.
    """
    # Create a copy to avoid SettingWithCopyWarning
    df_feat = df.copy()
    
    # Ensure timestamp is datetime
    if not pd.api.types.is_datetime64_any_dtype(df_feat['timestamp']):
        df_feat['timestamp'] = pd.to_datetime(df_feat['timestamp'])
        
    # Temporal features (hour of day)
    hour = df_feat['timestamp'].dt.hour + df_feat['timestamp'].dt.minute / 60.0
    df_feat['hour_sin'] = np.sin(hour * (2. * np.pi / 24))
    df_feat['hour_cos'] = np.cos(hour * (2. * np.pi / 24))
    
    # Rolling features (e.g. 1 hour = 12 * 5-min intervals)
    window = 12
    
    for col in ['temperature', 'humidity', 'pressure', 'wind_speed']:
        df_feat[f'{col}_rolling_mean'] = df_feat[col].rolling(window=window, min_periods=1).mean()
        # use fillna(0) for std since it might be NaN if min_periods=1 and count=1
        df_feat[f'{col}_rolling_std'] = df_feat[col].rolling(window=window, min_periods=2).std().fillna(0)
    
    # Drop timestamp and station_id for the final feature matrix
    feature_cols = [
        'temperature', 'humidity', 'pressure', 'wind_speed',
        'hour_sin', 'hour_cos',
        'temperature_rolling_mean', 'temperature_rolling_std',
        'humidity_rolling_mean', 'humidity_rolling_std',
        'pressure_rolling_mean', 'pressure_rolling_std',
        'wind_speed_rolling_mean', 'wind_speed_rolling_std'
    ]
    
    return df_feat[feature_cols]
