import json
import urllib.request
import threading
import time
from http.server import HTTPServer
from api.inference import handler

def run_server():
    server = HTTPServer(('localhost', 3001), handler)
    server.serve_forever()

if __name__ == "__main__":
    t = threading.Thread(target=run_server)
    t.daemon = True
    t.start()
    
    time.sleep(1)
    
    history = [
        {"timestamp": "2026-09-20T10:00:00", "temperature": 25.1, "humidity": 60, "pressure": 1010, "wind_speed": 5.2},
        {"timestamp": "2026-09-20T10:05:00", "temperature": 25.2, "humidity": 59, "pressure": 1010.1, "wind_speed": 5.1},
        {"timestamp": "2026-09-20T10:10:00", "temperature": 25.3, "humidity": 58, "pressure": 1010.2, "wind_speed": 5.3},
        {"timestamp": "2026-09-20T10:15:00", "temperature": 25.1, "humidity": 60, "pressure": 1010, "wind_speed": 5.2},
        {"timestamp": "2026-09-20T10:20:00", "temperature": 25.2, "humidity": 59, "pressure": 1010.1, "wind_speed": 5.1},
        {"timestamp": "2026-09-20T10:25:00", "temperature": 45.3, "humidity": 58, "pressure": 1010.2, "wind_speed": 5.3}
    ]

    data = json.dumps({"history": history}).encode("utf-8")
    req = urllib.request.Request("http://localhost:3001/", data=data, headers={"Content-Type": "application/json"})

    try:
        response = urllib.request.urlopen(req)
        print("Status:", response.status)
        print("Body:", response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        print("HTTP Error:", e.code)
        print("Error Body:", e.read().decode("utf-8"))
    except Exception as e:
        print("Error:", e)
