"""GoldenMinutes One-Command Demo Launcher.

Warms state, displays the 3-minute demo script, and serves FastAPI with built static UI.
"""

from __future__ import annotations

import uvicorn

from goldenminutes.api.service import get_service

BANNER = """
========================================================================================
  GoldenMinutes — Real-Time Scam & Mule Interception for upay
  UCB Fintech Company Limited (upay)
========================================================================================

  Application URLs:
    • Web Application (FastAPI Static): http://127.0.0.1:8000/
    • Customer Demo Screen:             http://127.0.0.1:8000/
    • Risk Analyst Console:             http://127.0.0.1:8000/analyst
    • Metrics & Ablation Dashboard:     http://127.0.0.1:8000/metrics
    • Interactive API Swagger Docs:     http://127.0.0.1:8000/docs

  3-Minute Rehearsal Script (ARCHITECTURE.md Section 20):
    1. Problem (30s):
       Explain the "Golden Minutes" in Bangladesh MFS: after an impersonation scam
       transfer, there is a narrow 30-minute window before physical cash-out at an
       agent counter. Once cashed out, the money cannot be recovered.
    2. Normal Send (20s):
       On the Customer screen, select Karim Ahmed -> Shakil Mia (known relative)
       and send ৳5,000. The transaction passes immediately with zero friction (ALLOW).
    3. Attack Replay (40s):
       Click "Run attack" (আক্রমণ চালান). Scripted fan-in builds into a fresh mule wallet,
       culminating in a ৳35,000 coercive transfer intercepted in real time with HOLD.
       Observe the clear Bengali warning with the mandatory SAFE_ACTION_HINT.
    4. Analyst Review (40s):
       Switch to the Analyst Console. Alert #A... appears at the top of the queue with
       a live 30-minute countdown. Open the drawer to inspect calibrated risk score,
       case narrative, TreeSHAP reason codes, and the 2-hop local wallet graph.
    5. Human Interception (20s):
       Analyst confirms the fraud ring link and approves the hold, intercepting cash-out.
    6. Metrics & Responsible AI (30s):
       Switch to Metrics Dashboard. Walk through the Variants A-D ablation (numbers come from reports/metrics.json),
       held-out typology recall, latency, and fairness slices.
========================================================================================
"""


def main():
    print("Warming GoldenMinutes demonstration state and feature store...")
    service = get_service()
    service.reset()
    print("State warmed successfully.")
    print(BANNER)
    print("Starting GoldenMinutes unified server on http://127.0.0.1:8000 ...\n")
    uvicorn.run("goldenminutes.api.main:app", host="127.0.0.1", port=8000, reload=False)


if __name__ == "__main__":
    main()
