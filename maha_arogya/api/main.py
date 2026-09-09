"""
Production FastAPI Application for MahaArogya-Agent.
Exposes endpoints for Vernacular Voice Intake, Closed-Loop Referral Tracking, and Epidemic Alerts.
"""

import json
import uuid
from typing import Optional, Dict, Any
from fastapi import FastAPI, HTTPException, Query, Body
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from maha_arogya.config import settings
from maha_arogya.agents.graph import maha_arogya_graph, maha_arogya_hitl_graph
from maha_arogya.agents.referral_agent import check_and_escalate_referral
from maha_arogya.agents.surveillance_agent import detect_spatial_temporal_clusters, generate_dho_briefing
from maha_arogya.mcp.server import check_stock_runway, REFERRAL_STORE, PATIENT_RECORDS

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Autonomous Multi-Agent Rural Healthcare & Closed-Loop Referral Tracking System (SIH 2026 PS 133 | Govt of Maharashtra)",
    version=settings.VERSION,
    docs_url="/docs",
    redoc_url="/redoc"
)

# Enable CORS for rural mobile tablets and dashboard integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Request & Response Schemas
class VoiceIntakeRequest(BaseModel):
    patient_id: Optional[str] = Field(None, example="PAT-4102")
    phone: Optional[str] = Field("+91-9822114477", example="+91-9822114477")
    district: Optional[str] = Field("Pune", example="Pune")
    phc_id: Optional[str] = Field("PHC-PUN-KND", example="PHC-PUN-KND")
    voice_transcript: str = Field(
        ...,
        description="Spoken Marathi or Hindi text transcript from ASHA worker or Bhashini STT",
        example="रुग्ण आयडी PAT-4102, गरोदर ३२ आठवडे, बीपी १५०/९५, तीव्र डोकेदुखी आणि डोळ्यासमोर अंधारी"
    )
    language: Optional[str] = Field("mr", example="mr")


class HITLApprovalRequest(BaseModel):
    referral_id: str = Field(..., example="REF-EC1FFD")
    approved: bool = Field(True, description="Clinician approval status")
    reviewer_name: str = Field("Dr. Vaishali Kulkarni", example="Dr. Vaishali Kulkarni")
    notes: Optional[str] = Field("Approved for emergency CEmONC admission.", example="Approved for emergency CEmONC admission.")


# ==========================================
# 1. ENDPOINT: /voice-intake
# ==========================================
@app.post("/voice-intake", summary="Vernacular Voice Intake & Clinical Triage")
async def voice_intake(payload: VoiceIntakeRequest):
    """
    Accepts spoken symptoms and vitals in Marathi/Hindi.
    Executes ASHA Voice Copilot -> HL7 FHIR entity extraction -> Clinical Triage (LOW/MED/HIGH)
    -> Closed-Loop Referral (if HIGH) -> Surveillance ingestion.
    """
    thread_id = f"session-{uuid.uuid4().hex[:8]}"
    config = {"configurable": {"thread_id": thread_id}}
    
    initial_state = {
        "patient_id": payload.patient_id or "PAT-UNKNOWN",
        "phone": payload.phone,
        "district": payload.district,
        "phc_id": payload.phc_id,
        "raw_input": payload.voice_transcript,
        "detected_language": payload.language or "mr"
    }
    
    try:
        final_state = maha_arogya_graph.invoke(initial_state, config=config)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent workflow execution error: {str(e)}")
        
    return {
        "session_id": thread_id,
        "patient_id": final_state.get("patient_id"),
        "triage_level": final_state.get("triage_level"),
        "triage_rationale": final_state.get("triage_rationale"),
        "red_flag_detected": final_state.get("red_flag_detected"),
        "specialty_needed": final_state.get("specialty_needed"),
        "requires_referral": final_state.get("requires_referral"),
        "referral_details": {
            "referral_id": final_state.get("referral_id"),
            "hospital_name": final_state.get("hospital_name"),
            "hospital_id": final_state.get("hospital_id"),
            "qr_token": final_state.get("qr_token"),
            "scheduled_at": final_state.get("scheduled_at"),
            "sla_expires_at": final_state.get("sla_expires_at"),
            "qr_image_base64": final_state.get("qr_image_base64")
        } if final_state.get("requires_referral") else None,
        "vernacular_alert_dispatched": final_state.get("alert_dispatched", False),
        "vernacular_message": final_state.get("vernacular_alert_text"),
        "fhir_bundle_summary": {
            "resourceType": "Bundle",
            "total_entries": len(final_state.get("fhir_bundle", {}).get("entry", []))
        }
    }


