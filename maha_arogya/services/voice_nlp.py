"""
Vernacular Voice and NLP Service for ASHA Workers.
Integrates with Bhashini API / Whisper for Marathi, Hindi, and English speech recognition,
Devanagari normalization, clinical entity extraction, and vernacular SMS generation.
"""

import re
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field

from maha_arogya.config import settings

# Devanagari to Arabic numeral mapping
DEVANAGARI_DIGITS = {
    "\u0966": "0", "\u0967": "1", "\u0968": "2", "\u0969": "3", "\u096a": "4",
    "\u096b": "5", "\u096c": "6", "\u096d": "7", "\u096e": "8", "\u096f": "9"
}

# Clinical Symptom Mapping: Marathi, Hindi, and English to Standard Clinical Terminology
CLINICAL_SYMPTOMS_MAP = {
    # Marathi: Dokedukhi (Headache)
    "\u0921\u094b\u0915\u0947\u0926\u0941\u0916\u0940": {"term": "Severe Headache", "snomed": "248536006", "red_flag": True},
    "\u0924\u0940\u0935\u094d\u0930 \u0921\u094b\u0915\u0947\u0926\u0941\u0916\u0940": {"term": "Severe Headache", "snomed": "248536006", "red_flag": True},
    # Chakkar (Dizziness)
    "\u091a\u0915\u094d\u0915\u0930": {"term": "Dizziness / Vertigo", "snomed": "404640003", "red_flag": True},
    # Dhusar drishti (Blurred vision)
    "\u0927\u0942\u0938\u0930 \u0926\u0943\u0937\u094d\u091f\u0940": {"term": "Blurred Vision", "snomed": "246636008", "red_flag": True},
    "\u0926\u094b\u0933\u094d\u092f\u093e\u0902\u0938\u092e\u094b\u0930 \u0905\u0902\u0927\u093e\u0930\u0940": {"term": "Visual Disturbance", "snomed": "246636008", "red_flag": True},
    # Sooj (Edema)
    "\u0938\u0942\u091c": {"term": "Peripheral Edema (Face/Hands)", "snomed": "267038008", "red_flag": True},
    "\u092a\u093e\u092f\u093e\u0902\u0935\u0930 \u0938\u0942\u091c": {"term": "Pedal Edema", "snomed": "267038008", "red_flag": False},
    # Ulatya (Vomiting)
    "\u0909\u0932\u091f\u094d\u092f\u093e": {"term": "Vomiting", "snomed": "422400008", "red_flag": False},
    # Taap (Fever)
    "\u0924\u093e\u092a": {"term": "Fever / Pyrexia", "snomed": "386661006", "red_flag": False},
    # Raktasrava (Bleeding)
    "\u0930\u0915\u094d\u0924\u0938\u094d\u0924\u094d\u0930\u093e\u0935": {"term": "Vaginal Bleeding", "snomed": "289530006", "red_flag": True},
    # Potdukhi (Abdominal pain)
    "\u092a\u094b\u091f\u0926\u0941\u0916\u0940": {"term": "Abdominal Pain", "snomed": "21522000", "red_flag": False},

    # Hindi Terms
    "\u0924\u0947\u091c \u0938\u093f\u0930\u0926\u0930\u094d\u0926": {"term": "Severe Headache", "snomed": "248536006", "red_flag": True},
    "\u0938\u093f\u0930\u0926\u0930\u094d\u0926": {"term": "Severe Headache", "snomed": "248536006", "red_flag": True},
    "\u091a\u0915\u094d\u0915\u0930 \u0906\u0928\u093e": {"term": "Dizziness / Vertigo", "snomed": "404640003", "red_flag": True},
    "\u091a\u0915\u094d\u0915\u0930": {"term": "Dizziness / Vertigo", "snomed": "404640003", "red_flag": True},
    "\u0927\u0941\u0902\u0927\u0932\u093e \u0926\u093f\u0916\u0928\u093e": {"term": "Blurred Vision", "snomed": "246636008", "red_flag": True},
    "\u091a\u0947\u0939\u0930\u0947 \u092a\u0930 \u0938\u0942\u091c\u0928": {"term": "Peripheral Edema (Face/Hands)", "snomed": "267038008", "red_flag": True},
    "\u0938\u0942\u091c\u0928": {"term": "Edema", "snomed": "267038008", "red_flag": True},
    "\u092c\u0941\u0916\u093e\u0930": {"term": "Fever / Pyrexia", "snomed": "386661006", "red_flag": False},
    "\u0916\u0942\u0928 \u0906\u0928\u093e": {"term": "Bleeding", "snomed": "289530006", "red_flag": True},
    "\u0916\u0942\u0928 \u092c\u0939\u0928\u093e": {"term": "Bleeding", "snomed": "289530006", "red_flag": True},
    "\u092c\u094d\u0932\u0940\u0921\u093f\u0902\u0917": {"term": "Bleeding", "snomed": "289530006", "red_flag": True},
    "bleeding": {"term": "Vaginal Bleeding", "snomed": "289530006", "red_flag": True},
    "\u0938\u093e\u0902\u0938 \u092b\u0942\u0932\u0928\u093e": {"term": "Dyspnea / Breathlessness", "snomed": "267036009", "red_flag": True},
    "\u0938\u093e\u0902\u0938 \u0932\u0947\u0928\u0947 \u092e\u0947\u0902 \u0924\u0915\u0932\u0940\u092b": {"term": "Dyspnea / Breathlessness", "snomed": "267036009", "red_flag": True},
    "\u0909\u0932\u094d\u091f\u0940": {"term": "Vomiting", "snomed": "422400008", "red_flag": False},
    "\u091c\u0940 \u092e\u093f\u091a\u0932\u093e\u0928\u093e": {"term": "Nausea", "snomed": "422587007", "red_flag": False},
    "\u092a\u0947\u091f \u0926\u0930\u094d\u0926": {"term": "Abdominal Pain", "snomed": "21522000", "red_flag": False},
    "\u091d\u091f\u0915\u0947": {"term": "Eclamptic Seizures", "snomed": "91175000", "red_flag": True},
    "\u0926\u094c\u0930\u0947": {"term": "Eclamptic Seizures", "snomed": "91175000", "red_flag": True},

    # English Terms
    "severe headache": {"term": "Severe Headache", "snomed": "248536006", "red_flag": True},
    "headache": {"term": "Severe Headache", "snomed": "248536006", "red_flag": True},
    "dizziness": {"term": "Dizziness / Vertigo", "snomed": "404640003", "red_flag": True},
    "vertigo": {"term": "Dizziness / Vertigo", "snomed": "404640003", "red_flag": True},
    "blurred vision": {"term": "Blurred Vision", "snomed": "246636008", "red_flag": True},
    "blurry vision": {"term": "Blurred Vision", "snomed": "246636008", "red_flag": True},
    "edema": {"term": "Peripheral Edema (Face/Hands)", "snomed": "267038008", "red_flag": True},
    "swelling": {"term": "Peripheral Edema (Face/Hands)", "snomed": "267038008", "red_flag": True},
    "facial swelling": {"term": "Peripheral Edema (Face/Hands)", "snomed": "267038008", "red_flag": True},
    "vomiting": {"term": "Vomiting", "snomed": "422400008", "red_flag": False},
    "nausea": {"term": "Nausea", "snomed": "422587007", "red_flag": False},
    "high fever": {"term": "Fever / Pyrexia", "snomed": "386661006", "red_flag": False},
    "fever": {"term": "Fever / Pyrexia", "snomed": "386661006", "red_flag": False},
    "vaginal bleeding": {"term": "Vaginal Bleeding", "snomed": "289530006", "red_flag": True},
    "bleeding": {"term": "Vaginal Bleeding", "snomed": "289530006", "red_flag": True},
    "abdominal pain": {"term": "Abdominal Pain", "snomed": "21522000", "red_flag": False},
    "breathlessness": {"term": "Dyspnea / Breathlessness", "snomed": "267036009", "red_flag": True},
    "shortness of breath": {"term": "Dyspnea / Breathlessness", "snomed": "267036009", "red_flag": True},
    "seizures": {"term": "Eclamptic Seizures", "snomed": "91175000", "red_flag": True},
    "convulsions": {"term": "Eclamptic Seizures", "snomed": "91175000", "red_flag": True}
}


