# AWS Sentinel — SIH 26073

**AI/ML-Based Intelligent Anomaly Detection for Automatic Weather Stations**

AWS Sentinel is an advanced telemetry monitoring and anomaly detection dashboard designed for Automatic Weather Stations (AWS). It continuously ingests meteorological data, visually tracks climate patterns over 30 days, and utilizes an AI/ML inference pipeline to detect sensor faults and climatic anomalies in real-time. 

Built for the **Smart India Hackathon (SIH 2026)**.

---

## 🏗 Architecture Overview

The system is designed around a decoupled, serverless architecture optimized for edge-rendering and stateless ML inference.

### 1. Frontend (Vanilla JS / Edge)
- **Zero-Dependency Core**: Built with pure HTML, CSS, and Vanilla JavaScript for maximum performance and minimal overhead. No heavy frameworks (React/Vue/Angular) are used.
- **Reactive State Management**: Uses a custom Pub/Sub `store.js` that acts as the single source of truth, managing live polling, historical caching, and ML synchronization.
- **Dynamic Visualization**: Uses `Chart.js` with a linear time-scale dynamically anchored to the current client time, allowing seamless transitions between 24-hour, 7-day, and 30-day temporal windows.

### 2. Data Pipeline & Telemetry Fusion
The platform intelligently merges two distinct data sources into a unified monotonic timeline:
- **30-Day Historical Data (Open-Meteo)**: The backend securely proxies the free Open-Meteo Archive API to fetch the last 744 hours (30 days) of real meteorological data for the selected station. This is cached in the browser's `localStorage` for 2 hours to optimize API quotas.
- **Live Polling (OpenWeatherMap)**: The frontend polls the OWM API periodically. 
- **Time-Series Deduplication**: Upstream providers often cache their data (e.g., OWM `dt` field updates slowly). To prevent collapsing the time-series, the system deduplicates and anchors observations using a monotonic `receivedEpoch` while preserving the original `observedEpoch`.

### 3. AI/ML Inference Engine (Python Serverless)
- **Model**: Scikit-Learn `IsolationForest` (Unsupervised Anomaly Detection).
- **Inference Environment**: Vercel Python 3.12 Serverless Functions (`/api/inference`).
- **Feature Engineering**: The pipeline receives a rolling window of recent telemetry (last 24 points). It computes moving averages, standard deviations, and temporal derivatives (e.g., sudden temperature spikes, unnatural humidity drops) before passing them to a `StandardScaler`.
- **Fault Classification**: Anomalies flagged by the Isolation Forest are categorized into specific fault types (e.g., `SENSOR_STUCK`, `NOISE_SPIKE`, `UNKNOWN_ANOMALY`) based on secondary threshold heuristics.

---

## 🛠 Technical Stack

### **Frontend**
- HTML5, CSS3 (CSS Variables for Dark/Light theme switching)
- Vanilla JavaScript (ES6+)
- Chart.js (Data Visualization)

### **Backend / API (Vercel)**
- Node.js (`/api/weather/history`, `/api/weather/current`)
- Python 3.12 (`/api/inference`)

### **Machine Learning**
- Scikit-Learn 1.7.2
- Pandas 2.3.3
- NumPy 2.3.5
- Joblib 1.5.2

---

## 🚀 Key Features

* **Unified Telemetry Graphing**: Seamlessly visualizes real 30-day historical data alongside live-polled data without arbitrary timeline shifts.
* **Stateless ML Pipeline**: The frontend strictly limits payloads (sending only the trailing 24 data points) to protect the Vercel Python endpoint from massive historical arrays, keeping compute times < 200ms.
* **Fault Injection Engine (Demo Mode)**: Includes a built-in anomaly injection UI. Presenters can inject synthetic data (e.g., an instant +15°C temperature spike) directly into the live data stream to visually demonstrate the ML model catching and classifying the fault in real time.
* **Graceful Degradation**: If the ML API goes down or times out, the system automatically falls back to an offline Z-score heuristic detector, ensuring the dashboard never stops monitoring.

---

## ⚙️ Local Development

### 1. Prerequisites
- Node.js (v18+)
- Python (Strictly **3.12** for Vercel ABI compatibility)
- Vercel CLI (`npm i -g vercel`)

### 2. Environment Setup
Create a `.env.local` file in the root directory:
```env
WEATHER_PROVIDER=openweathermap
OPENWEATHERMAP_API_KEY=your_owm_api_key
```

### 3. Run Locally
Use the Vercel CLI to boot both the Node.js frontend/proxy and the Python ML backend simultaneously:
```bash
vercel dev
```

### 4. Machine Learning Modification
If you wish to retrain the models:
1. Navigate to the `/ml` directory.
2. Ensure you train your models using a Pandas DataFrame so that `StandardScaler` saves `feature_names_in_`.
3. Save your outputs (`scaler.joblib` and `isolation_forest.joblib`) to the `ml/models/` directory.

---

## ☁️ Deployment

The project is configured for one-click deployment on **Vercel**.

1. Connect the repository to Vercel.
2. In the Vercel dashboard, navigate to **Settings > Environment Variables**.
3. Add `OPENWEATHERMAP_API_KEY` for **Production** and **Preview** environments.
4. Deploy!

*(Note: Vercel automatically detects the `.python-version` file and provisions a Python 3.12 runtime environment, resolving NumPy/Pandas C-extension compilation issues).*

---

*Built by [AWS Sentinel Team] for Smart India Hackathon 2026*