# ==========================================
# 2. ENDPOINT: /referral-status/{referral_id}
# ==========================================
@app.get("/referral-status/{referral_id}", summary="Closed-Loop Referral & 48h SLA Tracking")
async def get_referral_status(
    referral_id: str,
    force_sla_breach: bool = Query(False, description="Simulate 48-hour SLA breach for testing escalation")
):
    """
    Tracks hospital arrival for an issued referral pass.
    If patient fails to check in within 48 hours, automatically triggers Marathi WhatsApp
    alert and escalates to the designated ASHA worker.
    """
    result = check_and_escalate_referral(referral_id=referral_id, force_sla_breach=force_sla_breach)
    if result.get("status") == "NOT_FOUND":
        raise HTTPException(status_code=404, detail=f"Referral pass '{referral_id}' not found.")
    return result


# ==========================================
# 3. ENDPOINT: /epidemic-alerts
# ==========================================
@app.get("/epidemic-alerts", summary="Surveillance Watchdog Outbreaks & Medicine Stock Runways")
async def get_epidemic_alerts():
    """
    Returns spatial-temporal disease outbreak clusters across Maharashtra PHCs,
    critical pharmaceutical stock-out runways (< 7 days), and official DHO briefing.
    """
    outbreaks = detect_spatial_temporal_clusters()
    
    # Assess critical drugs
    critical_drugs = [
        ("PHC-GAD-BHM", "Chloroquine/ACT"),
        ("PHC-NSK-TRB", "ORS"),
        ("PHC-PUN-KND", "Magnesium Sulfate")
    ]
    
    stock_assessments = []
    for phc_id, drug in critical_drugs:
        runway_raw = check_stock_runway(phc_id=phc_id, drug_name=drug)
        stock_assessments.append(json.loads(runway_raw))
        
    dho_briefing = generate_dho_briefing(outbreaks, stock_assessments)
    
    return {
        "state": settings.DEFAULT_STATE,
        "department": "Public Health Department (Arogya Vibhag), Maharashtra",
        "total_active_outbreaks": len(outbreaks),
        "outbreaks": outbreaks,
        "critical_drug_runways": stock_assessments,
        "dho_briefing_text": dho_briefing
    }


# ==========================================
# 4. ENDPOINT: /hitl/approve
# ==========================================
@app.post("/hitl/approve", summary="Human-In-The-Loop Clinician Sign-Off")
async def hitl_approve(payload: HITLApprovalRequest):
    """Allows a Medical Officer (MO) to review and validate a pending high-risk referral."""
    referral = REFERRAL_STORE.get(payload.referral_id)
    if not referral:
        raise HTTPException(status_code=404, detail=f"Referral '{payload.referral_id}' not found.")
        
    referral["hitl_approved"] = payload.approved
    referral["hitl_reviewer"] = payload.reviewer_name
    referral["hitl_notes"] = payload.notes
    referral["status"] = "BOOKED" if payload.approved else "REJECTED_BY_CLINICIAN"
    
    return {
        "referral_id": payload.referral_id,
        "approved": payload.approved,
        "status": referral["status"],
        "reviewer": payload.reviewer_name,
        "notes": payload.notes,
        "message": "Clinician HITL verification recorded successfully."
    }


# ==========================================
# 5. HEALTH CHECK & DASHBOARD
# ==========================================
@app.get("/health", summary="Health Check & System Telemetry")
async def health():
    return {
        "status": "healthy",
        "project": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "active_referrals_count": len(REFERRAL_STORE),
        "patients_logged": len(PATIENT_RECORDS)
    }


