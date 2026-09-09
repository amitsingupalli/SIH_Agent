"""
ASHA Voice Copilot Agent Node.
Handles vernacular Marathi/Hindi voice input, clinical entity extraction,
HL7 FHIR bundle generation via FastMCP log_vitals, and clinical triage decisioning.
"""

import json
from typing import Dict, Any, Literal
from maha_arogya.agents.state import AgentState
from maha_arogya.services.voice_nlp import voice_nlp_service
from maha_arogya.mcp.server import log_vitals
from maha_arogya.core.audit import audit_logger, ActionType
from maha_arogya.agents.surveillance_agent import record_syndromic_case


def evaluate_clinical_triage(
    systolic: int | None,
    diastolic: int | None,
    gestation: int,
    symptoms: list[str],
    has_red_flag: bool
) -> tuple[Literal["LOW", "MED", "HIGH"], str, str]:
    """
    Evaluates clinical triage according to MoHFW National Health Mission & IPHS guidelines.
    Returns: (triage_level, rationale, recommended_specialty)
    """
    symptoms_text = " ".join(symptoms).lower()
    
    # 1. HIGH Triage (Obstetric Emergency / Preeclampsia / Severe Hypertensive Crisis)
    if gestation >= 20:
        if (systolic and systolic >= 140) or (diastolic and diastolic >= 90):
            if any(k in symptoms_text for k in ["headache", "vision", "blur", "dizziness", "edema", "सूज"]):
                return (
                    "HIGH",
                    f"CRITICAL RED FLAG: Gestational age {gestation}w with severe hypertension ({systolic}/{diastolic} mmHg) "
                    f"and neurological/visual symptoms indicative of impending Pre-eclampsia / Eclampsia. "
                    f"Requires urgent referral to Sub-District or Tertiary Civil Hospital with CEmONC.",
                    "Obstetrics & Gynecology"
                )
            return (
                "HIGH",
                f"HIGH RISK: Gestational Hypertension at {gestation}w ({systolic}/{diastolic} mmHg). "
                f"Immediate specialist consultation required.",
                "Obstetrics & Gynecology"
            )
            
    if has_red_flag or any(k in symptoms_text for k in ["bleeding", "severe", "dyspnea", "breathlessness"]):
        return (
            "HIGH",
            f"CRITICAL: Acute obstetric red flags detected ({', '.join(symptoms)}). Immediate emergency transfer required.",
            "Obstetrics & Gynecology"
        )
        
    if systolic and (systolic >= 160 or (diastolic and diastolic >= 100)):
        return (
            "HIGH",
            f"HIGH RISK: Stage 2 Hypertensive Crisis ({systolic}/{diastolic} mmHg). Emergency stabilization needed.",
            "Cardiology / Emergency Medicine"
        )

    # 2. MED Triage (Moderate condition, needs PHC Medical Officer Teleconsultation)
    if (systolic and (130 <= systolic < 140)) or (diastolic and (85 <= diastolic < 90)):
        return (
            "MED",
            f"MODERATE RISK: Pre-hypertension vitals ({systolic}/{diastolic} mmHg). Scheduled for PHC Medical Officer teleconsultation.",
            "General Medicine"
        )
        
    if gestation > 0 and any(k in symptoms_text for k in ["vomiting", "nausea", "fever", "pain"]):
        return (
            "MED",
            f"MODERATE RISK: Antenatal mother with symptomatic distress ({', '.join(symptoms)}). Local PHC checkup recommended.",
            "Obstetrics & Gynecology"
        )

    # 3. LOW Triage (Normal vitals, routine home advisory)
    return (
        "LOW",
        "LOW RISK: Stable vitals within normal physiological limits. Continue routine antenatal care and nutritional iron/folic acid supplementation.",
        "General Preventive Medicine"
    )


