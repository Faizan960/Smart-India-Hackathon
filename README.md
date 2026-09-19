# AWS Sentinel

## SIH26073
Working MVP for "AI/ML-Based Intelligent Anomaly Detection for Automatic Weather Stations (AWS)" — Ministry of Earth Sciences.

## Architecture
The application is a lightweight ES-module-based frontend backed by Vercel Serverless functions.
- **UI ↓ Store ↓ Provider ↓ Backend API**
- The UI contains no business logic for data fetching. It subscribes to the central store.

## Requirements
The frontend requires no package manager dependencies to build (native ES modules).
The Python pipeline requires minimal dependencies:
- `numpy`
- `pandas`

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
WEATHER_PROVIDER=weatherapi
WEATHERAPI_KEY=YOUR_KEY_HERE
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
1. **WEATHERAPI_KEY**: Used strictly on the backend to fetch live telemetry. It is securely kept on the server (`.env.local`) and never exposed to the frontend.
2. **CARTO_BASEMAP_KEY**: Used to authenticate the CARTO map tiles (Voyager and Dark Matter). The frontend retrieves this configuration via the ignored `src/config.local.js`.

For Vercel deployment:
Go to **Project → Settings → Environment Variables** and add `WEATHER_PROVIDER` and `WEATHERAPI_KEY`. (CARTO configuration must be injected into the static build or handled accordingly for production, but locally uses `config.local.js`).

## Live Weather Provider
The application uses WeatherAPI to fetch real-time weather telemetry. 
- The credential is only accessed server-side via the Vercel function `/api/weather/current`.
- The frontend will gracefully fall back to local `CACHED` mode if the API is unreachable.
- The original IMD integration is preserved and can be used in the future by changing the provider in the configuration.

## Demo Mode
A deterministic synthetic demo pipeline is kept separately available for development and evaluation when real telemetry is unavailable. It must always show **DEMO DATA** and never **LIVE**.

## Anomaly Detection
The anomaly detection engine waits until sufficient real observations (>= 6) are collected before generating a statistical baseline. It will not force anomalies onto live data.

## Running the Python Pipeline
```bash
python pipeline.py
```
This generates synthetic streams, evaluates the hybrid anomaly detectors, and exports evaluation metrics.

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
- Historical data is collected locally in the browser (up to 288 points). The application does not pull historical time-series data from the live API.