@app.get("/", response_class=HTMLResponse, summary="SIH 2026 Interactive Evaluation Dashboard")
async def dashboard():
    return """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>MahaArogya-Agent | SIH 2026 PS 133</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
        <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.1/font/bootstrap-icons.css">
        <style>
            :root { --primary-gov: #d9381e; --dark-gov: #1a2a3a; --bg-light: #f4f7f6; }
            body { background: var(--bg-light); font-family: 'Segoe UI', system-ui, sans-serif; }
            .navbar-gov { background: var(--dark-gov); border-bottom: 4px solid var(--primary-gov); }
            .card-agent { border-radius: 12px; border: none; box-shadow: 0 4px 15px rgba(0,0,0,0.06); transition: 0.2s; }
            .card-agent:hover { transform: translateY(-2px); }
            .badge-high { background-color: #dc3545; color: white; }
            .badge-med { background-color: #fd7e14; color: white; }
            .badge-low { background-color: #198754; color: white; }
            .mono-box { font-family: monospace; background: #212529; color: #00ff66; padding: 15px; border-radius: 8px; font-size: 13px; max-height: 250px; overflow-y: auto; }
        </style>
    </head>
    <body>
        <nav class="navbar navbar-dark navbar-gov px-4 py-3">
            <div class="container-fluid">
                <span class="navbar-brand fw-bold fs-4">
                    <i class="bi bi-hospital me-2 text-danger"></i> MahaArogya-Agent
                    <small class="fs-6 text-warning d-block d-md-inline ms-md-2">SIH 2026 PS 133 | Govt of Maharashtra</small>
                </span>
                <div class="text-white small text-end">
                    <span class="badge bg-success me-2"><i class="bi bi-circle-fill"></i> FastMCP 5/5 Active</span>
                    <span class="badge bg-info"><i class="bi bi-cpu"></i> LangGraph HITL Active</span>
                </div>
            </div>
        </nav>

        <div class="container-fluid px-4 py-4">
            <div class="row g-4">
                <!-- Left Column: Voice Intake Simulation -->
                <div class="col-lg-6">
                    <div class="card card-agent p-4 h-100">
                        <h5 class="fw-bold text-dark"><i class="bi bi-mic-fill text-danger me-2"></i> 1. ASHA Vernacular Voice Copilot</h5>
                        <p class="text-muted small">Input spoken Marathi or Hindi vitals and symptoms. Transcribes, structures into HL7 FHIR, and triages automatically.</p>
                        
                        <div class="mb-3">
                            <label class="form-label fw-semibold">Spoken Marathi / Hindi Transcript:</label>
                            <textarea id="voiceText" class="form-control" rows="3">रुग्ण आयडी PAT-4102, गरोदर माता ३२ आठवडे, बीपी १५०/९५, तीव्र डोकेदुखी आणि डोळ्यासमोर अंधारी, पायांवर सूज आहे.</textarea>
                        </div>
                        <div class="row g-2 mb-3">
                            <div class="col-6">
                                <label class="form-label small fw-semibold">District:</label>
                                <select id="districtSelect" class="form-select form-select-sm">
                                    <option value="Pune">Pune</option>
                                    <option value="Nashik">Nashik</option>
                                    <option value="Gadchiroli">Gadchiroli (Tribal)</option>
                                    <option value="Thane">Thane</option>
                                </select>
                            </div>
                            <div class="col-6">
                                <label class="form-label small fw-semibold">Patient Phone:</label>
                                <input type="text" id="phoneInput" class="form-control form-control-sm" value="+91-9822114477">
                            </div>
                        </div>
                        <button class="btn btn-danger fw-bold" onclick="runVoiceIntake()">
                            <i class="bi bi-play-fill"></i> Run Voice Intake & Triage
                        </button>

                        <div id="triageResult" class="mt-4 d-none">
                            <h6 class="fw-bold"><i class="bi bi-clipboard-pulse text-primary me-1"></i> Triage Assessment Result:</h6>
                            <div class="alert alert-secondary p-3 small mb-2" id="triageSummary"></div>
                            <div class="mono-box" id="triageJson"></div>
                        </div>
                    </div>
                </div>

                <!-- Right Column: Closed Loop Referral & Surveillance -->
                <div class="col-lg-6">
                    <div class="card card-agent p-4 mb-4">
                        <h5 class="fw-bold text-dark"><i class="bi bi-qr-code text-primary me-2"></i> 2. Closed-Loop Referral & 48h SLA Tracking</h5>
                        <p class="text-muted small">Validates priority hospital bed slot, generates cryptographic QR pass, and escalates no-shows after 48 hours.</p>
                        
                        <div class="input-group mb-3">
                            <input type="text" id="referralIdInput" class="form-control" placeholder="Enter Referral ID (e.g. REF-EC1FFD)">
                            <button class="btn btn-primary" onclick="checkReferral(false)"><i class="bi bi-search"></i> Check SLA</button>
                            <button class="btn btn-outline-danger" onclick="checkReferral(true)"><i class="bi bi-exclamation-triangle"></i> Simulate 48h Breach</button>
                        </div>
                        <div id="referralResultBox" class="mono-box d-none"></div>
                    </div>

                    <div class="card card-agent p-4">
                        <div class="d-flex justify-content-between align-items-center mb-2">
                            <h5 class="fw-bold text-dark mb-0"><i class="bi bi-shield-shaded text-success me-2"></i> 3. Surveillance Watchdog</h5>
                            <button class="btn btn-sm btn-outline-success" onclick="fetchEpidemicAlerts()"><i class="bi bi-arrow-clockwise"></i> Refresh</button>
                        </div>
                        <p class="text-muted small">Outbreak spatial-temporal clustering and medicine stock-out runway forecasts.</p>
                        <div id="epidemicBox" class="mono-box">Click 'Refresh' to load real-time syndromic clusters and drug runways.</div>
                    </div>
                </div>
            </div>
        </div>

        <script>
            async function runVoiceIntake() {
                const text = document.getElementById('voiceText').value;
                const district = document.getElementById('districtSelect').value;
                const phone = document.getElementById('phoneInput').value;
                
                const res = await fetch('/voice-intake', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({voice_transcript: text, district: district, phone: phone})
                });
                const data = await res.json();
                
                document.getElementById('triageResult').classList.remove('d-none');
                document.getElementById('triageSummary').innerHTML = `
                    <strong>Patient:</strong> ${data.patient_id} | 
                    <strong>Triage:</strong> <span class="badge ${data.triage_level === 'HIGH' ? 'badge-high' : 'badge-low'}">${data.triage_level}</span><br>
                    <strong>Rationale:</strong> ${data.triage_rationale}<br>
                    ${data.referral_details ? `<strong>Referral ID:</strong> <span class="badge bg-primary">${data.referral_details.referral_id}</span> | <strong>QR Token:</strong> <code>${data.referral_details.qr_token}</code><br><strong>Hospital:</strong> ${data.referral_details.hospital_name}` : ''}
                `;
                document.getElementById('triageJson').innerText = JSON.stringify(data, null, 2);
                if (data.referral_details) {
                    document.getElementById('referralIdInput').value = data.referral_details.referral_id;
                }
            }

            async function checkReferral(forceBreach) {
                const refId = document.getElementById('referralIdInput').value.trim();
                if (!refId) { alert('Please enter a Referral ID first'); return; }
                const res = await fetch(`/referral-status/${refId}?force_sla_breach=${forceBreach}`);
                const data = await res.json();
                const box = document.getElementById('referralResultBox');
                box.classList.remove('d-none');
                box.innerText = JSON.stringify(data, null, 2);
            }

            async function fetchEpidemicAlerts() {
                const res = await fetch('/epidemic-alerts');
                const data = await res.json();
                document.getElementById('epidemicBox').innerText = data.dho_briefing_text;
            }

            window.onload = fetchEpidemicAlerts;
        </script>
    </body>
    </html>
    """