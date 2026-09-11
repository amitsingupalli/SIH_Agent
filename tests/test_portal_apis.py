"""
Integration Test Suite for MahaArogya Unified Portal REST Endpoints.
SIH 2026 PS 133 | Govt of Maharashtra Arogya Vibhag

Validates:
1. Doctor Clinical Desk: /api/doctor/queue, /api/doctor/patient/{id}, /api/doctor/hospital-telemetry
2. State Health War Room: /api/war-room/kpis, /api/war-room/gis-data, /api/war-room/reallocate-stock
3. Offline 2G/3G Worker Sync: /api/offline-sync
4. Citizen Digital Referral Pass: /api/pass/{token}
5. Static HTML Portal Gateway: GET / and GET /pass/{token}
"""

import pytest
from starlette.testclient import TestClient

from maha_arogya.api.main import app
from maha_arogya.mcp.server import (
    REFERRAL_STORE,
    PATIENT_RECORDS,
    PHC_INVENTORY_STORE,
)


@pytest.fixture
def client():
    return TestClient(app)


# =====================================================================
# 1. Doctor Clinical Desk Endpoints
# =====================================================================

def test_doctor_queue_retrieval(client):
    """Validates prioritized referral queue retrieval and category breakdown."""
    response = client.get("/api/doctor/queue")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "SUCCESS"
    assert "total_queued" in data
    assert "critical_count" in data
    assert "queue" in data
    assert isinstance(data["queue"], list)
    assert len(data["queue"]) > 0


def test_doctor_queue_filtering(client):
    """Validates queue filtering by urgency level."""
    response = client.get("/api/doctor/queue?urgency=CRITICAL")
    assert response.status_code == 200
    data = response.json()
    for item in data["queue"]:
        assert item["category"] == "CRITICAL"


def test_doctor_patient_clinical_profile(client):
    """Validates full clinical profile with FHIR summary, BP trend, and voice note."""
    response = client.get("/api/doctor/patient/PAT-4102")
    assert response.status_code == 200
    data = response.json()
    assert data["patient_id"] == "PAT-4102"
    assert "bp_historical_trend" in data
    assert len(data["bp_historical_trend"]) >= 3
    assert "fhir_summary" in data
    assert "observations" in data["fhir_summary"]
    assert "conditions" in data["fhir_summary"]
    assert "voice_note" in data
    assert "transcript_vernacular" in data["voice_note"]
    assert "asha_worker" in data


def test_doctor_hospital_telemetry(client):
    """Validates real-time hospital bed and CEmONC telemetry."""
    response = client.get("/api/doctor/hospital-telemetry?district=Pune")
    assert response.status_code == 200
    data = response.json()
    assert data["district"] == "Pune"
    assert data["total_facilities"] >= 1
    assert "facilities" in data
    facility = data["facilities"][0]
    assert "name" in facility
    assert "hospital_id" in facility
    assert "available_emergency_slots" in facility
    assert "total_beds" in facility


# =====================================================================
# 2. State & District War Room GIS Endpoints
# =====================================================================

def test_war_room_kpis(client):
    """Validates executive state health command telemetry metrics."""
    response = client.get("/api/war-room/kpis")
    assert response.status_code == 200
    data = response.json()
    assert "state" in data
    assert "metrics" in data
    metrics = data["metrics"]
    assert "total_screenings_today" in metrics
    assert "high_risk_identified" in metrics
    assert "closed_loop_48h_attendance_rate" in metrics
    assert "active_outbreak_clusters" in metrics


def test_war_room_gis_data(client):
    """Validates GIS hubs, outbreak polygons, and 48h SLA drop-off funnel."""
    response = client.get("/api/war-room/gis-data")
    assert response.status_code == 200
    data = response.json()
    assert "districts" in data
    assert len(data["districts"]) >= 3
    # Validate coordinate structure for Leaflet
    for dist in data["districts"]:
        assert "lat" in dist and "lng" in dist
        assert "hub" in dist
    assert "outbreaks" in data
    assert "referral_funnel_48h" in data
    assert len(data["referral_funnel_48h"]) == 5


