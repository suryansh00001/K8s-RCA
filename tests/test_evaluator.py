"""
Unit tests for Evaluator and BenchmarkRunner.
"""

from k8s_rca.eval.benchmark_runner import BenchmarkRunner
from k8s_rca.eval.evaluator import ScenarioEvaluator, ScenarioEvalResult
from k8s_rca.llm.offline_sre import OfflineSREClient


def test_benchmark_runner_aggregates_metrics():
    runner = BenchmarkRunner(llm_client=OfflineSREClient())
    metrics = runner.run_all()

    assert metrics.total_scenarios == 7
    assert metrics.correct_scenarios == 7
    assert metrics.rca_accuracy_pct == 100.0
    assert metrics.false_positive_rate_pct == 0.0
    assert metrics.evidence_accuracy_pct >= 90.0
    assert metrics.safety_compliance_pct == 100.0
    assert metrics.calibration_brier_score < 0.10  # Low calibration error is desired


def test_evaluator_empty_list_handling():
    evaluator = ScenarioEvaluator()
    agg = evaluator.aggregate_benchmark([])
    assert agg.total_scenarios == 0
    assert agg.rca_accuracy_pct == 0.0
