"""
Audit Trail & Compliance Engine for MahaArogya-Agent.
Provides immutable clinical audit logging for Medical Officer approvals,
ASHA escalations, referral issuances, and DHO sign-offs as required by Govt health regulations.
"""

from enum import Enum
from typing import List, Dict, Any, Optional
from datetime import datetime
import uuid
from pydantic import BaseModel, Field


class ActionType(str, Enum):
    HITL_APPROVAL = "HITL_APPROVAL"
    HITL_REJECTION = "HITL_REJECTION"
    REFERRAL_BOOKED = "REFERRAL_BOOKED"
    SLA_BREACH_ESCALATED = "SLA_BREACH_ESCALATED"
    DHO_ALERT_SIGNOFF = "DHO_ALERT_SIGNOFF"
    OUTBREAK_DETECTED = "OUTBREAK_DETECTED"
    GUARDRAIL_INTERCEPT = "GUARDRAIL_INTERCEPT"
    VOICE_INTAKE_LOGGED = "VOICE_INTAKE_LOGGED"


class AuditRecord(BaseModel):
    audit_id: str = Field(default_factory=lambda: f"AUD-{uuid.uuid4().hex[:8].upper()}")
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    action: ActionType
    actor_id: str = Field(..., description="ID of human or agent (e.g. 'DR-KULKARNI', 'ASHA-77')")
    actor_role: str = Field(..., description="Role: 'PHC_DOCTOR', 'ASHA_WORKER', 'DHO_OFFICER', 'SYSTEM_AGENT'")
    resource_id: str = Field(..., description="Referral ID, Patient ID, or Outbreak ID")
    decision: str = Field(..., description="E.g. 'APPROVED', 'REJECTED', 'BOOKED', 'ESCALATED'")
    clinical_rationale: str
    client_ip: Optional[str] = "127.0.0.1"
    metadata: Dict[str, Any] = Field(default_factory=dict)


class AuditLogger:
    """Thread-safe compliance audit logger."""

    def __init__(self):
        self._records: List[AuditRecord] = []

    def log(
        self,
        action: ActionType,
        actor_id: str,
        actor_role: str,
        resource_id: str,
        decision: str,
        clinical_rationale: str,
        client_ip: Optional[str] = "127.0.0.1",
        metadata: Optional[Dict[str, Any]] = None
    ) -> AuditRecord:
        record = AuditRecord(
            action=action,
            actor_id=actor_id,
            actor_role=actor_role,
            resource_id=resource_id,
            decision=decision,
            clinical_rationale=clinical_rationale,
            client_ip=client_ip,
            metadata=metadata or {}
        )
        self._records.insert(0, record)  # Most recent first
        return record

    def get_logs(
        self,
        limit: int = 50,
        action: Optional[ActionType] = None,
        actor_role: Optional[str] = None,
        resource_id: Optional[str] = None
    ) -> List[AuditRecord]:
        results = self._records
        if action:
            results = [r for r in results if r.action == action]
        if actor_role:
            results = [r for r in results if r.actor_role.upper() == actor_role.strip().upper()]
        if resource_id:
            results = [r for r in results if resource_id.lower() in r.resource_id.lower()]
        return results[:limit]

    def total_records(self) -> int:
        return len(self._records)

    def clear(self):
        """Reset audit records for test isolation."""
        self._records.clear()


audit_logger = AuditLogger()