def asha_voice_copilot_node(state: AgentState) -> Dict[str, Any]:
    """
    LangGraph Node: ASHA Voice Copilot
    Flow: Transcribe vernacular speech -> Extract clinical entities -> Log FHIR bundle -> Clinical Triage
    """
    raw_input = state.get("raw_input", "")
    lang = state.get("detected_language", "mr")
    
    # 1. Transcribe audio / vernacular speech
    transcript = voice_nlp_service.transcribe_audio(raw_input, language=lang)
    
    # 2. Extract clinical entities
    extracted = voice_nlp_service.extract_clinical_entities(transcript)
    
    patient_id = state.get("patient_id")
    if not patient_id or patient_id == "PAT-UNKNOWN":
        patient_id = extracted.patient_id if extracted.patient_id != "PAT-UNKNOWN" else "PAT-4102"
        
    phone = state.get("phone", "+91-9822114477")
    district = state.get("district", "Pune")
    phc_id = state.get("phc_id", "PHC-PUN-KND")
    
    bp_str = f"{extracted.bp_systolic or 120}/{extracted.bp_diastolic or 80}"
    symptoms_str = ", ".join(extracted.standardized_symptoms) if extracted.standardized_symptoms else "General Health Checkup"
    
    # 3. Log vitals to HL7 FHIR via FastMCP tool
    fhir_bundle_json = log_vitals(
        patient_id=patient_id,
        bp=bp_str,
        gestation=extracted.gestation_weeks,
        symptoms=symptoms_str
    )
    fhir_bundle = json.loads(fhir_bundle_json)
    
    # 4. Clinical Triage Evaluation
    triage_level, rationale, specialty = evaluate_clinical_triage(
        systolic=extracted.bp_systolic,
        diastolic=extracted.bp_diastolic,
        gestation=extracted.gestation_weeks,
        symptoms=extracted.standardized_symptoms,
        has_red_flag=extracted.has_obstetric_red_flag
    )
    
    requires_referral = (triage_level == "HIGH")
    hitl_pending = (triage_level == "HIGH")

    # 5. Cross-Agent Linkage: Stream clinical symptoms to Surveillance Watchdog
    if extracted.standardized_symptoms:
        for sym in extracted.standardized_symptoms:
            record_syndromic_case(
                phc_id=phc_id,
                district=district,
                taluka="Block-1",
                syndrome=sym,
                patient_id=patient_id
            )
    elif triage_level == "HIGH":
        record_syndromic_case(
            phc_id=phc_id,
            district=district,
            taluka="Block-1",
            syndrome="Maternal Gestational Hypertension / Preeclampsia",
            patient_id=patient_id
        )

    # 6. Immutable Clinical Audit Log
    audit_logger.log(
        action=ActionType.VOICE_INTAKE_LOGGED,
        actor_id=state.get("auth_user_id", "ASHA-VOICE-AGENT"),
        actor_role=state.get("auth_role", "ASHA_WORKER"),
        resource_id=patient_id,
        decision=triage_level,
        clinical_rationale=rationale,
        metadata={
            "bp": bp_str,
            "gestation": extracted.gestation_weeks,
            "requires_referral": requires_referral,
            "specialty": specialty,
            "district": district,
            "phc_id": phc_id
        }
    )
    
    message_entry = {
        "role": "assistant",
        "name": "ASHA_Voice_Copilot",
        "content": (
            f"Transcribed Input: {transcript}\n"
            f"Patient: {patient_id} | BP: {bp_str} | Gestation: {extracted.gestation_weeks}w\n"
            f"Triage Outcome: [{triage_level}] - {rationale}\n"
            f"Specialty Required: {specialty}\n"
            f"Referral Required: {requires_referral} (HITL Medical Officer Guardrail: {hitl_pending})"
        )
    }
    
    return {
        "patient_id": patient_id,
        "phone": phone,
        "district": district,
        "phc_id": phc_id,
        "raw_input": raw_input,
        "detected_language": extracted.language_detected,
        "extracted_entities": extracted.model_dump(),
        "fhir_bundle": fhir_bundle,
        "triage_level": triage_level,
        "triage_rationale": rationale,
        "red_flag_detected": extracted.has_obstetric_red_flag,
        "specialty_needed": specialty,
        "requires_referral": requires_referral,
        "hitl_pending": hitl_pending,
        "current_stage": "TRIAGE_COMPLETED",
        "messages": [message_entry]
    }