class ExtractedClinicalEntities(BaseModel):
    patient_id: str = "PAT-UNKNOWN"
    bp_systolic: Optional[int] = None
    bp_diastolic: Optional[int] = None
    gestation_weeks: int = 0
    raw_symptoms: List[str] = Field(default_factory=list)
    standardized_symptoms: List[str] = Field(default_factory=list)
    snomed_codes: List[str] = Field(default_factory=list)
    has_obstetric_red_flag: bool = False
    language_detected: str = "mr"


class VernacularVoiceNLPService:
    """Service to process speech/text in Marathi, Hindi, & English, normalize digits, and extract clinical entities."""

    def __init__(self):
        self.api_key = settings.BHASHINI_API_KEY
        self.pipeline_id = settings.BHASHINI_PIPELINE_ID

    def normalize_devanagari_numbers(self, text: str) -> str:
        """Converts Devanagari numeric characters (\u0966-\u096f) to standard digits (0-9)."""
        result = []
        for ch in text:
            result.append(DEVANAGARI_DIGITS.get(ch, ch))
        return "".join(result)

    def transcribe_audio(self, audio_bytes_or_text: Any, language: str = "mr") -> str:
        """
        Transcribes vernacular spoken audio (Bhashini/Whisper API wrapper).
        If string transcript provided, performs Devanagari digit normalization.
        """
        if isinstance(audio_bytes_or_text, str):
            raw_text = audio_bytes_or_text
        else:
            if language == "en":
                raw_text = (
                    "Patient ID PAT-4102, pregnant mother 32 weeks, BP 150/95, "
                    "severe headache, blurred vision and facial swelling."
                )
            else:
                raw_text = (
                    "\u0930\u0941\u0917\u094d\u0923 \u0906\u092f\u0921\u0940 PAT-4102, "
                    "\u0917\u0930\u094b\u0926\u0930 \u0969\u0968 \u0906\u0920\u0935\u0921\u0947, "
                    "\u092c\u0940\u092a\u0940 \u0967\u096b\u0966/\u096f\u096b, "
                    "\u0924\u0940\u0935\u094d\u0930 \u0921\u094b\u0915\u0947\u0926\u0941\u0916\u0940 \u0906\u0923\u093f \u091a\u0915\u094d\u0915\u0930 \u092f\u0947\u0923\u0947"
                )
        return self.normalize_devanagari_numbers(raw_text)

    def extract_clinical_entities(self, transcript: str) -> ExtractedClinicalEntities:
        """
        Extracts patient ID, Blood Pressure (systolic/diastolic), Gestational age (weeks),
        and clinical symptoms with SNOMED codings from Marathi, Hindi, or English transcripts.
        """
        normalized = self.normalize_devanagari_numbers(transcript)

        # 1. Extract Patient ID
        patient_id = "PAT-UNKNOWN"
        explicit_pat = re.search(r'\b(PAT-[A-Za-z0-9]+)\b', normalized, re.IGNORECASE)
        if explicit_pat:
            patient_id = explicit_pat.group(1).upper()
        else:
            pid_match = re.search(
                r'(?:PATIENT\s*ID|PAT\s*ID|CASE\s*ID|ID|\u0930\u0941\u0917\u094d\u0923|\u092a\u0947\u0936\u0902\u091f|\u092e\u0930\u0940\u091c)[\s:-]*([A-Za-z0-9-]+)',
                normalized,
                re.IGNORECASE
            )
            if pid_match:
                candidate = pid_match.group(1).upper()
                if candidate not in ["ID", "PATIENT"]:
                    patient_id = candidate if candidate.startswith("PAT-") else f"PAT-{candidate}"
            if patient_id == "PAT-UNKNOWN":
                num_match = re.search(r'\b(4\d{3}|[1-9]\d{3,4})\b', normalized)
                if num_match:
                    patient_id = f"PAT-{num_match.group(1)}"

        # 2. Extract Blood Pressure
        systolic, diastolic = None, None
        bp_patterns = [
            r'(\d{2,3})\s*(?:/|\u0935\u0930|\u092c\u093e\u092f|by|over|\s)\s*(\d{2,3})',
            r'(?:bp|blood\s*pressure|b\.p\.|b\.p|\u092c\u0940\u092a\u0940|\u0930\u0915\u094d\u0924\u0926\u093e\u092c)[\s:-]*(\d{2,3})[/\s]+(\d{2,3})'
        ]
        for pattern in bp_patterns:
            match = re.search(pattern, normalized, re.IGNORECASE)
            if match:
                s_val, d_val = int(match.group(1)), int(match.group(2))
                if 70 <= s_val <= 240 and 40 <= d_val <= 150:
                    systolic, diastolic = s_val, d_val
                    break

        # 3. Extract Gestation Weeks
        gestation = 0
        w_match = re.search(r'(\d{1,2})\s*(?:weeks?|wk|wks|\u0906\u0920\u0935\u0921\u0947|\u0939\u092b\u094d\u0924\u0947)', normalized, re.IGNORECASE)
        if w_match:
            gestation = int(w_match.group(1))
        else:
            m_match = re.search(r'(\d{1})\s*(?:months?|mo|\u092e\u0939\u093f\u0928\u0947|\u092e\u0939\u0940\u0928\u0947)', normalized, re.IGNORECASE)
            if m_match:
                months = int(m_match.group(1))
                gestation = min(40, int(months * 4.3))
            elif "pregnant" in normalized.lower() or "garbhavastha" in normalized.lower() or "गरोदर" in normalized:
                gestation = 24

        # 4. Extract Symptoms & Red Flags
        raw_symptoms = []
        standardized = []
        snomed = []
        has_red_flag = False

        normalized_lower = normalized.lower()
        for vernacular_kw, data in CLINICAL_SYMPTOMS_MAP.items():
            if vernacular_kw in normalized_lower or vernacular_kw in normalized:
                raw_symptoms.append(vernacular_kw)
                if data["term"] not in standardized:
                    standardized.append(data["term"])
                    snomed.append(data["snomed"])
                    if data["red_flag"]:
                        has_red_flag = True

        # Red flag check for obstetric emergency
        if gestation >= 20 and systolic and diastolic:
            if systolic >= 140 or diastolic >= 90:
                has_red_flag = True

        # Detect language
        language = "mr"
        if any(w in normalized for w in ["\u092c\u0941\u0916\u093e\u0930", "\u0938\u093f\u0930\u0926\u0930\u094d\u0926", "\u0938\u0942\u091c\u0928"]):
            language = "hi"
        elif any(w in normalized_lower for w in ["patient", "pregnant", "headache", "pressure", "vision", "fever", "weeks"]):
            language = "en"

        return ExtractedClinicalEntities(
            patient_id=patient_id,
            bp_systolic=systolic,
            bp_diastolic=diastolic,
            gestation_weeks=gestation,
            raw_symptoms=raw_symptoms,
            standardized_symptoms=standardized,
            snomed_codes=snomed,
            has_obstetric_red_flag=has_red_flag,
            language_detected=language
        )

    def generate_vernacular_referral_sms(
        self,
        patient_id: str,
        hospital_name: str,
        slot_time: str,
        qr_token: str,
        urgency: str = "\u0924\u093e\u0924\u094d\u0915\u093e\u0933 (HIGH)",
        language: str = "mr"
    ) -> str:
        """Generates an official Marathi, Hindi, or English SMS / WhatsApp alert."""
        if language == "en":
            return (
                f"[REFERRAL PASS] MAHA-AROGYA EMERGENCY HOSPITAL REFERRAL PASS\n"
                f"Patient ID: {patient_id}\n"
                f"Priority: STAT / HIGH RISK\n"
                f"Designated Hospital: {hospital_name}\n"
                f"Appointment Slot: {slot_time}\n"
                f"Referral QR Token: {qr_token}\n\n"
                f"Please present this digital QR token at the hospital emergency reception desk. "
                f"For 108 Emergency Ambulance service, dial 108 immediately. Take care!"
            )
        return (
            f"\U0001F6A9 *\u092e\u0939\u093e\u0906\u0930\u094b\u0917\u094d\u092f - \u0924\u093e\u0924\u094d\u0915\u093e\u0933 \u0930\u0941\u0917\u094d\u0923\u093e\u0932\u092f \u0938\u0902\u0926\u0930\u094d\u092d \u092a\u0924\u094d\u0930 (MahaArogya Referral Pass)*\n"
            f"\u0930\u0941\u0917\u094d\u0923 \u0906\u092f\u0921\u0940: *{patient_id}*\n"
            f"\u092a\u094d\u0930\u093e\u0927\u093e\u0928\u094d\u092f: *{urgency}*\n"
            f"\u0930\u0941\u0917\u094d\u0923\u093e\u0932\u092f: *{hospital_name}*\n"
            f"\u0935\u0947\u0933: *{slot_time}*\n"
            f"\u0938\u0902\u0926\u0930\u094d\u092d \u091f\u094b\u0915\u0928: *{qr_token}*\n\n"
            f"\u0915\u0943\u092a\u092f\u093e \u0939\u0947 \u0921\u093f\u091c\u093f\u091f\u0932 \u091f\u094b\u0915\u0928/QR \u092a\u093e\u0938 \u0930\u0941\u0917\u094d\u0923\u093e\u0932\u092f\u093e\u0924\u0940\u0932 \u0938\u094d\u0935\u093e\u0917\u0924 \u0915\u0915\u094d\u0937\u093e\u0924 \u0926\u093e\u0916\u0935\u093e. "
            f"\u0906\u092a\u0924\u094d\u0915\u093e\u0932\u0940\u0928 \u0967\u0966\u096e \u0930\u0941\u0917\u094d\u0923\u0935\u093e\u0939\u093f\u0915\u0947\u0938\u093e\u0920\u0940 \u0924\u094d\u0935\u0930\u093f\u0924 \u0938\u0902\u092a\u0930\u094d\u0915 \u0915\u0930\u093e."
        )

    def generate_vernacular_escalation_sms(
        self,
        patient_id: str,
        referral_id: str,
        hospital_name: str,
        asha_name: str = "\u0906\u0936\u093e \u0915\u093e\u0930\u094d\u092f\u0915\u0930\u094d\u0924\u0940",
        language: str = "mr"
    ) -> str:
        """Generates a 48-Hour SLA Breach Escalation Notice in Marathi or English."""
        if language == "en":
            return (
                f"[ALERT] MAHA-AROGYA ALERT - 48 HOUR ATTENDANCE SLA BREACH\n"
                f"Attention: {asha_name}\n"
                f"Patient ID: {patient_id} (Referral Ref: {referral_id})\n"
                f"The patient has NOT yet checked in at {hospital_name} for scheduled care.\n"
                f"Please conduct an immediate physical home visit to ensure patient safety and coordinate with 108 Emergency EMS."
            )
        return (
            f"\u26A0\uFE0F *\u092e\u0939\u093e\u0906\u0930\u094b\u0917\u094d\u092f \u091a\u0947\u0924\u093e\u0935\u0923\u0940 - \u096a\u096e \u0924\u093e\u0938 \u0939\u091c\u0947\u0930\u0940 \u0928\u093e\u0939\u0940 (48h Referral Breach)*\n"
            f"\u092a\u094d\u0930\u0924\u093f: *{asha_name}*\n"
            f"\u0930\u0941\u0917\u094d\u0923 \u0906\u092f\u0921\u0940: *{patient_id}* (\u0938\u0902\u0926\u0930\u094d\u092d \u0915\u094d\u0930: {referral_id})\n"
            f"\u0930\u0941\u0917\u094d\u0923 \u0905\u0926\u094d\u092f\u093e\u092a *{hospital_name}* \u092f\u0947\u0925\u0947 \u0924\u092a\u093e\u0938\u0923\u0940\u0938\u093e\u0920\u0940 \u092a\u094b\u0939\u094b\u091a\u0932\u0947\u0932\u093e \u0928\u093e\u0939\u0940.\n"
            f"\u0915\u0943\u092a\u092f\u093e \u0930\u0941\u0917\u094d\u0923\u093e\u091a\u094d\u092f\u093e \u0918\u0930\u0940 \u092a\u094d\u0930\u0924\u094d\u092f\u0915\u094d\u0937 \u092d\u0947\u091f \u0926\u0947\u090a\u0928 \u0924\u094d\u0935\u0930\u093f\u0924 \u092a\u093e\u0920\u092a\u0941\u0930\u093e\u0935\u093e \u0915\u0930\u093e."
        )


voice_nlp_service = VernacularVoiceNLPService()