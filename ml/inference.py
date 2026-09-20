import os
import joblib
import pandas as pd
from .features import extract_features

def predict_anomaly(df_history):
    """
    Given a dataframe containing the recent history of a single station 
    (including the current observation as the last row),
    calculates features, runs ML inference, and returns anomaly status.
    
    Returns a dict with anomaly score, is_anomaly (bool)
    """
    # Check if models exist
    base_dir = os.path.dirname(os.path.abspath(__file__))
    scaler_path = os.path.join(base_dir, 'models', 'scaler.joblib')
    model_path = os.path.join(base_dir, 'models', 'isolation_forest.joblib')
    
    if not os.path.exists(scaler_path) or not os.path.exists(model_path):
        return {"error": "ML Models not found. Train models first."}
        
    scaler = joblib.load(scaler_path)
    model = joblib.load(model_path)
    
    # Extract features for all rows in history
    features_df = extract_features(df_history)
    
    # We only care about the prediction for the CURRENT (last) observation
    # But rolling features need the history.
    last_observation_features = features_df.iloc[-1:]
    
    # If there are NaNs due to insufficient history, fill them safely
    last_observation_features = last_observation_features.bfill().fillna(0)
    
    scaled_data = scaler.transform(last_observation_features.to_numpy())
    
    # IsolationForest predict returns 1 for inliers, -1 for outliers
    prediction = model.predict(scaled_data)[0]
    
    # score_samples gives opposite of anomaly score (closer to 0 is normal, more negative is abnormal)
    # Convert to a 0-1 range where 1 is highly anomalous
    raw_score = model.score_samples(scaled_data)[0]
    
    # Typical IsolationForest scores are between -1.0 and 0.5.
    # Map raw_score to a 0-1 probability-like confidence.
    # We can say a score < -0.5 is high confidence anomaly
    anomaly_score = min(1.0, max(0.0, -raw_score))
    
    is_anomaly = bool(prediction == -1)
    
    return {
        "is_anomaly": is_anomaly,
        "anomaly_score": anomaly_score,
        "raw_score": float(raw_score)
    }
