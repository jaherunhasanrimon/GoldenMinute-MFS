"""SQLite Database Store via SQLAlchemy for GoldenMinutes.

Manages persistent storage and audit logging for:
- Decisions (scored transactions)
- Alerts (fraud/mule interventions requiring review)
- Analyst Actions (approve, release, escalate)
- Feedback (customer & analyst labels)
- Audit Logs (immutable operational event trail)
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
    desc,
)
from sqlalchemy.orm import Session, declarative_base, relationship, sessionmaker

from goldenminutes.common.config import get_settings

Base = declarative_base()


class DecisionRecord(Base):
    """Storage model for a scored transaction decision."""
    __tablename__ = "decisions"

    decision_id = Column(String(64), primary_key=True, index=True)
    txn_id = Column(String(64), nullable=False, index=True)
    ts = Column(DateTime(timezone=True), nullable=False)
    sender_wallet_id = Column(String(64), nullable=False, index=True)
    recipient_wallet_id = Column(String(64), nullable=False, index=True)
    amount_bdt = Column(Float, nullable=False)
    channel = Column(String(32), nullable=False, default="app")
    device_id = Column(String(64), nullable=False)
    risk_score = Column(Float, nullable=False)
    action = Column(String(32), nullable=False)
    model_version = Column(String(64), nullable=False)
    policy_version = Column(String(32), nullable=False)
    latency_ms = Column(Float, nullable=False, default=0.0)
    reason_codes_json = Column(Text, nullable=False, default="[]")
    evidence_json = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    alert = relationship("AlertRecord", back_populates="decision", uselist=False, cascade="all, delete-orphan")


class AlertRecord(Base):
    """Storage model for an intervention alert."""
    __tablename__ = "alerts"

    alert_id = Column(String(64), primary_key=True, index=True)
    decision_id = Column(String(64), ForeignKey("decisions.decision_id", ondelete="CASCADE"), nullable=False, index=True)
    txn_id = Column(String(64), nullable=False, index=True)
    status = Column(String(32), nullable=False, default="open", index=True)  # open, in_review, resolved, late
    priority = Column(Float, nullable=False, index=True)
    money_at_risk = Column(Float, nullable=False)
    deadline_ts = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    sender_wallet_id = Column(String(64), nullable=False, index=True)
    recipient_wallet_id = Column(String(64), nullable=False, index=True)
    amount_bdt = Column(Float, nullable=False)
    risk_score = Column(Float, nullable=False)
    action = Column(String(32), nullable=False)

    reason_codes_json = Column(Text, nullable=False, default="[]")
    customer_message_json = Column(Text, nullable=True)
    narrative_json = Column(Text, nullable=True)
    evidence_json = Column(Text, nullable=False, default="{}")

    decision = relationship("DecisionRecord", back_populates="alert")
    actions = relationship("AnalystActionRecord", back_populates="alert", cascade="all, delete-orphan")


class AnalystActionRecord(Base):
    """Storage model for actions taken by analysts on an alert."""
    __tablename__ = "analyst_actions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    alert_id = Column(String(64), ForeignKey("alerts.alert_id", ondelete="CASCADE"), nullable=False, index=True)
    analyst_id = Column(String(64), nullable=False)
    action = Column(String(32), nullable=False)  # approve, release, escalate
    note = Column(Text, nullable=True)
    ts = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    alert = relationship("AlertRecord", back_populates="actions")


class FeedbackRecord(Base):
    """Storage model for customer or analyst feedback."""
    __tablename__ = "feedback"

    feedback_id = Column(String(64), primary_key=True, index=True)
    decision_id = Column(String(64), nullable=False, index=True)
    source = Column(String(32), nullable=False)  # customer, analyst
    label = Column(String(32), nullable=False)  # this_was_me, not_me, fraud, legit
    note = Column(Text, nullable=True)
    ts = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


class AuditLogRecord(Base):
    """Storage model for immutable operational audit records."""
    __tablename__ = "audit_logs"

    audit_id = Column(String(64), primary_key=True, index=True)
    event_type = Column(String(64), nullable=False, index=True)
    user_id = Column(String(64), nullable=False)
    resource_type = Column(String(64), nullable=False, index=True)
    resource_id = Column(String(64), nullable=False, index=True)
    action = Column(String(64), nullable=False)
    details_json = Column(Text, nullable=False, default="{}")
    ts = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


class DatabaseStore:
    """Thread-safe database storage manager."""

    def __init__(self, db_url: Optional[str] = None) -> None:
        if db_url is None:
            settings = get_settings()
            db_url = settings.gm_db_url

        self.db_url = db_url
        connect_args = {"check_same_thread": False} if self.db_url.startswith("sqlite") else {}
        self.engine = create_engine(self.db_url, connect_args=connect_args)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        self.create_tables()

    def create_tables(self) -> None:
        """Create all tables in the database."""
        Base.metadata.create_all(bind=self.engine)

    def get_session(self) -> Session:
        """Get a new database session."""
        return self.SessionLocal()

    def reset_all(self) -> None:
        """Clear all tables (used for simulation reset)."""
        with self.get_session() as session:
            session.query(AuditLogRecord).delete()
            session.query(AnalystActionRecord).delete()
            session.query(FeedbackRecord).delete()
            session.query(AlertRecord).delete()
            session.query(DecisionRecord).delete()
            session.commit()

    def save_decision(
        self,
        decision_id: str,
        txn_id: str,
        ts: datetime,
        sender_wallet_id: str,
        recipient_wallet_id: str,
        amount_bdt: float,
        channel: str,
        device_id: str,
        risk_score: float,
        action: str,
        model_version: str,
        policy_version: str,
        latency_ms: float,
        reason_codes: List[Dict[str, Any]],
        evidence: Dict[str, Any],
    ) -> DecisionRecord:
        """Persist a transaction scoring decision."""
        with self.get_session() as session:
            record = DecisionRecord(
                decision_id=decision_id,
                txn_id=txn_id,
                ts=ts,
                sender_wallet_id=sender_wallet_id,
                recipient_wallet_id=recipient_wallet_id,
                amount_bdt=amount_bdt,
                channel=channel,
                device_id=device_id,
                risk_score=risk_score,
                action=action,
                model_version=model_version,
                policy_version=policy_version,
                latency_ms=latency_ms,
                reason_codes_json=json.dumps(reason_codes),
                evidence_json=json.dumps(evidence),
                created_at=datetime.now(timezone.utc),
            )
            session.add(record)
            session.commit()
            session.refresh(record)
            return record

    def create_alert(
        self,
        alert_id: str,
        decision_id: str,
        txn_id: str,
        sender_wallet_id: str,
        recipient_wallet_id: str,
        amount_bdt: float,
        risk_score: float,
        action: str,
        priority: float,
        money_at_risk: float,
        deadline_ts: datetime,
        reason_codes: List[Dict[str, Any]],
        customer_message: Optional[Dict[str, str]] = None,
        narrative: Optional[Dict[str, str]] = None,
        evidence: Optional[Dict[str, Any]] = None,
        status: str = "open",
    ) -> AlertRecord:
        """Create an alert for an intervention action."""
        with self.get_session() as session:
            now = datetime.now(timezone.utc)
            alert = AlertRecord(
                alert_id=alert_id,
                decision_id=decision_id,
                txn_id=txn_id,
                status=status,
                priority=priority,
                money_at_risk=money_at_risk,
                deadline_ts=deadline_ts,
                created_at=now,
                updated_at=now,
                sender_wallet_id=sender_wallet_id,
                recipient_wallet_id=recipient_wallet_id,
                amount_bdt=amount_bdt,
                risk_score=risk_score,
                action=action,
                reason_codes_json=json.dumps(reason_codes),
                customer_message_json=json.dumps(customer_message) if customer_message else None,
                narrative_json=json.dumps(narrative) if narrative else None,
                evidence_json=json.dumps(evidence or {}),
            )
            session.add(alert)
            session.commit()
            session.refresh(alert)
            return alert

    def list_alerts(
        self,
        status_filter: Optional[str] = None,
        limit: int = 100,
    ) -> List[AlertRecord]:
        """List alerts sorted by priority descending."""
        with self.get_session() as session:
            q = session.query(AlertRecord)
            if status_filter:
                q = q.filter(AlertRecord.status == status_filter)
            return q.order_by(desc(AlertRecord.priority)).limit(limit).all()

    def get_alert(self, alert_id: str) -> Optional[AlertRecord]:
        """Retrieve full alert details including actions taken."""
        with self.get_session() as session:
            alert = (
                session.query(AlertRecord)
                .filter(AlertRecord.alert_id == alert_id)
                .first()
            )
            if alert:
                # Eagerly access actions so they are loaded before session closes
                _ = len(alert.actions)
            return alert

    def record_analyst_action(
        self,
        alert_id: str,
        action: str,
        analyst_id: str,
        note: Optional[str] = None,
    ) -> Tuple[AlertRecord, AnalystActionRecord]:
        """Record analyst action (approve, release, escalate) and update alert status."""
        with self.get_session() as session:
            alert = session.query(AlertRecord).filter(AlertRecord.alert_id == alert_id).first()
            if not alert:
                raise ValueError(f"Alert {alert_id} not found")

            # Determine new alert status
            if action in ["approve", "release"]:
                alert.status = "resolved"
            elif action == "escalate":
                alert.status = "in_review"

            alert.updated_at = datetime.now(timezone.utc)

            action_record = AnalystActionRecord(
                alert_id=alert_id,
                analyst_id=analyst_id,
                action=action,
                note=note,
                ts=datetime.now(timezone.utc),
            )
            session.add(action_record)

            # Mandatory audit log entry
            audit = AuditLogRecord(
                audit_id=f"AUD-{uuid.uuid4().hex[:12]}",
                event_type="analyst_action",
                user_id=analyst_id,
                resource_type="alert",
                resource_id=alert_id,
                action=action,
                details_json=json.dumps({"note": note, "new_status": alert.status}),
                ts=datetime.now(timezone.utc),
            )
            session.add(audit)

            session.commit()
            session.refresh(alert)
            session.refresh(action_record)
            return alert, action_record

    def record_feedback(
        self,
        decision_id: str,
        source: str,
        label: str,
        note: Optional[str] = None,
    ) -> FeedbackRecord:
        """Record customer or analyst feedback."""
        with self.get_session() as session:
            fb = FeedbackRecord(
                feedback_id=f"FB-{uuid.uuid4().hex[:10]}",
                decision_id=decision_id,
                source=source,
                label=label,
                note=note,
                ts=datetime.now(timezone.utc),
            )
            session.add(fb)

            # Audit entry
            audit = AuditLogRecord(
                audit_id=f"AUD-{uuid.uuid4().hex[:12]}",
                event_type="feedback_recorded",
                user_id=source,
                resource_type="decision",
                resource_id=decision_id,
                action=label,
                details_json=json.dumps({"note": note}),
                ts=datetime.now(timezone.utc),
            )
            session.add(audit)

            session.commit()
            session.refresh(fb)
            return fb

    def get_audit_trail(self, resource_id: Optional[str] = None) -> List[AuditLogRecord]:
        """Fetch audit log records."""
        with self.get_session() as session:
            q = session.query(AuditLogRecord)
            if resource_id:
                q = q.filter(AuditLogRecord.resource_id == resource_id)
            return q.order_by(desc(AuditLogRecord.ts)).all()


# Global default store instance
_db_store: Optional[DatabaseStore] = None


def get_db_store() -> DatabaseStore:
    """Get or create singleton DatabaseStore."""
    global _db_store
    if _db_store is None:
        _db_store = DatabaseStore()
    return _db_store
