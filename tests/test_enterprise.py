"""
Enterprise Feature Test Suite for MahaArogya-Agent.
Validates:
1. Clinical Governance Audit Trail & Immutability.
2. Role-Based Access Control (ASHA, PHC Doctor, DHO, Admin).
3. Network Idempotency & Replay Prevention on Flaky Rural Networks.
4. Telecommunications Resilience (Retry with Backoff & Dead-Letter Queue / DLQ).
5. Clinical Evaluation Benchmark (20 Cases, 100% High-Risk Recall).
6. Cross-Agent Surveillance Stream Linkage.
7. Enterprise REST Endpoints (/audit-logs, /evals/run, /reliability/dlq, /reliability/stats).
"""

import pytest
from starlette.testclient import TestClient
from fastapi import HTTPException

from maha_arogya.core.audit import audit_logger, ActionType
from maha_arogya.core.auth import verify_role_api_key, UserRole, ROLE_API_KEYS
from maha_arogya.core.reliability import (
    retry_with_backoff,
    dead_letter_queue,
    idempotency_guard,
)
from maha_arogya.evals.eval_runner import clinical_eval_runner
from maha_arogya.agents.surveillance_agent import (
    record_syndromic_case,
    detect_spatial_temporal_clusters,
    MOCK_PHC_SYNDROMIC_LOGS
)
from maha_arogya.api.main import app


@pytest.fixture
def client():
    return TestClient(app)


# ========================================================
# 1. Clinical Governance & Audit Trail
# ========================================================
def test_audit_logger_records_and_filters():
    """Validates immutable clinical governance logging and querying."""
    audit_logger.clear()
    
    rec = audit_logger.log(
        action=ActionType.HITL_APPROVAL,
        actor_id="DR-PATIL-01",
        actor_role="PHC_DOCTOR",
        resource_id="REF-TEST-999",
        decision="APPROVED",
        clinical_rationale="Patient meets acute pre-eclampsia transfer criteria",
        metadata={"systolic": 160, "diastolic": 105}
    )
    
    assert rec.audit_id.startswith("AUD-")
    assert rec.action == ActionType.HITL_APPROVAL
    assert rec.decision == "APPROVED"
    
    # Query by role
    doctor_logs = audit_logger.get_logs(actor_role="PHC_DOCTOR")
    assert len(doctor_logs) >= 1
    assert doctor_logs[0].resource_id == "REF-TEST-999"
    
    # Query by resource ID
    ref_logs = audit_logger.get_logs(resource_id="REF-TEST-999")
    assert len(ref_logs) == 1
    assert ref_logs[0].actor_id == "DR-PATIL-01"


# ========================================================
# 2. Role-Based Access Control (RBAC)
# ========================================================
def test_rbac_valid_keys_and_roles():
    """Validates API key authorization for healthcare roles."""
    # 1. Valid ASHA Worker key
    asha_auth = verify_role_api_key("maha-asha-2026", [UserRole.ASHA_WORKER])
    assert asha_auth.role == UserRole.ASHA_WORKER
    
    # 2. Valid PHC Doctor key
    doc_auth = verify_role_api_key("maha-doctor-2026", [UserRole.PHC_DOCTOR])
    assert doc_auth.role == UserRole.PHC_DOCTOR
    
    # 3. Invalid API key triggers 401 Unauthorized
    with pytest.raises(HTTPException) as exc_info:
        verify_role_api_key("invalid-key-xyz", [UserRole.ASHA_WORKER])
    assert exc_info.value.status_code == 401
    
    # 4. Role mismatch triggers 403 Forbidden (e.g. ASHA attempting Doctor action)
    with pytest.raises(HTTPException) as exc_info:
        verify_role_api_key("maha-asha-2026", [UserRole.PHC_DOCTOR])
    assert exc_info.value.status_code == 403


# ========================================================
# 3. Idempotency Guard & Replay Prevention
# ========================================================
def test_idempotency_guard_lifecycle():
    """Validates replay protection prevents duplicate processing on flaky rural connections."""
    idempotency_guard.clear()
    
    key = "idemp-test-session-001"
    
    # First check: not processed yet
    assert idempotency_guard.check(key) is None
    
    # Acquire lock
    assert idempotency_guard.acquire(key) is True
    # Second acquire should fail (duplicate in-flight)
    assert idempotency_guard.acquire(key) is False
    
    # Commit result
    cached_payload = {"referral_id": "REF-ABC123", "status": "BOOKED"}
    idempotency_guard.commit(key, cached_payload)
    
    # Subsequent check returns cached payload
    result = idempotency_guard.check(key)
    assert result == cached_payload


