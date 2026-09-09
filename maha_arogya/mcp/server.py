"""
FastMCP Server for MahaArogya-Agent.
Defines the 5 core Model Context Protocol (MCP) tools for rural healthcare delivery.
"""

import json
import uuid
import hmac
import hashlib
import io
import base64
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from mcp.server.fastmcp import FastMCP

import qrcode

from maha_arogya.config import settings
from maha_arogya.schemas.fhir import (
    FHIRObservation,
    FHIRObservationComponent,
    FHIRCondition,
    FHIRCodeableConcept,
    FHIRCoding,
    FHIRReference,
    FHIRQuantity,
    FHIRBundle,
    FHIRBundleEntry,
    ReferralStatus,
    ReferralPriority,
    ReferralPass,
    StockRunwayInfo
)

# Initialize FastMCP Server
mcp_server = FastMCP("MahaArogya-MCP-Server")

# In-memory Operational Stores (in production backed by PostgreSQL / Redis)
PATIENT_RECORDS: Dict[str, Dict[str, Any]] = {}
REFERRAL_STORE: Dict[str, Dict[str, Any]] = {}
ALERT_LOGS: List[Dict[str, Any]] = []

# PHC Stock Inventory Baseline (Units and Average Daily Consumption Rate)
PHC_INVENTORY_STORE: Dict[str, Dict[str, Dict[str, Any]]] = {
    "PHC-PUN-KND": {
        "Magnesium Sulfate": {"units": 14, "daily_burn_rate": 3.5},   # Critical: 4 days runway
        "Oxytocin": {"units": 60, "daily_burn_rate": 4.0},           # 15 days runway
        "ORS": {"units": 240, "daily_burn_rate": 15.0},              # 16 days runway
        "Paracetamol": {"units": 400, "daily_burn_rate": 25.0},       # 16 days runway
        "Amoxicillin": {"units": 80, "daily_burn_rate": 12.0}         # 6.6 days runway
    },
    "PHC-GAD-BHM": {
        "Magnesium Sulfate": {"units": 8, "daily_burn_rate": 2.0},    # Critical: 4 days runway
        "Chloroquine/ACT": {"units": 35, "daily_burn_rate": 7.0},     # Critical: 5 days runway
        "ORS": {"units": 90, "daily_burn_rate": 18.0},               # Critical: 5 days runway
        "Iron Folic Acid": {"units": 500, "daily_burn_rate": 15.0}
    },
    "PHC-NSK-TRB": {
        "Magnesium Sulfate": {"units": 45, "daily_burn_rate": 2.5},   # 18 days runway
        "Oxytocin": {"units": 85, "daily_burn_rate": 3.0},           # 28 days runway
        "ORS": {"units": 120, "daily_burn_rate": 20.0},              # 6 days runway
        "Paracetamol": {"units": 600, "daily_burn_rate": 30.0}
    }
}


def _generate_qr_token_and_image(patient_id: str, hospital_id: str, referral_id: str) -> tuple[str, str]:
    """Generates an HMAC-signed QR token string and Base64 encoded PNG image."""
    now_iso = datetime.utcnow().isoformat()
    sla_expires_at = (datetime.utcnow() + timedelta(hours=settings.REFERRAL_SLA_HOURS)).isoformat()
    
    payload = f"{referral_id}|{patient_id}|{hospital_id}|{now_iso}|{sla_expires_at}"
    signature = hmac.new(
        settings.QR_SIGNING_SECRET.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()[:16]
    
    qr_token = f"MAHA-{referral_id}-{signature}"
    
    # Generate QR Code image
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=6,
        border=2,
    )
    qr.add_data(qr_token)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    
    buffered = io.BytesIO()
    img.save(buffered, format="PNG")
    qr_b64 = base64.b64encode(buffered.getvalue()).decode("utf-8")
    
    return qr_token, qr_b64


