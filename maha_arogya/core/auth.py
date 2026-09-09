"""
Role-Based Access Control (RBAC) & API-Key Authentication for MahaArogya-Agent.
Enforces separation of duties across ASHA Workers, PHC Medical Officers, and District Health Officers (DHO).
"""

from enum import Enum
from typing import List, Optional, Any
from fastapi import Header, HTTPException, Security, status
from pydantic import BaseModel


class UserRole(str, Enum):
    ASHA_WORKER = "ASHA_WORKER"
    PHC_DOCTOR = "PHC_DOCTOR"
    DHO_OFFICER = "DHO_OFFICER"
    STATE_ADMIN = "STATE_ADMIN"


class AuthenticatedUser(BaseModel):
    user_id: str
    role: UserRole
    organization: str = "Arogya Vibhag, Maharashtra"


# Configured Role API Keys for SIH Demonstration
ROLE_API_KEYS = {
    "maha-asha-2026": AuthenticatedUser(user_id="ASHA-PUN-042", role=UserRole.ASHA_WORKER),
    "maha-doctor-2026": AuthenticatedUser(user_id="MO-DR-KULKARNI", role=UserRole.PHC_DOCTOR),
    "maha-dho-2026": AuthenticatedUser(user_id="DHO-DR-PATIL", role=UserRole.DHO_OFFICER),
    "maha-admin-2026": AuthenticatedUser(user_id="ADMIN-SYS", role=UserRole.STATE_ADMIN),
}

DEFAULT_DEMO_USER = AuthenticatedUser(user_id="DEMO-USER-GUEST", role=UserRole.STATE_ADMIN)


def verify_role_api_key(
    arg1: Any = None,
    arg2: Any = None
) -> AuthenticatedUser:
    """
    Validates API key and verifies that user has permission for the requested endpoint.
    Accepts either (x_api_key, allowed_roles) or (allowed_roles, x_api_key).
    Defaults to demo user if no key is provided during live browser hackathon demonstration.
    """
    x_api_key: Optional[str] = None
    allowed_roles: List[UserRole] = []

    if isinstance(arg1, str) or arg1 is None:
        x_api_key = arg1
        if isinstance(arg2, list):
            allowed_roles = arg2
    elif isinstance(arg1, list):
        allowed_roles = arg1
        if isinstance(arg2, str):
            x_api_key = arg2

    if not x_api_key:
        return DEFAULT_DEMO_USER
        
    user = ROLE_API_KEYS.get(x_api_key.strip())
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid X-API-Key provided for MahaArogya health gateway."
        )
        
    # State Admin has universal access, or if no specific roles were restricted
    if not allowed_roles or user.role == UserRole.STATE_ADMIN or user.role in allowed_roles:
        return user
        
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=f"Access Denied: Role '{user.role.value}' is not authorized. Allowed roles: {[r.value for r in allowed_roles]}."
    )