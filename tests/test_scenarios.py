"""
Integration tests evaluating SRE Investigation Agent across all 7 benchmark incident classes.
"""

import pytest
from k8s_rca.scenarios.registry import get_all_scenarios, get_scenario
from k8s_rca.engine.agent import SREInvestigationAgent
from k8s_rca.llm.offline_sre import OfflineSREClient
from k8s_rca.eval.evaluator import ScenarioEvaluator


def test_all_scenarios_registered():
    scenarios = get_all_scenarios()
    assert len(scenarios) >= 7
    ids = [s.id for s in scenarios]
    assert "sc-01-crashloop" in ids
    assert "sc-02-oomkilled" in ids
    assert "sc-03-failed-probes" in ids
    assert "sc-04-image-pull" in ids
    assert "sc-05-failed-deployment" in ids
    assert "sc-06-resource-throttling" in ids
    assert "sc-07-cascading-5xx" in ids


@pytest.mark.parametrize("scenario_id", [
    "sc-01-crashloop",
    "sc-02-oomkilled",
    "sc-03-failed-probes",
    "sc-04-image-pull",
    "sc-05-failed-deployment",
    "sc-06-resource-throttling",
    "sc-07-cascading-5xx",
])
def test_agent_investigation_on_scenario(scenario_id):
    scenario = get_scenario(scenario_id)
    assert scenario is not None

    cluster = scenario.build_cluster()
    agent = SREInvestigationAgent(provider=cluster, llm_client=OfflineSREClient())
    report = agent.investigate(scenario.incident)

    # Verify RCA report structure
    assert report.incident_id == scenario.incident.id
    assert report.root_cause != ""
    assert report.confidence >= 0.70
    assert len(report.causal_chain.steps) >= 3
    assert len(report.evidence) >= 1
    assert len(report.recommended_actions) >= 1

    # Evaluate with benchmark evaluator
    evaluator = ScenarioEvaluator()
    eval_res = evaluator.evaluate_scenario(scenario, report)

    assert eval_res.is_correct, f"Failed RCA on {scenario_id}. Identified: {report.root_cause} | Ground truth: {scenario.ground_truth_root_cause}"
    assert eval_res.safety_passed
    assert not eval_res.is_false_positive
