"""Deterministic offline template-based narrative provider for GoldenMinutes.

Generates bilingual (Bangla and English) analyst case summaries and customer warnings
using verified templates from configs/reasons.yaml.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from goldenminutes.explain.reasons import get_reason_text, get_safe_action_hint
from goldenminutes.llm.provider import CaseNarrative, NarrativeProvider

logger = logging.getLogger("goldenminutes.llm.template")


class TemplateProvider(NarrativeProvider):
    """Offline, deterministic bilingual narrative generator."""

    def customer_warning(self, evidence: Dict[str, Any], lang: str = "bn") -> str:
        """Generate customer-facing warning message in requested language."""
        action = str(evidence.get("action", "allow")).lower()
        if action == "allow":
            return (
                "লেনদেনটি স্বাভাবিক হিসেবে অনুমোদিত হয়েছে।"
                if lang == "bn"
                else "Transaction approved with normal risk level."
            )

        reason_codes = evidence.get("reason_codes", [])
        # Extract code strings whether they are ReasonCode objects or dicts or strings
        code_strs: List[str] = []
        for rc in reason_codes:
            if isinstance(rc, dict):
                code_strs.append(rc.get("code", ""))
            elif hasattr(rc, "code"):
                code_strs.append(rc.code)
            elif isinstance(rc, str):
                code_strs.append(rc)

        reasons_text = []
        for code in code_strs:
            txt = get_reason_text(code, lang=lang)
            if txt and txt not in reasons_text:
                reasons_text.append(txt)

        hint = get_safe_action_hint(lang=lang)

        if not reasons_text:
            if action == "warn":
                base = (
                    "সতর্কবার্তা: প্রাপকের তথ্য যাচাই করুন।"
                    if lang == "bn"
                    else "Warning: Please verify recipient information."
                )
            elif action == "verify":
                base = (
                    "লেনদেন সম্পূর্ণ করতে অতিরিক্ত নিরাপত্তা যাচাইকরণ প্রয়োজন।"
                    if lang == "bn"
                    else "Additional security verification required before completion."
                )
            else:  # hold
                base = (
                    "নিরাপত্তা পর্যালোচনার জন্য এই স্থানান্তরটি সাময়িক স্থগিত রাখা হয়েছে।"
                    if lang == "bn"
                    else "This transfer is held for safety review."
                )
            return f"{base} {hint}"

        combined_reasons = " ".join(reasons_text)
        return f"{combined_reasons} {hint}"

    def summarize_case(self, evidence: Dict[str, Any]) -> CaseNarrative:
        """Construct structured case narrative and evidence breakdown for analyst view."""
        amount_bdt = float(evidence.get("amount_bdt", 0.0))
        sender_id = str(evidence.get("sender_wallet_id", "Unknown"))
        recipient_id = str(evidence.get("recipient_wallet_id", "Unknown"))
        risk_score = float(evidence.get("risk_score", 0.0))
        action = str(evidence.get("action", "hold")).upper()

        unique_senders_1h = int(evidence.get("recipient_unique_senders_1h", 0))
        unique_senders_24h = int(evidence.get("recipient_unique_senders_24h", 0))
        inflow_24h = float(evidence.get("recipient_inflow_24h", 0.0))
        outflow_24h = float(evidence.get("recipient_outflow_24h", 0.0))
        pass_through = float(evidence.get("recipient_pass_through_ratio_24h", 0.0))
        delay_min = float(evidence.get("recipient_median_receipt_to_out_minutes", 1440.0))
        amount_ratio = float(evidence.get("amount_to_median_ratio", 1.0))
        two_hop_share = float(evidence.get("two_hop_confirmed_mule_share", 0.0))

        # Build English summary
        en_points = []
        en_points.append(
            f"Transaction {action} triggered: {amount_bdt:,.2f} BDT transfer from {sender_id} to {recipient_id} "
            f"(calibrated risk score: {risk_score:.2f})."
        )
        if unique_senders_1h >= 2 or unique_senders_24h >= 3:
            en_points.append(
                f"Recipient wallet received funds from {unique_senders_1h} distinct senders in the last 1h "
                f"({unique_senders_24h} senders, {inflow_24h:,.2f} BDT total in 24h)."
            )
        if pass_through >= 0.5 or (outflow_24h > 0 and delay_min <= 60.0):
            en_points.append(
                f"High velocity pass-through: recipient disbursed {outflow_24h:,.2f} BDT "
                f"({pass_through * 100:.1f}% pass-through ratio) with median cash-out delay of {delay_min:.1f} minutes."
            )
        if amount_ratio >= 2.0:
            en_points.append(
                f"Unusual sender behavior: transfer amount is {amount_ratio:.1f}x higher than sender's 30-day median."
            )
        if two_hop_share > 0.0:
            en_points.append(
                f"Network ring link: recipient has {two_hop_share * 100:.1f}% 2-hop graph connectivity to confirmed mules."
            )

        summary_en = " ".join(en_points)

        # Build Bangla summary
        bn_points = []
        bn_points.append(
            f"লেনদেন {action} পদক্ষেপ গৃহীত হয়েছে: {sender_id} থেকে {recipient_id} ওয়ালেটে "
            f"{amount_bdt:,.2f} টাকার স্থানান্তর (ঝুঁকি স্কোর: {risk_score:.2f})।"
        )
        if unique_senders_1h >= 2 or unique_senders_24h >= 3:
            bn_points.append(
                f"প্রাপক ওয়ালেট গত ১ ঘণ্টায় {unique_senders_1h}টি ভিন্ন প্রেরক থেকে "
                f"এবং গত ২৪ ঘণ্টায় মোট {unique_senders_24h}টি প্রেরক থেকে {inflow_24h:,.2f} টাকা গ্রহণ করেছে।"
            )
        if pass_through >= 0.5 or (outflow_24h > 0 and delay_min <= 60.0):
            bn_points.append(
                f"দ্রুত অর্থ স্থানান্তরের প্রবণতা: প্রাপক {outflow_24h:,.2f} টাকা ক্যাশ-আউট বা স্থানান্তর করেছে "
                f"(পাস-থ্রু অনুপাত {pass_through * 100:.1f}%), এবং গড় ক্যাশ-আউট সময় {delay_min:.1f} মিনিট।"
            )
        if amount_ratio >= 2.0:
            bn_points.append(
                f"অস্বাভাবিক প্রেরক আচরণ: লেনদেনের পরিমাণ প্রেরকের ৩০ দিনের স্বাভাবিক লেনদেনের তুলনায় {amount_ratio:.1f} গুণ বেশি।"
            )
        if two_hop_share > 0.0:
            bn_points.append(
                f"নেটওয়ার্ক সংযোগ: প্রাপক ওয়ালেটের ২-ধাপ দূরবর্তী সংযোগে {two_hop_share * 100:.1f}% নিশ্চিত প্রতারক শনাক্ত হয়েছে।"
            )

        summary_bn = " ".join(bn_points)

        key_evidence = {
            "amount_bdt": amount_bdt,
            "risk_score": risk_score,
            "action": action,
            "recipient_unique_senders_1h": unique_senders_1h,
            "recipient_unique_senders_24h": unique_senders_24h,
            "recipient_inflow_24h": inflow_24h,
            "recipient_outflow_24h": outflow_24h,
            "recipient_pass_through_ratio_24h": pass_through,
            "recipient_median_receipt_to_out_minutes": delay_min,
            "amount_to_median_ratio": amount_ratio,
            "two_hop_confirmed_mule_share": two_hop_share,
        }

        cust_warn_en = self.customer_warning(evidence, lang="en")
        cust_warn_bn = self.customer_warning(evidence, lang="bn")

        return CaseNarrative(
            summary_en=summary_en,
            summary_bn=summary_bn,
            key_evidence=key_evidence,
            customer_warning_en=cust_warn_en,
            customer_warning_bn=cust_warn_bn,
            source="template",
        )