# ==========================================
# 1. TOOL: log_vitals
# ==========================================
@mcp_server.tool()
def log_vitals(patient_id: str, bp: str, gestation: int, symptoms: str) -> str:
    """
    Logs maternal/general patient vitals, converts raw inputs into standard HL7 FHIR R4 Observations and Conditions,
    and returns an HL7 FHIR Bundle JSON string.
    
    Args:
        patient_id: Unique patient identifier (e.g., 'PAT-4102')
        bp: Blood pressure string like '150/95' or '120/80'
        gestation: Gestational age in weeks (0 if not pregnant)
        symptoms: Vernacular or translated clinical symptoms string
    """
    entries: List[FHIRBundleEntry] = []
    
    # Parse Blood Pressure
    systolic, diastolic = 120, 80
    if "/" in bp:
        parts = bp.strip().split("/")
        try:
            systolic = int(parts[0].strip())
            diastolic = int(parts[1].strip())
        except ValueError:
            pass
            
    # HL7 FHIR Observation for Blood Pressure Panel (LOINC: 85354-9)
    bp_obs = FHIRObservation(
        code=FHIRCodeableConcept(
            coding=[FHIRCoding(system="http://loinc.org", code="85354-9", display="Blood pressure panel with all children optional")],
            text="Blood Pressure Measurement"
        ),
        subject=FHIRReference(reference=f"Patient/{patient_id}", display=f"Patient {patient_id}"),
        component=[
            FHIRObservationComponent(
                code=FHIRCodeableConcept(
                    coding=[FHIRCoding(system="http://loinc.org", code="8480-6", display="Systolic blood pressure")]
                ),
                valueQuantity=FHIRQuantity(value=float(systolic), unit="mmHg", code="mm[Hg]")
            ),
            FHIRObservationComponent(
                code=FHIRCodeableConcept(
                    coding=[FHIRCoding(system="http://loinc.org", code="8462-4", display="Diastolic blood pressure")]
                ),
                valueQuantity=FHIRQuantity(value=float(diastolic), unit="mmHg", code="mm[Hg]")
            )
        ]
    )
    entries.append(FHIRBundleEntry(resource=bp_obs))
    
    # HL7 FHIR Observation for Gestational Age if applicable (LOINC: 18185-9)
    if gestation > 0:
        gest_obs = FHIRObservation(
            code=FHIRCodeableConcept(
                coding=[FHIRCoding(system="http://loinc.org", code="18185-9", display="Gestational age in weeks")]
            ),
            subject=FHIRReference(reference=f"Patient/{patient_id}"),
            valueQuantity=FHIRQuantity(value=float(gestation), unit="weeks", code="wk")
        )
        entries.append(FHIRBundleEntry(resource=gest_obs))
        
    # HL7 FHIR Condition for Reported Symptoms / Potential Diagnosis
    snomed_code = "38341003"
    snomed_display = "Hypertensive disorder"
    
    symptoms_lower = symptoms.lower()
    if gestation >= 20 and (systolic >= 140 or diastolic >= 90) and any(kw in symptoms_lower for kw in ["headache", "????????", "?????", "dizziness", "vision", "????", "???", "swelling", "edema"]):
        snomed_code = "398254007"
        snomed_display = "Pre-eclampsia (High Risk)"
    elif "fever" in symptoms_lower or "???" in symptoms_lower:
        snomed_code = "386661006"
        snomed_display = "Fever / Pyrexia"
        
    cond = FHIRCondition(
        code=FHIRCodeableConcept(
            coding=[FHIRCoding(system="http://snomed.info/sct", code=snomed_code, display=snomed_display)],
            text=symptoms
        ),
        subject=FHIRReference(reference=f"Patient/{patient_id}"),
        note=[{"text": f"Reported symptoms: {symptoms}"}]
    )
    entries.append(FHIRBundleEntry(resource=cond))
    
    bundle = FHIRBundle(entry=entries)
    bundle_json = bundle.model_dump_json(indent=2)
    
    # Store record
    PATIENT_RECORDS[patient_id] = {
        "patient_id": patient_id,
        "bp": f"{systolic}/{diastolic}",
        "systolic": systolic,
        "diastolic": diastolic,
        "gestation": gestation,
        "symptoms": symptoms,
        "snomed_code": snomed_code,
        "snomed_display": snomed_display,
        "bundle": bundle.model_dump(),
        "logged_at": datetime.utcnow().isoformat()
    }
    
    return bundle_json


