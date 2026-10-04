"""Scripted impersonation/mule attack scenario for the demo (ARCHITECTURE.md Section 4/20).

Synthetic data only. Each run creates a fresh mule wallet and ring device so the
scenario is repeatable against live online state.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from goldenminutes.common.schemas import ScoreRequest


def run_attack(service: Any) -> Dict[str, Any]:
    """Replay the attack through the real scoring pipeline; return steps and final result."""
    now = datetime.now(timezone.utc)
    mule_id = f"W_MULE_{uuid.uuid4().hex[:6].upper()}"
    service.features.register_wallet(mule_id, now - timedelta(days=2), "customer")

    # Step 1: Low-friction probe transaction
    res1 = service.score(ScoreRequest(
        txn_id=f"TXN_P1_{uuid.uuid4().hex[:6].upper()}",
        ts=now - timedelta(minutes=25),
        type="send_money",
        sender_wallet_id="W01443",
        recipient_wallet_id=mule_id,
        amount_bdt=250.0,
        channel="app",
        device_id="DEV_VICTIM_1",
        balance_before=15000.0,
    ))

    # Step 2: Second victim transfer
    res2 = service.score(ScoreRequest(
        txn_id=f"TXN_P2_{uuid.uuid4().hex[:6].upper()}",
        ts=now - timedelta(minutes=10),
        type="send_money",
        sender_wallet_id="W03312",
        recipient_wallet_id=mule_id,
        amount_bdt=8000.0,
        channel="app",
        device_id="DEV_VICTIM_2",
        balance_before=20000.0,
    ))

    # Step 3: High-value coercive transfer
    res3 = service.score(ScoreRequest(
        txn_id=f"TXN_ATK_{uuid.uuid4().hex[:6].upper()}",
        ts=now,
        type="send_money",
        sender_wallet_id="W01928",
        recipient_wallet_id=mule_id,
        amount_bdt=35000.0,
        channel="app",
        device_id=f"DEV_RING_{uuid.uuid4().hex[:4].upper()}",
        balance_before=45000.0,
        session_seconds=30,
    ))

    steps = [
        {
            "step": 1,
            "title": "Probe Transfer (Victim 1)",
            "sender_wallet_id": "W01443",
            "recipient_wallet_id": mule_id,
            "amount_bdt": 250.0,
            "action": res1.action,
            "risk_score": round(res1.risk_score, 2),
            "description": f"Victim 1 sends test transfer of 250 BDT to fresh mule wallet {mule_id}. Interception result: {res1.action.upper()}.",
            "description_bn": f"প্রথম ভুক্তভোগী নতুন মিউল ওয়ালেট {mule_id}-এ ২৫০ টাকার প্রাথমিক লেনদেন পাঠায় (পদক্ষেপ: {res1.action.upper()})।",
        },
        {
            "step": 2,
            "title": "Second Victim Transfer",
            "sender_wallet_id": "W03312",
            "recipient_wallet_id": mule_id,
            "amount_bdt": 8000.0,
            "action": res2.action,
            "risk_score": round(res2.risk_score, 2),
            "description": f"Second victim transfers 8,000 BDT. Recipient fan-in velocity begins rising (risk_score={res2.risk_score:.2f}).",
            "description_bn": "দ্বিতীয় ভুক্তভোগী ৮,০০০ টাকা পাঠায়। প্রাপক ওয়ালেটের ফ্যান-ইন গতিবেগ বৃদ্ধি পেতে শুরু করে।",
        },
        {
            "step": 3,
            "title": "High-Value Coercive Transfer",
            "sender_wallet_id": "W01928",
            "recipient_wallet_id": mule_id,
            "amount_bdt": 35000.0,
            "action": res3.action,
            "risk_score": round(res3.risk_score, 2),
            "description": f"Scammer coerces Karim Ahmed (W01928) to transfer 35,000 BDT to mule wallet {mule_id}.",
            "description_bn": f"প্রতারকের নির্দেশে করিম আহমেদ (W01928) মিউল ওয়ালেট {mule_id}-এ ৩৫,০০০ টাকা পাঠানোর সূচনা করে।",
        },
        {
            "step": 4,
            "title": "AI Pipeline Interception",
            "sender_wallet_id": "W01928",
            "recipient_wallet_id": mule_id,
            "amount_bdt": 35000.0,
            "action": res3.action,
            "risk_score": round(res3.risk_score, 2),
            "alert_id": res3.alert_id,
            "description": f"GoldenMinutes real-time scoring evaluates fan-in burst, new recipient age, and ring link: risk_score={res3.risk_score:.2f}, action={res3.action.upper()}.",
            "description_bn": f"গোল্ডেন-মিনিটস এআই ইঞ্জিন অস্বাভাবিক ফ্যান-ইন ও নেটওয়ার্ক রিং লিংক শনাক্ত করে: ঝুঁকি স্কোর={res3.risk_score:.2f}, অ্যাকশন={res3.action.upper()}।",
        },
        {
            "step": 5,
            "title": "Analyst Queue Interception",
            "sender_wallet_id": "W01928",
            "recipient_wallet_id": mule_id,
            "amount_bdt": 35000.0,
            "action": res3.action,
            "risk_score": round(res3.risk_score, 2),
            "alert_id": res3.alert_id,
            "description": f"High-priority alert {res3.alert_id or ''} dispatched to Analyst Console. Analyst confirms fraud and locks mule wallet before cash-out within 30-minute golden window.",
            "description_bn": f"উচ্চ অগ্রাধিকারের অ্যালার্ট {res3.alert_id or ''} অ্যানালিস্ট কনসোলে প্রেরিত। ৩০ মিনিটের গোল্ডেন উইন্ডোর মধ্যে ক্যাশ-আউটের পূর্বেই অর্থ সুরক্ষিত করা হয়।",
        },
    ]

    return {"steps": steps, "final": res3, "mule_id": mule_id}
