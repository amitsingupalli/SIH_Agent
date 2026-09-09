# 🏥 MahaArogya-Agent (महाआरोग्य)
### Autonomous Multi-Agent Rural Healthcare & Closed-Loop Referral Tracking System
**Smart India Hackathon (SIH) 2026 | Problem Statement 133 | Govt of Maharashtra (Arogya Vibhag)**

[![Python 3.11](https://img.shields.io/badge/Python-3.11-blue.svg)](https://www.python.org/)
[![LangGraph](https://img.shields.io/badge/Orchestration-LangGraph%20StateGraph-orange.svg)](https://langchain-ai.github.io/langgraph/)
[![FastMCP](https://img.shields.io/badge/Tools-Model%20Context%20Protocol%20(FastMCP)-purple.svg)](https://modelcontextprotocol.io/)
[![HL7 FHIR R4](https://img.shields.io/badge/Validation-HL7%20FHIR%20R4%20(Pydantic)-red.svg)](https://hl7.org/fhir/)
[![FastAPI](https://img.shields.io/badge/Backend-FastAPI-teal.svg)](https://fastapi.tiangolo.com/)
[![Tests](https://img.shields.io/badge/Tests-11%20Passed%20(100%25)-brightgreen.svg)]()

---

## 📌 Executive Summary
In rural Maharashtra, maternal mortality and untreated critical emergencies persist due to:
1. Delayed clinical triage and vernacular documentation barriers facing front-line **ASHA workers**.
2. Broken referral chains where high-risk pregnant mothers or acute patients are sent to distant civil hospitals without real-time bed capacity reservation or attendance tracking.
3. Silent syndromic outbreaks (e.g. Malaria in tribal Gadchiroli, Gastroenteritis in Trimbak) and unanticipated PHC stock-outs of life-saving drugs like Magnesium Sulfate.

**MahaArogya-Agent** solves this via an autonomous, multi-agent AI framework equipped with **HL7 FHIR R4 standards**, **Model Context Protocol (FastMCP)**, **LangGraph orchestration with Human-In-The-Loop (HITL)** guardrails, and **vernacular Marathi/Hindi voice NLP**.

---

## 🏛️ System Architecture

```
                    ┌─────────────────────────────────────────┐
                    │  ASHA Worker Spoken Vernacular Audio    │
                    │  (Marathi: "बीपी १५०/९५, तीव्र डोकेदुखी") │
                    └────────────────────┬────────────────────┘
                                         │
                                         ▼
                    ┌─────────────────────────────────────────┐
                    │  Vernacular Voice & NLP Service         │
                    │  (Bhashini / Whisper STT + Normalizer)  │
                    └────────────────────┬────────────────────┘
                                         │
                                         ▼
               ╔═══════════════════════════════════════════════════╗
               ║             LangGraph StateGraph Engine           ║
               ╠═══════════════════════════════════════════════════╣
               ║                                                   ║
               ║  [1. ASHA_Voice_Copilot Node]                     ║
               ║      - FastMCP: log_vitals()                      ║
               ║      - HL7 FHIR Bundle (LOINC & SNOMED CT)        ║
               ║      - Clinical Triage (LOW / MED / HIGH)         ║
               ║                         │                         ║
               ║         ┌───────────────┴───────────────┐         ║
               ║         ▼                               ▼         ║
               ║   [LOW / MED]                        [HIGH]       ║
               ║   Routine Advisory             HITL Guardrail     ║
               ║   (Local PHC Advice)         (MO Clinician Sign)  ║
               ║                                         │         ║
               ║                                         ▼         ║
               ║                        [2. Closed_Loop_Referral]  ║
               ║                            - check_capacity()     ║
               ║                            - book_referral()      ║
               ║                            - QR Token & Pass      ║
               ║                            - send_alert(Marathi)  ║
               ║                                         │         ║
               ║                         ┌───────────────┘         ║
               ║                         ▼                         ║
               ║               [48-Hour SLA Watcher]               ║
               ║               (If no-show, auto-escalate          ║
               ║                to ASHA worker via WhatsApp)       ║
               ║                         │                         ║
               ║                         ▼                         ║
               ║  [3. Surveillance_Watchdog Node]                  ║
               ║      - Spatio-temporal clustering on PHC logs     ║
               ║      - Outbreak detection (Z-score anomaly)       ║
               ║      - FastMCP: check_stock_runway()              ║
               ║      - DHO District Health Officer Briefing       ║
               ╚═══════════════════════════════════════════════════╝
```

---

## 🛠️ The 5 FastMCP Tools

| Tool Signature | Purpose | Standards & Protocols |
|---|---|---|
| `log_vitals(patient_id, bp, gestation, symptoms)` | Structures raw vitals into interoperable HL7 FHIR Observation & Condition Bundles | LOINC: `85354-9`, `18185-9`, SNOMED-CT: `398254007` |
| `check_hospital_capacity(specialty, district)` | Real-time query of district & sub-district emergency hospital bed availability | Maharashtra Civil Hospital Registry |
| `book_referral(patient_id, hospital_id)` | Reserves emergency slot and issues HMAC-SHA256 signed QR referral pass | RFC 2104 HMAC / Base64 QR Image |
| `send_vernacular_alert(phone, msg_marathi)` | Dispatches culturally empathetic vernacular WhatsApp/SMS alerts | Marathi/Hindi Unicode Gateway |
| `check_stock_runway(phc_id, drug_name)` | Calculates inventory burn-rate vs days left and flags critical shortage (< 7d) | NHM Maharashtra Supply Chain Standards |

---

## 🤖 Core Agents & Roles

### 1. `ASHA_Voice_Copilot`
- **Input**: Spoken vernacular Marathi/Hindi symptoms and maternal vitals.
- **Processing**: Transcribes Devanagari numerals (१५०/९५ -> 150/95), maps clinical symptoms to SNOMED CT concepts (`Severe Headache`, `Dizziness`, `Edema`).
- **Triage**: Categorizes into `LOW`, `MED`, or `HIGH` risk (e.g. Gestation $\ge$ 20w + BP $\ge$ 140/90 = Severe Pre-eclampsia).

### 2. `Closed_Loop_Referral_Agent`
- **Matching**: Matches target hospital (e.g., Sassoon General Hospital, Pune; Nashik Civil Hospital; Gadchiroli District Hospital).
- **Booking**: Reserves emergency slot and issues a verifiable QR Referral Token (`MAHA-REF-XXXX-HASH`).
- **48-Hour SLA Guarantee**: Continuously monitors attendance. If no-show after 48h, auto-dispatches an escalation alert to the ASHA worker for an immediate home visit.

### 3. `Surveillance_Watchdog_Agent`
- **Clustering**: Runs spatio-temporal clustering on PHC syndromic logs to detect anomalous spikes (e.g., Malaria in Bhamragad, Gastroenteritis in Trimbak).
- **Stock Runway**: Evaluates critical medicines (Magnesium Sulfate, Oxytocin, ORS, ACT).
- **DHO Briefing**: Compiles an administrative briefing for the District Health Officer (DHO) with containment actions.

---

## 🚀 Quickstart & Setup

### Prerequisites
- Python 3.11+
- Git

### Installation
```bash
# Clone the repository
git clone https://github.com/amitsingupalli/SIH_Agent.git
cd SIH_Agent

# Install dependencies
pip install -r requirements.txt
```

### Run Automated Test Suite (100% Pass)
```bash
python -m pytest tests/test_flow.py -v
```

### Launch the Production FastAPI Application & Interactive Dashboard
```bash
python -m uvicorn maha_arogya.api.main:app --host 127.0.0.1 --port 8000 --reload
```
Open **http://127.0.0.1:8000** in your browser to access the **Interactive Evaluation Dashboard**!

---

## 📡 REST API Documentation

### 1. `POST /voice-intake`
Accepts vernacular spoken transcripts from ASHA workers:
```bash
curl -X POST "http://127.0.0.1:8000/voice-intake" \
  -H "Content-Type: application/json" \
  -d '{
    "voice_transcript": "रुग्ण आयडी PAT-4102, गरोदर ३२ आठवडे, बीपी १५०/९५, तीव्र डोकेदुखी आणि चक्कर येणे",
    "district": "Pune",
    "phone": "+91-9822114477"
  }'
```

### 2. `GET /referral-status/{referral_id}`
Monitors 48h referral SLA and triggers automated escalation:
```bash
curl "http://127.0.0.1:8000/referral-status/REF-8423B5?force_sla_breach=true"
```

### 3. `GET /epidemic-alerts`
Returns real-time spatial-temporal outbreak clusters and medicine stock-out runways:
```bash
curl "http://127.0.0.1:8000/epidemic-alerts"
```

---

## 👥 Contributors & SIH 2026 Team
- **Amit Singupalli** ([@amitsingupalli](https://github.com/amitsingupalli)) - Agentic AI & Systems Engineer
