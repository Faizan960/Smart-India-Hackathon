# AWS Sentinel

## SIH26073
Working MVP for "AI/ML-Based Intelligent Anomaly Detection for Automatic Weather Stations (AWS)" — Ministry of Earth Sciences.

## Architecture
The application is a lightweight ES-module-based frontend backed by Vercel Serverless functions.
- **UI ↓ Store ↓ Provider ↓ Backend API**
- The UI contains no business logic for data fetching. It subscribes to the central store.

## Requirements
The frontend requires no package manager dependencies to build (native ES modules).
The Python pipeline requires dependencies for the ML engine:
- `numpy`
- `pandas`
- `scikit-learn`
- `joblib`

## Local Setup
Clone the repository and set up your Python environment:
### Windows
```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```
### Linux/macOS
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Environment Variables
Create a `.env.local` file in the root of the project:
```env
WEATHER_PROVIDER=openweathermap
OPENWEATHERMAP_API_KEY=YOUR_KEY_HERE
```
> [!CAUTION]
> **Never commit your `.env.local` file.**

For the map frontend, create a `src/config.local.js` file:
```js
export const LOCAL_CONFIG = {
  CARTO_BASEMAP_KEY: "YOUR_CARTO_KEY_HERE"
};
```
> [!CAUTION]
> **Never commit your `src/config.local.js` file.**

The project uses two separate credentials:
1. **OPENWEATHERMAP_API_KEY**: Used strictly on the backend to fetch live telemetry. It is securely kept on the server (`.env.local`) and never exposed to the frontend.
2. **CARTO_BASEMAP_KEY**: Used to authenticate the CARTO map tiles (Voyager and Dark Matter). The frontend retrieves this configuration via the ignored `src/config.local.js`.

For Vercel deployment:
Go to **Project → Settings → Environment Variables** and add `WEATHER_PROVIDER` and `OPENWEATHERMAP_API_KEY`. (CARTO configuration must be injected into the static build or handled accordingly for production, but locally uses `config.local.js`).

## Live Weather Provider
The application uses OpenWeatherMap to fetch real-time weather telemetry. 
- The credential is only accessed server-side via the Vercel function `/api/weather/current`.
- The frontend will gracefully fall back to local `CACHED` mode if the API is unreachable.
- The original IMD integration is preserved and can be used in the future by changing the provider in the configuration.

## ML Architecture & Anomaly Detection
AWS Sentinel uses an unsupervised **Isolation Forest** model trained on healthy synthetic weather telemetry to identify abnormal station observations. 

**Data Flow:**
1. **Healthy synthetic historical data** is generated (with diurnal cycles and appropriate noise).
2. **Feature engineering** extracts temporal features (`hour_sin`, `hour_cos`) and rolling statistical features (means, standard deviations).
3. A **StandardScaler** scales the features.
4. An **Isolation Forest** is trained to learn the boundaries of normal telemetry and exported to `ml/models/`.
5. **Inference API**: A Vercel Python Serverless Function (`/api/inference`) receives real-time telemetry history from the frontend.
6. **Fault Classification**: If the model detects an anomaly, a deterministic classifier assigns a specific fault type (e.g., `TEMPERATURE_SPIKE`, `SENSOR_FREEZE`).

*Note: The prototype includes controlled fault injection to demonstrate detection and classification of common AWS sensor failure patterns. The model is NOT trained on nationwide IMD historical data and is currently a proof-of-concept for SIH.*

## Demo Mode (Anomaly Injection)
For SIH judging and evaluation, a **Demo Control Panel** is integrated into the frontend. 
This allows injecting synthetic faults into the telemetry pipeline.
- It is clearly separated from live data and labeled as **DEMO DATA / CONTROLLED SIMULATION**.
- The injected anomaly modifies the raw observation and is routed through the **exact same ML inference path** as real data.
- The UI features a `RESET DEMO` button to clear injected faults and resume normal behavior.

## Running the ML Training Pipeline
```bash
python ml/train.py
```
This generates the synthetic healthy dataset, fits the scaler and Isolation Forest, and saves the `.joblib` artifacts for inference.

## Running the Web Application
The web app is optimized for Vercel. 
If you have the Vercel CLI installed (`npm install -g vercel`), simply run:
```bash
npm run dev
```
(Or run `vercel dev` directly). 
This will spin up a local development server on port 3000 and run the serverless API proxy.

## Security
- The `.gitignore` protects all environment files.
- No secrets are exposed to the browser.
- The API key is securely routed through the Vercel proxy.

## Current Limitations
- Historical data is collected locally in the browser (up to 1440 points). The application does not pull historical time-series data from the live API.
