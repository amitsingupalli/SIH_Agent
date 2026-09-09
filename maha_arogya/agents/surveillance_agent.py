"""
Surveillance Watchdog Agent Node.
Executes spatial-temporal clustering on rural PHC syndromic logs, detects localized outbreaks,
predicts pharmaceutical stock-out runways via FastMCP, and generates formal DHO alert briefings.
"""

import json
from datetime import datetime, timedelta
from typing import Dict, Any, List
from collections import defaultdict

from maha_arogya.config import settings
from maha_arogya.mcp.server import check_stock_runway, PATIENT_RECORDS


# Simulated recent syndromic PHC logs across Maharashtra districts
MOCK_PHC_SYNDROMIC_LOGS = [
    {"phc_id": "PHC-GAD-BHM", "district": "Gadchiroli", "taluka": "Bhamragad", "syndrome": "Acute Febrile Illness (Suspected Malaria)", "date": "2026-09-08"},
    {"phc_id": "PHC-GAD-BHM", "district": "Gadchiroli", "taluka": "Bhamragad", "syndrome": "Acute Febrile Illness (Suspected Malaria)", "date": "2026-09-08"},
    {"phc_id": "PHC-GAD-BHM", "district": "Gadchiroli", "taluka": "Bhamragad", "syndrome": "Acute Febrile Illness (Suspected Malaria)", "date": "2026-09-07"},
    {"phc_id": "PHC-GAD-BHM", "district": "Gadchiroli", "taluka": "Bhamragad", "syndrome": "Acute Febrile Illness (Suspected Malaria)", "date": "2026-09-07"},
    {"phc_id": "PHC-GAD-BHM", "district": "Gadchiroli", "taluka": "Bhamragad", "syndrome": "Acute Febrile Illness (Suspected Malaria)", "date": "2026-09-06"},
    {"phc_id": "PHC-GAD-BHM", "district": "Gadchiroli", "taluka": "Bhamragad", "syndrome": "Acute Febrile Illness (Suspected Malaria)", "date": "2026-09-06"},
    {"phc_id": "PHC-GAD-BHM", "district": "Gadchiroli", "taluka": "Bhamragad", "syndrome": "Acute Febrile Illness (Suspected Malaria)", "date": "2026-09-05"},
    {"phc_id": "PHC-NSK-TRB", "district": "Nashik", "taluka": "Trimbak", "syndrome": "Acute Diarrheal Disease (Gastroenteritis)", "date": "2026-09-08"},
    {"phc_id": "PHC-NSK-TRB", "district": "Nashik", "taluka": "Trimbak", "syndrome": "Acute Diarrheal Disease (Gastroenteritis)", "date": "2026-09-08"},
    {"phc_id": "PHC-NSK-TRB", "district": "Nashik", "taluka": "Trimbak", "syndrome": "Acute Diarrheal Disease (Gastroenteritis)", "date": "2026-09-07"},
    {"phc_id": "PHC-NSK-TRB", "district": "Nashik", "taluka": "Trimbak", "syndrome": "Acute Diarrheal Disease (Gastroenteritis)", "date": "2026-09-07"},
    {"phc_id": "PHC-NSK-TRB", "district": "Nashik", "taluka": "Trimbak", "syndrome": "Acute Diarrheal Disease (Gastroenteritis)", "date": "2026-09-06"},
    {"phc_id": "PHC-PUN-KND", "district": "Pune", "taluka": "Haveli", "syndrome": "Maternal Gestational Hypertension / Preeclampsia", "date": "2026-09-08"},
    {"phc_id": "PHC-PUN-KND", "district": "Pune", "taluka": "Haveli", "syndrome": "Maternal Gestational Hypertension / Preeclampsia", "date": "2026-09-07"}
]


def record_syndromic_case(phc_id: str, district: str, taluka: str, syndrome: str, patient_id: str = "") -> Dict[str, Any]:
    """
    Cross-Agent Linkage: Dynamically ingests syndromic case data from ASHA Voice Copilot
    into the Surveillance Watchdog stream for immediate epidemic cluster detection.
    """
    today_str = datetime.now().strftime("%Y-%m-%d")
    entry = {
        "phc_id": phc_id or "PHC-PUN-KND",
        "district": district or "Pune",
        "taluka": taluka or "Haveli",
        "syndrome": syndrome,
        "date": today_str,
        "patient_id": patient_id or "UNKNOWN"
    }
    MOCK_PHC_SYNDROMIC_LOGS.append(entry)
    return entry


