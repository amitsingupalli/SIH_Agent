"""
Integration & End-to-End Test Suite for MahaArogya-Agent.
Tests FastMCP tools, HL7 FHIR validation, LangGraph StateGraph routing,
48-hour SLA closed-loop referral tracking, and FastAPI REST endpoints.
"""

import json
import pytest
from starlette.testclient import TestClient

from maha_arogya.mcp.server import (
    log_vitals,
    check_hospital_capacity,
    book_referral,
    send_vernacular_alert,
    check_stock_runway,
    REFERRAL_STORE
)
from maha_arogya.services.voice_nlp import voice_nlp_service
from maha_arogya.agents.graph import maha_arogya_graph
from maha_arogya.agents.referral_agent import check_and_escalate_referral
from maha_arogya.agents.surveillance_agent import detect_spatial_temporal_clusters, generate_dho_briefing
from maha_arogya.api.main import app


@pytest.fixture
def client():
    return TestClient(app)


# ========================================================
# 1. FastMCP 5 Core Healthcare Tools
# ========================================================
def test_fastmcp_log_vitals_fhir_compliance():
    """Validates log_vitals produces HL7 FHIR compliant JSON with LOINC and SNOMED codes."""
    bundle_raw = log_vitals(
        patient_id="PAT-TEST-001",
        bp="150/95",
        gestation=32,
        symptoms="Severe headache, चक्कर येणे, blurry vision"
    )
    bundle = json.loads(bundle_raw)
    assert bundle["resourceType"] == "Bundle"
    assert len(bundle["entry"]) >= 2
    
    # Verify LOINC coding for Blood Pressure Observation
    bp_obs = bundle["entry"][0]["resource"]
    assert bp_obs["resourceType"] == "Observation"
    assert bp_obs["code"]["coding"][0]["code"] == "85354-9"
    assert len(bp_obs["component"]) == 2  # Systolic and Diastolic
    
    # Verify SNOMED coding for Condition (Pre-eclampsia)
    cond = bundle["entry"][-1]["resource"]
    assert cond["resourceType"] == "Condition"
    assert cond["code"]["coding"][0]["code"] == "398254007"  # Pre-eclampsia


def test_fastmcp_check_hospital_capacity():
    """Validates hospital capacity queries for Maharashtra districts."""
    res_raw = check_hospital_capacity(specialty="Obstetrics & Gynecology", district="Pune")
    data = json.loads(res_raw)
    assert "available_slots" in data
    assert data["total_hospitals_available"] >= 1
    assert any("Sassoon" in h["hospital_name"] for h in data["available_slots"])


def test_fastmcp_book_referral_qr_generation():
    """Validates booking generates cryptographic QR pass token and base64 image."""
    booking_raw = book_referral(patient_id="PAT-TEST-002", hospital_id="HOSP-PUN-01")
    booking = json.loads(booking_raw)
    assert booking["status"] == "BOOKED"
    assert booking["qr_token"].startswith("MAHA-REF-")
    assert "REF-" in booking["referral_id"]
    
    ref_id = booking["referral_id"]
    assert ref_id in REFERRAL_STORE
    assert REFERRAL_STORE[ref_id]["qr_image_base64"] is not None


def test_fastmcp_send_vernacular_alert():
    """Validates vernacular dispatch gateway."""
    alert_raw = send_vernacular_alert(phone="+91-9822110000", msg_marathi="चाचणी संदेश: तातडीने रुग्णालयात जा.")
    alert = json.loads(alert_raw)
    assert alert["status"] == "DELIVERED"
    assert alert["recipient"] == "+91-9822110000"


def test_fastmcp_check_stock_runway():
    """Validates pharmaceutical stock-out runway calculation and critical threshold flags."""
    runway_raw = check_stock_runway(phc_id="PHC-PUN-KND", drug_name="Magnesium Sulfate")
    runway = json.loads(runway_raw)
    assert runway["drug_name"] == "Magnesium Sulfate"
    assert runway["days_left"] <= 7.0
    assert runway["is_critical_shortage"] is True
    assert runway["action_required"] == "EMERGENCY_REORDER_ALERT"


# ========================================================
# 2. Vernacular Voice & NLP Service
# ========================================================
def test_voice_nlp_entity_extraction():
    """Tests Devanagari digit normalization and clinical extraction."""
    raw_marathi = "रुग्ण आयडी PAT-4102, गरोदर ३२ आठवडे, बीपी १५०/९५, तीव्र डोकेदुखी आणि चक्कर"
    extracted = voice_nlp_service.extract_clinical_entities(raw_marathi)
    assert extracted.patient_id == "PAT-4102"
    assert extracted.bp_systolic == 150
    assert extracted.bp_diastolic == 95
    assert extracted.gestation_weeks == 32
    assert extracted.has_obstetric_red_flag is True
    assert "Severe Headache" in extracted.standardized_symptoms


