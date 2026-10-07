"""Database Store via SQLAlchemy for GoldenMinutes.

Manages persistent storage, user identity, and cryptographic audit logging for:
- Users & Role-Based Access Control (analyst, senior_analyst, admin, auditor, customer_demo)
- API Clients (MFS core system service authentication)
- Refresh Tokens (secure session revocation)
- Decisions (scored transactions)
- Alerts (fraud/mule interventions requiring review)
- Analyst Actions (approve, release, escalate with four-eyes enforcement)
- Feedback (customer & analyst labels)
- Cryptographic Audit Chain (tamper-evident SHA-256 hash-chained operational event trail)
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import (
    Boolean,
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
from sqlalchemy.orm import Session, declarative_base, joinedload, relationship, sessionmaker

from goldenminutes.api.auth import hash_api_key, hash_password
from goldenminutes.common.config import get_settings

logger = logging.getLogger(__name__)

Base = declarative_base()

GENESIS_HASH = "GENESIS_ROOT_HASH_GOLDENMINUTES_2026"


def format_audit_ts(dt: datetime) -> str:
    """Format audit datetime as deterministic UTC ISO string."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


def compute_entry_hash(
    prev_hash: str,
    sequence_number: int,
    event_type: str,
    user_id: str,
    resource_type: str,
    resource_id: str,
    action: str,
    details_json: str,
    ts_str: str,
) -> str:
    """Compute SHA-256 cryptographic entry hash linking to prev_hash."""
    raw = f"{prev_hash}|{sequence_number}|{event_type}|{user_id}|{resource_type}|{resource_id}|{action}|{details_json}|{ts_str}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class UserRecord(Base):
    """Storage model for authenticated users and RBAC roles."""
    __tablename__ = "users"

    user_id = Column(String(64), primary_key=True, index=True)
    username = Column(String(64), unique=True, nullable=False, index=True)
    email = Column(String(128), unique=True, nullable=False, index=True)
    password_hash = Column(String(256), nullable=False)
    full_name = Column(String(128), nullable=False)
    role = Column(String(32), nullable=False, default="analyst", index=True)
    is_active = Column(Boolean, nullable=False, default=True)
    failed_login_attempts = Column(Integer, nullable=False, default=0)
    locked_until = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    refresh_tokens = relationship("RefreshTokenRecord", back_populates="user", cascade="all, delete-orphan")


