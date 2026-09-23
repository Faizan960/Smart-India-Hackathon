"""Serverless inference endpoint (Vercel Python function).

Bridges the existing dashboard's ``POST /api/inference`` call to the NEW real-data
AWS Sentinel pipeline (``ml/pipeline``) via :func:`ml.pipeline.live_adapter.assess_live`.
The legacy ``ml/inference.py`` + ``ml/classifier.py`` path is intentionally no
longer used here (those files are left untouched as the previous checkpoint).

Request  (unchanged contract):  {"history": [ {timestamp, temperature, humidity,
                                 pressure, windSpeed}, ... ],
                                 "station_id"?, "latitude"?, "longitude"? }
Response (superset of the old contract): is_anomaly, anomaly_score, fault_type,
    confidence  (legacy fields the dashboard already reads)  PLUS  severity,
    fused_status, reasons, explanation, laya_decision, verification, health,
    baseline_source, data_complete (richer Sentinel output).

The response is serialized with ``allow_nan=False`` so a NaN/Infinity can never
silently reach the client -- an unavailable score is ``null``, never fabricated.
"""
from http.server import BaseHTTPRequestHandler
import json
import os
import sys
import traceback

# Make the repo-root packages (``ml``) importable from the serverless bundle.
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ml.pipeline.live_adapter import assess_live  # noqa: E402


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_POST(self):
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length) if content_length else b""
            req_json = json.loads(post_data.decode('utf-8')) if post_data else {}

            history = req_json.get("history", [])
            if not isinstance(history, list) or len(history) == 0:
                self._send_error(400, "Missing history data")
                return

            result = assess_live(
                history,
                station_id=req_json.get("station_id") or req_json.get("stationId"),
                latitude=req_json.get("latitude"),
                longitude=req_json.get("longitude"),
            )
            self._send_success(result)

        except Exception as e:
            tb = traceback.format_exc()
            self._send_error(500, f"Internal Error: {str(e)}\nTraceback:\n{tb}")

    def _send_success(self, data):
        # Strict: no NaN/Infinity may reach the client (they are invalid JSON and
        # would misrepresent an unavailable score). predict_observation guarantees
        # a JSON-safe dict, so this never raises in normal operation.
        body = json.dumps(data, allow_nan=False).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(body)

    def _send_error(self, code, message):
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps({"error": message}).encode('utf-8'))