# ========================================================
# 3. LangGraph Multi-Agent StateGraph Workflows
# ========================================================
def test_langgraph_high_risk_obstetric_workflow():
    """Tests HIGH risk path: ASHA Copilot -> HITL -> Closed-Loop Referral -> Surveillance."""
    config = {"configurable": {"thread_id": "test-flow-high-risk"}}
    state = {
        "raw_input": "रुग्ण आयडी PAT-4102, गरोदर ३२ आठवडे, बीपी १५०/९५, तीव्र डोकेदुखी",
        "district": "Pune"
    }
    final = maha_arogya_graph.invoke(state, config=config)
    assert final["triage_level"] == "HIGH"
    assert final["requires_referral"] is True
    assert final.get("referral_id") is not None
    assert final["current_stage"] == "SURVEILLANCE_EVALUATED"


def test_langgraph_low_risk_routine_workflow():
    """Tests LOW risk path: ASHA Copilot -> Routine Advisory -> Surveillance."""
    config = {"configurable": {"thread_id": "test-flow-low-risk"}}
    state = {
        "raw_input": "रुग्ण आयडी PAT-7001, नियमित तपासणी, बीपी ११८/७८, सर्व ठीक आहे",
        "district": "Pune"
    }
    final = maha_arogya_graph.invoke(state, config=config)
    assert final["triage_level"] == "LOW"
    assert final["requires_referral"] is False
    assert final["current_stage"] == "SURVEILLANCE_EVALUATED"


# ========================================================
# 4. Closed-Loop Referral 48h SLA Tracking
# ========================================================
def test_referral_sla_monitoring_and_breach_escalation():
    """Validates 48h SLA tracking and automated escalation upon simulated breach."""
    booking_raw = book_referral(patient_id="PAT-SLA-99", hospital_id="HOSP-PUN-01")
    ref_id = json.loads(booking_raw)["referral_id"]
    
    # Check within SLA
    active_status = check_and_escalate_referral(ref_id, force_sla_breach=False)
    assert active_status["status"] == "BOOKED"
    
    # Simulate 48h SLA breach
    escalated_status = check_and_escalate_referral(ref_id, force_sla_breach=True)
    assert escalated_status["status"] == "NO_SHOW"
    assert escalated_status["escalated"] is True
    assert "alert_dispatched_to" in escalated_status


# ========================================================
# 5. Surveillance Watchdog Clustering
# ========================================================
def test_surveillance_watchdog_clusters():
    """Validates spatio-temporal cluster detection and DHO administrative report."""
    outbreaks = detect_spatial_temporal_clusters()
    assert len(outbreaks) >= 1
    assert any(ob["district"] == "Gadchiroli" for ob in outbreaks)
    
    briefing = generate_dho_briefing(outbreaks, [])
    assert "MAHARASHTRA HEALTH DEPARTMENT" in briefing
    assert "Gadchiroli" in briefing


# ========================================================
# 6. FastAPI REST Endpoints End-to-End
# ========================================================
def test_fastapi_endpoints(client):
    # 1. Health
    res_health = client.get("/health")
    assert res_health.status_code == 200
    assert res_health.json()["status"] == "healthy"
    
    # 2. Voice Intake
    res_intake = client.post("/voice-intake", json={
        "voice_transcript": "रुग्ण आयडी PAT-4102, गरोदर ३२ आठवडे, बीपी १५०/९५, चक्कर येणे",
        "district": "Pune"
    })
    assert res_intake.status_code == 200
    body = res_intake.json()
    assert body["triage_level"] == "HIGH"
    assert body["requires_referral"] is True
    ref_id = body["referral_details"]["referral_id"]
    
    # 3. Referral Status
    res_ref = client.get(f"/referral-status/{ref_id}")
    assert res_ref.status_code == 200
    assert res_ref.json()["status"] == "BOOKED"
    
    # 4. Referral Escalation (simulated 48h breach)
    res_esc = client.get(f"/referral-status/{ref_id}?force_sla_breach=true")
    assert res_esc.status_code == 200
    assert res_esc.json()["escalated"] is True
    
    # 5. Epidemic Alerts
    res_alerts = client.get("/epidemic-alerts")
    assert res_alerts.status_code == 200
    assert res_alerts.json()["total_active_outbreaks"] >= 1
    
    # 6. Dashboard
    res_dash = client.get("/")
    assert res_dash.status_code == 200
    assert "MahaArogya-Agent" in res_dash.text