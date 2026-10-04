"""Latency benchmark measuring p50, p90, p95, and p99 latency over 1,000 requests.

Writes results to reports/latency.json matching Phase P4 gate requirements.
Target p95 latency: < 150 ms.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import numpy as np
from fastapi.testclient import TestClient

from goldenminutes.api.main import app

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("goldenminutes.benchmark")


def run_latency_benchmark(n_requests: int = 1000) -> Dict[str, Any]:
    """Execute n_requests against POST /v1/score and compute percentiles."""
    client = TestClient(app)
    headers = {"X-API-Key": "demo_customer_secret_key"}

    logger.info("Warming up API server with 25 requests...")
    for i in range(25):
        client.post(
            "/v1/score",
            json={
                "txn_id": f"WARMUP_{i}",
                "ts": datetime.now(timezone.utc).isoformat(),
                "sender_wallet_id": f"W_WARM_{i%5}",
                "recipient_wallet_id": f"W_WARM_{(i+1)%5}",
                "amount_bdt": 1500.0,
                "channel": "app",
                "device_id": f"DEV_WARM_{i%3}",
                "balance_before": 5000.0,
            },
            headers=headers,
        )

    logger.info(f"Measuring latency across {n_requests:,} live scoring requests...")
    latencies_ms: List[float] = []

    np.random.seed(42)
    amounts = np.random.exponential(scale=3500.0, size=n_requests) + 50.0
    senders = [f"W_BENCH_{i%50:04d}" for i in range(n_requests)]
    recipients = [f"W_BENCH_{(i+7)%50:04d}" for i in range(n_requests)]
    devices = [f"DEV_BENCH_{i%20:04d}" for i in range(n_requests)]

    for i in range(n_requests):
        amt = float(amounts[i])
        payload = {
            "txn_id": f"BENCH_{i:05d}",
            "ts": datetime.now(timezone.utc).isoformat(),
            "sender_wallet_id": senders[i],
            "recipient_wallet_id": recipients[i],
            "amount_bdt": amt,
            "channel": "app",
            "device_id": devices[i],
            "balance_before": amt * 1.5 + 500.0,
            "session_seconds": int(30 + (i % 60)),
        }

        t0 = time.perf_counter()
        res = client.post("/v1/score", json=payload, headers=headers)
        t1 = time.perf_counter()

        assert res.status_code == 200, f"Request failed: {res.text}"
        assert "x-gm-stub" not in res.headers, "X-GM-Stub header found on response!"

        elapsed_ms = (t1 - t0) * 1000.0
        latencies_ms.append(elapsed_ms)

    arr = np.array(latencies_ms)
    p50 = float(np.percentile(arr, 50))
    p90 = float(np.percentile(arr, 90))
    p95 = float(np.percentile(arr, 95))
    p99 = float(np.percentile(arr, 99))
    mean_lat = float(np.mean(arr))
    max_lat = float(np.max(arr))

    results = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_requests": n_requests,
        "mean_latency_ms": round(mean_lat, 2),
        "p50_latency_ms": round(p50, 2),
        "p90_latency_ms": round(p90, 2),
        "p95_latency_ms": round(p95, 2),
        "p99_latency_ms": round(p99, 2),
        "max_latency_ms": round(max_lat, 2),
        "target_p95_ms": 150.0,
        "p95_under_target": p95 < 150.0,
    }

    # Save to reports/latency.json
    repo_root = Path(__file__).resolve().parents[1]
    out_file = repo_root / "reports" / "latency.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    logger.info(f"Latency benchmark complete. Saved to {out_file}")
    logger.info(
        f"Summary: p50={p50:.2f} ms | p95={p95:.2f} ms | p99={p99:.2f} ms (Target p95 < 150 ms: {p95 < 150.0})"
    )
    return results


if __name__ == "__main__":
    run_latency_benchmark(1000)
