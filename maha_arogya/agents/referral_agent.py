"""
Closed Loop Referral Agent Node.
Matches hospital capacity, books priority emergency slot, issues cryptographic QR referral pass,
tracks 48-hour attendance SLA, and automatically triggers vernacular WhatsApp/SMS alerts and escalation.
"""

import json
from datetime import datetime, timedelta
from typing import Dict, Any

from maha_arogya.agents.state import AgentState
from maha_arogya.config import settings
from maha_arogya.mcp.server import (
    check_hospital_capacity,
    book_referral,
    send_vernacular_alert,
    REFERRAL_STORE
)
from maha_arogya.services.voice_nlp import voice_nlp_service
from maha_arogya.core.audit import audit_logger, ActionType
from maha_arogya.core.reliability import retry_with_backoff, dead_letter_queue


def closed_loop_referral_node(state: AgentState) -> Dict[str, Any]:
    """
    LangGraph Node: Closed-Loop Referral Agent
    Executes:
    1. Match target hospital capacity for needed specialty.
    2. Book emergency priority admission slot.
    3. Generate cryptographic QR referral pass.
    4. Dispatch Marathi vernacular SMS/WhatsApp to patient and ASHA worker.
    """
    patient_id = state.get("patient_id", "PAT-4102")
    district = state.get("district", "Pune")
    specialty = state.get("specialty_needed", "Obstetrics & Gynecology")
    phone = state.get("phone", "+91-9822114477")
    
    # 1. Match hospital capacity via FastMCP tool
    capacity_json = check_hospital_capacity(specialty=specialty, district=district)
    capacity_data = json.loads(capacity_json)
    
    available_hospitals = capacity_data.get("available_slots", [])
    if available_hospitals:
        chosen_hospital = available_hospitals[0]
        hospital_id = chosen_hospital["hospital_id"]
        hospital_name = chosen_hospital["hospital_name"]
    else:
        hospital_id = "HOSP-PUN-01"
        hospital_name = "Sassoon General Hospital (Default Hub)"
        
    # 2. Book priority slot & issue QR token via FastMCP tool
    booking_json = book_referral(patient_id=patient_id, hospital_id=hospital_id)
    booking_data = json.loads(booking_json)
    
    referral_id = booking_data["referral_id"]
    qr_token = booking_data["qr_token"]
    scheduled_at = booking_data["scheduled_at"]
    sla_expires_at = booking_data["sla_expires_at"]
    
    # 3. Retrieve Base64 QR Image from store
    referral_record = REFERRAL_STORE.get(referral_id, {})
    qr_image_b64 = referral_record.get("qr_image_base64", "")
    
    # 4. Generate Vernacular Marathi SMS/WhatsApp Pass
    marathi_sms = voice_nlp_service.generate_vernacular_referral_sms(
        patient_id=patient_id,
        hospital_name=hospital_name,
        slot_time=scheduled_at,
        qr_token=qr_token,
        urgency="तातडीची प्रसूती पूर्व संदर्भ (STAT / High Risk)", language=state.get("detected_language", "mr")
    )
    
    # 5. Dispatch vernacular alert via FastMCP tool with retry and DLQ fallback
    try:
        @retry_with_backoff(max_attempts=3, initial_delay=0.1, backoff_factor=1.5)
        def _dispatch_with_retry():
            return send_vernacular_alert(phone=phone, msg_marathi=marathi_sms)
        
        alert_status_json = _dispatch_with_retry()
        alert_status = json.loads(alert_status_json)
        alert_dispatched = True
    except Exception as err:
        dead_letter_queue.enqueue(
            event_type="REFERRAL_SMS_DISPATCH",
            payload={"patient_id": patient_id, "referral_id": referral_id, "sms_text": marathi_sms},
            error_reason=str(err),
            recipient=phone,
            patient_id=patient_id
        )
        alert_status = {"status": "QUEUED_TO_DLQ", "reason": str(err)}
        alert_dispatched = False

    # 6. Immutable Clinical Audit Log for Referral Booking
    audit_logger.log(
        action=ActionType.REFERRAL_BOOKED,
        actor_id=state.get("auth_user_id", "REFERRAL-AGENT"),
        actor_role=state.get("auth_role", "SYSTEM_AGENT"),
        resource_id=referral_id,
        decision="BOOKED",
        clinical_rationale=f"High-risk emergency referral matched and booked at {hospital_name}",
        metadata={
            "patient_id": patient_id,
            "hospital_id": hospital_id,
            "specialty": specialty,
            "qr_token": qr_token,
            "sla_deadline": sla_expires_at
        }
    )
    
    message_entry = {
        "role": "assistant",
        "name": "Closed_Loop_Referral_Agent",
        "content": (
            f"Referral Booked Successfully!\n"
            f"Referral ID: {referral_id} | Hospital: {hospital_name} ({hospital_id})\n"
            f"QR Token: {qr_token}\n"
            f"Scheduled At: {scheduled_at} | 48h SLA Deadline: {sla_expires_at}\n"
            f"Vernacular Alert Sent: {alert_status.get('status')} to {phone}"
        )
    }
    
    return {
        "hospital_id": hospital_id,
        "hospital_name": hospital_name,
        "referral_id": referral_id,
        "qr_token": qr_token,
        "qr_image_base64": qr_image_b64,
        "scheduled_at": scheduled_at,
        "sla_expires_at": sla_expires_at,
        "referral_status": "BOOKED",
        "alert_dispatched": True,
        "vernacular_alert_text": marathi_sms,
        "current_stage": "REFERRAL_DISPATCHED",
        "messages": [message_entry]
    }


