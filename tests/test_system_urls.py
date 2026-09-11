"""
Comprehensive URL, API, Asset & DOM Integrity Test Suite for MahaArogya.
SIH 2026 PS 133 | Govt of Maharashtra Health Department (Arogya Vibhag)

Verifies:
1. All Website URLs & Pages:
   - GET / (Master Portal Gateway)
   - GET /pass/{token} (Standalone Citizen Pass)
   - GET /health
2. All Static Assets (CSS, JS, HTML templates):
   - GET /static/css/app.css
   - GET /static/js/asha_copilot.js
   - GET /static/js/doctor_desk.js
   - GET /static/js/war_room.js
   - GET /static/js/citizen_pass.js
   - GET /static/index.html
   - GET /static/pass.html
3. All Core & Enterprise API Endpoints:
   - POST /voice-intake (Multilingual English, Marathi, Hindi)
   - GET /referral-status/{referral_id}
   - POST /hitl/approve
   - GET /epidemic-alerts
   - GET /audit-logs
   - GET /evals/run
   - GET /reliability/dlq
   - GET /reliability/stats
4. All Dedicated Multi-Portal REST APIs:
   - GET /api/doctor/queue (Default & Filtered by Urgency: CRITICAL, MODERATE, ROUTINE)
   - GET /api/doctor/patient/{patient_id}
   - GET /api/doctor/hospital-telemetry
   - GET /api/war-room/kpis
   - GET /api/war-room/gis-data
   - POST /api/war-room/reallocate-stock
   - POST /api/offline-sync
   - GET /api/pass/{token}
5. DOM Element Integrity Check:
   - Extracts all document.getElementById calls in JS modules and verifies the IDs exist in HTML.
"""

import json
import re
import subprocess
from pathlib import Path
import pytest
from starlette.testclient import TestClient

from maha_arogya.api.main import app
from maha_arogya.mcp.server import PHC_INVENTORY_STORE

BASE_DIR = Path(__file__).resolve().parent.parent


@pytest.fixture
def client():
    return TestClient(app)


# =========================================================================
# 1. Website URLs & Pages
# =========================================================================

def test_url_master_portal(client):
    """GET / serves the complete multi-portal master shell."""
    res = client.get("/")
    assert res.status_code == 200
    assert "text/html" in res.headers["content-type"]
    assert "MahaArogya" in res.text
    assert "ASHA Field Copilot" in res.text
    assert "डॉक्टर डेस्क" in res.text
    assert "राज्य वॉर रूम" in res.text
    assert "नागरिक संदर्भ पास" in res.text
    assert "क्लिनिकल बेंचमार्क मूल्यांकन" in res.text


def test_url_citizen_pass(client):
    """GET /pass/{token} serves the standalone lightweight mobile view."""
    res = client.get("/pass/MAHA-REF-4102-EMRG")
    assert res.status_code == 200
    assert "text/html" in res.headers["content-type"]
    assert "आपत्कालीन संदर्भ पास" in res.text
    assert "१०८ मोफत रुग्णवाहिका बोलवा" in res.text
    assert "DPDP" in res.text


def test_url_health_endpoint(client):
    """GET /health returns healthy system status."""
    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "healthy"
    assert "project" in data
    assert data["project"] == "MahaArogya-Agent"


# =========================================================================
# 2. Static Assets (CSS, JS, HTML)
# =========================================================================

@pytest.mark.parametrize("asset_path,content_snippet", [
    ("/static/css/app.css", "MahaArogya Enterprise UI Design System"),
    ("/static/js/asha_copilot.js", "AshaCopilot"),
    ("/static/js/doctor_desk.js", "DoctorDesk"),
    ("/static/js/war_room.js", "WarRoom"),
    ("/static/js/citizen_pass.js", "CitizenPass"),
    ("/static/index.html", "<!DOCTYPE html>"),
    ("/static/pass.html", "<!DOCTYPE html>"),
])
def test_static_asset_serving(client, asset_path, content_snippet):
    """Validates that all CSS, JS, and HTML static assets are correctly served."""
    res = client.get(asset_path)
    assert res.status_code == 200
    assert content_snippet in res.text
    assert len(res.text) > 100


# =========================================================================
# 3. Core & Enterprise APIs
# =========================================================================

