import hmac
from typing import List, Optional

from fastapi import Header, HTTPException, status

from goldenminutes.common.config import get_settings


def verify_api_key(x_api_key: Optional[str] = Header(None, alias="X-API-Key")) -> str:
    """Validate X-API-Key against configured environment keys in constant time.

    Returns the role: 'customer_demo' or 'analyst'.
    """
    settings = get_settings()

    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "UNAUTHORIZED", "message": "Missing X-API-Key header"},
        )

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
    """Dependency factory checking that the caller has one of the allowed roles."""

    def role_checker(
        x_api_key: Optional[str] = Header(None, alias="X-API-Key", description="API Key"),
    ) -> str:
        actual_role = verify_api_key(x_api_key)
        if actual_role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "FORBIDDEN",
                    "message": f"Endpoint requires one of roles: {allowed_roles}, got: {actual_role}",
                },
            )
        return actual_role

    return role_checker


# Public demo safety stopgap (D2 option a):
# public_demo has sandbox read-access to analyst views, while real analyst key retains full privilege.
require_analyst = require_roles(["analyst", "public_demo"])
require_authenticated = require_roles(["customer_demo", "analyst", "public_demo"])
