from http.server import BaseHTTPRequestHandler
import json
import os
import sys
import pandas as pd
import traceback

# Add the root project directory to the Python path so it can find 'ml' module
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ml.inference import predict_anomaly
from ml.classifier import classify_fault

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
            post_data = self.rfile.read(content_length)
            
            req_json = json.loads(post_data.decode('utf-8'))
            history_data = req_json.get("history", [])
            
            if not history_data or len(history_data) == 0:
                self._send_error(400, "Missing history data")
                return
                
            # Convert to DataFrame
            df = pd.DataFrame(history_data)
            
            # Predict
            anomaly_res = predict_anomaly(df)
            if "error" in anomaly_res:
                self._send_error(500, anomaly_res["error"])
                return
                
            # Classify
            fault_res = classify_fault(df, anomaly_res)
            
            result = {
                **anomaly_res,
                **fault_res
            }
            
            self._send_success(result)
            
        except Exception as e:
            tb = traceback.format_exc()
            self._send_error(500, f"Internal Error: {str(e)}\nTraceback:\n{tb}")

    def _send_success(self, data):
        self.send_response(200)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode('utf-8'))
        
    def _send_error(self, code, message):
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps({"error": message}).encode('utf-8'))