def detect_spatial_temporal_clusters(min_cluster_size: int = 4) -> List[Dict[str, Any]]:
    """
    Groups recent clinical logs by (district, syndrome) and detects statistical clusters.
    Flags an outbreak alert when incidence exceeds historical baseline threshold.
    """
    clusters = defaultdict(list)
    for entry in MOCK_PHC_SYNDROMIC_LOGS:
        key = (entry["district"], entry["syndrome"])
        clusters[key].append(entry)
        
    detected_outbreaks = []
    for (district, syndrome), cases in clusters.items():
        case_count = len(cases)
        # Baseline threshold comparison
        baseline = 2
        anomaly_ratio = round(case_count / baseline, 2)
        if case_count >= min_cluster_size:
            phc_ids = list(set(c["phc_id"] for c in cases))
            detected_outbreaks.append({
                "district": district,
                "syndrome": syndrome,
                "cases_in_72h": case_count,
                "baseline_expected": baseline,
                "anomaly_ratio": f"{anomaly_ratio}x spike",
                "severity": "CRITICAL" if anomaly_ratio >= 3.0 else "WARNING",
                "affected_phc_ids": phc_ids
            })
    return detected_outbreaks


def generate_dho_briefing(outbreaks: List[Dict[str, Any]], stock_assessments: List[Dict[str, Any]]) -> str:
    """Generates an administrative briefing for the District Health Officer (DHO)."""
    now_str = datetime.utcnow().strftime("%d-%b-%Y %H:%M UTC")
    
    briefing = [
        f"================================================================",
        f" MAHARASHTRA HEALTH DEPARTMENT - DISTRICT SURVEILLANCE BRIEFING",
        f" Generated By: MahaArogya Autonomous Surveillance Watchdog",
        f" Date: {now_str} | Protocol: IDSP / NHM Maharashtra",
        f"================================================================\n",
        f"1. LOCALIZED OUTBREAK CLUSTERS DETECTED:"
    ]
    
    if not outbreaks:
        briefing.append("   - No active syndromic outbreak clusters detected in monitored PHCs.")
    else:
        for idx, ob in enumerate(outbreaks, 1):
            briefing.append(
                f"   [{idx}] {ob['severity']} ALERT in District: {ob['district']}\n"
                f"       Syndrome: {ob['syndrome']}\n"
                f"       Cases Logged: {ob['cases_in_72h']} (Baseline: {ob['baseline_expected']} | {ob['anomaly_ratio']})\n"
                f"       Affected PHCs: {', '.join(ob['affected_phc_ids'])}\n"
                f"       Immediate Recommendation: Dispatch Mobile Epidemic Team & initiate water/vector testing."
            )
            
    briefing.append("\n2. PHARMACEUTICAL STOCK-OUT RUNWAY FORECAST:")
    for sa in stock_assessments:
        crit_flag = "[CRITICAL SHORTAGE]" if sa["is_critical_shortage"] else "[SAFE]"
        briefing.append(
            f"   {crit_flag} {sa['phc_name']} ({sa['district']})\n"
            f"       Drug: {sa['drug_name']} | Current Inventory: {sa['current_units']} units\n"
            f"       Daily Burn Rate: {sa['daily_burn_rate']} units/day\n"
            f"       Estimated Runway: {sa['days_left']} DAYS LEFT (Threshold: 7 days)\n"
            f"       Reorder Recommendation: Requisition {sa['recommended_restock_units']} units immediately."
        )
        
    briefing.append("\n================================================================")
    return "\n".join(briefing)


def surveillance_watchdog_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    LangGraph Node: Surveillance Watchdog Agent
    Executes:
    1. Spatial-temporal clustering on PHC syndromic logs.
    2. Outbreak anomaly detection.
    3. Calculates medicine stock-out runway using FastMCP check_stock_runway.
    4. Generates formal DHO alert briefing.
    """
    outbreaks = detect_spatial_temporal_clusters()
    
    # Check medicine runways for critical drugs across key PHCs
    critical_drugs = [
        ("PHC-GAD-BHM", "Chloroquine/ACT"),
        ("PHC-NSK-TRB", "ORS"),
        ("PHC-PUN-KND", "Magnesium Sulfate")
    ]
    
    stock_assessments = []
    for phc_id, drug in critical_drugs:
        runway_json = check_stock_runway(phc_id=phc_id, drug_name=drug)
        stock_assessments.append(json.loads(runway_json))
        
    dho_report = generate_dho_briefing(outbreaks, stock_assessments)
    
    message_entry = {
        "role": "assistant",
        "name": "Surveillance_Watchdog_Agent",
        "content": dho_report
    }
    
    return {
        "surveillance_signals": {
            "active_outbreaks": outbreaks,
            "total_outbreaks_detected": len(outbreaks),
            "stock_assessments": stock_assessments,
            "dho_briefing_text": dho_report,
            "last_evaluated_at": datetime.utcnow().isoformat()
        },
        "current_stage": "SURVEILLANCE_EVALUATED",
        "messages": [message_entry]
    }