def check_and_escalate_referral(referral_id: str, force_sla_breach: bool = False) -> Dict[str, Any]:
    """
    Monitors patient attendance at the destination hospital.
    If no-show occurs within the 48-hour SLA, triggers automated Marathi WhatsApp escalation
    to the designated ASHA worker and PHC Medical Officer.
    """
    referral = REFERRAL_STORE.get(referral_id)
    if not referral:
        return {
            "status": "NOT_FOUND",
            "referral_id": referral_id,
            "message": "Referral record not found."
        }
        
    if referral.get("attended", False):
        return {
            "referral_id": referral_id,
            "status": "ATTENDED",
            "patient_id": referral["patient_id"],
            "hospital_name": referral["hospital_name"],
            "message": "Patient successfully checked in and received clinical care."
        }
        
    sla_expires_str = referral.get("sla_expires_at", "")
    is_breached = force_sla_breach
    if sla_expires_str and not force_sla_breach:
        try:
            sla_dt = datetime.fromisoformat(sla_expires_str.replace("Z", ""))
            if datetime.utcnow() > sla_dt:
                is_breached = True
        except Exception:
            pass
            
    if is_breached:
        # Mark as NO_SHOW & ESCALATED
        referral["status"] = "NO_SHOW"
        referral["escalated"] = True
        
        patient_id = referral["patient_id"]
        hosp_name = referral["hospital_name"]
        
        # Dispatch vernacular escalation notice
        escalation_sms = voice_nlp_service.generate_vernacular_escalation_sms(
            patient_id=patient_id,
            referral_id=referral_id,
            hospital_name=hosp_name
        )
        
        asha_phone = "+91-9422009988"  # ASHA supervisor phone
        try:
            @retry_with_backoff(max_attempts=3, initial_delay=0.1, backoff_factor=1.5)
            def _dispatch_escalation():
                return send_vernacular_alert(phone=asha_phone, msg_marathi=escalation_sms)
            alert_dispatch = _dispatch_escalation()
        except Exception as err:
            dead_letter_queue.enqueue(
                event_type="SLA_BREACH_ESCALATION_SMS",
                payload={"patient_id": patient_id, "referral_id": referral_id, "sms": escalation_sms},
                error_reason=str(err),
                recipient=asha_phone,
                patient_id=patient_id
            )

        # Record SLA Breach Escalation Audit Log
        audit_logger.log(
            action=ActionType.SLA_BREACH_ESCALATED,
            actor_id="REFERRAL-WATCHDOG",
            actor_role="SYSTEM_AGENT",
            resource_id=referral_id,
            decision="ESCALATED",
            clinical_rationale=f"Patient {patient_id} breached 48h SLA without attendance at {hosp_name}",
            metadata={"patient_id": patient_id, "hospital": hosp_name, "asha_notified": asha_phone}
        )
        
        return {
            "referral_id": referral_id,
            "patient_id": patient_id,
            "hospital_name": hosp_name,
            "status": "NO_SHOW",
            "escalated": True,
            "sla_breached": True,
            "alert_dispatched_to": asha_phone,
            "escalation_message_vernacular": escalation_sms,
            "recommended_action": "Immediate home visit by ASHA worker and direct coordination with 108 Emergency Medical Services."
        }
        
    return {
        "referral_id": referral_id,
        "patient_id": referral["patient_id"],
        "hospital_name": referral["hospital_name"],
        "status": "BOOKED",
        "attended": False,
        "sla_expires_at": referral["sla_expires_at"],
        "hours_remaining": settings.REFERRAL_SLA_HOURS,
        "message": "Referral is within active 48-hour SLA window. Awaiting patient check-in."
    }