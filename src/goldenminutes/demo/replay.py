"""Demo transaction replay runner for GoldenMinutes.

Implements ARCHITECTURE.md Section 4 and Section 20 demo script:
- Replay synthetic transaction streams against the live scoring pipeline
- Record latency, action transitions, and intervention outcomes
"""

from __future__ import annotations

import time
from typing import Any, Dict, List

from goldenminutes.common.schemas import ScoreRequest, ScoreResponse


def replay_transactions(
    service: Any,
    requests: List[ScoreRequest],
    delay_seconds: float = 0.0,
) -> List[Dict[str, Any]]:
    """Replay a sequence of ScoreRequests through the live service."""
    results: List[Dict[str, Any]] = []

    for req in requests:
        t0 = time.perf_counter()
        resp: ScoreResponse = service.score(req)
        latency_ms = (time.perf_counter() - t0) * 1000.0

        results.append({
            "txn_id": req.txn_id,
            "sender_wallet_id": req.sender_wallet_id,
            "recipient_wallet_id": req.recipient_wallet_id,
            "amount_bdt": req.amount_bdt,
            "risk_score": resp.risk_score,
            "action": resp.action,
            "alert_id": resp.alert_id,
            "latency_ms": latency_ms,
        })

        if delay_seconds > 0:
            time.sleep(delay_seconds)

    return results