def test_api_voice_intake_multilingual(client):
    """Tests /voice-intake with Marathi, Hindi, and English payloads."""
    test_cases = [
        ("mr", "रुग्ण आयडी PAT-TEST-MR, गरोदर ३२ आठवडे, बीपी १५०/९५, तीव्र डोकेदुखी आणि चक्कर.", "HIGH"),
        ("hi", "मरीज आईडी PAT-TEST-HI, 32 हफ्ते की गर्भवती, बीपी 155/98, तेज सिरदर्द और सूजन।", "HIGH"),
        ("en", "Patient ID PAT-TEST-EN, 24 weeks pregnant, blood pressure 118/76, routine checkup.", "LOW")
    ]
    for lang, transcript, expected_triage in test_cases:
        res = client.post("/voice-intake", json={
            "patient_id": f"PAT-TEST-{lang.upper()}",
            "phone": "+91-9822114477",
            "district": "Pune",
            "voice_transcript": transcript,
            "language": lang
        }, headers={"X-API-Key": "maha-asha-2026"})
        assert res.status_code == 200
        d = res.json()
        assert d["triage_level"] == expected_triage
        assert "guardrail_status" in d
        assert d["guardrail_status"]["passed"] is True


def test_api_hitl_approval_and_status(client):
    """Tests /hitl/approve and /referral-status/{id}."""
    from maha_arogya.mcp.server import book_referral
    booking_raw = book_referral(patient_id="PAT-TEST-HITL", hospital_id="HOSP-PUN-01")
    booking = json.loads(booking_raw)
    ref_id = booking["referral_id"]

    res = client.post("/hitl/approve", json={
        "referral_id": ref_id,
        "approved": True,
        "reviewer_name": "Dr. Vaishali Kulkarni (PHC MO)",
        "notes": "Verified pre-eclampsia symptoms, allocated emergency bed"
    })
    assert res.status_code == 200
    d = res.json()
    assert d["approved"] is True
    assert d["referral_id"] == ref_id

    # Verify status lookup
    res_status = client.get(f"/referral-status/{ref_id}")
    assert res_status.status_code == 200
    status_data = res_status.json()
    assert status_data["referral_id"] == ref_id
    assert status_data["status"] == "BOOKED"


def test_api_epidemic_and_evals_and_dlq(client):
    """Tests /epidemic-alerts, /evals/run, /audit-logs, /reliability/dlq, /reliability/stats."""
    # Epidemic alerts
    res = client.get("/epidemic-alerts")
    assert res.status_code == 200
    assert "dho_briefing_text" in res.json()

    # Audit logs
    res = client.get("/audit-logs?limit=10")
    assert res.status_code == 200
    assert res.json()["status"] == "SUCCESS"

    # Clinical Benchmark Evals
    res = client.get("/evals/run")
    assert res.status_code == 200
    data = res.json()
    assert data["total_benchmark_cases"] == 20
    assert data["high_risk_sensitivity_recall_percent"] == 100.0

    # Reliability DLQ & Stats
    res = client.get("/reliability/dlq")
    assert res.status_code == 200
    res = client.get("/reliability/stats")
    assert res.status_code == 200


# =========================================================================
# 4. Multi-Portal Dedicated REST Endpoints
# =========================================================================

def test_api_doctor_desk_endpoints(client):
    """Tests Doctor Desk queue, filtering, patient history, and telemetry."""
    # Queue
    res = client.get("/api/doctor/queue")
    assert res.status_code == 200
    assert res.json()["status"] == "SUCCESS"

    for urg in ["CRITICAL", "MODERATE", "ROUTINE"]:
        res_urg = client.get(f"/api/doctor/queue?urgency={urg}")
        assert res_urg.status_code == 200
        for item in res_urg.json()["queue"]:
            assert item["category"] == urg

    # Patient profile
    res = client.get("/api/doctor/patient/PAT-4102")
    assert res.status_code == 200
    p = res.json()
    assert p["patient_id"] == "PAT-4102"
    assert len(p["bp_historical_trend"]) >= 3
    assert len(p["fhir_summary"]["observations"]) >= 2

    # Hospital bed telemetry
    res = client.get("/api/doctor/hospital-telemetry?district=Pune")
    assert res.status_code == 200
    assert len(res.json()["facilities"]) >= 1


