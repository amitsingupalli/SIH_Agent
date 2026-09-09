"""
Live End-to-End System Integration Test Suite for MahaArogya-Agent.
SIH 2026 PS 133 | Govt of Maharashtra Health Department

Tests all 13 core capabilities against the live FastAPI server at http://127.0.0.1:8000:
1. Health check telemetry
2. Interactive dashboard HTML serving
3. English Voice Intake -> High-Risk Triage + Base64 QR Referral Pass
4. Marathi Devanagari Intake -> High-Risk Triage + Vernacular Alert
5. Low-Risk Routine ANC Intake -> Normal Advisory (Zero Unnecessary Referrals)
6. Network Idempotency Guard (Double-booking prevention on flaky 2G/3G)
7. Role-Based Access Control (401 Rejection on invalid API keys)
8. Closed-Loop Referral (48h Attendance SLA Tracking & Auto-Escalation)
9. Human-In-The-Loop (Clinician sign-off & audit logging)
10. Surveillance Watchdog (Spatial-temporal outbreak clustering & stock runways)
11. Clinical Benchmark Evals (20 Cases, 100% Sensitivity & 100% Accuracy)
12. Clinical Governance Audit Trail (/audit-logs)
13. Telecommunications DLQ & Reliability (/reliability/dlq & /stats)
"""

import json
import sys
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")
BASE = "http://127.0.0.1:8000"