class RefreshTokenRecord(Base):
    """Storage model for active/revoked refresh tokens."""
    __tablename__ = "refresh_tokens"

    token_id = Column(String(64), primary_key=True, index=True)
    user_id = Column(String(64), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash = Column(String(64), unique=True, nullable=False, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    revoked = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    user = relationship("UserRecord", back_populates="refresh_tokens")


class ApiClientRecord(Base):
    """Storage model for service-to-service API clients (e.g. MFS Core)."""
    __tablename__ = "api_clients"

    client_id = Column(String(64), primary_key=True, index=True)
    name = Column(String(128), nullable=False)
    key_hash = Column(String(64), unique=True, nullable=False, index=True)
    role = Column(String(32), nullable=False, default="service_core_mfs")
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


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
    """Storage model for cryptographically tamper-evident hash-chained operational audit records."""
    __tablename__ = "audit_logs"

    audit_id = Column(String(64), primary_key=True, index=True)
    sequence_number = Column(Integer, nullable=False, unique=True, index=True)
    prev_hash = Column(String(64), nullable=False)
    entry_hash = Column(String(64), nullable=False, unique=True, index=True)
    event_type = Column(String(64), nullable=False, index=True)
    user_id = Column(String(64), nullable=False, index=True)
    resource_type = Column(String(64), nullable=False, index=True)
    resource_id = Column(String(64), nullable=False, index=True)
    action = Column(String(64), nullable=False)
    details_json = Column(Text, nullable=False, default="{}")
    ts = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


class DatabaseStore:
    """Thread-safe database storage manager with RBAC and hash-chain audit logging."""

    def __init__(self, db_url: Optional[str] = None) -> None:
        if db_url is None:
            settings = get_settings()
            db_url = settings.gm_db_url

        self.db_url = db_url
        connect_args = {"check_same_thread": False} if self.db_url.startswith("sqlite") else {}
        self.engine = create_engine(self.db_url, connect_args=connect_args)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        self.create_tables()
        self.seed_default_identities()

    def create_tables(self) -> None:
        """Create all tables in the database, automatically migrating schema if needed."""
        try:
            from sqlalchemy import inspect, text
            with self.engine.connect() as conn:
                inspector = inspect(conn)
                if "audit_logs" in inspector.get_table_names():
                    cols = [c["name"] for c in inspector.get_columns("audit_logs")]
                    if "sequence_number" not in cols:
                        logger.info("Migrating audit_logs table to hash-chained schema...")
                        conn.execute(text("DROP TABLE audit_logs"))
                        conn.commit()
        except Exception as e:
            logger.warning("Table schema check warning: %s", e)

        Base.metadata.create_all(bind=self.engine)

    def get_session(self) -> Session:
        """Get a new database session."""
        return self.SessionLocal()

    def reset_all(self) -> None:
        """Clear dynamic tables (used for simulation reset). Retains users and client identities."""
        with self.get_session() as session:
            session.query(AuditLogRecord).delete()
            session.query(AnalystActionRecord).delete()
            session.query(FeedbackRecord).delete()
            session.query(AlertRecord).delete()
            session.query(DecisionRecord).delete()
            session.commit()

    # --- Hash-Chained Audit Logging ---

    def record_audit_log(
        self,
        session: Session,
        event_type: str,
        user_id: str,
        resource_type: str,
        resource_id: str,
        action: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> AuditLogRecord:
        """Record a tamper-evident audit log chained cryptographically to the preceding record."""
        details_dict = details or {}
        details_json = json.dumps(details_dict, sort_keys=True)

        # Retrieve last audit record to chain hash
        last_rec = (
            session.query(AuditLogRecord)
            .order_by(desc(AuditLogRecord.sequence_number))
            .first()
        )

        if last_rec is None:
            sequence_number = 1
            prev_hash = GENESIS_HASH
        else:
            sequence_number = last_rec.sequence_number + 1
            prev_hash = last_rec.entry_hash

        ts = datetime.now(timezone.utc)
        ts_str = format_audit_ts(ts)

        entry_hash = compute_entry_hash(
            prev_hash=prev_hash,
            sequence_number=sequence_number,
            event_type=event_type,
            user_id=user_id,
            resource_type=resource_type,
            resource_id=resource_id,
            action=action,
            details_json=details_json,
            ts_str=ts_str,
        )

        audit = AuditLogRecord(
            audit_id=f"AUD-{uuid.uuid4().hex[:12].upper()}",
            sequence_number=sequence_number,
            prev_hash=prev_hash,
            entry_hash=entry_hash,
            event_type=event_type,
            user_id=user_id,
            resource_type=resource_type,
            resource_id=resource_id,
            action=action,
            details_json=details_json,
            ts=ts,
        )
        session.add(audit)
        session.flush()
        return audit

    def verify_audit_chain(self) -> Tuple[bool, int, str, str, Optional[str]]:
        """Verify the integrity of the entire audit hash chain.

        Returns (is_valid, total_records, genesis_hash, last_hash, error_message).
        """
        with self.get_session() as session:
            records = (
                session.query(AuditLogRecord)
                .order_by(AuditLogRecord.sequence_number.asc())
                .all()
            )
            if not records:
                return True, 0, GENESIS_HASH, GENESIS_HASH, None

            expected_prev = GENESIS_HASH
            for r in records:
                if r.prev_hash != expected_prev:
                    return (
                        False,
                        len(records),
                        records[0].entry_hash,
                        records[-1].entry_hash,
                        f"Broken chain at sequence {r.sequence_number}: expected prev_hash {expected_prev}, found {r.prev_hash}",
                    )

                recalc = compute_entry_hash(
                    prev_hash=r.prev_hash,
                    sequence_number=r.sequence_number,
                    event_type=r.event_type,
                    user_id=r.user_id,
                    resource_type=r.resource_type,
                    resource_id=r.resource_id,
                    action=r.action,
                    details_json=r.details_json,
                    ts_str=format_audit_ts(r.ts),
                )
                if r.entry_hash != recalc:
                    return (
                        False,
                        len(records),
                        records[0].entry_hash,
                        records[-1].entry_hash,
                        f"Tampered record at sequence {r.sequence_number}: expected hash {recalc}, found {r.entry_hash}",
                    )
                expected_prev = r.entry_hash

            return True, len(records), records[0].entry_hash, records[-1].entry_hash, None

    # --- Identity & RBAC Management ---

    def seed_default_identities(self) -> None:
        """Seed default operational users and API client identities if not already present."""
        default_users = [
            {
                "user_id": "USR-KARIM",
                "username": "analyst_karim",
                "email": "karim.chowdhury@upay.com.bd",
                "password": "AnalystPass123!",
                "full_name": "Karim Chowdhury",
                "role": "analyst",
            },
            {
                "user_id": "USR-AYESHA",
                "username": "senior_ayesha",
                "email": "ayesha.siddiqua@upay.com.bd",
                "password": "SeniorPass123!",
                "full_name": "Ayesha Siddiqua",
                "role": "senior_analyst",
            },
            {
                "user_id": "USR-TARIQ",
                "username": "admin_tariq",
                "email": "tariq.hasan@upay.com.bd",
                "password": "AdminPass123!",
                "full_name": "Tariq Hasan",
                "role": "admin",
            },
            {
                "user_id": "USR-SALMAN",
                "username": "auditor_salman",
                "email": "salman.khan@upay.com.bd",
                "password": "AuditorPass123!",
                "full_name": "Salman Khan",
                "role": "auditor",
            },
            {
                "user_id": "USR-CUSTOMER",
                "username": "demo_customer",
                "email": "customer@goldenminutes.demo",
                "password": "CustomerPass123!",
                "full_name": "Demo Customer",
                "role": "customer_demo",
            },
        ]

        with self.get_session() as session:
            for u in default_users:
                existing = session.query(UserRecord).filter(UserRecord.username == u["username"]).first()
                if not existing:
                    user = UserRecord(
                        user_id=u["user_id"],
                        username=u["username"],
                        email=u["email"],
                        password_hash=hash_password(u["password"]),
                        full_name=u["full_name"],
                        role=u["role"],
                        is_active=True,
                        failed_login_attempts=0,
                        locked_until=None,
                    )
                    session.add(user)

            # Seed MFS Core API Client
            existing_client = session.query(ApiClientRecord).filter(ApiClientRecord.client_id == "core_mfs_client").first()
            if not existing_client:
                client = ApiClientRecord(
                    client_id="core_mfs_client",
                    name="upay MFS Core Banking Engine",
                    key_hash=hash_api_key("core_mfs_secret_key_2026"),
                    role="service_core_mfs",
                    is_active=True,
                )
                session.add(client)

            session.commit()

    def get_user_by_username(self, username: str) -> Optional[UserRecord]:
        """Fetch user by unique username."""
        with self.get_session() as session:
            return session.query(UserRecord).filter(UserRecord.username == username).first()

    def get_user_by_id(self, user_id: str) -> Optional[UserRecord]:
        """Fetch user by user_id."""
        with self.get_session() as session:
            return session.query(UserRecord).filter(UserRecord.user_id == user_id).first()

    def record_login_attempt(self, username: str, success: bool) -> Tuple[bool, Optional[str]]:
        """Record login attempt with lockout enforcement after max attempts."""
        settings = get_settings()
        with self.get_session() as session:
            user = session.query(UserRecord).filter(UserRecord.username == username).first()
            if not user:
                # Still log failed attempt for non-existent username
                self.record_audit_log(
                    session=session,
                    event_type="auth_failure",
                    user_id="anonymous",
                    resource_type="auth",
                    resource_id=username,
                    action="login_failed",
                    details={"reason": "user_not_found"},
                )
                session.commit()
                return False, "Invalid username or password"

            now = datetime.now(timezone.utc)
            locked_until = user.locked_until
            if locked_until is not None:
                if locked_until.tzinfo is None:
                    locked_until = locked_until.replace(tzinfo=timezone.utc)
                if locked_until > now:
                    remaining = int((locked_until - now).total_seconds() / 60) + 1
                    return False, f"Account is locked due to multiple failed attempts. Try again in {remaining} minute(s)."

            if success:
                user.failed_login_attempts = 0
                user.locked_until = None
                user.updated_at = now
                self.record_audit_log(
                    session=session,
                    event_type="auth_login",
                    user_id=user.user_id,
                    resource_type="auth",
                    resource_id=user.username,
                    action="login_success",
                    details={"role": user.role},
                )
                session.commit()
                return True, None
            else:
                user.failed_login_attempts += 1
                lockout_msg = None
                if user.failed_login_attempts >= settings.gm_max_login_attempts:
                    user.locked_until = now + timedelta(minutes=settings.gm_lockout_duration_minutes)
                    lockout_msg = f"Account locked for {settings.gm_lockout_duration_minutes} minutes due to excessive failed attempts."

                self.record_audit_log(
                    session=session,
                    event_type="auth_failure",
                    user_id=user.user_id,
                    resource_type="auth",
                    resource_id=user.username,
                    action="login_failed",
                    details={"attempt": user.failed_login_attempts, "locked": user.locked_until is not None},
                )
                session.commit()
                return False, lockout_msg or "Invalid username or password"

    def store_refresh_token(self, user_id: str, token_hash: str, expires_at: datetime) -> RefreshTokenRecord:
        """Store a new refresh token."""
        with self.get_session() as session:
            rec = RefreshTokenRecord(
                token_id=f"RT-{uuid.uuid4().hex[:12].upper()}",
                user_id=user_id,
                token_hash=token_hash,
                expires_at=expires_at,
                revoked=False,
            )
            session.add(rec)
            session.commit()
            session.refresh(rec)
            return rec

    def get_refresh_token(self, token_hash: str) -> Optional[RefreshTokenRecord]:
        """Fetch refresh token record by token_hash."""
        with self.get_session() as session:
            return session.query(RefreshTokenRecord).filter(RefreshTokenRecord.token_hash == token_hash).first()

    def revoke_refresh_token(self, token_hash: str) -> bool:
        """Revoke a refresh token on logout or rotation."""
        with self.get_session() as session:
            token = session.query(RefreshTokenRecord).filter(RefreshTokenRecord.token_hash == token_hash).first()
            if token:
                token.revoked = True
                self.record_audit_log(
                    session=session,
                    event_type="auth_token_revoked",
                    user_id=token.user_id,
                    resource_type="auth",
                    resource_id=token.token_id,
                    action="revoke_token",
                )
                session.commit()
                return True
            return False

    def verify_api_client_key(self, api_key: str) -> Optional[ApiClientRecord]:
        """Verify an API client key hash in constant time."""
        key_hash = hash_api_key(api_key)
        with self.get_session() as session:
            client = session.query(ApiClientRecord).filter(ApiClientRecord.key_hash == key_hash).first()
            if client and client.is_active:
                return client
            return None

    # --- Core Decision & Alert Operations ---

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
        """Persist transaction decision."""
        with self.get_session() as session:
            rec = DecisionRecord(
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
            session.add(rec)
            session.commit()
            session.refresh(rec)
            return rec

    def create_alert(
        self,
        alert_id: str,
        decision_id: str,
        txn_id: str,
        priority: float,
        money_at_risk: float,
        deadline_ts: datetime,
        sender_wallet_id: str,
        recipient_wallet_id: str,
        amount_bdt: float,
        risk_score: float,
        action: str,
        reason_codes: List[Dict[str, Any]],
        customer_message: Optional[Dict[str, Any]] = None,
        narrative: Optional[Dict[str, Any]] = None,
        evidence: Optional[Dict[str, Any]] = None,
        status: str = "open",
    ) -> AlertRecord:
        """Create an operational alert for an intervention with hash-chained audit."""
        with self.get_session() as session:
            rec = AlertRecord(
                alert_id=alert_id,
                decision_id=decision_id,
                txn_id=txn_id,
                status=status,
                priority=priority,
                money_at_risk=money_at_risk,
                deadline_ts=deadline_ts,
                sender_wallet_id=sender_wallet_id,
                recipient_wallet_id=recipient_wallet_id,
                amount_bdt=amount_bdt,
                risk_score=risk_score,
                action=action,
                reason_codes_json=json.dumps(reason_codes),
                customer_message_json=json.dumps(customer_message) if customer_message else None,
                narrative_json=json.dumps(narrative) if narrative else None,
                evidence_json=json.dumps(evidence or {}),
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
            session.add(rec)
            session.commit()
            session.refresh(rec)
            return rec

    def list_alerts(
        self,
        status_filter: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[AlertRecord]:
        """List alerts sorted by priority descending."""
        with self.get_session() as session:
            q = session.query(AlertRecord)
            if status_filter:
                q = q.filter(AlertRecord.status == status_filter)
            return q.order_by(desc(AlertRecord.priority)).offset(offset).limit(limit).all()

    def get_alert(self, alert_id: str) -> Optional[AlertRecord]:
        """Get alert record by ID."""
        with self.get_session() as session:
            return (
                session.query(AlertRecord)
                .options(joinedload(AlertRecord.actions))
                .filter(AlertRecord.alert_id == alert_id)
                .first()
            )

    def record_analyst_action(
        self,
        alert_id: str,
        analyst_id: str,
        action: str,
        note: Optional[str] = None,
    ) -> Tuple[AlertRecord, AnalystActionRecord]:
        """Record analyst decision and transition alert status with hash-chained audit."""
        with self.get_session() as session:
            alert = session.query(AlertRecord).filter(AlertRecord.alert_id == alert_id).first()
            if not alert:
                raise ValueError(f"Alert {alert_id} not found")

            if action in ("approve", "release"):
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

            self.record_audit_log(
                session=session,
                event_type="analyst_action",
                user_id=analyst_id,
                resource_type="alert",
                resource_id=alert_id,
                action=action,
                details={
                    "note": note,
                    "new_status": alert.status,
                    "money_at_risk": alert.money_at_risk,
                },
            )

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
        """Record customer or analyst feedback with hash-chained audit."""
        with self.get_session() as session:
            fb = FeedbackRecord(
                feedback_id=f"FB-{uuid.uuid4().hex[:10].upper()}",
                decision_id=decision_id,
                source=source,
                label=label,
                note=note,
                ts=datetime.now(timezone.utc),
            )
            session.add(fb)

            self.record_audit_log(
                session=session,
                event_type="feedback_recorded",
                user_id=source,
                resource_type="decision",
                resource_id=decision_id,
                action=label,
                details={"note": note},
            )

            session.commit()
            session.refresh(fb)
            return fb

    def get_audit_trail(
        self, resource_id: Optional[str] = None, limit: int = 100
    ) -> List[AuditLogRecord]:
        """Fetch audit log records ordered by sequence number descending."""
        with self.get_session() as session:
            q = session.query(AuditLogRecord)
            if resource_id:
                q = q.filter(AuditLogRecord.resource_id == resource_id)
            return q.order_by(desc(AuditLogRecord.sequence_number)).limit(limit).all()


# Global default store instance
_db_store: Optional[DatabaseStore] = None


def get_db_store() -> DatabaseStore:
    """Get or create singleton DatabaseStore."""
    global _db_store
    if _db_store is None:
        _db_store = DatabaseStore()
    return _db_store
