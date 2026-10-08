"""Standalone metrics exporter daemon for transaction-producer on port 8003."""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from rag.metrics import start_metrics_server


def main():
    port = int(os.getenv("PRODUCER_METRICS_PORT", "8003"))
    host = os.getenv("METRICS_HOST", "0.0.0.0")
    print(f"Starting transaction-producer Prometheus exporter on {host}:{port}/metrics ...")
    server = start_metrics_server(host=host, port=port)
    if server is None:
        print(f"Port {port} is already actively serving metrics.")
    else:
        print(f"Metrics exporter listening on http://{host}:{port}/metrics")
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        print("Stopping transaction-producer metrics exporter.")


if __name__ == "__main__":
    main()

