"""
MahaArogya Clinical Evaluation Benchmark Dataset
SIH 2026 PS 133 | Govt of Maharashtra Health Department

20 expert-validated clinical scenarios across Marathi, Hindi, and English for measuring:
- Triage classification accuracy
- High-risk clinical recall / sensitivity (Must be 100% to avoid preventable maternal mortality)
- Red-flag detection rate
- SNOMED-CT / LOINC clinical coding consistency
"""

from typing import List, Dict, Any
from pydantic import BaseModel


class ClinicalBenchmarkCase(BaseModel):
    case_id: str
    language: str
    patient_id: str
    condition_name: str
    transcript: str
    expected_systolic: int | None
    expected_diastolic: int | None
    expected_gestation: int
    expected_triage: str  # "HIGH", "MED", "LOW"
    expected_red_flag: bool
    requires_emergency_referral: bool
    notes: str


BENCHMARK_CASES: List[ClinicalBenchmarkCase] = [
    # -------------------------------------------------------------
    # MARATHI SCENARIOS (CASES 1-7)
    # -------------------------------------------------------------
    ClinicalBenchmarkCase(
        case_id="EVAL-MR-001",
        language="mr",
        patient_id="PAT-5001",
        condition_name="Severe Pre-eclampsia with neurological prodromes",
        transcript="रुग्ण PAT-5001, वय २६, गरोदर ३२ आठवडे, बीपी १६०/१००, तीव्र डोकेदुखी आणि अंधारी येणे, पायांवर सूज आहे.",
        expected_systolic=160,
        expected_diastolic=100,
        expected_gestation=32,
        expected_triage="HIGH",
        expected_red_flag=True,
        requires_emergency_referral=True,
        notes="Obstetric emergency: Severe pre-eclampsia warning signs requiring immediate CEmONC tertiary referral."
    ),
    ClinicalBenchmarkCase(
        case_id="EVAL-MR-002",
        language="mr",
        patient_id="PAT-5002",
        condition_name="Antepartum Hemorrhage / Active Vaginal Bleeding",
        transcript="रुग्ण आयडी PAT-5002, गरोदर २८ आठवडे, बीपी १२०/८०, अचानक तीव्र रक्तस्त्राव सुरू झाला आहे आणि पोटदुखी.",
        expected_systolic=120,
        expected_diastolic=80,
        expected_gestation=28,
        expected_triage="HIGH",
        expected_red_flag=True,
        requires_emergency_referral=True,
        notes="Obstetric hemorrhage: Critical red-flag symptom triggering emergency hospital transfer."
    ),
    ClinicalBenchmarkCase(
        case_id="EVAL-MR-003",
        language="mr",
        patient_id="PAT-5003",
        condition_name="Impending Eclampsia with Convulsions",
        transcript="रुग्ण PAT-5003, गरोदर ३४ आठवडे, बीपी १७०/११०, झटके येणे आणि चक्कर येणे, बेशुद्ध होत आहे.",
        expected_systolic=170,
        expected_diastolic=110,
        expected_gestation=34,
        expected_triage="HIGH",
        expected_red_flag=True,
        requires_emergency_referral=True,
        notes="Eclamptic seizure: Highest possible acuity priority, immediate Magnesium Sulfate and 108 ambulance dispatch."
    ),
    ClinicalBenchmarkCase(
        case_id="EVAL-MR-004",
        language="mr",
        patient_id="PAT-5004",
        condition_name="Gestational Hypertension without neurological red flags",
        transcript="रुग्ण PAT-5004, गरोदर २४ आठवडे, बीपी १४४/९२, थोडी मळमळ आहे.",
        expected_systolic=144,
        expected_diastolic=92,
        expected_gestation=24,
        expected_triage="HIGH",
        expected_red_flag=False,
        requires_emergency_referral=True,
        notes="Gestational hypertension (>140/90 after 20 weeks) requiring specialist evaluation."
    ),
    ClinicalBenchmarkCase(
        case_id="EVAL-MR-005",
        language="mr",
        patient_id="PAT-5005",
        condition_name="Mild Antenatal Distress with Nausea & Vomiting",
        transcript="रुग्ण PAT-5005, गरोदर १२ आठवडे, बीपी ११८/७६, मळमळ आणि उलट्या होत आहेत.",
        expected_systolic=118,
        expected_diastolic=76,
        expected_gestation=12,
        expected_triage="MED",
        expected_red_flag=False,
        requires_emergency_referral=False,
        notes="First trimester hyperemesis: Moderate risk, requires PHC MO teleconsultation and oral hydration."
    ),
    ClinicalBenchmarkCase(
        case_id="EVAL-MR-006",
        language="mr",
        patient_id="PAT-5006",
        condition_name="Antenatal Pyrexia / Suspected Malaria",
        transcript="रुग्ण PAT-5006, गरोदर १८ आठवडे, बीपी १२४/८२, ताप आणि अंगदुखी आहे.",
        expected_systolic=124,
        expected_diastolic=82,
        expected_gestation=18,
        expected_triage="MED",
        expected_red_flag=False,
        requires_emergency_referral=False,
        notes="Febrile illness during pregnancy: Moderate triage, needs PHC blood smear & peripheral screening."
    ),
    ClinicalBenchmarkCase(
        case_id="EVAL-MR-007",
        language="mr",
        patient_id="PAT-5007",
        condition_name="Normal Physiological Antenatal Checkup",
        transcript="रुग्ण आयडी PAT-5007, गरोदर २० आठवडे, बीपी ११०/७०, कोणतीही तक्रार नाही, नियमित तपासणी.",
        expected_systolic=110,
        expected_diastolic=70,
        expected_gestation=20,
        expected_triage="LOW",
        expected_red_flag=False,
        requires_emergency_referral=False,
        notes="Completely normal antenatal vitals and asymptomatic presentation."
    ),

    # -------------------------------------------------------------
    # HINDI SCENARIOS (CASES 8-14)
    # -------------------------------------------------------------
    ClinicalBenchmarkCase(
        case_id="EVAL-HI-008",
        language="hi",
        patient_id="PAT-5008",
        condition_name="Severe Pre-eclampsia with Facial Edema and Vision Blur",
        transcript="मरीज PAT-5008, गर्भवती ३० हफ्ते, बीपी १५२/९८, तेज सिरदर्द, धुंधला दिखना और चेहरे पर सूजन है।",
        expected_systolic=152,
        expected_diastolic=98,
        expected_gestation=30,
        expected_triage="HIGH",
        expected_red_flag=True,
        requires_emergency_referral=True,
        notes="High-risk pre-eclampsia with visual disturbances in Hindi."
    ),
    ClinicalBenchmarkCase(
        case_id="EVAL-HI-009",
        language="hi",
        patient_id="PAT-5009",
        condition_name="Acute Dyspnea and Pulmonary Congestion in Pregnancy",
        transcript="मरीज PAT-5009, गर्भवती ३६ हफ्ते, बीपी १३०/८५, बहुत सांस फूलना और सांस लेने में तकलीफ हो रही है।",
        expected_systolic=130,
        expected_diastolic=85,
        expected_gestation=36,
        expected_triage="HIGH",
        expected_red_flag=True,
        requires_emergency_referral=True,
        notes="Acute dyspnea is a recognized maternal red flag requiring tertiary evaluation."
    ),
    ClinicalBenchmarkCase(
        case_id="EVAL-HI-010",
        language="hi",
        patient_id="PAT-5010",
        condition_name="Antepartum Vaginal Bleeding with Abdominal Pain",
        transcript="मरीज PAT-5010, गर्भवती २६ हफ्ते, बीपी ११५/७५, अचानक ब्लीडिंग और पेट दर्द शुरू हुआ।",
        expected_systolic=115,
        expected_diastolic=75,
        expected_gestation=26,
        expected_triage="HIGH",
        expected_red_flag=True,
        requires_emergency_referral=True,
        notes="Vaginal bleeding indicates possible placental abruption or placenta previa."
    ),
    ClinicalBenchmarkCase(
        case_id="EVAL-HI-011",
        language="hi",
        patient_id="PAT-5011",
        condition_name="Pre-hypertension Borderline Vitals",
        transcript="मरीज PAT-5011, गर्भवती १४ हफ्ते, बीपी १३६/८८, हल्का सिर में भारीपन।",
        expected_systolic=136,
        expected_diastolic=88,
        expected_gestation=14,
        expected_triage="MED",
        expected_red_flag=False,
        requires_emergency_referral=False,
        notes="Borderline systolic (136) / diastolic (88) warrants teleconsultation monitoring."
    ),
    ClinicalBenchmarkCase(
        case_id="EVAL-HI-012",
        language="hi",
        patient_id="PAT-5012",
        condition_name="Persistent Gestational Vomiting",
        transcript="मरीज PAT-5012, गर्भवती १६ हफ्ते, बीपी ११०/७०, बार-बार उल्टी और जी मिचलाना हो रहा है।",
        expected_systolic=110,
        expected_diastolic=70,
        expected_gestation=16,
        expected_triage="MED",
        expected_red_flag=False,
        requires_emergency_referral=False,
        notes="Hyperemesis gravidarum requiring PHC antiemetic care and hydration assessment."
    ),
    ClinicalBenchmarkCase(
        case_id="EVAL-HI-013",
        language="hi",
        patient_id="PAT-5013",
        condition_name="Normal Third Trimester ANC Visit",
        transcript="मरीज PAT-5013, गर्भवती ३४ हफ्ते, बीपी १२०/८०, बच्चा घूम रहा है, कोई दर्द नहीं है।",
        expected_systolic=120,
        expected_diastolic=80,
        expected_gestation=34,
        expected_triage="LOW",
        expected_red_flag=False,
        requires_emergency_referral=False,
        notes="Stable textbook antenatal visit with fetal movement and normal blood pressure."
    ),
    ClinicalBenchmarkCase(
        case_id="EVAL-HI-014",
        language="hi",
        patient_id="PAT-5014",
        condition_name="Normal Early Antenatal Baseline",
        transcript="मरीज PAT-5014, गर्भवती १० हफ्ते, बीपी ११२/७४, सामान्य स्वास्थ्य जांच।",
        expected_systolic=112,
        expected_diastolic=74,
        expected_gestation=10,
        expected_triage="LOW",
        expected_red_flag=False,
        requires_emergency_referral=False,
        notes="Routine first-trimester registration and baseline vitals."
    ),

    # -------------------------------------------------------------
    # ENGLISH SCENARIOS (CASES 15-20)
    # -------------------------------------------------------------
    ClinicalBenchmarkCase(
        case_id="EVAL-EN-015",
        language="en",
        patient_id="PAT-5015",
        condition_name="Classic Severe Pre-eclampsia Triad",
        transcript="Patient ID PAT-5015, pregnant 32 weeks, BP 155/96, severe headache, blurry vision and facial swelling.",
        expected_systolic=155,
        expected_diastolic=96,
        expected_gestation=32,
        expected_triage="HIGH",
        expected_red_flag=True,
        requires_emergency_referral=True,
        notes="Classic pre-eclampsia triad (HTN + headache + blurred vision) triggering high priority triage."
    ),
    ClinicalBenchmarkCase(
        case_id="EVAL-EN-016",
        language="en",
        patient_id="PAT-5016",
        condition_name="Stage 2 Hypertensive Emergency",
        transcript="Patient ID PAT-5016, pregnant 26 weeks, BP 168/104, patient complaining of dizziness.",
        expected_systolic=168,
        expected_diastolic=104,
        expected_gestation=26,
        expected_triage="HIGH",
        expected_red_flag=True,
        requires_emergency_referral=True,
        notes="Critical systolic >160 and diastolic >100 in mid-trimester."
    ),
    ClinicalBenchmarkCase(
        case_id="EVAL-EN-017",
        language="en",
        patient_id="PAT-5017",
        condition_name="Acute Obstetric Hemorrhage",
        transcript="Patient ID PAT-5017, pregnant 29 weeks, BP 118/76, vaginal bleeding and abdominal pain.",
        expected_systolic=118,
        expected_diastolic=76,
        expected_gestation=29,
        expected_triage="HIGH",
        expected_red_flag=True,
        requires_emergency_referral=True,
        notes="Vaginal bleeding in third trimester is an automatic emergency."
    ),
    ClinicalBenchmarkCase(
        case_id="EVAL-EN-018",
        language="en",
        patient_id="PAT-5018",
        condition_name="Borderline Gestational Pre-Hypertension",
        transcript="Patient ID PAT-5018, pregnant 18 weeks, BP 134/86, mild nausea.",
        expected_systolic=134,
        expected_diastolic=86,
        expected_gestation=18,
        expected_triage="MED",
        expected_red_flag=False,
        requires_emergency_referral=False,
        notes="Systolic 134 mmHg falls in MED tier (130-139 mmHg) requiring teleconsultation."
    ),
    ClinicalBenchmarkCase(
        case_id="EVAL-EN-019",
        language="en",
        patient_id="PAT-5019",
        condition_name="Optimal Physiological Pregnancy Vitals",
        transcript="Patient ID PAT-5019, pregnant 24 weeks, BP 116/74, routine prenatal checkup no complaints.",
        expected_systolic=116,
        expected_diastolic=74,
        expected_gestation=24,
        expected_triage="LOW",
        expected_red_flag=False,
        requires_emergency_referral=False,
        notes="Normal physiological pregnancy parameters, routine iron & calcium advisory."
    ),
    ClinicalBenchmarkCase(
        case_id="EVAL-EN-020",
        language="en",
        patient_id="PAT-5020",
        condition_name="Full Term Normal Antenatal Assessment",
        transcript="Patient ID PAT-5020, pregnant 38 weeks, BP 120/78, good fetal movement, routine visit.",
        expected_systolic=120,
        expected_diastolic=78,
        expected_gestation=38,
        expected_triage="LOW",
        expected_red_flag=False,
        requires_emergency_referral=False,
        notes="Term pregnancy with normal maternal and fetal well-being indicators."
    ),
]
