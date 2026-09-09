"""
LangGraph AgentState Definition for MahaArogya-Agent.
Manages context across ASHA Voice Copilot, Closed-Loop Referral Agent, and Surveillance Watchdog.
"""

from typing import TypedDict, Annotated, List, Dict, Any, Optional, Literal
from langgraph.graph.message import add_messages


class AgentState(TypedDict, total=False):
    """
    Central state container passed between nodes in the LangGraph StateGraph.
    Includes HITL (Human-In-The-Loop) checkpointing variables and HL7 FHIR structures.
    """
    # LangGraph message history
    messages: Annotated[List[Dict[str, Any]], add_messages]
    
    # Patient Demographics & Session Context
    patient_id: str
    phone: str
    district: str
    phc_id: str
    raw_input: str
    detected_language: str  # "mr", "hi", "en"
    
    # Clinical Entities & FHIR Validation
    extracted_entities: Dict[str, Any]
    fhir_bundle: Dict[str, Any]
    
    # Triage Decision
    triage_level: Literal["LOW", "MED", "HIGH"]
    triage_rationale: str
    red_flag_detected: bool
    specialty_needed: str
    requires_referral: bool
    
    # Human-In-The-Loop (HITL) Clinical Guardrails
    hitl_pending: bool               # Set to True when HIGH-risk referral requires Medical Officer review
    hitl_approved: Optional[bool]     # Approved by MO / Clinician
    hitl_reviewer: Optional[str]      # Clinician / MO Name
    hitl_notes: Optional[str]         # Clinician notes / instructions
    
    # Closed-Loop Referral Booking
    hospital_id: Optional[str]
    hospital_name: Optional[str]
    referral_id: Optional[str]
    qr_token: Optional[str]
    qr_image_base64: Optional[str]
    scheduled_at: Optional[str]
    sla_expires_at: Optional[str]
    referral_status: str             # "PENDING_APPROVAL", "BOOKED", "ATTENDED", "NO_SHOW", "ESCALATED"
    
    # Vernacular Alert Dispatches
    alert_dispatched: bool
    vernacular_alert_text: Optional[str]
    
    # Surveillance Watchdog Signals
    surveillance_signals: Optional[Dict[str, Any]]
    stock_runway_report: Optional[Dict[str, Any]]
    
    # Ethics, Safety & Guardrail Context
    guardrail_passed: bool
    guardrail_blocked: bool
    guardrail_violations: List[str]
    statutory_disclaimer: str
    vitals_safety_status: Optional[Dict[str, Any]]
    
    # Operational Stage Tracking
    current_stage: str
    next_node: Optional[str]
    error: Optional[str]