def test_api_war_room_endpoints(client):
    """Tests War Room KPIs, GIS geospatial layers, and stock buffer transfer."""
    res = client.get("/api/war-room/kpis")
    assert res.status_code == 200
    assert res.json()["metrics"]["total_screenings_today"] > 1000

    res = client.get("/api/war-room/gis-data")
    assert res.status_code == 200
    gis = res.json()
    assert len(gis["districts"]) >= 3
    assert len(gis["outbreaks"]) >= 1
    assert len(gis["referral_funnel_48h"]) == 5

    # Stock Reallocation
    if "PHC-NSK-TRB" not in PHC_INVENTORY_STORE:
        PHC_INVENTORY_STORE["PHC-NSK-TRB"] = {"Oxytocin": {"units": 50, "daily_burn_rate": 3}}
    else:
        PHC_INVENTORY_STORE["PHC-NSK-TRB"]["Oxytocin"] = {"units": 50, "daily_burn_rate": 3}

    res = client.post("/api/war-room/reallocate-stock", json={
        "source_phc_id": "PHC-NSK-TRB",
        "target_phc_id": "PHC-GAD-BHM",
        "drug_name": "Oxytocin",
        "units_transferred": 10,
        "authorized_by": "Dr. Patil (DHO)"
    })
    assert res.status_code == 200
    assert res.json()["status"] == "TRANSFERRED"


def test_api_offline_sync_and_citizen_pass(client):
    """Tests /api/offline-sync and /api/pass/{token}."""
    res = client.post("/api/offline-sync", json={
        "worker_id": "ASHA-PUN-042",
        "records": [
            {
                "patient_id": "PAT-SYNC-TEST-01",
                "phone": "+91-9822114477",
                "district": "Pune",
                "voice_transcript": "रुग्ण आयडी PAT-SYNC-TEST-01, गरोदर ३२ आठवडे, बीपी १५०/९५, तीव्र डोकेदुखी",
                "language": "mr"
            }
        ]
    })
    assert res.status_code == 200
    assert res.json()["synced_count"] >= 1

    res = client.get("/api/pass/MAHA-PASS-TEST")
    assert res.status_code == 200
    assert res.json()["ambulance_helpline"] == "108"


# =========================================================================
# 5. DOM Element Integrity Check
# =========================================================================

def test_dom_element_integrity():
    """
    Parses all document.getElementById calls in JavaScript files
    and verifies that each referenced ID actually exists in index.html or pass.html.
    Prevents runtime null reference errors in the browser.
    """
    static_dir = BASE_DIR / "maha_arogya" / "static"
    index_html = (static_dir / "index.html").read_text(encoding="utf-8")
    pass_html = (static_dir / "pass.html").read_text(encoding="utf-8")

    # Extract all id="..." from index.html and pass.html
    html_ids = set(re.findall(r'id=["\']([a-zA-Z0-9_\-]+)["\']', index_html + pass_html))

    # JavaScript files to inspect
    js_files = [
        static_dir / "js" / "asha_copilot.js",
        static_dir / "js" / "doctor_desk.js",
        static_dir / "js" / "war_room.js",
        static_dir / "js" / "citizen_pass.js",
    ]

    missing_ids = []
    for js_path in js_files:
        content = js_path.read_text(encoding="utf-8")
        # Match getElementById("...")
        matches = re.findall(r'getElementById\(["\']([a-zA-Z0-9_\-]+)["\']\)', content)
        for elem_id in matches:
            if elem_id not in html_ids:
                missing_ids.append((js_path.name, elem_id))

    assert not missing_ids, f"Found JavaScript references to non-existent HTML element IDs: {missing_ids}"


def test_javascript_syntax_via_node():
    """Validates JavaScript syntax across all client files using Node.js."""
    static_dir = BASE_DIR / "maha_arogya" / "static" / "js"
    js_files = list(static_dir.glob("*.js"))
    assert len(js_files) == 4

    for js_path in js_files:
        res = subprocess.run(["node", "-c", str(js_path)], capture_output=True, text=True)
        assert res.returncode == 0, f"JS Syntax Error in {js_path.name}: {res.stderr}"