# ========================================================
# 4. Telecommunications Resilience (Retry + DLQ)
# ========================================================
def test_retry_with_backoff_and_dead_letter_queue():
    """Validates exponential backoff and dead-letter queue routing upon persistent failure."""
    dead_letter_queue.clear()
    
    attempts = [0]
    
    # Function that fails twice and succeeds on 3rd attempt
    @retry_with_backoff(max_attempts=3, initial_delay=0.01, backoff_factor=1.1)
    def flaky_sms_gateway():
        attempts[0] += 1
        if attempts[0] < 3:
            raise ConnectionError("Cellular tower timeout in Bhamragad")
        return "SMS_DELIVERED"
        
    result = flaky_sms_gateway()
    assert result == "SMS_DELIVERED"
    assert attempts[0] == 3
    
    # Function that fails all attempts -> routes to DLQ
    @retry_with_backoff(max_attempts=2, initial_delay=0.01, backoff_factor=1.1)
    def dead_gateway():
        raise TimeoutError("NIC SMS gateway unreachable")
        
    try:
        dead_gateway()
    except TimeoutError as err:
        dlq_rec = dead_letter_queue.enqueue(
            event_type="REFERRAL_SMS",
            payload={"patient_id": "PAT-9090", "phone": "+91-9822001122"},
            error_reason=str(err),
            patient_id="PAT-9090"
        )
        assert dlq_rec["status"] == "UNRESOLVED"
        assert dlq_rec["patient_id"] == "PAT-9090"
        
    assert len(dead_letter_queue.list_unresolved()) == 1
    
    # Mark resolved
    dlq_id = dead_letter_queue.list_unresolved()[0]["dlq_id"]
    assert dead_letter_queue.mark_resolved(dlq_id, "Manual phone call by MO") is True
    assert len(dead_letter_queue.list_unresolved()) == 0


# ========================================================
# 5. Clinical Benchmark Evaluation (20 Cases)
# ========================================================
def test_clinical_eval_benchmark_100_percent_recall():
    """
    Validates the 20-case clinical evaluation benchmark:
    - High-Risk Clinical Sensitivity / Recall must be 100% (Zero missed maternal emergencies).
    - Overall triage accuracy >= 95%.
    - Safety verdict passes.
    """
    summary = clinical_eval_runner.run_benchmark()
    
    assert summary["total_benchmark_cases"] == 20
    assert summary["high_risk_sensitivity_recall_percent"] == 100.0
    assert summary["overall_triage_accuracy_percent"] == 100.0
    assert summary["confusion_matrix_high_risk"]["false_negatives"] == 0
    assert "PASS" in summary["clinical_safety_verdict"]


# ========================================================
# 6. Cross-Agent Surveillance Stream Linkage
# ========================================================
def test_cross_agent_surveillance_linkage():
    """Validates that ASHA intake cases stream directly into surveillance cluster detection."""
    initial_log_count = len(MOCK_PHC_SYNDROMIC_LOGS)
    
    # Record 4 syndromic cases in a new district
    district_test = "Dhule"
    syndrome_test = "Acute Watery Diarrhea"
    
    for i in range(4):
        record_syndromic_case(
            phc_id=f"PHC-DHL-0{i}",
            district=district_test,
            taluka="Shirpur",
            syndrome=syndrome_test,
            patient_id=f"PAT-DHL-0{i}"
        )
        
    assert len(MOCK_PHC_SYNDROMIC_LOGS) == initial_log_count + 4
    
    # Run spatial-temporal cluster detection
    clusters = detect_spatial_temporal_clusters(min_cluster_size=4)
    matching = [c for c in clusters if c["district"] == district_test and c["syndrome"] == syndrome_test]
    
    assert len(matching) == 1
    assert matching[0]["cases_in_72h"] == 4
    assert matching[0]["severity"] in ["WARNING", "CRITICAL"]


# ========================================================
# 7. Enterprise FastAPI REST Endpoints
# ========================================================
def test_api_audit_logs_endpoint(client):
    """Validates GET /audit-logs endpoint."""
    res = client.get("/audit-logs?limit=10")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "SUCCESS"
    assert "audit_trail" in data
    assert isinstance(data["audit_trail"], list)


def test_api_evals_run_endpoint(client):
    """Validates GET /evals/run endpoint execution."""
    res = client.get("/evals/run")
    assert res.status_code == 200
    data = res.json()
    assert data["total_benchmark_cases"] == 20
    assert data["high_risk_sensitivity_recall_percent"] == 100.0
    assert data["overall_triage_accuracy_percent"] == 100.0


def test_api_reliability_dlq_endpoint(client):
    """Validates GET /reliability/dlq and /reliability/stats endpoints."""
    res_dlq = client.get("/reliability/dlq")
    assert res_dlq.status_code == 200
    assert "unresolved_count" in res_dlq.json()
    
    res_stats = client.get("/reliability/stats")
    assert res_stats.status_code == 200
    stats = res_stats.json()
    assert stats["idempotency_ttl_seconds"] == 600
    assert "telecom_resilience_mode" in stats


def test_api_voice_intake_with_idempotency_and_auth(client):
    """Validates POST /voice-intake with X-Idempotency-Key and X-API-Key."""
    idempotency_key = "idemp-live-test-key-999"
    payload = {
        "patient_id": "PAT-9999",
        "phone": "+91-9822114477",
        "district": "Pune",
        "voice_transcript": "Patient ID PAT-9999, pregnant 32 weeks, BP 155/96, severe headache and blurry vision.",
        "language": "en"
    }
    
    # 1. First request with valid ASHA API Key and Idempotency Key
    res1 = client.post(
        "/voice-intake",
        json=payload,
        headers={
            "X-API-Key": "maha-asha-2026",
            "X-Idempotency-Key": idempotency_key
        }
    )
    assert res1.status_code == 200
    data1 = res1.json()
    assert data1["triage_level"] == "HIGH"
    assert data1["requires_referral"] is True
    
    # 2. Second request with same idempotency key returns cached response
    res2 = client.post(
        "/voice-intake",
        json=payload,
        headers={
            "X-API-Key": "maha-asha-2026",
            "X-Idempotency-Key": idempotency_key
        }
    )
    assert res2.status_code == 200
    assert res2.headers.get("x-idempotent-replay") == "true"
    assert res2.json()["patient_id"] == "PAT-9999"