def run_e2e_tests():
    results = []

    def run_test(name, fn):
        try:
            fn()
            results.append((name, "PASS", ""))
            print(f"[PASS] {name}")
        except Exception as e:
            results.append((name, "FAIL", str(e)))
            print(f"[FAIL] {name} - {e}")

    # 1. Health Check
    def test_health():
        with urllib.request.urlopen(f"{BASE}/health") as r:
            assert r.status == 200
            data = json.loads(r.read())
            assert data["status"] == "healthy"
    run_test("1. Health Check Endpoint", test_health)

    # 2. UI Dashboard
    def test_dashboard():
        with urllib.request.urlopen(f"{BASE}/") as r:
            assert r.status == 200
            html = r.read().decode("utf-8")
            assert "MahaArogya" in html
            assert "ASHA Voice Copilot" in html
    run_test("2. UI Dashboard HTML Serving", test_dashboard)

    # 3. Voice Intake - English High Risk
    saved_ref = {"id": None}
    def test_voice_en_high():
        payload = {
            "patient_id": "PAT-TEST-EN",
            "phone": "+91-9822114477",
            "district": "Pune",
            "voice_transcript": "Patient ID PAT-TEST-EN, 32 weeks pregnant, BP 155/96, severe headache and blurry vision.",
            "language": "en"
        }
        req = urllib.request.Request(
            f"{BASE}/voice-intake",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "X-API-Key": "maha-asha-2026"}
        )
        with urllib.request.urlopen(req) as r:
            assert r.status == 200
            data = json.loads(r.read())
            assert data["triage_level"] == "HIGH"
            assert data["requires_referral"] is True
            assert data["referral_details"] is not None
            saved_ref["id"] = data["referral_details"]["referral_id"]
            assert len(data["referral_details"]["qr_image_base64"]) > 50
    run_test("3. Voice Intake (English Severe Preeclampsia -> High Triage + QR Pass)", test_voice_en_high)

    # 4. Voice Intake - Marathi High Risk
    def test_voice_mr_high():
        payload = {
            "patient_id": "PAT-TEST-MR",
            "phone": "+91-9822114477",
            "district": "Pune",
            "voice_transcript": "रुग्ण आयडी PAT-TEST-MR, गरोदर ३२ आठवडे, बीपी १६०/१००, तीव्र डोकेदुखी आणि चक्कर येणे.",
            "language": "mr"
        }
        req = urllib.request.Request(
            f"{BASE}/voice-intake",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "X-API-Key": "maha-asha-2026"}
        )
        with urllib.request.urlopen(req) as r:
            assert r.status == 200
            data = json.loads(r.read())
            assert data["triage_level"] == "HIGH"
            assert data["requires_referral"] is True
    run_test("4. Voice Intake (Marathi Devanagari Vitals -> High Triage)", test_voice_mr_high)

    # 5. Voice Intake - Low Risk Normal ANC
    def test_voice_low():
        payload = {
            "patient_id": "PAT-TEST-LOW",
            "phone": "+91-9822114477",
            "district": "Nashik",
            "voice_transcript": "Patient ID PAT-TEST-LOW, pregnant 20 weeks, BP 116/74, routine antenatal checkup, no complaints.",
            "language": "en"
        }
        req = urllib.request.Request(
            f"{BASE}/voice-intake",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req) as r:
            assert r.status == 200
            data = json.loads(r.read())
            assert data["triage_level"] == "LOW"
            assert data["requires_referral"] is False
    run_test("5. Voice Intake (Low Risk Routine ANC -> No Referral)", test_voice_low)

    # 6. Idempotency Check
    def test_idempotency():
        idem_key = "idem-test-token-777"
        payload = {
            "patient_id": "PAT-IDEM-99",
            "phone": "+91-9822114477",
            "district": "Pune",
            "voice_transcript": "Patient ID PAT-IDEM-99, 32 weeks, BP 152/98, severe headache.",
            "language": "en"
        }
        req1 = urllib.request.Request(
            f"{BASE}/voice-intake",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "X-Idempotency-Key": idem_key}
        )
        with urllib.request.urlopen(req1) as r1:
            data1 = json.loads(r1.read())
        
        req2 = urllib.request.Request(
            f"{BASE}/voice-intake",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "X-Idempotency-Key": idem_key}
        )
        with urllib.request.urlopen(req2) as r2:
            assert r2.headers.get("X-Idempotent-Replay") == "true"
            data2 = json.loads(r2.read())
            assert data1["patient_id"] == data2["patient_id"]
    run_test("6. Idempotency Guard (Network Double-Booking Prevention)", test_idempotency)

    # 7. Role-Based Auth
    def test_auth_rejection():
        payload = {
            "voice_transcript": "Testing invalid auth",
            "language": "en"
        }
        req = urllib.request.Request(
            f"{BASE}/voice-intake",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "X-API-Key": "completely-wrong-key"}
        )
        try:
            urllib.request.urlopen(req)
            raise AssertionError("Should have failed with 401")
        except urllib.error.HTTPError as err:
            assert err.code == 401
    run_test("7. Role-Based Auth (Rejection of Invalid API Key with 401)", test_auth_rejection)

    # 8. Referral Status & 48h SLA Breach Escalation
    def test_referral_and_breach():
        ref_id = saved_ref["id"]
        assert ref_id is not None
        # 8a: Normal status
        with urllib.request.urlopen(f"{BASE}/referral-status/{ref_id}") as r:
            assert r.status == 200
            d = json.loads(r.read())
            assert d["status"] == "BOOKED"
            assert d["hours_remaining"] == 48
        # 8b: Simulated 48h breach
        with urllib.request.urlopen(f"{BASE}/referral-status/{ref_id}?force_sla_breach=true") as r_breach:
            assert r_breach.status == 200
            d_breach = json.loads(r_breach.read())
            assert d_breach["status"] == "NO_SHOW"
            assert d_breach["escalated"] is True
            assert "escalation_message_vernacular" in d_breach
    run_test("8. Closed-Loop Referral (48h Attendance SLA Tracking & Auto-Escalation)", test_referral_and_breach)

    # 9. HITL Medical Officer Clinician Sign-off
    def test_hitl_approval():
        ref_id = saved_ref["id"]
        payload = {
            "referral_id": ref_id,
            "approved": True,
            "reviewer_name": "Dr. Vaishali Kulkarni",
            "notes": "Verified clinical signs of impending eclampsia, approved emergency admission"
        }
        req = urllib.request.Request(
            f"{BASE}/hitl/approve",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req) as r:
            assert r.status == 200
            d = json.loads(r.read())
            assert d["approved"] is True
            assert d["status"] == "BOOKED"
    run_test("9. Human-In-The-Loop (Clinician Sign-off & Audit Capture)", test_hitl_approval)

    # 10. Surveillance Watchdog
    def test_surveillance():
        with urllib.request.urlopen(f"{BASE}/epidemic-alerts") as r:
            assert r.status == 200
            d = json.loads(r.read())
            assert d["total_active_outbreaks"] >= 1
            assert len(d["critical_drug_runways"]) >= 1
            assert "MAHARASHTRA HEALTH DEPARTMENT" in d["dho_briefing_text"]
    run_test("10. Surveillance Watchdog (Spatial-Temporal Outbreak & Stock-Out Briefing)", test_surveillance)

    # 11. Clinical Benchmark (20 Cases)
    def test_evals_run():
        with urllib.request.urlopen(f"{BASE}/evals/run") as r:
            assert r.status == 200
            d = json.loads(r.read())
            assert d["total_benchmark_cases"] == 20
            assert d["high_risk_sensitivity_recall_percent"] == 100.0
            assert d["overall_triage_accuracy_percent"] == 100.0
            assert d["confusion_matrix_high_risk"]["false_negatives"] == 0
    run_test("11. Clinical Benchmark Evals (20 Cases, 100% Sensitivity & 100% Accuracy)", test_evals_run)

    # 12. Clinical Governance Audit Trail
    def test_audit_logs():
        with urllib.request.urlopen(f"{BASE}/audit-logs") as r:
            assert r.status == 200
            d = json.loads(r.read())
            assert d["status"] == "SUCCESS"
            assert d["total_records"] >= 3
    run_test("12. Clinical Governance Audit Trail (/audit-logs)", test_audit_logs)

    # 13. Telecommunications DLQ & Reliability
    def test_reliability_dlq():
        with urllib.request.urlopen(f"{BASE}/reliability/dlq") as r:
            assert r.status == 200
            d = json.loads(r.read())
            assert "unresolved_count" in d
        with urllib.request.urlopen(f"{BASE}/reliability/stats") as r:
            assert r.status == 200
            d = json.loads(r.read())
            assert d["telecom_resilience_mode"] == "ACTIVE (Exponential Backoff + DLQ Routing)"
    run_test("13. Reliability & Telecommunications DLQ (/reliability/dlq & /stats)", test_reliability_dlq)

    failed = [n for n, s, e in results if s == "FAIL"]
    print("=" * 50)
    print(f"LIVE E2E TEST RUN SUMMARY: {len(results) - len(failed)}/{len(results)} PASSED")
    if failed:
        print("Failed tests:", failed)
        sys.exit(1)
    print("ALL 13 SYSTEM INTEGRATION TESTS PASSED PERFECTLY!")
    print("=" * 50)


if __name__ == "__main__":
    run_e2e_tests()
