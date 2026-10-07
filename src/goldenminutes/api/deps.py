"""FastAPI Dependencies for Authentication, JWT Sessions, and Role-Based Access Control."""

from __future__ import annotations

import hmac
from datetime import datetime, timezone
from typing import List, Optional

import jwt
from fastapi import Cookie, Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from goldenminutes.api.auth import decode_access_token
from goldenminutes.api.store import DatabaseStore, UserRecord, get_db_store
from goldenminutes.common.config import get_settings

security = HTTPBearer(auto_error=False)


def get_current_user(
    auth: Optional[HTTPAuthorizationCredentials] = Depends(security),
    gm_access_token: Optional[str] = Cookie(None),
    db: DatabaseStore = Depends(get_db_store),
) -> UserRecord:
    """Validate JWT access token from Authorization header or httpOnly cookie.

    Returns the authenticated UserRecord.
    """
    token = None
    if auth and auth.credentials:
        token = auth.credentials
    elif gm_access_token:
        token = gm_access_token

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "UNAUTHORIZED", "message": "Authentication required"},
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = decode_access_token(token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "TOKEN_EXPIRED", "message": "Access token has expired"},
            headers={"WWW-Authenticate": "Bearer"},
        ) from None
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "INVALID_TOKEN", "message": "Invalid access token signature"},
            headers={"WWW-Authenticate": "Bearer"},
        ) from None

    user_id = payload.get("sub") or payload.get("user_id")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "INVALID_TOKEN", "message": "Token missing user identifier"},
        )

    user = db.get_user_by_id(user_id)
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "USER_DISABLED", "message": "User account is disabled or does not exist"},
        )

    # Check lockout
    now = datetime.now(timezone.utc)
    locked_until = user.locked_until
    if locked_until is not None:
        if locked_until.tzinfo is None:
            locked_until = locked_until.replace(tzinfo=timezone.utc)
        if locked_until > now:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"code": "ACCOUNT_LOCKED", "message": "User account is temporarily locked"},
            )

    return user


def get_optional_current_user(
    auth: Optional[HTTPAuthorizationCredentials] = Depends(security),
    gm_access_token: Optional[str] = Cookie(None),
    db: DatabaseStore = Depends(get_db_store),
) -> Optional[UserRecord]:
    """Extract authenticated user if valid token present, else return None."""
    token = None
    if auth and auth.credentials:
        token = auth.credentials
    elif gm_access_token:
        token = gm_access_token

    if not token:
        return None

    try:
        payload = decode_access_token(token)
        user_id = payload.get("sub") or payload.get("user_id")
        if user_id:
            return db.get_user_by_id(user_id)
    except Exception:
        return None
    return None


def verify_api_key(
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    db: DatabaseStore = Depends(get_db_store),
) -> str:
    """Validate X-API-Key against hashed client table and environment keys.

    Returns the verified role.
    """
    settings = get_settings()

    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "UNAUTHORIZED", "message": "Missing X-API-Key header"},
        )

    # Check database-backed API clients
    client = db.verify_api_client_key(x_api_key)
    if client:
        return client.role

    # Environment keys (constant-time compare)
    if hmac.compare_digest(x_api_key, settings.gm_analyst_key):
        return "analyst"
    elif hmac.compare_digest(x_api_key, settings.gm_public_demo_key):
        return "public_demo"
    elif hmac.compare_digest(x_api_key, settings.gm_customer_key):
        return "customer_demo"
    else:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "FORBIDDEN", "message": "Invalid API key"},
        )


def require_roles(allowed_roles: List[str]):
    """Flexible dependency checking either JWT session role or API Key role."""

    def role_checker(
        user: Optional[UserRecord] = Depends(get_optional_current_user),
        x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
        db: DatabaseStore = Depends(get_db_store),
    ) -> str:
        if user is not None:
            if user.role in allowed_roles:
                return user.role
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "FORBIDDEN",
                    "message": f"Endpoint requires one of roles: {allowed_roles}, got: {user.role}",
                },
            )

        if x_api_key:
            key_role = verify_api_key(x_api_key, db=db)
            if key_role in allowed_roles:
                return key_role
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "FORBIDDEN",
                    "message": f"Endpoint requires one of roles: {allowed_roles}, got: {key_role}",
                },
            )

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "UNAUTHORIZED", "message": "Authentication required via JWT or API key"},
        )

    return role_checker


# Role dependencies
require_analyst = require_roles(["analyst", "senior_analyst", "admin", "public_demo"])
require_senior_analyst = require_roles(["senior_analyst", "admin"])
require_admin = require_roles(["admin"])
require_authenticated = require_roles([
    "customer_demo",
    "analyst",
    "senior_analyst",
    "admin",
    "auditor",
    "public_demo",
    "service_core_mfs",
])
