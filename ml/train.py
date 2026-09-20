import os
import pandas as pd
from datetime import datetime
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler
import joblib

from data_gen import generate_healthy_telemetry
from features import extract_features

def train_model():
    print("Generating healthy telemetry data...")
    start_time = datetime(2026, 1, 1)
    df = generate_healthy_telemetry("DL-001", start_time, n_points=10000)
    
    print("Extracting features...")
    features_df = extract_features(df)
    
    # Handle any potential NaNs (e.g., if rolling mean doesn't have min_periods=1)
    features_df = features_df.bfill().fillna(0)
    
    print("Fitting Scaler...")
    scaler = StandardScaler()
    # Use .to_numpy() to prevent scikit-learn from serializing pandas dtypes
    scaled_data = scaler.fit_transform(features_df.to_numpy())
    
    print("Training Isolation Forest...")
    # contamination defines the proportion of outliers in the data set. 
    # Since data is generated healthy, we use a very low contamination 
    # to define the tight boundaries of normal behavior.
    clf = IsolationForest(n_estimators=100, contamination=0.01, random_state=42)
    clf.fit(scaled_data)
    
    print("Saving models...")
    os.makedirs('models', exist_ok=True)
    joblib.dump(scaler, 'models/scaler.joblib')
    joblib.dump(clf, 'models/isolation_forest.joblib')
    print("Models saved successfully in 'models/' directory.")

if __name__ == "__main__":
    train_model()
