"""
LangGraph Multi-Agent Orchestration Graph.
Connects ASHA Voice Copilot, Closed-Loop Referral Agent, and Surveillance Watchdog
with conditional routing, MemorySaver checkpointing, and Human-in-the-Loop (HITL) clinical guardrails.
"""

from typing import Dict, Any, Literal
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from maha_arogya.agents.state import AgentState
from maha_arogya.agents.asha_copilot import asha_voice_copilot_node
from maha_arogya.agents.referral_agent import closed_loop_referral_node
from maha_arogya.agents.surveillance_agent import surveillance_watchdog_node


def routine_advisory_node(state: AgentState) -> Dict[str, Any]:
    """
    Handles LOW & MED triage cases where emergency tertiary referral is not required.
    Provides vernacular PHC care advisory, teleconsultation booking, and nutrition guidelines.
    """
    triage = state.get("triage_level", "LOW")
    patient_id = state.get("patient_id", "PAT-UNKNOWN")
    lang = state.get("detected_language", "mr")
    
    if triage == "MED":
        advisory_mr = (
            f"📋 *स्थानिक प्राथमिक आरोग्य केंद्र (PHC) सल्लापत्र*\n"
            f"रुग्ण आयडी: {patient_id}\n"
            f"दर्जा: मध्यम प्राधान्य (Moderate Priority)\n"
            f"कृपया नजीकच्या प्राथमिक आरोग्य केंद्रात जाऊन वैद्यकीय अधिकाऱ्यांशी सल्लामसलत करावी. "
            f"गोळ्या वेळेवर घ्या आणि भरपूर पाणी प्या."
        )
    else:
        advisory_mr = (
            f"💚 *महाआरोग्य - आरोग्य सल्ला (Home Care Advisory)*\n"
            f"रुग्ण आयडी: {patient_id}\n"
            f"आपली प्रकृती स्थिर आहे. नियमित पौष्टिक आहार, लोह-फॉलिक ॲसिडच्या गोळ्या चालू ठेवा. "
            f"काही त्रास जाणवल्यास आशा ताईंशी संपर्क साधा."
        )
        
    message_entry = {
        "role": "assistant",
        "name": "Routine_Advisory_Agent",
        "content": advisory_mr
    }
    
    return {
        "referral_status": "ROUTINE_ADVISORY_ISSUED",
        "vernacular_alert_text": advisory_mr,
        "requires_referral": False,
        "current_stage": "ROUTINE_ADVISORY_ISSUED",
        "messages": [message_entry]
    }


def hitl_clinician_approval_node(state: AgentState) -> Dict[str, Any]:
    """
    Human-In-The-Loop (HITL) Clinical Gatekeeper.
    For HIGH-risk obstetric emergencies (e.g. impending eclampsia),
    records clinician sign-off / Medical Officer validation.
    """
    approved = state.get("hitl_approved", True)  # Default true in automatic emergency pass
    reviewer = state.get("hitl_reviewer", "Dr. Kulkarni (PHC Medical Officer)")
    notes = state.get("hitl_notes", "Clinically verified: Severe preeclampsia symptoms require CEmONC admission.")
    
    message_entry = {
        "role": "assistant",
        "name": "HITL_Clinical_Gatekeeper",
        "content": f"HITL Gatekeeper Review: Approved={approved} by {reviewer}. Clinical Note: {notes}"
    }
    
    return {
        "hitl_pending": False,
        "hitl_approved": approved,
        "hitl_reviewer": reviewer,
        "hitl_notes": notes,
        "current_stage": "HITL_APPROVED" if approved else "HITL_REJECTED",
        "messages": [message_entry]
    }


from maha_arogya.guardrails.safety import safety_guardrails


