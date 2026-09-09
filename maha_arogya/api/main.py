"""
Production FastAPI Application for MahaArogya-Agent.
Exposes endpoints for Vernacular Voice Intake, Audio Uploads, Closed-Loop Referral Tracking, and Epidemic Alerts.
"""

import json
import uuid
import base64
from typing import Optional, Dict, Any
from fastapi import FastAPI, HTTPException, Query, UploadFile, File, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from maha_arogya.config import settings
from maha_arogya.agents.graph import maha_arogya_graph, maha_arogya_hitl_graph
from maha_arogya.agents.referral_agent import check_and_escalate_referral
from maha_arogya.agents.surveillance_agent import detect_spatial_temporal_clusters, generate_dho_briefing
from maha_arogya.mcp.server import check_stock_runway, REFERRAL_STORE, PATIENT_RECORDS
from maha_arogya.services.voice_nlp import voice_nlp_service

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
# 1. ENDPOINTS: /voice-intake & /voice-intake/audio
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


@app.post("/voice-intake/audio", summary="Direct Audio File Intake (WAV/MP3/M4A)")
async def voice_intake_audio(
    audio_file: UploadFile = File(..., description="Recorded audio file from ASHA worker"),
    patient_id: Optional[str] = Form(None),
    district: Optional[str] = Form("Pune"),
    language: Optional[str] = Form("mr")
):
    """
    Accepts raw audio file upload, transcribes Marathi/Hindi speech via Bhashini/Whisper STT,
    and runs the full multi-agent triage and referral loop.
    """
    audio_bytes = await audio_file.read()
    # Transcribe via Voice NLP Service
    transcript = voice_nlp_service.transcribe_audio(audio_bytes, language=language)
    
    req = VoiceIntakeRequest(
        patient_id=patient_id,
        district=district,
        voice_transcript=transcript,
        language=language
    )
    res = await voice_intake(req)
    res["audio_file_received"] = audio_file.filename
    res["transcribed_text"] = transcript
    return res


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
    <html lang="mr">
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
            .btn-mic-recording { animation: pulse 1s infinite alternate; background-color: #dc3545 !important; color: white !important; }
            @keyframes pulse { from { transform: scale(1); } to { transform: scale(1.06); } }
            .qr-display { background: white; padding: 10px; border-radius: 8px; display: inline-block; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        </style>
    </head>
    <body>
        <nav class="navbar navbar-dark navbar-gov px-4 py-3">
            <div class="container-fluid">
                <span class="navbar-brand fw-bold fs-4">
                    <i class="bi bi-hospital me-2 text-danger"></i> महाआरोग्य-Agent (MahaArogya)
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
                <!-- Left Column: Voice Intake & Presets -->
                <div class="col-lg-6">
                    <div class="card card-agent p-4 h-100">
                        <div class="d-flex justify-content-between align-items-center mb-2">
                            <h5 class="fw-bold text-dark mb-0"><i class="bi bi-mic-fill text-danger me-2"></i> 1. ASHA Voice Copilot (Voice / आवाज नोंदणी)</h5>
                            <span class="badge bg-primary-subtle text-primary border border-primary">English / मराठी / हिंदी</span>
                        </div>
                        <p class="text-muted small">
                            Direct voice input via microphone or text. Converts speech to HL7 FHIR Observation/Condition, computes triage (LOW/MED/HIGH), and books specialist emergency care.
                        </p>

                        <!-- Language Tab Selector for Presets -->
                        <div class="mb-3">
                            <div class="d-flex justify-content-between align-items-center mb-2">
                                <label class="form-label small fw-semibold text-secondary mb-0">Clinical Presets (Language):</label>
                                <div class="btn-group btn-group-sm" role="group">
                                    <button class="btn btn-sm btn-primary fw-bold" id="btnTabEn" onclick="switchPresetLang('en')">English</button>
                                    <button class="btn btn-sm btn-outline-danger" id="btnTabMr" onclick="switchPresetLang('mr')">मराठी (Marathi)</button>
                                    <button class="btn btn-sm btn-outline-warning text-dark" id="btnTabHi" onclick="switchPresetLang('hi')">हिंदी (Hindi)</button>
                                </div>
                            </div>
                            <!-- Preset Buttons Container -->
                            <div id="presetsContainer" class="d-flex flex-wrap gap-2">
                                <button class="btn btn-sm btn-outline-danger" onclick="setPreset('preeclampsia_en')">🚨 Severe Preeclampsia (English)</button>
                                <button class="btn btn-sm btn-outline-warning text-dark" onclick="setPreset('fever_en')">⚠️ High Fever / Malaria (English)</button>
                                <button class="btn btn-sm btn-outline-success" onclick="setPreset('routine_en')">✅ Normal Antenatal (English)</button>
                            </div>
                        </div>

                        <!-- Live Microphone Controls -->
                        <div class="p-3 bg-light rounded border mb-3">
                            <div class="d-flex align-items-center justify-content-between mb-2">
                                <span class="fw-bold text-dark"><i class="bi bi-record-circle me-1"></i> Live Microphone Recording:</span>
                                <select id="voiceLang" class="form-select form-select-sm w-auto" onchange="syncVoiceLanguage()">
                                    <option value="en-US" selected>English (India / Global)</option>
                                    <option value="mr-IN">Marathi (मराठी)</option>
                                    <option value="hi-IN">Hindi (हिंदी)</option>
                                </select>
                            </div>
                            <div class="d-flex gap-2">
                                <button id="micBtn" class="btn btn-danger fw-bold flex-grow-1" onclick="toggleLiveMic()">
                                    <i class="bi bi-mic-fill me-1"></i> Start Speaking (Microphone)
                                </button>
                                <button id="speakAloudBtn" class="btn btn-outline-secondary" onclick="speakAloudOutput()" title="Read out vernacular response">
                                    <i class="bi bi-volume-up-fill"></i> Read Aloud
                                </button>
                            </div>
                            <small id="micStatus" class="text-muted d-block mt-2">Click button and speak your symptoms into the microphone.</small>
                        </div>

                        <div class="mb-3">
                            <label class="form-label fw-semibold">Transcript (बोललेला मजकूर):</label>
                            <textarea id="voiceText" class="form-control" rows="3">रुग्ण आयडी PAT-4102, गरोदर माता ३२ आठवडे, बीपी १५०/९५, तीव्र डोकेदुखी आणि डोळ्यासमोर अंधारी, पायांवर सूज आहे.</textarea>
                        </div>

                        <div class="row g-2 mb-3">
                            <div class="col-6">
                                <label class="form-label small fw-semibold">District:</label>
                                <select id="districtSelect" class="form-select form-select-sm">
                                    <option value="Pune">Pune (पुणे)</option>
                                    <option value="Nashik">Nashik (नाशिक)</option>
                                    <option value="Gadchiroli">Gadchiroli (गडचिरोली Tribal)</option>
                                    <option value="Thane">Thane (ठाणे)</option>
                                </select>
                            </div>
                            <div class="col-6">
                                <label class="form-label small fw-semibold">Patient Phone:</label>
                                <input type="text" id="phoneInput" class="form-control form-control-sm" value="+91-9822114477">
                            </div>
                        </div>

                        <button class="btn btn-primary fw-bold w-100" onclick="runVoiceIntake()">
                            <i class="bi bi-send-fill me-1"></i> Submit to Multi-Agent Engine (तपासणी सुरू करा)
                        </button>

                        <div id="triageResult" class="mt-4 d-none">
                            <h6 class="fw-bold"><i class="bi bi-clipboard-pulse text-primary me-1"></i> Triage Assessment Result:</h6>
                            <div class="alert alert-secondary p-3 small mb-2" id="triageSummary"></div>
                            
                            <!-- QR Code Visual Display -->
                            <div id="qrContainer" class="text-center my-3 p-3 bg-white border rounded d-none">
                                <h6 class="fw-bold text-success mb-2"><i class="bi bi-check-circle-fill"></i> Emergency Referral Pass Generated!</h6>
                                <div class="qr-display mb-2">
                                    <img id="qrImageElement" src="" alt="Referral QR Pass" width="160" height="160">
                                </div>
                                <div class="small fw-semibold text-dark" id="qrTokenDisplay"></div>
                                <small class="text-muted d-block">Show this QR pass at the Civil Hospital Emergency Triage Desk</small>
                            </div>

                            <div class="mono-box" id="triageJson"></div>
                        </div>
                    </div>
                </div>

                <!-- Right Column: Closed Loop Referral & Surveillance -->
                <div class="col-lg-6">
                    <div class="card card-agent p-4 mb-4">
                        <h5 class="fw-bold text-dark"><i class="bi bi-qr-code text-primary me-2"></i> 2. Closed-Loop Referral & 48h SLA Tracking</h5>
                        <p class="text-muted small">Tracks attendance at destination hospital. If no-show within 48h, auto-dispatches Marathi WhatsApp escalation to ASHA worker.</p>
                        
                        <div class="input-group mb-3">
                            <input type="text" id="referralIdInput" class="form-control" placeholder="Enter Referral ID (e.g. REF-AA7BA4)">
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
                        <p class="text-muted small">Spatial-temporal syndromic clustering & medicine stock-out runway forecasts (< 7 days).</p>
                        <div id="epidemicBox" class="mono-box">Click 'Refresh' to load real-time syndromic clusters and drug runways.</div>
                    </div>
                </div>
            </div>
        </div>

        <script>
            let recognition = null;
            let isRecording = false;
            let lastMarathiResponse = "";

            // Initialize Web Speech API for Browser Voice Input
            if ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window) {
                const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
                recognition = new SpeechRecognition();
                recognition.continuous = false;
                recognition.interimResults = false;

                recognition.onstart = function() {
                    isRecording = true;
                    document.getElementById('micBtn').classList.add('btn-mic-recording');
                    document.getElementById('micBtn').innerHTML = '<i class="bi bi-stop-circle-fill me-1"></i> Recording... Click to Stop';
                    document.getElementById('micStatus').innerText = '🎤 Listening... Please speak your symptoms in Marathi/Hindi now!';
                };

                recognition.onresult = function(event) {
                    const transcript = event.results[0][0].transcript;
                    document.getElementById('voiceText').value = transcript;
                    document.getElementById('micStatus').innerText = '✅ Speech captured successfully! Now submitting to Multi-Agent Engine...';
                    runVoiceIntake();
                };

                recognition.onerror = function(event) {
                    document.getElementById('micStatus').innerText = '⚠️ Microphone error or permission denied: ' + event.error;
                    stopMic();
                };

                recognition.onend = function() {
                    stopMic();
                };
            }

            function toggleLiveMic() {
                if (!recognition) {
                    alert('Web Speech API is not supported in this browser. Please type or use Chrome/Edge.');
                    return;
                }
                if (isRecording) {
                    recognition.stop();
                    stopMic();
                } else {
                    const lang = document.getElementById('voiceLang').value;
                    recognition.lang = lang;
                    recognition.start();
                }
            }

            function stopMic() {
                isRecording = false;
                document.getElementById('micBtn').classList.remove('btn-mic-recording');
                document.getElementById('micBtn').innerHTML = '<i class="bi bi-mic-fill me-1"></i> Start Speaking (Microphone)';
            }

            const PRESETS = {
                en: [
                    { title: "🚨 Severe Preeclampsia (English)", class: "btn-outline-danger", text: "Patient ID PAT-4102, 32 weeks pregnant, blood pressure 150/95, severe headache, blurred vision, and swelling in face and hands.", district: "Pune" },
                    { title: "⚠️ High Fever / Malaria (English)", class: "btn-outline-warning text-dark", text: "Patient ID PAT-3301, acute high fever with chills, body ache, nausea, and vomiting.", district: "Gadchiroli" },
                    { title: "✅ Normal Antenatal (English)", class: "btn-outline-success", text: "Patient ID PAT-1050, routine antenatal checkup, 24 weeks pregnant, blood pressure 118/76, fetal movement normal, feeling healthy.", district: "Nashik" }
                ],
                mr: [
                    { title: "🚨 प्री-एक्लॅम्पसिया तातडी (मराठी)", class: "btn-outline-danger", text: "रुग्ण आयडी PAT-4102, गरोदर माता ३२ आठवडे, बीपी १५०/९५, तीव्र डोकेदुखी आणि डोळ्यासमोर अंधारी, पायांवर सूज आहे.", district: "Pune" },
                    { title: "⚠️ तीव्र ताप / हिवताप (मराठी)", class: "btn-outline-warning text-dark", text: "रुग्ण आयडी PAT-3301, अंगात तीव्र ताप, थंडी वाजून येणे, मळमळ आणि उलट्या होत आहेत.", district: "Gadchiroli" },
                    { title: "✅ नियमित तपासणी (मराठी)", class: "btn-outline-success", text: "रुग्ण आयडी PAT-1050, नियमित गरोदर तपासणी, २० आठवडे, बीपी ११८/७८, सर्व काही व्यवस्थित आहे.", district: "Nashik" }
                ],
                hi: [
                    { title: "🚨 प्री-एक्लेम्पसिया आपातकाल (हिंदी)", class: "btn-outline-danger", text: "मरीज आईडी PAT-4102, 32 हफ्ते की गर्भवती, बीपी 150/95, तेज सिरदर्द, धुंधला दिखना और चेहरे पर सूजन है.", district: "Pune" },
                    { title: "⚠️ तेज बुखार / मलेरिया (हिंदी)", class: "btn-outline-warning text-dark", text: "मरीज आईडी PAT-3301, तेज बुखार, ठंड लगना, उल्टी और चक्कर आना.", district: "Gadchiroli" },
                    { title: "✅ सामान्य जांच (हिंदी)", class: "btn-outline-success", text: "मरीज आईडी PAT-1050, सामान्य गर्भावस्था जांच, बीपी 118/78, सब सामान्य है.", district: "Nashik" }
                ]
            };

            let currentLangCode = "en";

            function switchPresetLang(lang) {
                currentLangCode = lang;
                const selectElem = document.getElementById('voiceLang');
                if (lang === 'en') {
                    selectElem.value = 'en-US';
                    document.getElementById('btnTabEn').className = 'btn btn-sm btn-primary fw-bold';
                    document.getElementById('btnTabMr').className = 'btn btn-sm btn-outline-danger';
                    document.getElementById('btnTabHi').className = 'btn btn-sm btn-outline-warning text-dark';
                } else if (lang === 'mr') {
                    selectElem.value = 'mr-IN';
                    document.getElementById('btnTabEn').className = 'btn btn-sm btn-outline-primary';
                    document.getElementById('btnTabMr').className = 'btn btn-sm btn-danger fw-bold';
                    document.getElementById('btnTabHi').className = 'btn btn-sm btn-outline-warning text-dark';
                } else if (lang === 'hi') {
                    selectElem.value = 'hi-IN';
                    document.getElementById('btnTabEn').className = 'btn btn-sm btn-outline-primary';
                    document.getElementById('btnTabMr').className = 'btn btn-sm btn-outline-danger';
                    document.getElementById('btnTabHi').className = 'btn btn-sm btn-warning fw-bold text-dark';
                }

                renderPresets();
                const first = PRESETS[lang][0];
                document.getElementById('voiceText').value = first.text;
                document.getElementById('districtSelect').value = first.district;
            }

            function syncVoiceLanguage() {
                const val = document.getElementById('voiceLang').value;
                if (val.startsWith('en')) switchPresetLang('en');
                else if (val.startsWith('mr')) switchPresetLang('mr');
                else if (val.startsWith('hi')) switchPresetLang('hi');
            }

            function renderPresets() {
                const container = document.getElementById('presetsContainer');
                container.innerHTML = '';
                const items = PRESETS[currentLangCode] || PRESETS.en;
                items.forEach((item) => {
                    const btn = document.createElement('button');
                    btn.className = `btn btn-sm ${item.class}`;
                    btn.innerText = item.title;
                    btn.onclick = () => {
                        document.getElementById('voiceText').value = item.text;
                        document.getElementById('districtSelect').value = item.district;
                        runVoiceIntake();
                    };
                    container.appendChild(btn);
                });
            }

            function setPreset(type) {
                if (type.endsWith('_en')) switchPresetLang('en');
                else if (type.endsWith('_hi')) switchPresetLang('hi');
                else switchPresetLang('mr');
                runVoiceIntake();
            }

            async function runVoiceIntake() {
                const text = document.getElementById('voiceText').value;
                const district = document.getElementById('districtSelect').value;
                const phone = document.getElementById('phoneInput').value;
                const voiceLangVal = document.getElementById('voiceLang').value;
                const langCode = voiceLangVal.startsWith('en') ? 'en' : (voiceLangVal.startsWith('hi') ? 'hi' : 'mr');
                
                const res = await fetch('/voice-intake', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({voice_transcript: text, district: district, phone: phone, language: langCode})
                });
                const data = await res.json();
                
                document.getElementById('triageResult').classList.remove('d-none');
                document.getElementById('triageSummary').innerHTML = `
                    <strong>Patient:</strong> ${data.patient_id} | 
                    <strong>Language:</strong> <span class="badge bg-secondary">${data.detected_language ? data.detected_language.toUpperCase() : 'AUTO'}</span> |
                    <strong>Triage:</strong> <span class="badge ${data.triage_level === 'HIGH' ? 'badge-high' : 'badge-low'}">${data.triage_level}</span><br>
                    <strong>Clinical Assessment:</strong> ${data.triage_rationale}<br>
                    ${data.referral_details ? `<strong>Referral ID:</strong> <span class="badge bg-primary">${data.referral_details.referral_id}</span> | <strong>QR Token:</strong> <code>${data.referral_details.qr_token}</code><br><strong>Hospital:</strong> ${data.referral_details.hospital_name}` : ''}
                `;
                
                // Show QR code if generated
                if (data.referral_details && data.referral_details.qr_image_base64) {
                    document.getElementById('qrContainer').classList.remove('d-none');
                    document.getElementById('qrImageElement').src = 'data:image/png;base64,' + data.referral_details.qr_image_base64;
                    document.getElementById('qrTokenDisplay').innerText = data.referral_details.qr_token;
                    document.getElementById('referralIdInput').value = data.referral_details.referral_id;
                } else {
                    document.getElementById('qrContainer').classList.add('d-none');
                }

                document.getElementById('triageJson').innerText = JSON.stringify(data, null, 2);
                lastMarathiResponse = data.vernacular_message || data.triage_rationale;
            }

            function speakAloudOutput() {
                if (!window.speechSynthesis) {
                    alert('Text to speech is not supported in this browser.');
                    return;
                }
                if (!lastMarathiResponse) {
                    alert('Please run a voice intake first.');
                    return;
                }
                const utterance = new SpeechSynthesisUtterance(lastMarathiResponse);
                const voiceLangVal = document.getElementById('voiceLang').value;
                utterance.lang = voiceLangVal || 'en-US';
                window.speechSynthesis.speak(utterance);
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

            window.onload = function() {
                renderPresets();
                fetchEpidemicAlerts();
            };
        </script>
    </body>
    </html>
    """