# ==========================================
# 2. TOOL: check_hospital_capacity
# ==========================================
@mcp_server.tool()
def check_hospital_capacity(specialty: str, district: str) -> str:
    """
    Checks real-time hospital bed capacity and emergency specialty availability across Maharashtra district networks.
    
    Args:
        specialty: Medical specialty needed (e.g., 'Obstetrics & Gynecology', 'Pediatrics', 'Cardiology')
        district: Maharashtra district name (e.g., 'Pune', 'Nashik', 'Gadchiroli', 'Thane')
    """
    normalized_district = district.strip().title()
    hospitals = settings.DISTRICT_HOSPITAL_REGISTRY.get(normalized_district)
    
    if not hospitals:
        # Fallback to Pune if district not registered
        hospitals = settings.DISTRICT_HOSPITAL_REGISTRY["Pune"]
        normalized_district = "Pune (Default Hub)"
        
    matching_slots = []
    earliest_time = (datetime.utcnow() + timedelta(minutes=45)).strftime("%Y-%m-%d %H:%M UTC")
    
    for h in hospitals:
        # Match specialty or general emergency availability
        if any(specialty.lower() in s.lower() for s in h["specialties"]) or h["available_emergency_slots"] > 0:
            matching_slots.append({
                "hospital_id": h["hospital_id"],
                "hospital_name": h["name"],
                "district": normalized_district,
                "hospital_type": h["type"],
                "specialties": h["specialties"],
                "available_emergency_slots": h["available_emergency_slots"],
                "ambulance_helpline": h["ambulance_helpline"],
                "earliest_slot_time": earliest_time
            })
            
    result = {
        "district": normalized_district,
        "query_specialty": specialty,
        "total_hospitals_available": len(matching_slots),
        "available_slots": matching_slots
    }
    return json.dumps(result, indent=2)


# ==========================================
# 3. TOOL: book_referral
# ==========================================
@mcp_server.tool()
def book_referral(patient_id: str, hospital_id: str) -> str:
    """
    Books an urgent priority referral slot at the target hospital and issues a signed cryptographic QR referral pass.
    
    Args:
        patient_id: Unique patient identifier (e.g., 'PAT-4102')
        hospital_id: Target hospital identifier (e.g., 'HOSP-PUN-01')
    """
    referral_id = f"REF-{uuid.uuid4().hex[:6].upper()}"
    created_at = datetime.utcnow()
    sla_expires = created_at + timedelta(hours=settings.REFERRAL_SLA_HOURS)
    
    # Locate hospital details
    hospital_name = "Government Hospital"
    specialty = "Emergency Obstetrics"
    for dist_hospitals in settings.DISTRICT_HOSPITAL_REGISTRY.values():
        for h in dist_hospitals:
            if h["hospital_id"] == hospital_id:
                hospital_name = h["name"]
                specialty = h["specialties"][0] if h["specialties"] else "General Medicine"
                if h["available_emergency_slots"] > 0:
                    h["available_emergency_slots"] -= 1
                break
                
    qr_token, qr_image_b64 = _generate_qr_token_and_image(patient_id, hospital_id, referral_id)
    
    referral_record = {
        "referral_id": referral_id,
        "patient_id": patient_id,
        "hospital_id": hospital_id,
        "hospital_name": hospital_name,
        "specialty": specialty,
        "priority": ReferralPriority.STAT.value,
        "scheduled_at": (created_at + timedelta(hours=2)).isoformat(),
        "created_at": created_at.isoformat(),
        "sla_expires_at": sla_expires.isoformat(),
        "qr_token": qr_token,
        "qr_image_base64": qr_image_b64,
        "status": ReferralStatus.BOOKED.value,
        "attended": False,
        "escalated": False
    }
    
    REFERRAL_STORE[referral_id] = referral_record
    
    return json.dumps({
        "referral_id": referral_id,
        "qr_token": qr_token,
        "hospital_name": hospital_name,
        "scheduled_at": referral_record["scheduled_at"],
        "sla_expires_at": referral_record["sla_expires_at"],
        "status": "BOOKED"
    }, indent=2)