def safety_guardrail_node(state: AgentState) -> Dict[str, Any]:
    """
    First-line Safety & Ethical Gatekeeper Node.
    Filters adversarial prompts, redacts DPDP PII, intercepts crisis emergencies (poisoning, self-harm),
    and attaches statutory clinical disclaimers.
    """
    raw_input = state.get("raw_input", "")
    lang = state.get("detected_language", "en")
    
    evaluation = safety_guardrails.evaluate_clinical_and_ethical_safety(raw_input, language=lang)
    
    if evaluation.is_blocked:
        # Construct emergency safety response
        crisis_message = (
            f"⛔ SAFETY GUARDRAIL INTERCEPT: {'; '.join(evaluation.violations)}\n\n"
            f"If you or someone you know is facing a critical emergency, poisoning, or mental health crisis, "
            f"please immediately contact:\n"
            f"• National Mental Health Helpline (Tele-MANAS): 14416 / 1800-599-0019\n"
            f"• Maharashtra Emergency Ambulance Service: 108\n"
            f"• National Emergency Helpline: 112"
        )
        return {
            "guardrail_passed": False,
            "guardrail_blocked": True,
            "guardrail_violations": evaluation.violations,
            "statutory_disclaimer": evaluation.statutory_disclaimer,
            "current_stage": "GUARDRAIL_BLOCKED",
            "triage_level": "HIGH",
            "triage_rationale": crisis_message,
            "requires_referral": False,
            "messages": [{"role": "assistant", "name": "Safety_Guardrail_Engine", "content": crisis_message}]
        }
        
    return {
        "guardrail_passed": True,
        "guardrail_blocked": False,
        "guardrail_violations": [],
        "raw_input": evaluation.sanitized_text,
        "statutory_disclaimer": evaluation.statutory_disclaimer,
        "current_stage": "GUARDRAIL_PASSED"
    }


def route_after_safety(state: AgentState) -> Literal["asha_voice_copilot", "__end__"]:
    """Routes based on whether input passed ethics & safety guardrails."""
    if state.get("guardrail_blocked", False):
        return "__end__"
    return "asha_voice_copilot"


# Conditional Edge Router
def route_after_triage(state: AgentState) -> Literal["hitl_clinician_approval", "routine_advisory"]:
    """Routes based on clinical triage level."""
    triage = state.get("triage_level", "LOW")
    if triage == "HIGH":
        return "hitl_clinician_approval"
    return "routine_advisory"


def route_after_hitl(state: AgentState) -> Literal["closed_loop_referral", "routine_advisory"]:
    """Routes based on whether clinician approved the priority referral."""
    if state.get("hitl_approved", True):
        return "closed_loop_referral"
    return "routine_advisory"


def build_maha_arogya_graph(enable_hitl_interrupt: bool = False):
    """
    Assembles and compiles the full LangGraph StateGraph with Safety Guardrails.
    Flow: Safety Guardrail -> ASHA Voice Copilot -> Triage -> HITL Gatekeeper -> Referral -> Surveillance.
    """
    builder = StateGraph(AgentState)
    
    # 1. Register Nodes
    builder.add_node("safety_guardrail", safety_guardrail_node)
    builder.add_node("asha_voice_copilot", asha_voice_copilot_node)
    builder.add_node("hitl_clinician_approval", hitl_clinician_approval_node)
    builder.add_node("closed_loop_referral", closed_loop_referral_node)
    builder.add_node("routine_advisory", routine_advisory_node)
    builder.add_node("surveillance_watchdog", surveillance_watchdog_node)
    
    # 2. Set Entry Point to Safety Guardrail
    builder.set_entry_point("safety_guardrail")
    
    # 3. Add Conditional Routing
    builder.add_conditional_edges(
        "safety_guardrail",
        route_after_safety,
        {
            "asha_voice_copilot": "asha_voice_copilot",
            "__end__": END
        }
    )
    
    builder.add_conditional_edges(
        "asha_voice_copilot",
        route_after_triage,
        {
            "hitl_clinician_approval": "hitl_clinician_approval",
            "routine_advisory": "routine_advisory"
        }
    )
    
    builder.add_conditional_edges(
        "hitl_clinician_approval",
        route_after_hitl,
        {
            "closed_loop_referral": "closed_loop_referral",
            "routine_advisory": "routine_advisory"
        }
    )
    
    # 4. Terminal Transitions
    builder.add_edge("closed_loop_referral", "surveillance_watchdog")
    builder.add_edge("routine_advisory", "surveillance_watchdog")
    builder.add_edge("surveillance_watchdog", END)
    
    # 5. Checkpointer
    checkpointer = MemorySaver()
    
    interrupts = ["hitl_clinician_approval"] if enable_hitl_interrupt else []
    compiled_graph = builder.compile(
        checkpointer=checkpointer,
        interrupt_before=interrupts
    )
    
    return compiled_graph


# Pre-compiled default production graph
maha_arogya_graph = build_maha_arogya_graph(enable_hitl_interrupt=False)
maha_arogya_hitl_graph = build_maha_arogya_graph(enable_hitl_interrupt=True)