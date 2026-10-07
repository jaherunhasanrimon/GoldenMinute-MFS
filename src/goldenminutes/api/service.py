"""Service layer coordinating OnlineFeatureStore, ModelRegistry, PolicyEngine, and DatabaseStore."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from goldenminutes.api.store import DatabaseStore, get_db_store
from goldenminutes.common.schemas import CustomerMessage, ReasonCode, ScoreRequest, ScoreResponse
from goldenminutes.explain.shap_explainer import TreeShapExplainer
from goldenminutes.features.online import OnlineFeatureStore
from goldenminutes.llm.guards import LLMGuards
from goldenminutes.llm.provider import NarrativeProvider, get_narrative_provider
from goldenminutes.models.anomaly import AnomalyIsolationForest
from goldenminutes.models.calibration import IsotonicCalibrator
from goldenminutes.models.fusion import FusionModel
from goldenminutes.models.registry import REPO_ROOT, ModelRegistry
from goldenminutes.models.risk_lgbm import RiskLGBM
from goldenminutes.policy.engine import PolicyDecision, PolicyEngine
from goldenminutes.rules.baseline import RulesBaseline

logger = logging.getLogger("goldenminutes.api.service")


class GoldenMinutesService:
    """Core runtime engine for scoring, alerting, and simulation."""

    def __init__(
        self,
        db_store: Optional[DatabaseStore] = None,
        online_store: Optional[OnlineFeatureStore] = None,
        policy_engine: Optional[PolicyEngine] = None,
        narrative_provider: Optional[NarrativeProvider] = None,
    ) -> None:
        self.db = db_store or get_db_store()
        self.features = online_store or OnlineFeatureStore()
        self.policy = policy_engine or PolicyEngine()
        self.registry = ModelRegistry()
        self.narrative = narrative_provider or get_narrative_provider()

        self.rules_engine = RulesBaseline()
        self.model_c: Optional[RiskLGBM] = None
        self.calibrator_c: Optional[IsotonicCalibrator] = None
        self.model_e: Optional[RiskLGBM] = None
        self.calibrator_e: Optional[IsotonicCalibrator] = None
        self.anomaly_model: Optional[AnomalyIsolationForest] = None
        self.fusion_model: Optional[FusionModel] = None
        self.explainer: Optional[TreeShapExplainer] = None
        self.active_version: str = "m-1.0.0-full"

        self._load_active_models()
        champion_model = self.model_e or self.model_c
        self.explainer = TreeShapExplainer(champion_model) if champion_model is not None else None
        self._seed_demo_state()

    def _load_active_models(self) -> None:
        """Load Champion Fusion artifacts from ModelRegistry."""
        active_meta = self.registry.get_active_metadata()
        if not active_meta:
            # Check demo_assets safety net for fresh checkout demo
            demo_models_dir = REPO_ROOT / "demo_assets" / "models"
            if demo_models_dir.exists():
                import shutil
                (REPO_ROOT / "models").mkdir(parents=True, exist_ok=True)
                shutil.copytree(demo_models_dir, REPO_ROOT / "models", dirs_exist_ok=True)
                if (REPO_ROOT / "demo_assets" / "registry.json").exists():
                    shutil.copy(REPO_ROOT / "demo_assets" / "registry.json", REPO_ROOT / "models" / "registry.json")
                self.registry = ModelRegistry()
                active_meta = self.registry.get_active_metadata()

        if not active_meta:
            # Fallback to small if full not present
            versions = self.registry.data.get("versions", {})
            if "m-1.0.0-small" in versions:
                active_meta = self.registry.get_version_metadata("m-1.0.0-small")
            else:
                logger.warning("No trained models found in registry. Running in fallback mode.")
                return

        self.active_version = active_meta["version"]
        artifacts = active_meta.get("artifacts", {})

        try:
            if "variant_e_lgbm" in artifacts and Path(artifacts["variant_e_lgbm"]).exists():
                self.model_e = RiskLGBM.load(artifacts["variant_e_lgbm"])
            if "variant_e_calibrator" in artifacts and Path(artifacts["variant_e_calibrator"]).exists():
                self.calibrator_e = IsotonicCalibrator.load(artifacts["variant_e_calibrator"])
            if "variant_c_lgbm" in artifacts and Path(artifacts["variant_c_lgbm"]).exists():
                self.model_c = RiskLGBM.load(artifacts["variant_c_lgbm"])
            if "variant_c_calibrator" in artifacts and Path(artifacts["variant_c_calibrator"]).exists():
                self.calibrator_c = IsotonicCalibrator.load(artifacts["variant_c_calibrator"])
            if "anomaly_iforest" in artifacts and Path(artifacts["anomaly_iforest"]).exists():
                self.anomaly_model = AnomalyIsolationForest.load(artifacts["anomaly_iforest"])
            if "fusion_model" in artifacts and Path(artifacts["fusion_model"]).exists():
                self.fusion_model = FusionModel.load(artifacts["fusion_model"])
            if "gnn_embeddings" in artifacts and Path(artifacts["gnn_embeddings"]).exists():
                from goldenminutes.models.embedding_store import InMemoryEmbeddingStore
                emb_store = InMemoryEmbeddingStore.load(artifacts["gnn_embeddings"])
                self.features.set_embedding_store(emb_store)

            logger.info("Loaded active Champion Fusion model: %s", self.active_version)
        except Exception as e:
            logger.error("Failed to load model artifacts: %s", e)

    def _seed_demo_state(self) -> None:
        """Seed demo wallets into online feature store to power the customer & analyst demo."""
        now = datetime.now(timezone.utc)
        # Senders
        self.features.register_wallet("W01928", now - timedelta(days=450), "customer")
        self.features.register_wallet("W01443", now - timedelta(days=180), "customer")
        self.features.register_wallet("W03312", now - timedelta(days=700), "customer")

        # Recipients
        self.features.register_wallet("W08371", now - timedelta(days=4), "customer")  # Fresh mule
        self.features.register_wallet("W07712", now - timedelta(days=500), "customer")  # Known relative
        self.features.register_wallet("W09920", now - timedelta(days=600), "customer")  # House rent

        # Prepopulate W08371 (mule) with rapid fan-in inflows
        for i in range(4):
            t = now - timedelta(minutes=40 - i * 8)
            sender = f"W_DEMO_{i+10}"
            self.features.register_wallet(sender, now - timedelta(days=200), "customer")
            self.features.update({
                "ts": t,
                "txn_id": f"TXN_SEED_{i}",
                "type": "send_money",
                "sender_wallet_id": sender,
                "recipient_wallet_id": "W08371",
                "amount_bdt": 18000.0 + i * 2000,
                "device_id": "DEV_RING_01",
                "balance_before": 50000.0,
            })

        # Prepopulate past cash-out for W08371
        self.features.update({
            "ts": now - timedelta(minutes=15),
            "txn_id": "TXN_SEED_CO",
            "type": "cash_out",
            "sender_wallet_id": "W08371",
            "recipient_wallet_id": None,
            "amount_bdt": 35000.0,
            "device_id": "DEV_RING_01",
            "balance_before": 38000.0,
        })

        # Prepopulate trusted pair history for W01928 -> W07712
        for i in range(5):
            t = now - timedelta(days=60 - i * 10)
            self.features.update({
                "ts": t,
                "txn_id": f"TXN_LEGIT_{i}",
                "type": "send_money",
                "sender_wallet_id": "W01928",
                "recipient_wallet_id": "W07712",
                "amount_bdt": 5000.0,
                "device_id": "DEV_W01928",
                "balance_before": 45000.0,
            })

    def reset(self) -> None:
        """Reset database, policy state, and feature store for simulation demo."""
        self.db.reset_all()
        self.policy.reset()
        self.features = OnlineFeatureStore()
        self._seed_demo_state()

    def predict_risk(self, feat_dict: Dict[str, Any]) -> Tuple[float, List[ReasonCode]]:
        """Compute model risk score and explainable reason codes."""
        feat_df = pd.DataFrame([feat_dict])

        # 1. Rules baseline
        rules_res = self.rules_engine.evaluate_batch(feat_df)
        rules_hit_count = float(rules_res["rules_hit_count"].iloc[0])
        rules_risk = float(rules_res["risk_score"].iloc[0])

        if self.model_e is not None and self.calibrator_e is not None and self.anomaly_model is not None and self.fusion_model is not None:
            raw_e = self.model_e.predict_proba(feat_df)
            p_e = self.calibrator_e.predict(raw_e)
            anom = self.anomaly_model.predict_anomaly_score(feat_df)
            fused = self.fusion_model.predict_risk(p_e, anom, np.array([rules_hit_count]))
            risk_score = float(fused[0])
        elif self.model_c is not None and self.calibrator_c is not None and self.anomaly_model is not None and self.fusion_model is not None:
            raw_c = self.model_c.predict_proba(feat_df)
            p_c = self.calibrator_c.predict(raw_c)
            anom = self.anomaly_model.predict_anomaly_score(feat_df)
            fused = self.fusion_model.predict_risk(p_c, anom, np.array([rules_hit_count]))
            risk_score = float(fused[0])
        else:
            logger.warning("predict_risk: using fallback rules risk because models are not loaded!")
            risk_score = rules_risk

        # Extract top reason codes via TreeSHAP
        reason_codes: List[ReasonCode] = []
        if self.explainer is not None:
            reason_codes = self.explainer.get_top_reasons(feat_df, top_k=3)

        # Fallback to heuristic reason codes if SHAP yielded empty
        if not reason_codes:
            if feat_dict.get("recipient_unique_senders_1h", 0) >= 2 or feat_dict.get("recipient_unique_senders_24h", 0) >= 3:
                reason_codes.append(ReasonCode(code="RECIPIENT_FAN_IN_BURST", weight=0.38))
            if feat_dict.get("amount_to_median_ratio", 1.0) >= 2.5 or feat_dict.get("balance_drain_ratio", 0.0) >= 0.75:
                reason_codes.append(ReasonCode(code="AMOUNT_UNUSUAL_FOR_SENDER", weight=0.28))
            if feat_dict.get("recipient_pass_through_ratio_24h", 0.0) >= 0.6 or feat_dict.get("recipient_median_receipt_to_out_minutes", 1440.0) <= 30.0:
                reason_codes.append(ReasonCode(code="RECIPIENT_FAST_PASS_THROUGH", weight=0.22))
            if feat_dict.get("recipient_age_days", 100.0) <= 7.0:
                reason_codes.append(ReasonCode(code="RECIPIENT_NEW", weight=0.18))
            if feat_dict.get("new_device_flag", 0) == 1 or feat_dict.get("minutes_since_pin_reset", 43200.0) <= 1440.0:
                reason_codes.append(ReasonCode(code="DEVICE_OR_PIN_CHANGE_RECENT", weight=0.15))
            if feat_dict.get("is_first_time_pair", 0) == 1:
                reason_codes.append(ReasonCode(code="FIRST_TIME_PAIR", weight=0.12))
            if feat_dict.get("two_hop_confirmed_mule_share", 0.0) > 0.0 or feat_dict.get("shared_device_wallet_count", 1) >= 2:
                reason_codes.append(ReasonCode(code="RING_LINK", weight=0.25))

        reason_codes.sort(key=lambda r: r.weight, reverse=True)
        return float(np.clip(risk_score, 0.0, 1.0)), reason_codes[:3]

    def score(self, req: ScoreRequest) -> ScoreResponse:
        """Full real-time transaction scoring pipeline."""
        start_ts = datetime.now(timezone.utc)

        # 1. Online feature extraction (point-in-time)
        feats = self.features.features(req.model_dump())
        feats["amount_bdt"] = float(req.amount_bdt)
        feats["type"] = str(req.type)
        feats["channel"] = str(req.channel)
        feats["session_seconds"] = float(req.session_seconds or 60)
        feats["device_id"] = str(req.device_id)
        feats["sender_wallet_id"] = str(req.sender_wallet_id)
        feats["recipient_wallet_id"] = str(req.recipient_wallet_id)
        feats["balance_before"] = float(req.balance_before)

        # 2. Risk scoring & reason attribution via TreeSHAP
        risk_score, reason_codes = self.predict_risk(feats)

        # 3. Policy evaluation
        policy_decision: PolicyDecision = self.policy.evaluate(
            amount_bdt=req.amount_bdt,
            risk_score=risk_score,
            context={
                "minutes_since_first_inflow": self.features.recipient_first_inflow_minutes(
                    req.recipient_wallet_id, req.ts
                ),
                "cashed_out": self.features.recipient_cashed_out(req.recipient_wallet_id, req.ts),
            },
            current_ts=req.ts,
        )

        action = policy_decision.action

        # Gate guarantee: Every non-allow response MUST have at least one reason code
        if action != "allow" and not reason_codes:
            fallback_code = (
                "AMOUNT_UNUSUAL_FOR_SENDER"
                if req.amount_bdt >= self.policy.min_amount_bdt * 2
                else "FIRST_TIME_PAIR"
            )
            reason_codes = [ReasonCode(code=fallback_code, weight=1.0)]

        # 4. Generate narrative and warnings via NarrativeProvider & LLMGuards
        evidence_dict = dict(feats)
        evidence_dict["risk_score"] = risk_score
        evidence_dict["action"] = action
        evidence_dict["reason_codes"] = [r.model_dump() for r in reason_codes]
        if req.reference:
            evidence_dict["reference"] = LLMGuards.sanitize_reference(req.reference)

        case_narrative = self.narrative.summarize_case(evidence_dict)
        cust_msg = CustomerMessage(
            bn=case_narrative.customer_warning_bn,
            en=case_narrative.customer_warning_en,
        )
        narrative = {
            "bn": case_narrative.summary_bn,
            "en": case_narrative.summary_en,
        }

        # 4. Generate alert if hold or verify intervention
        alert_id = None
        if action == "hold":
            alert_id = f"A{uuid.uuid4().hex[:8].upper()}"
            decision_id = f"D{uuid.uuid4().hex[:8].upper()}"
            self.db.create_alert(
                alert_id=alert_id,
                decision_id=decision_id,
                txn_id=req.txn_id,
                sender_wallet_id=req.sender_wallet_id,
                recipient_wallet_id=req.recipient_wallet_id,
                amount_bdt=req.amount_bdt,
                risk_score=risk_score,
                action=action,
                priority=policy_decision.priority or (risk_score * req.amount_bdt),
                money_at_risk=req.amount_bdt,
                deadline_ts=policy_decision.deadline_ts or (req.ts + timedelta(minutes=30)),
                reason_codes=[r.model_dump() for r in reason_codes],
                customer_message=cust_msg.model_dump(),
                narrative=narrative,
                evidence=feats,
                status=policy_decision.alert_status or "open",
            )
        else:
            decision_id = f"D{uuid.uuid4().hex[:8].upper()}"

        latency_ms = (datetime.now(timezone.utc) - start_ts).total_seconds() * 1000.0

        # 5. Save decision in database
        self.db.save_decision(
            decision_id=decision_id,
            txn_id=req.txn_id,
            ts=req.ts,
            sender_wallet_id=req.sender_wallet_id,
            recipient_wallet_id=req.recipient_wallet_id,
            amount_bdt=req.amount_bdt,
            channel=req.channel,
            device_id=req.device_id,
            risk_score=risk_score,
            action=action,
            model_version=self.active_version,
            policy_version=self.policy.version,
            latency_ms=latency_ms,
            reason_codes=[r.model_dump() for r in reason_codes],
            evidence=feats,
        )

        # 6. Update online rolling state
        self.features.update(req.model_dump())

        return ScoreResponse(
            txn_id=req.txn_id,
            risk_score=round(risk_score, 4),
            action=action,
            reason_codes=reason_codes,
            customer_message=cust_msg,
            alert_id=alert_id,
            model_version=self.active_version,
            policy_version=self.policy.version,
            latency_ms=round(latency_ms, 2),
        )


_service_instance: Optional[GoldenMinutesService] = None


def get_service() -> GoldenMinutesService:
    """Get or create singleton GoldenMinutesService."""
    global _service_instance
    if _service_instance is None:
        _service_instance = GoldenMinutesService()
    return _service_instance
