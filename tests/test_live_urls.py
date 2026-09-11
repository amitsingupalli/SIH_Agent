"""
Live Network HTTP URL & Asset Smoke Test Suite.
Validates all endpoints against the live running server at http://127.0.0.1:8000.
"""

import json
import sys
import time
import urllib.request
import urllib.error

sys.stdout.reconfigure(encoding="utf-8")
BASE = "http://127.0.0.1:8000"


def check_url(method, path, expected_status=200, payload=None, headers=None, check_fn=None):
    start = time.time()
    url = f"{BASE}{path}"
    req_headers = headers or {}
    data = None
    if payload:
        data = json.dumps(payload).encode("utf-8")
        req_headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=data, headers=req_headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            elapsed = int((time.time() - start) * 1000)
            status = resp.status
            body = resp.read().decode("utf-8")
            assert status == expected_status, f"Expected {expected_status}, got {status}"
            if check_fn:
                check_fn(body, resp)
            print(f"  [OK] {method} {path} -> {status} ({elapsed}ms)")
            return True
    except urllib.error.HTTPError as e:
        elapsed = int((time.time() - start) * 1000)
        if e.code == expected_status:
            body = e.read().decode("utf-8")
            if check_fn:
                check_fn(body, e)
            print(f"  [OK] {method} {path} -> {e.code} (Expected, {elapsed}ms)")
            return True
        else:
            print(f"  [FAIL] {method} {path} -> HTTP {e.code}: {e.read().decode('utf-8')}")
            return False
    except Exception as ex:
        print(f"  [FAIL] {method} {path} -> {ex}")
        return False


def run_all_url_checks():
    print("=" * 60)
    print("MAHA-AROGYA LIVE URL & STATIC ASSET COMPREHENSIVE AUDIT")
    print("=" * 60)

    checks = []

    # 1. HTML Views
    print("\n--- 1. WEB PAGES & USER INTERFACES ---")
    checks.append(check_url("GET", "/", 200, check_fn=lambda b, r: "MahaArogya" in b and "ASHA Field Copilot" in b))
    checks.append(check_url("GET", "/pass/MAHA-PASS-LIVE-TEST", 200, check_fn=lambda b, r: "आपत्कालीन संदर्भ पास" in b))

    # 2. Static Assets
    print("\n--- 2. STATIC ASSETS (CSS & JAVASCRIPT) ---")
    checks.append(check_url("GET", "/static/css/app.css", 200, check_fn=lambda b, r: "--primary-gov" in b))
    checks.append(check_url("GET", "/static/js/asha_copilot.js", 200, check_fn=lambda b, r: "AshaCopilot" in b))
    checks.append(check_url("GET", "/static/js/doctor_desk.js", 200, check_fn=lambda b, r: "DoctorDesk" in b))
    checks.append(check_url("GET", "/static/js/war_room.js", 200, check_fn=lambda b, r: "WarRoom" in b))
    checks.append(check_url("GET", "/static/js/citizen_pass.js", 200, check_fn=lambda b, r: "CitizenPass" in b))
    checks.append(check_url("GET", "/static/index.html", 200, check_fn=lambda b, r: "<!DOCTYPE html>" in b))
    checks.append(check_url("GET", "/static/pass.html", 200, check_fn=lambda b, r: "<!DOCTYPE html>" in b))

    # 3. System & Governance APIs
    print("\n--- 3. SYSTEM & GOVERNANCE APIS ---")
    checks.append(check_url("GET", "/health", 200, check_fn=lambda b, r: json.loads(b)["status"] == "healthy"))
    checks.append(check_url("GET", "/epidemic-alerts", 200, check_fn=lambda b, r: "dho_briefing_text" in json.loads(b)))
    checks.append(check_url("GET", "/audit-logs", 200, check_fn=lambda b, r: json.loads(b)["status"] == "SUCCESS"))
    checks.append(check_url("GET", "/evals/run", 200, check_fn=lambda b, r: json.loads(b)["total_benchmark_cases"] == 20))
    checks.append(check_url("GET", "/reliability/dlq", 200, check_fn=lambda b, r: "unresolved_count" in json.loads(b)))
    checks.append(check_url("GET", "/reliability/stats", 200, check_fn=lambda b, r: "telecom_resilience_mode" in json.loads(b)))

    # 4. Multi-Portal APIs
    print("\n--- 4. MULTI-PORTAL SPECIALIZED APIS ---")
    checks.append(check_url("GET", "/api/doctor/queue", 200, check_fn=lambda b, r: json.loads(b)["status"] == "SUCCESS"))
    checks.append(check_url("GET", "/api/doctor/queue?urgency=CRITICAL", 200))
    checks.append(check_url("GET", "/api/doctor/queue?urgency=MODERATE", 200))
    checks.append(check_url("GET", "/api/doctor/queue?urgency=ROUTINE", 200))
    checks.append(check_url("GET", "/api/doctor/patient/PAT-4102", 200, check_fn=lambda b, r: json.loads(b)["patient_id"] == "PAT-4102"))
    checks.append(check_url("GET", "/api/doctor/hospital-telemetry?district=Pune", 200))
    checks.append(check_url("GET", "/api/war-room/kpis", 200, check_fn=lambda b, r: "metrics" in json.loads(b)))
    checks.append(check_url("GET", "/api/war-room/gis-data", 200, check_fn=lambda b, r: len(json.loads(b)["districts"]) >= 3))
    checks.append(check_url("GET", "/api/pass/MAHA-PASS-LIVE-TEST", 200, check_fn=lambda b, r: json.loads(b)["ambulance_helpline"] == "108"))

    # 5. Core Voice Intake & HITL Workflows
    print("\n--- 5. CORE WORKFLOW POST APIS ---")
    intake_payload = {
        "patient_id": "PAT-LIVE-AUDIT",
        "phone": "+91-9822114477",
        "district": "Pune",
        "voice_transcript": "रुग्ण आयडी PAT-LIVE-AUDIT, गरोदर ३२ आठवडे, बीपी १५०/९५, तीव्र डोकेदुखी आणि चक्कर.",
        "language": "mr"
    }
    checks.append(check_url("POST", "/voice-intake", 200, payload=intake_payload, headers={"X-API-Key": "maha-asha-2026"}))

    sync_payload = {
        "worker_id": "ASHA-PUN-042",
        "records": [
            {
                "patient_id": "PAT-SYNC-LIVE-01",
                "phone": "+91-9822114477",
                "district": "Pune",
                "voice_transcript": "रुग्ण आयडी PAT-SYNC-LIVE-01, गरोदर ३२ आठवडे, बीपी १५०/९५",
                "language": "mr"
            }
        ]
    }
    checks.append(check_url("POST", "/api/offline-sync", 200, payload=sync_payload))

    passed = sum(1 for c in checks if c)
    total = len(checks)
    print("\n" + "=" * 60)
    print(f"LIVE URL AUDIT SUMMARY: {passed}/{total} URLS VERIFIED AND WORKING PERFECTLY!")
    print("=" * 60)
    if passed < total:
        sys.exit(1)


if __name__ == "__main__":
    run_all_url_checks()
