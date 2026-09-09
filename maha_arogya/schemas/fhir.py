"""
HL7 FHIR R4 Compliant Schemas for MahaArogya-Agent.
Follows standard healthcare interoperability specifications with LOINC and SNOMED-CT codings.
"""

from enum import Enum
from typing import List, Optional, Dict, Any, Union
from datetime import datetime
from pydantic import BaseModel, Field
import uuid


class TriageLevel(str, Enum):
    LOW = "LOW"
    MED = "MED"
    HIGH = "HIGH"


class ReferralPriority(str, Enum):
    ROUTINE = "routine"
    URGENT = "urgent"
    STAT = "stat"  # Immediate emergency


class ReferralStatus(str, Enum):
    PENDING_APPROVAL = "PENDING_APPROVAL"
    BOOKED = "BOOKED"
    ATTENDED = "ATTENDED"
    NO_SHOW = "NO_SHOW"
    ESCALATED = "ESCALATED"


# FHIR Data Types
class FHIRCoding(BaseModel):
    system: str = Field(..., description="Coding system URI (e.g., http://loinc.org or http://snomed.info/sct)")
    code: str = Field(..., description="Standard clinical code")
    display: str = Field(..., description="Human-readable concept name")


class FHIRCodeableConcept(BaseModel):
    coding: List[FHIRCoding] = Field(default_factory=list)
    text: Optional[str] = None


class FHIRQuantity(BaseModel):
    value: float
    unit: str
    system: str = "http://unitsofmeasure.org"
    code: str


class FHIRReference(BaseModel):
    reference: str = Field(..., description="Relative URI like 'Patient/123'")
    display: Optional[str] = None


class FHIRObservationComponent(BaseModel):
    code: FHIRCodeableConcept
    valueQuantity: Optional[FHIRQuantity] = None
    valueString: Optional[str] = None


# FHIR Resources
class FHIRPatient(BaseModel):
    resourceType: str = "Patient"
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    identifier: List[Dict[str, Any]] = Field(default_factory=list)
    active: bool = True
    name: Optional[List[Dict[str, Any]]] = None
    gender: Optional[str] = "female"
    birthDate: Optional[str] = None
    address: Optional[List[Dict[str, Any]]] = None
    telecom: Optional[List[Dict[str, Any]]] = None


class FHIRObservation(BaseModel):
    """HL7 FHIR Observation for Clinical Vitals & Measurements."""
    resourceType: str = "Observation"
    id: str = Field(default_factory=lambda: f"obs-{uuid.uuid4().hex[:8]}")
    status: str = "final"
    category: Optional[List[FHIRCodeableConcept]] = None
    code: FHIRCodeableConcept
    subject: FHIRReference
    effectiveDateTime: str = Field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    valueQuantity: Optional[FHIRQuantity] = None
    valueString: Optional[str] = None
    component: Optional[List[FHIRObservationComponent]] = None
    interpretation: Optional[List[FHIRCodeableConcept]] = None
    note: Optional[List[Dict[str, str]]] = None


class FHIRCondition(BaseModel):
    """HL7 FHIR Condition for Clinical Symptoms & Diagnoses."""
    resourceType: str = "Condition"
    id: str = Field(default_factory=lambda: f"cond-{uuid.uuid4().hex[:8]}")
    clinicalStatus: FHIRCodeableConcept = Field(
        default_factory=lambda: FHIRCodeableConcept(
            coding=[FHIRCoding(system="http://terminology.hl7.org/CodeSystem/condition-clinical", code="active", display="Active")]
        )
    )
    verificationStatus: FHIRCodeableConcept = Field(
        default_factory=lambda: FHIRCodeableConcept(
            coding=[FHIRCoding(system="http://terminology.hl7.org/CodeSystem/condition-ver-status", code="provisional", display="Provisional")]
        )
    )
    category: Optional[List[FHIRCodeableConcept]] = None
    severity: Optional[FHIRCodeableConcept] = None
    code: FHIRCodeableConcept
    subject: FHIRReference
    onsetDateTime: Optional[str] = Field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    recordedDate: Optional[str] = Field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    note: Optional[List[Dict[str, str]]] = None


class FHIRServiceRequest(BaseModel):
    """HL7 FHIR ServiceRequest for Closed-Loop Referral."""
    resourceType: str = "ServiceRequest"
    id: str = Field(default_factory=lambda: f"req-{uuid.uuid4().hex[:8]}")
    status: str = "active"
    intent: str = "order"
    priority: ReferralPriority = ReferralPriority.STAT
    code: FHIRCodeableConcept
    subject: FHIRReference
    requester: Optional[FHIRReference] = None
    performer: Optional[List[FHIRReference]] = None
    reasonCode: Optional[List[FHIRCodeableConcept]] = None
    authoredOn: str = Field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    patientInstruction: Optional[str] = None


class FHIRBundleEntry(BaseModel):
    fullUrl: Optional[str] = None
    resource: Union[FHIRObservation, FHIRCondition, FHIRPatient, FHIRServiceRequest, Dict[str, Any]]


class FHIRBundle(BaseModel):
    """HL7 FHIR Bundle aggregating patient context, vitals, and conditions."""
    resourceType: str = "Bundle"
    id: str = Field(default_factory=lambda: f"bundle-{uuid.uuid4().hex[:8]}")
    type: str = "collection"
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    entry: List[FHIRBundleEntry] = Field(default_factory=list)


# Domain-specific Schemas for Multi-Agent Workflows
class TriageAssessment(BaseModel):
    patient_id: str
    triage_level: TriageLevel
    systolic_bp: Optional[int] = None
    diastolic_bp: Optional[int] = None
    gestation_weeks: Optional[int] = None
    primary_symptoms: List[str] = Field(default_factory=list)
    red_flag_detected: bool = False
    clinical_rationale: str
    requires_emergency_referral: bool = False
    recommended_specialty: str = "Obstetrics & Gynecology"


class HospitalSlot(BaseModel):
    hospital_id: str
    hospital_name: str
    district: str
    specialty: str
    available_emergency_slots: int
    ambulance_contact: str
    earliest_slot_time: str


class ReferralPass(BaseModel):
    referral_id: str
    patient_id: str
    hospital_id: str
    hospital_name: str
    specialty: str
    priority: ReferralPriority
    scheduled_at: str
    qr_token: str
    qr_image_base64: Optional[str] = None
    status: ReferralStatus = ReferralStatus.BOOKED
    created_at: str
    sla_expires_at: str
    attended: bool = False


class StockRunwayInfo(BaseModel):
    phc_id: str
    phc_name: str
    district: str
    drug_name: str
    current_inventory_units: int
    daily_burn_rate: float
    days_left: float
    is_critical_shortage: bool
    recommended_reorder_units: int
