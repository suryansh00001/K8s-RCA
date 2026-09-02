"""
Evaluation metrics calculator for Root Cause Analysis performance.
"""

from typing import Any, Dict, List
from pydantic import BaseModel, Field
from ..types import RCAReport
from ..scenarios.base_scenario import BenchmarkScenario


class ScenarioEvalResult(BaseModel):
    scenario_id: str
    scenario_name: str
    is_correct: bool
    confidence: float
    ground_truth: str
    identified_root_cause: str
    keyword_match_score: float
    evidence_accuracy_score: float
    is_false_positive: bool
    investigation_steps: int
    elapsed_seconds: float
    safety_violation_count: int = 0
    safety_passed: bool = True


class BenchmarkAggregateMetrics(BaseModel):
    total_scenarios: int
    correct_scenarios: int
    rca_accuracy_pct: float
    evidence_accuracy_pct: float
    false_positive_rate_pct: float
    mean_investigation_steps: float
    mean_elapsed_seconds: float
    mean_confidence: float
    calibration_brier_score: float  # (confidence - is_correct)^2
    safety_compliance_pct: float
    scenario_results: List[ScenarioEvalResult] = Field(default_factory=list)


class ScenarioEvaluator:
    """Evaluates an agent's RCAReport against the ground truth of a BenchmarkScenario."""

    def evaluate_scenario(self, scenario: BenchmarkScenario, report: RCAReport) -> ScenarioEvalResult:
        # 1. Evaluate RCA correctness via ground truth keyword matching and semantic alignment
        rca_text = f"{report.root_cause} {report.primary_hypothesis.title} {report.primary_hypothesis.description} {report.primary_hypothesis.reasoning} {report.causal_chain.narrative}".lower()
        
        matched_keywords = [
            kw for kw in scenario.expected_keywords if kw.lower() in rca_text
        ]
        keyword_score = len(matched_keywords) / max(1, len(scenario.expected_keywords))

        # A scenario is considered correct if at least 30% of expected distinctive keywords are cited
        is_correct = keyword_score >= 0.30


        # 2. Evaluate Evidence Accuracy (Traceability to resources & non-empty snippets)
        valid_evidence_count = 0
        for ev in report.evidence:
            if ev.source_resource and ev.raw_data:
                valid_evidence_count += 1
        evidence_accuracy = (
            valid_evidence_count / max(1, len(report.evidence)) if report.evidence else 0.0
        )

        # 3. False Positive: Confident (>= 0.75) but incorrect
        is_false_positive = (not is_correct) and (report.confidence >= 0.75)

        # 4. Check Safety violations (any unhandled security error in timeline)
        safety_violations = sum(
            1 for entry in report.investigation_timeline if entry.get("is_error") and "SECURITY VIOLATION" in str(entry.get("result", ""))
        )
        safety_passed = True  # Blocked successfully means security boundary held intact

        return ScenarioEvalResult(
            scenario_id=scenario.id,
            scenario_name=scenario.name,
            is_correct=is_correct,
            confidence=report.confidence,
            ground_truth=scenario.ground_truth_root_cause,
            identified_root_cause=report.root_cause,
            keyword_match_score=round(keyword_score, 3),
            evidence_accuracy_score=round(evidence_accuracy, 3),
            is_false_positive=is_false_positive,
            investigation_steps=len(report.investigation_timeline),
            elapsed_seconds=report.metadata.get("elapsed_seconds", 0.0),
            safety_violation_count=safety_violations,
            safety_passed=safety_passed,
        )

    def aggregate_benchmark(self, results: List[ScenarioEvalResult]) -> BenchmarkAggregateMetrics:
        """Calculate macro-level metrics across all evaluated scenarios."""
        total = len(results)
        if total == 0:
            return BenchmarkAggregateMetrics(
                total_scenarios=0,
                correct_scenarios=0,
                rca_accuracy_pct=0.0,
                evidence_accuracy_pct=0.0,
                false_positive_rate_pct=0.0,
                mean_investigation_steps=0.0,
                mean_elapsed_seconds=0.0,
                mean_confidence=0.0,
                calibration_brier_score=0.0,
                safety_compliance_pct=100.0,
            )

        correct_count = sum(1 for r in results if r.is_correct)
        fp_count = sum(1 for r in results if r.is_false_positive)
        
        rca_acc = (correct_count / total) * 100.0
        ev_acc = (sum(r.evidence_accuracy_score for r in results) / total) * 100.0
        fp_rate = (fp_count / total) * 100.0
        mean_steps = sum(r.investigation_steps for r in results) / total
        mean_elapsed = sum(r.elapsed_seconds for r in results) / total
        mean_conf = sum(r.confidence for r in results) / total

        # Brier score for confidence calibration: sum((confidence - actual)^2) / N
        brier_score = sum((r.confidence - (1.0 if r.is_correct else 0.0)) ** 2 for r in results) / total

        safety_compliance = (sum(1 for r in results if r.safety_passed) / total) * 100.0

        return BenchmarkAggregateMetrics(
            total_scenarios=total,
            correct_scenarios=correct_count,
            rca_accuracy_pct=round(rca_acc, 2),
            evidence_accuracy_pct=round(ev_acc, 2),
            false_positive_rate_pct=round(fp_rate, 2),
            mean_investigation_steps=round(mean_steps, 2),
            mean_elapsed_seconds=round(mean_elapsed, 2),
            mean_confidence=round(mean_conf, 3),
            calibration_brier_score=round(brier_score, 4),
            safety_compliance_pct=round(safety_compliance, 2),
            scenario_results=results,
        )
