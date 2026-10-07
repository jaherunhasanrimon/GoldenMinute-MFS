"""GoldenMinutes FastAPI application with real scoring, policy, alerts, graph, and simulation."""

from __future__ import annotations

import hashlib
import json
import logging
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from fastapi import Cookie, Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from goldenminutes.api.auth import (
    create_access_token,
    create_refresh_token,
    verify_password,
)
from goldenminutes.api.deps import (
    get_current_user,
    get_optional_current_user,
    require_analyst,
    require_authenticated,
    require_senior_analyst,
)
from goldenminutes.api.service import get_service
from goldenminutes.api.store import AlertRecord, AnalystActionRecord, DecisionRecord, UserRecord
from goldenminutes.common.config import get_settings
from goldenminutes.common.schemas import (
    AlertDecisionRequest,
    AlertDecisionResponse,
    AlertDetailResponse,
    AlertListResponse,
    AlertSummary,
    AuditLogEntry,
    AuditLogListResponse,
    AuditVerifyResponse,
    CustomerMessage,
    DemoAccount,
    DemoAccountsResponse,
    ErrorDetail,
    ErrorResponse,
    FeedbackRequest,
    FeedbackResponse,
    GraphEdge,
    GraphNode,
    GraphResponse,
    HealthResponse,
    LoginRequest,
    MetricsResponse,
    ReasonCode,
    RefreshTokenRequest,
    ScoreRequest,
    ScoreResponse,
    SimulateAttackRequest,
    SimulateAttackResponse,
    SimulateResetResponse,
    TokenResponse,
    UserSummary,
)
from goldenminutes.demo.scenarios import run_attack


class RequestIdFormatter(logging.Formatter):
    def format(self, record):
        if not hasattr(record, "request_id"):
            record.request_id = "-"
        return super().format(record)


handler = logging.StreamHandler()
handler.setFormatter(
    RequestIdFormatter("%(asctime)s [%(levelname)s] [req_id=%(request_id)s] %(message)s")
)
logger = logging.getLogger("goldenminutes.api")
logger.setLevel(logging.INFO)
if not logger.handlers:
    logger.addHandler(handler)


