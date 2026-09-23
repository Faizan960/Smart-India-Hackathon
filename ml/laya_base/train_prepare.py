"""Prepare Laya JSONL data from a healthy telemetry CSV."""
from __future__ import annotations
import argparse
import pandas as pd
from .dataset import build_jsonl

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="Healthy telemetry CSV")
    parser.add_argument("--output", required=True, help="Output JSONL path")
    parser.add_argument("--stride", type=int, default=12)
    parser.add_argument("--max-windows", type=int, default=None)
    args = parser.parse_args()
    df = pd.read_csv(args.input)
    required = ["timestamp", "temperature", "humidity", "pressure", "wind_speed"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise SystemExit(f"Missing required columns: {missing}")
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df = df.dropna(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
    count = build_jsonl(df, args.output, stride=args.stride, max_windows=args.max_windows)
    print(f"Created {count} Laya training cases at {args.output}")

if __name__ == "__main__":
    main()
