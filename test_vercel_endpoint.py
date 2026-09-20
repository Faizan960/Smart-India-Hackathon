import json
import urllib.request

history = [
    {"timestamp": "2026-09-20T10:00:00", "temperature": 25.1, "humidity": 60, "pressure": 1010, "wind_speed": 5.2},
    {"timestamp": "2026-09-20T10:05:00", "temperature": 25.2, "humidity": 59, "pressure": 1010.1, "wind_speed": 5.1},
    {"timestamp": "2026-09-20T10:10:00", "temperature": 25.3, "humidity": 58, "pressure": 1010.2, "wind_speed": 5.3},
    {"timestamp": "2026-09-20T10:15:00", "temperature": 25.1, "humidity": 60, "pressure": 1010, "wind_speed": 5.2},
    {"timestamp": "2026-09-20T10:20:00", "temperature": 25.2, "humidity": 59, "pressure": 1010.1, "wind_speed": 5.1},
    {"timestamp": "2026-09-20T10:25:00", "temperature": 45.3, "humidity": 58, "pressure": 1010.2, "wind_speed": 5.3}
]

data = json.dumps({"history": history}).encode("utf-8")
req = urllib.request.Request("https://smart-india-hackathon-9ngd1prc9-faizans-projects-af84d79d.vercel.app/api/inference", data=data, headers={
    "Content-Type": "application/json",
    "x-vercel-protection-bypass": "CS6xseTusM7YiWKxyhoUVLACOjAt6E6Z"
})

try:
    response = urllib.request.urlopen(req)
    print("Status:", response.status)
    print("Body:", response.read().decode("utf-8"))
except urllib.error.HTTPError as e:
    print("HTTP Error:", e.code)
    print("Error Body:", e.read().decode("utf-8"))
except Exception as e:
    print("Error:", e)