def test_war_room_stock_reallocation(client):
    """Validates inter-PHC drug buffer re-allocation and inventory tracking."""
    # Ensure source has stock
    source_phc = "PHC-NSK-TRB"
    target_phc = "PHC-GAD-BHM"
    drug = "Magnesium Sulfate"
    
    if source_phc not in PHC_INVENTORY_STORE:
        PHC_INVENTORY_STORE[source_phc] = {drug: {"units": 50, "daily_burn_rate": 5}}
    else:
        PHC_INVENTORY_STORE[source_phc][drug]["units"] = 50

    if target_phc not in PHC_INVENTORY_STORE:
        PHC_INVENTORY_STORE[target_phc] = {drug: {"units": 10, "daily_burn_rate": 5}}

    initial_source = PHC_INVENTORY_STORE[source_phc][drug]["units"]

    payload = {
        "source_phc_id": source_phc,
        "target_phc_id": target_phc,
        "drug_name": drug,
        "units_transferred": 15,
        "authorized_by": "Dr. Patil (DHO Test)"
    }
    response = client.post("/api/war-room/reallocate-stock", json=payload)
    assert response.status_code == 200
    res_data = response.json()
    assert res_data["status"] == "TRANSFERRED"
    assert res_data["units"] == 15
    assert res_data["source_remaining"] == initial_source - 15

    # Test insufficient stock rejection
    excess_payload = {
        "source_phc_id": source_phc,
        "target_phc_id": target_phc,
        "drug_name": drug,
        "units_transferred": 99999,
        "authorized_by": "Dr. Patil (DHO Test)"
    }
    excess_res = client.post("/api/war-room/reallocate-stock", json=excess_payload)
    assert excess_res.status_code == 400


# =====================================================================
# 3. Offline 2G/3G Batch Sync Endpoint
# =====================================================================

def test_offline_batch_sync(client):
    """Validates batch processing of offline intake records collected in deep rural areas."""
    batch_payload = {
        "worker_id": "ASHA-PUN-TEST-001",
        "records": [
            {
                "patient_id": "PAT-OFFLINE-01",
                "phone": "+91-9822001122",
                "district": "Pune",
                "phc_id": "PHC-PUN-KND",
                "voice_transcript": "रुग्ण आयडी PAT-OFFLINE-01, गरोदर माता ३२ आठवडे, बीपी १५०/९५, तीव्र डोकेदुखी आणि पायांवर सूज आहे.",
                "language": "mr"
            }
        ]
    }
    response = client.post("/api/offline-sync", json=batch_payload)
    assert response.status_code == 200
    data = response.json()
    assert data["worker_id"] == "ASHA-PUN-TEST-001"
    assert data["total_submitted"] == 1
    assert data["synced_count"] >= 1
    assert len(data["results"]) == 1
    assert data["results"][0]["status"] == "SYNCED"


# =====================================================================
# 4. Citizen Digital Vernacular Referral Pass
# =====================================================================

def test_citizen_pass_endpoint(client):
    """Validates citizen mobile pass endpoint data contract."""
    response = client.get("/api/pass/SAMPLE-QR-TOKEN-123")
    assert response.status_code == 200
    data = response.json()
    assert "referral_id" in data
    assert "patient_name" in data
    assert "hospital_name" in data
    assert data["ambulance_helpline"] == "108"
    assert "instructions_vernacular" in data
    assert "instructions_english" in data


# =====================================================================
# 5. HTML Frontend Portal Gateways
# =====================================================================

def test_frontend_master_portal_served(client):
    """Validates master UI application is served at root GET /."""
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "MahaArogya" in response.text
    assert "ASHA Field Copilot" in response.text
    assert "डॉक्टर डेस्क" in response.text
    assert "राज्य वॉर रूम" in response.text


def test_frontend_citizen_pass_page_served(client):
    """Validates citizen mobile referral pass HTML view is served at GET /pass/{token}."""
    response = client.get("/pass/MAHA-PASS-TEST-99")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "MahaArogya" in response.text
    assert "आपत्कालीन संदर्भ पास" in response.text
    assert "Emergency Referral Pass" in response.text