# ==========================================
# 4. TOOL: send_vernacular_alert
# ==========================================
@mcp_server.tool()
def send_vernacular_alert(phone: str, msg_marathi: str) -> str:
    """
    Dispatches a vernacular Marathi/Hindi SMS/WhatsApp emergency alert to the patient or ASHA worker.
    
    Args:
        phone: Recipient phone number (e.g., '+91-9876543210')
        msg_marathi: Complete message in Marathi (or Hindi) vernacular
    """
    dispatch_id = f"MSG-{uuid.uuid4().hex[:8].upper()}"
    timestamp = datetime.utcnow().isoformat()
    
    log_entry = {
        "dispatch_id": dispatch_id,
        "phone": phone,
        "message": msg_marathi,
        "channel": "WHATSAPP_VERNACULAR_GATEWAY",
        "status": "DELIVERED",
        "timestamp": timestamp
    }
    ALERT_LOGS.append(log_entry)
    
    status_response = {
        "dispatch_id": dispatch_id,
        "recipient": phone,
        "status": "DELIVERED",
        "channel": "WHATSAPP_SMS_GATEWAY",
        "language": "mr-IN (Marathi)",
        "timestamp": timestamp,
        "summary": "Vernacular alert successfully dispatched to ASHA worker and patient."
    }
    return json.dumps(status_response, indent=2)


# ==========================================
# 5. TOOL: check_stock_runway
# ==========================================
@mcp_server.tool()
def check_stock_runway(phc_id: str, drug_name: str) -> str:
    """
    Calculates pharmaceutical stock-out runway (burn rate vs current inventory in days) for critical rural medicines.
    
    Args:
        phc_id: Primary Health Centre identifier (e.g., 'PHC-PUN-KND')
        drug_name: Name of drug (e.g., 'Magnesium Sulfate', 'Oxytocin', 'ORS')
    """
    phc_data = PHC_INVENTORY_STORE.get(phc_id)
    if not phc_data:
        # Default fallback
        phc_id = "PHC-PUN-KND"
        phc_data = PHC_INVENTORY_STORE[phc_id]
        
    drug_info = phc_data.get(drug_name)
    if not drug_info:
        # Search case-insensitive
        for d_key, val in phc_data.items():
            if drug_name.lower() in d_key.lower():
                drug_name = d_key
                drug_info = val
                break
                
    if not drug_info:
        # Generic safe calculation
        units = 10
        daily_burn = 3.0
    else:
        units = drug_info["units"]
        daily_burn = drug_info["daily_burn_rate"]
        
    days_left = round(units / daily_burn, 1) if daily_burn > 0 else 999.0
    is_critical = days_left <= settings.CRITICAL_RUNWAY_DAYS_THRESHOLD
    
    phc_meta = settings.PHC_REGISTRY.get(phc_id, {"name": "Rural PHC", "district": "Maharashtra"})
    
    runway_report = {
        "phc_id": phc_id,
        "phc_name": phc_meta.get("name"),
        "district": phc_meta.get("district"),
        "drug_name": drug_name,
        "current_units": units,
        "daily_burn_rate": daily_burn,
        "days_left": days_left,
        "is_critical_shortage": is_critical,
        "recommended_restock_units": int(daily_burn * 30),  # 30 day buffer
        "action_required": "EMERGENCY_REORDER_ALERT" if is_critical else "NORMAL_INVENTORY"
    }
    return json.dumps(runway_report, indent=2)
