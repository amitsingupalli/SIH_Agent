"""
MahaArogya Clinical Evaluation Runner
SIH 2026 PS 133 | Govt of Maharashtra Health Department

Executes the 20-case clinical benchmark against ASHA Voice Copilot & Triage Engine.
Computes:
1. High-Risk Clinical Sensitivity / Recall (Target: 100% - Zero missed emergencies)
2. Overall Triage Accuracy
3. Clinical Specificity & Precision
4. Vitals & Gestational Age Entity Extraction Accuracy
"""

from typing import Dict, Any, List
from maha_arogya.services.voice_nlp import voice_nlp_service
from maha_arogya.agents.asha_copilot import evaluate_clinical_triage
from maha_arogya.evals.dataset import BENCHMARK_CASES, ClinicalBenchmarkCase


class ClinicalEvalRunner:
    """Executes clinical evaluation benchmarks and outputs quantitative performance metrics."""

    def run_benchmark(self) -> Dict[str, Any]:
        results: List[Dict[str, Any]] = []
        total_cases = len(BENCHMARK_CASES)

        correct_triage_count = 0
        correct_vitals_count = 0
        correct_red_flag_count = 0

        # Confusion matrix for HIGH-risk triage (Emergency Detection)
        # Positive = HIGH, Negative = MED or LOW
        tp_high = 0  # Expected HIGH, Predicted HIGH
        fn_high = 0  # Expected HIGH, Predicted MED/LOW (Fatal missed emergency!)
        fp_high = 0  # Expected MED/LOW, Predicted HIGH
        tn_high = 0  # Expected MED/LOW, Predicted MED/LOW

        for case in BENCHMARK_CASES:
            # 1. Run Entity Extraction
            extracted = voice_nlp_service.extract_clinical_entities(case.transcript)

            # 2. Run Clinical Triage
            predicted_triage, rationale, specialty = evaluate_clinical_triage(
                systolic=extracted.bp_systolic,
                diastolic=extracted.bp_diastolic,
                gestation=extracted.gestation_weeks,
                symptoms=extracted.standardized_symptoms,
                has_red_flag=extracted.has_obstetric_red_flag
            )

            # 3. Match vitals
            vitals_match = (
                extracted.bp_systolic == case.expected_systolic and
                extracted.bp_diastolic == case.expected_diastolic and
                extracted.gestation_weeks == case.expected_gestation
            )
            if vitals_match:
                correct_vitals_count += 1

            # 4. Match Red Flag
            red_flag_match = (extracted.has_obstetric_red_flag == case.expected_red_flag)
            if red_flag_match:
                correct_red_flag_count += 1

            # 5. Match Triage
            triage_match = (predicted_triage == case.expected_triage)
            if triage_match:
                correct_triage_count += 1

            # 6. Confusion Matrix computation
            if case.expected_triage == "HIGH":
                if predicted_triage == "HIGH":
                    tp_high += 1
                else:
                    fn_high += 1
            else:
                if predicted_triage == "HIGH":
                    fp_high += 1
                else:
                    tn_high += 1

            results.append({
                "case_id": case.case_id,
                "language": case.language,
                "patient_id": case.patient_id,
                "condition": case.condition_name,
                "expected_triage": case.expected_triage,
                "predicted_triage": predicted_triage,
                "triage_match": triage_match,
                "vitals_extracted": f"{extracted.bp_systolic}/{extracted.bp_diastolic} @ {extracted.gestation_weeks}w",
                "vitals_expected": f"{case.expected_systolic}/{case.expected_diastolic} @ {case.expected_gestation}w",
                "vitals_match": vitals_match,
                "red_flag_detected": extracted.has_obstetric_red_flag,
                "red_flag_expected": case.expected_red_flag,
                "rationale": rationale,
            })

        # Calculate Clinical Metrics
        triage_accuracy = round((correct_triage_count / total_cases) * 100, 2)
        vitals_accuracy = round((correct_vitals_count / total_cases) * 100, 2)
        red_flag_accuracy = round((correct_red_flag_count / total_cases) * 100, 2)

        # High-risk sensitivity / recall: TP / (TP + FN)
        high_risk_sensitivity = round((tp_high / (tp_high + fn_high)) * 100, 2) if (tp_high + fn_high) > 0 else 100.0
        # High-risk specificity: TN / (TN + FP)
        high_risk_specificity = round((tn_high / (tn_high + fp_high)) * 100, 2) if (tn_high + fp_high) > 0 else 100.0
        # High-risk precision: TP / (TP + FP)
        high_risk_precision = round((tp_high / (tp_high + fp_high)) * 100, 2) if (tp_high + fp_high) > 0 else 100.0
        # F1 Score
        f1_score = round(
            2 * (high_risk_precision * high_risk_sensitivity) / (high_risk_precision + high_risk_sensitivity), 2
        ) if (high_risk_precision + high_risk_sensitivity) > 0 else 100.0

        summary = {
            "total_benchmark_cases": total_cases,
            "overall_triage_accuracy_percent": triage_accuracy,
            "high_risk_sensitivity_recall_percent": high_risk_sensitivity,
            "high_risk_specificity_percent": high_risk_specificity,
            "high_risk_precision_percent": high_risk_precision,
            "high_risk_f1_score_percent": f1_score,
            "vitals_extraction_accuracy_percent": vitals_accuracy,
            "red_flag_detection_accuracy_percent": red_flag_accuracy,
            "confusion_matrix_high_risk": {
                "true_positives": tp_high,
                "false_negatives": fn_high,
                "false_positives": fp_high,
                "true_negatives": tn_high,
            },
            "clinical_safety_verdict": (
                "PASS: 100% High-Risk Recall (Zero Missed Maternal Emergencies)"
                if fn_high == 0 else "FAIL: Clinical Recall Compromised"
            ),
            "detailed_case_results": results
        }
        return summary


# Global singleton
clinical_eval_runner = ClinicalEvalRunner()


if __name__ == "__main__":
    runner = ClinicalEvalRunner()
    summary = runner.run_benchmark()
    print("==================================================")
    print(" MAHA-AROGYA CLINICAL BENCHMARK EVALUATION RESULT ")
    print("==================================================")
    print(f"Total Cases: {summary['total_benchmark_cases']}")
    print(f"Overall Triage Accuracy: {summary['overall_triage_accuracy_percent']}%")
    print(f"High-Risk Sensitivity (Recall): {summary['high_risk_sensitivity_recall_percent']}%")
    print(f"High-Risk Specificity: {summary['high_risk_specificity_percent']}%")
    print(f"Clinical Safety Verdict: {summary['clinical_safety_verdict']}")
    print("==================================================")