def create_app() -> FastAPI:
    """Application factory for GoldenMinutes API."""
    settings = get_settings()
    service = get_service()

    app = FastAPI(
        title="GoldenMinutes API",
        version="0.1.0",
        description="Real-Time Scam and Mule Interception for upay",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    # 1. CORS Middleware
    cors_origins = [o.strip() for o in settings.gm_cors_origins.split(",") if o.strip()]
    if "*" in cors_origins:
        cors_origins = ["*"]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID", "X-Process-Time"],
    )

    # 2. Request-ID Middleware (X-GM-Stub is completely removed for P4)
    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        req_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        start_time = time.perf_counter()

        response = await call_next(request)

        duration_ms = (time.perf_counter() - start_time) * 1000
        response.headers["X-Request-ID"] = req_id
        response.headers["X-Process-Time"] = f"{duration_ms:.2f}ms"

        return response

    # 3. Standardized Error Handlers (C8, error shape)
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        detail = exc.detail
        if isinstance(detail, dict) and "code" in detail and "message" in detail:
            error_body = ErrorResponse(
                error=ErrorDetail(
                    code=detail.get("code", "ERROR"),
                    message=detail.get("message", "An error occurred"),
                    details=detail.get("details"),
                )
            )
        else:
            code_str = "NOT_FOUND" if exc.status_code == 404 else f"HTTP_{exc.status_code}"
            error_body = ErrorResponse(
                error=ErrorDetail(
                    code=code_str,
                    message=str(detail),
                )
            )
        return JSONResponse(
            status_code=exc.status_code,
            content=error_body.model_dump(),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        error_body = ErrorResponse(
            error=ErrorDetail(
                code="VALIDATION_ERROR",
                message="Request validation failed",
                details=exc.errors(),
            )
        )
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=error_body.model_dump(),
        )

    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception):
        logger.exception("Unhandled server error: %s", exc)
        error_body = ErrorResponse(
            error=ErrorDetail(
                code="INTERNAL_SERVER_ERROR",
                message="An unexpected server error occurred",
            )
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=error_body.model_dump(),
        )

    # 3.1 Authentication & User Session Endpoints (Phase 3)
    @app.post("/v1/auth/login", response_model=TokenResponse, tags=["Authentication"])
    def login(login_req: LoginRequest, response: Response) -> TokenResponse:
        """Authenticate user, enforce lockout, issue JWT access & refresh tokens."""
        user = service.db.get_user_by_username(login_req.username)
        if not user:
            service.db.record_login_attempt(login_req.username, success=False)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": "INVALID_CREDENTIALS", "message": "Invalid username or password"},
            )

        is_valid = verify_password(login_req.password, user.password_hash)
        success, err_msg = service.db.record_login_attempt(user.username, success=is_valid)
        if not success:
            code = "ACCOUNT_LOCKED" if "locked" in (err_msg or "").lower() else "INVALID_CREDENTIALS"
            status_code = status.HTTP_403_FORBIDDEN if code == "ACCOUNT_LOCKED" else status.HTTP_401_UNAUTHORIZED
            raise HTTPException(
                status_code=status_code,
                detail={"code": code, "message": err_msg or "Invalid username or password"},
            )

        access_token = create_access_token(
            data={
                "sub": user.user_id,
                "user_id": user.user_id,
                "username": user.username,
                "role": user.role,
                "full_name": user.full_name,
            }
        )
        raw_refresh, token_hash = create_refresh_token()
        expires_at = datetime.now(timezone.utc) + timedelta(days=settings.gm_refresh_token_expire_days)
        service.db.store_refresh_token(user_id=user.user_id, token_hash=token_hash, expires_at=expires_at)

        # Set secure httpOnly cookies for web browsers
        is_secure = settings.gm_env == "prod"
        response.set_cookie(
            key="gm_access_token",
            value=access_token,
            httponly=True,
            samesite="lax",
            secure=is_secure,
            max_age=settings.gm_access_token_expire_minutes * 60,
        )
        response.set_cookie(
            key="gm_refresh_token",
            value=raw_refresh,
            httponly=True,
            samesite="lax",
            secure=is_secure,
            max_age=settings.gm_refresh_token_expire_days * 86400,
        )

        return TokenResponse(
            access_token=access_token,
            refresh_token=raw_refresh,
            token_type="bearer",
            expires_in=settings.gm_access_token_expire_minutes * 60,
            user=UserSummary(
                user_id=user.user_id,
                username=user.username,
                full_name=user.full_name,
                email=user.email,
                role=user.role,
                is_active=user.is_active,
            ),
        )

    @app.post("/v1/auth/refresh", response_model=TokenResponse, tags=["Authentication"])
    def refresh_user_token(
        response: Response,
        refresh_req: Optional[RefreshTokenRequest] = None,
        gm_refresh_token: Optional[str] = Cookie(None),
    ) -> TokenResponse:
        """Rotate refresh token and issue new JWT access token."""
        raw_token = (refresh_req.refresh_token if refresh_req and refresh_req.refresh_token else None) or gm_refresh_token
        if not raw_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": "UNAUTHORIZED", "message": "Missing refresh token"},
            )

        token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
        rec = service.db.get_refresh_token(token_hash)
        if not rec or rec.revoked:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": "TOKEN_INVALID", "message": "Invalid or expired refresh token"},
            )

        exp = rec.expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if exp < datetime.now(timezone.utc):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": "TOKEN_EXPIRED", "message": "Refresh token expired"},
            )

        user = service.db.get_user_by_id(rec.user_id)
        if not user or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": "USER_DISABLED", "message": "User account inactive"},
            )

        # Rotate token
        service.db.revoke_refresh_token(token_hash)
        new_raw_refresh, new_token_hash = create_refresh_token()
        new_expires_at = datetime.now(timezone.utc) + timedelta(days=settings.gm_refresh_token_expire_days)
        service.db.store_refresh_token(user_id=user.user_id, token_hash=new_token_hash, expires_at=new_expires_at)

        new_access_token = create_access_token(
            data={
                "sub": user.user_id,
                "user_id": user.user_id,
                "username": user.username,
                "role": user.role,
                "full_name": user.full_name,
            }
        )

        is_secure = settings.gm_env == "prod"
        response.set_cookie(
            key="gm_access_token",
            value=new_access_token,
            httponly=True,
            samesite="lax",
            secure=is_secure,
            max_age=settings.gm_access_token_expire_minutes * 60,
        )
        response.set_cookie(
            key="gm_refresh_token",
            value=new_raw_refresh,
            httponly=True,
            samesite="lax",
            secure=is_secure,
            max_age=settings.gm_refresh_token_expire_days * 86400,
        )

        return TokenResponse(
            access_token=new_access_token,
            refresh_token=new_raw_refresh,
            token_type="bearer",
            expires_in=settings.gm_access_token_expire_minutes * 60,
            user=UserSummary(
                user_id=user.user_id,
                username=user.username,
                full_name=user.full_name,
                email=user.email,
                role=user.role,
                is_active=user.is_active,
            ),
        )

    @app.post("/v1/auth/logout", tags=["Authentication"])
    def logout(
        response: Response,
        refresh_req: Optional[RefreshTokenRequest] = None,
        gm_refresh_token: Optional[str] = Cookie(None),
    ) -> Dict[str, str]:
        """Revoke refresh token and clear authentication session cookies."""
        raw_token = (refresh_req.refresh_token if refresh_req and refresh_req.refresh_token else None) or gm_refresh_token
        if raw_token:
            token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
            service.db.revoke_refresh_token(token_hash)

        response.delete_cookie(key="gm_access_token")
        response.delete_cookie(key="gm_refresh_token")
        return {"status": "ok", "message": "Successfully logged out"}

    @app.get("/v1/auth/me", response_model=UserSummary, tags=["Authentication"])
    def get_current_user_profile(user: UserRecord = Depends(get_current_user)) -> UserSummary:
        """Return profile and role for current authenticated user."""
        return UserSummary(
            user_id=user.user_id,
            username=user.username,
            full_name=user.full_name,
            email=user.email,
            role=user.role,
            is_active=user.is_active,
        )

    # 3.2 Audit Chain Verification Endpoints
    @app.get("/v1/audit/verify", response_model=AuditVerifyResponse, tags=["Audit"])
    def verify_audit_trail(role: str = Depends(require_senior_analyst)) -> AuditVerifyResponse:
        """Cryptographically verify the entire SHA-256 audit hash chain."""
        is_valid, total, genesis, last, err = service.db.verify_audit_chain()
        return AuditVerifyResponse(
            valid=is_valid,
            total_records=total,
            genesis_hash=genesis,
            last_hash=last,
            error=err,
        )

    @app.get("/v1/audit/logs", response_model=AuditLogListResponse, tags=["Audit"])
    def list_audit_logs(
        resource_id: Optional[str] = None,
        limit: int = 100,
        role: str = Depends(require_senior_analyst),
    ) -> AuditLogListResponse:
        """Fetch audit log records ordered by sequence descending with hash links."""
        records = service.db.get_audit_trail(resource_id=resource_id, limit=limit)
        is_valid, _, _, _, _ = service.db.verify_audit_chain()
        logs = [
            AuditLogEntry(
                audit_id=r.audit_id,
                sequence_number=r.sequence_number,
                prev_hash=r.prev_hash,
                entry_hash=r.entry_hash,
                event_type=r.event_type,
                user_id=r.user_id,
                resource_type=r.resource_type,
                resource_id=r.resource_id,
                action=r.action,
                details=json.loads(r.details_json) if r.details_json else {},
                ts=r.ts,
            )
            for r in records
        ]
        return AuditLogListResponse(logs=logs, total=len(logs), chain_valid=is_valid)

    # 4. Health endpoint
    @app.get("/health", response_model=HealthResponse, tags=["System"])
    def get_health() -> HealthResponse:
        return HealthResponse(
            status="ok",
            model_version=service.active_version,
            policy_version=service.policy.version,
            environment=settings.gm_env,
            models_loaded=getattr(service, "models_loaded", False),
            degraded=getattr(service, "degraded", True),
            artifact_source=getattr(service, "artifact_source", "none"),
        )

    # 5. POST /v1/score (Real pipeline)
    @app.post("/v1/score", response_model=ScoreResponse, tags=["Scoring"])
    def score_transaction(
        score_req: ScoreRequest,
        role: str = Depends(require_authenticated),
    ) -> ScoreResponse:
        """Score a send_money transaction and return proportionate intervention."""
        return service.score(score_req)

    # 6. GET /v1/alerts (Real alert queue)
    @app.get("/v1/alerts", response_model=AlertListResponse, tags=["Analyst"])
    def list_alerts(
        status_filter: Optional[str] = None,
        role: str = Depends(require_analyst),
    ) -> AlertListResponse:
        """List alerts sorted by priority descending."""
        records = service.db.list_alerts(status_filter=status_filter)
        summaries: List[AlertSummary] = []
        for r in records:
            summaries.append(
                AlertSummary(
                    alert_id=r.alert_id,
                    decision_id=r.decision_id,
                    txn_id=r.txn_id,
                    status=r.status,  # type: ignore[arg-type]
                    priority=r.priority,
                    money_at_risk=r.money_at_risk,
                    deadline_ts=r.deadline_ts,
                    created_at=r.created_at,
                    sender_wallet_id=r.sender_wallet_id,
                    recipient_wallet_id=r.recipient_wallet_id,
                    amount_bdt=r.amount_bdt,
                )
            )
        return AlertListResponse(alerts=summaries, total=len(summaries))

    # 7. GET /v1/alerts/{alert_id} (Real alert detail)
    @app.get("/v1/alerts/{alert_id}", response_model=AlertDetailResponse, tags=["Analyst"])
    def get_alert_detail(
        alert_id: str,
        role: str = Depends(require_analyst),
    ) -> AlertDetailResponse:
        """Get alert details, evidence, narrative, reason codes, and actions taken."""
        record = service.db.get_alert(alert_id)
        if not record:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "NOT_FOUND", "message": f"Alert {alert_id} not found"},
            )

        reason_codes_data = json.loads(record.reason_codes_json or "[]")
        reason_codes = [ReasonCode(**rc) for rc in reason_codes_data]

        cust_msg = None
        if record.customer_message_json:
            cust_msg = CustomerMessage(**json.loads(record.customer_message_json))

        narrative = json.loads(record.narrative_json) if record.narrative_json else None
        evidence = json.loads(record.evidence_json) if record.evidence_json else {}

        actions_taken = [
            {
                "id": a.id,
                "action": a.action,
                "analyst_id": a.analyst_id,
                "note": a.note,
                "ts": a.ts.isoformat(),
            }
            for a in record.actions
        ]

        return AlertDetailResponse(
            alert_id=record.alert_id,
            decision_id=record.decision_id,
            txn_id=record.txn_id,
            status=record.status,  # type: ignore[arg-type]
            priority=record.priority,
            money_at_risk=record.money_at_risk,
            deadline_ts=record.deadline_ts,
            created_at=record.created_at,
            risk_score=record.risk_score,
            action=record.action,  # type: ignore[arg-type]
            reason_codes=reason_codes,
            sender_wallet_id=record.sender_wallet_id,
            recipient_wallet_id=record.recipient_wallet_id,
            amount_bdt=record.amount_bdt,
            customer_message=cust_msg,
            narrative=narrative,
            evidence=evidence,
            actions_taken=actions_taken,
        )

    # 8. POST /v1/alerts/{alert_id}/decision (Real analyst action, four-eyes enforcement & audit log)
    @app.post(
        "/v1/alerts/{alert_id}/decision", response_model=AlertDecisionResponse, tags=["Analyst"]
    )
    def decide_alert(
        alert_id: str,
        decision_req: AlertDecisionRequest,
        role: str = Depends(require_analyst),
        user: Optional[UserRecord] = Depends(get_optional_current_user),
    ) -> AlertDecisionResponse:
        """Record analyst action (approve, release, escalate) with four-eyes enforcement and hash-chain audit."""
        # Release requires an explanatory note
        if decision_req.action == "release" and not (
            decision_req.note and decision_req.note.strip()
        ):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "code": "VALIDATION_ERROR",
                    "message": "Release action requires an explanatory note",
                },
            )

        target_alert = service.db.get_alert(alert_id)
        if not target_alert:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "NOT_FOUND", "message": f"Alert {alert_id} not found"},
            )

        # Four-Eyes rule: Releasing holds with high money-at-risk requires senior_analyst or admin
        if decision_req.action in ("release", "approve"):
            if target_alert.money_at_risk >= settings.gm_four_eyes_threshold_bdt:
                effective_role = user.role if user else role
                if effective_role not in ("senior_analyst", "admin"):
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail={
                            "code": "FOUR_EYES_REQUIRED",
                            "message": (
                                f"Four-Eyes dual authorization required: Releasing holds with money-at-risk >= "
                                f"৳{settings.gm_four_eyes_threshold_bdt:,.2f} requires senior analyst sign-off "
                                f"(current role: '{effective_role}', alert money at risk: ৳{target_alert.money_at_risk:,.2f})."
                            ),
                        },
                    )

        # Attribute action to individual user or fallback for legacy role
        analyst_id = user.user_id if user else getattr(decision_req, "analyst_id", f"analyst_{role}")

        try:
            alert, action = service.db.record_analyst_action(
                alert_id=alert_id,
                action=decision_req.action,
                analyst_id=analyst_id,
                note=decision_req.note,
            )
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "NOT_FOUND", "message": str(e)},
            ) from e

        return AlertDecisionResponse(
            alert_id=alert.alert_id,
            status=alert.status,  # type: ignore[arg-type]
            action_taken=decision_req.action,
            analyst_id=action.analyst_id,
            ts=action.ts,
            note=action.note,
        )

    # 9. POST /v1/feedback (Real feedback persistence)
    @app.post("/v1/feedback", response_model=FeedbackResponse, tags=["Scoring"])
    def submit_feedback(
        feedback_req: FeedbackRequest,
        role: str = Depends(require_authenticated),
    ) -> FeedbackResponse:
        """Record customer or analyst feedback with audit trail."""
        fb = service.db.record_feedback(
            decision_id=feedback_req.decision_id,
            source=feedback_req.source,
            label=feedback_req.label,
        )
        return FeedbackResponse(
            feedback_id=fb.feedback_id,
            status="recorded",
        )

    # 10. GET /v1/graph/{wallet_id} (Real local neighborhood graph)
    @app.get("/v1/graph/{wallet_id}", response_model=GraphResponse, tags=["Analyst"])
    def get_wallet_graph(
        wallet_id: str,
        role: str = Depends(require_analyst),
    ) -> GraphResponse:
        """Return 1-2 hop neighborhood graph for a wallet based on online feature store."""
        nodes: Dict[str, GraphNode] = {}
        edges: List[GraphEdge] = []

        # Risk/mule attributes come from live decisions and alerts only (None when unknown).
        risk_by_wallet: Dict[str, float] = {}
        mule_wallets: set = set()
        with service.db.get_session() as sess:
            for d in sess.query(DecisionRecord).filter(
                (DecisionRecord.sender_wallet_id == wallet_id)
                | (DecisionRecord.recipient_wallet_id == wallet_id)
            ):
                for w in (d.sender_wallet_id, d.recipient_wallet_id):
                    risk_by_wallet[w] = max(risk_by_wallet.get(w, 0.0), float(d.risk_score))
            for a in sess.query(AlertRecord).filter(AlertRecord.action == "hold"):
                mule_wallets.add(a.recipient_wallet_id)

        def _attrs(wid: str) -> Dict[str, object]:
            return {"risk_score": risk_by_wallet.get(wid), "is_mule": wid in mule_wallets}

        nodes[wallet_id] = GraphNode(
            id=wallet_id, label=f"Wallet {wallet_id}", type="wallet", **_attrs(wallet_id)
        )

        # Inflows to target wallet
        inflows = service.features.recipient_inflows.get(wallet_id, [])
        sender_agg: Dict[str, Tuple[float, int]] = {}
        for entry in inflows:
            s_id = entry[1]
            amt = entry[2]
            prev_amt, prev_cnt = sender_agg.get(s_id, (0.0, 0))
            sender_agg[s_id] = (prev_amt + amt, prev_cnt + 1)

        for s_id, (amt, cnt) in sender_agg.items():
            if s_id not in nodes:
                nodes[s_id] = GraphNode(
                    id=s_id,
                    label=f"Sender {s_id}",
                    type="wallet",
                    **_attrs(s_id),
                )
            edges.append(
                GraphEdge(
                    source=s_id,
                    target=wallet_id,
                    amount_bdt=amt,
                    txn_count=cnt,
                )
            )

        # Outflows from target wallet
        outflows = service.features.wallet_outflows.get(wallet_id, [])
        for entry in outflows:
            r_id = entry[1]
            amt = entry[2]
            if r_id:
                if r_id not in nodes:
                    nodes[r_id] = GraphNode(
                        id=r_id,
                        label=f"Recipient {r_id}",
                        type="wallet",
                        **_attrs(r_id),
                    )
                edges.append(
                    GraphEdge(
                        source=wallet_id,
                        target=r_id,
                        amount_bdt=amt,
                        txn_count=1,
                    )
                )

        # Devices used
        devs = service.features.sender_devices.get(wallet_id, set())
        for d in devs:
            nodes[d] = GraphNode(
                id=d,
                label=f"Device {d}",
                type="device",
            )
            edges.append(
                GraphEdge(
                    source=wallet_id,
                    target=d,
                    amount_bdt=0.0,
                    txn_count=1,
                )
            )

        return GraphResponse(wallet_id=wallet_id, nodes=list(nodes.values()), edges=edges)

    # 11. GET /v1/metrics (Real metrics and live counters)
    @app.get("/v1/metrics", response_model=MetricsResponse, tags=["Analytics"])
    def get_metrics(
        role: str = Depends(require_analyst),
    ) -> MetricsResponse:
        """Return system KPIs, ablation results, and live database counters."""
        repo_root = Path(__file__).resolve().parents[3]
        metrics_file = repo_root / "reports" / "metrics.json"

        # Count live database decisions, alerts, and resolution duration
        with service.db.get_session() as s:
            live_scored = s.query(DecisionRecord).count()
            live_alerts = s.query(AlertRecord).count()

            durations = []
            for action in s.query(AnalystActionRecord).all():
                if action.alert and action.alert.created_at:
                    dur = (action.ts - action.alert.created_at).total_seconds() / 60.0
                    if dur >= 0:
                        durations.append(dur)
            import numpy as np

            live_hold_res = round(float(np.median(durations)), 2) if durations else None

        if metrics_file.exists():
            try:
                with open(metrics_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                data["total_scored"] = data.get("total_scored", 0) + live_scored
                data["total_alerts"] = data.get("total_alerts", 0) + live_alerts
                data["hold_resolution_minutes"] = live_hold_res
                lift_file = repo_root / "reports" / "lift.json"
                if lift_file.exists():
                    try:
                        with open(lift_file, "r", encoding="utf-8") as lf:
                            lift = json.load(lf)
                        diffs = lift.get("bootstrap", {}).get("differences", {})
                        data["lift_summary"] = {
                            "profile": lift.get("profile"),
                            "n_bootstraps": lift.get("bootstrap", {}).get("n_bootstraps"),
                            "pr_auc_deltas": {k: v.get("pr_auc") for k, v in diffs.items()},
                            "rewiring_test": lift.get("rewiring_test"),
                            "max_single_feature": {
                                "feature": lift.get("single_feature_auc_scan", {}).get(
                                    "max_feature"
                                ),
                                "roc_auc": lift.get("single_feature_auc_scan", {}).get("max_auc"),
                            },
                        }
                    except Exception as e:  # pragma: no cover - report is optional
                        logger.warning("Failed to parse reports/lift.json: %s", e)
                return MetricsResponse(**data)
            except Exception as e:
                logger.warning("Failed to parse reports/metrics.json: %s", e)

        # reports/metrics.json missing: report only live counters, no invented figures.
        return MetricsResponse(
            fraud_value_intercepted_bdt=0.0,
            false_friction_rate=0.0,
            median_decision_time_ms=0.0,
            p95_decision_time_ms=0.0,
            ablation_table=[],
            held_out_typology_recall=0.0,
            fairness_slices={},
            hold_resolution_minutes=live_hold_res,
            total_scored=live_scored,
            total_alerts=live_alerts,
        )

    # 12. POST /v1/simulate/attack (Real attack replay creating active alert)
    @app.post("/v1/simulate/attack", response_model=SimulateAttackResponse, tags=["Simulation"])
    def simulate_attack(
        req: Optional[SimulateAttackRequest] = None,
        role: str = Depends(require_authenticated),
    ) -> SimulateAttackResponse:
        """Trigger replay of synthetic impersonation/mule attack demo scenario."""
        attack_req = req or SimulateAttackRequest()
        out = run_attack(service)
        res3 = out["final"]
        return SimulateAttackResponse(
            status="started",
            scenario_id=attack_req.scenario_id or "impersonation_scam_01",
            message=f"Attack scenario replayed: 35,000 BDT transfer intercepted with {res3.action.upper()}",
            steps=out["steps"],
        )

    # 13. POST /v1/simulate/reset (Real simulation state reset)
    @app.post("/v1/simulate/reset", response_model=SimulateResetResponse, tags=["Simulation"])
    def simulate_reset(
        role: str = Depends(require_authenticated),
    ) -> SimulateResetResponse:
        """Reset simulation state, database tables, and hold tracking."""
        service.reset()
        return SimulateResetResponse(
            status="reset_completed",
            message="Demo simulation state and alert queue reset to baseline",
        )

    # 14. GET /v1/demo/accounts
    @app.get("/v1/demo/accounts", response_model=DemoAccountsResponse, tags=["Simulation"])
    def get_demo_accounts(
        role: str = Depends(require_authenticated),
    ) -> DemoAccountsResponse:
        """Get preconfigured synthetic sender and recipient demo accounts."""
        senders = [
            DemoAccount(
                wallet_id="W01928",
                customer_id="C10001",
                name="Karim Ahmed (Salaried)",
                balance_bdt=45000.0,
                persona="salaried",
                description="Regular monthly salary receiver, uses app in Dhaka",
            ),
            DemoAccount(
                wallet_id="W01443",
                customer_id="C10002",
                name="Fatima Begum (Student)",
                balance_bdt=12000.0,
                persona="student",
                description="University student, sends occasional small peer payments",
            ),
            DemoAccount(
                wallet_id="W03312",
                customer_id="C10003",
                name="Rafiqul Islam (Trader)",
                balance_bdt=85000.0,
                persona="small_trader",
                description="Small grocery merchant, frequent supplier payments",
            ),
        ]
        recipients = [
            DemoAccount(
                wallet_id="W08371",
                customer_id="C90001",
                name="Suspicious Mule W08371",
                balance_bdt=3400.0,
                persona="mule",
                description="Fresh wallet, high fan-in burst, rapid pass-through history",
            ),
            DemoAccount(
                wallet_id="W07712",
                customer_id="C90002",
                name="Shakil Mia (Known Relative)",
                balance_bdt=8500.0,
                persona="legitimate",
                description="Trusted regular recipient with frequent past transfers",
            ),
            DemoAccount(
                wallet_id="W09920",
                customer_id="C90003",
                name="Ayesha Khatun (House Rent)",
                balance_bdt=22000.0,
                persona="legitimate_large",
                description="Monthly legitimate large transfer (confounder scenario)",
            ),
        ]
        return DemoAccountsResponse(senders=senders, recipients=recipients)

    # Mount built UI static files from ui/dist if present (make demo support)
    ui_dist = Path(__file__).resolve().parents[3] / "ui" / "dist"
    if ui_dist.exists() and (ui_dist / "index.html").exists():
        if (ui_dist / "assets").exists():
            app.mount("/assets", StaticFiles(directory=str(ui_dist / "assets")), name="ui_assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        def serve_spa(full_path: str):
            candidate = ui_dist / full_path
            if full_path and candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(ui_dist / "index.html")

    return app


app = create_app()
