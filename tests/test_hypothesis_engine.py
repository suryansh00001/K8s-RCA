"""
Unit tests for Hypothesis Manager and Bayesian updates.
"""

from k8s_rca.engine.hypothesis import HypothesisManager
from k8s_rca.types import Evidence, EvidenceType, HypothesisStatus


def test_hypothesis_lifecycle_and_confidence_scoring():
    manager = HypothesisManager()

    h1 = manager.add_hypothesis("H1", "Application Crash", "Code panic", initial_confidence=0.5)
    h2 = manager.add_hypothesis("H2", "OOMKilled", "Memory leak", initial_confidence=0.5)

    assert h1.confidence == 0.5
    assert h2.confidence == 0.5

    # Record supporting evidence for H2 and refuting evidence for H1
    ev1 = Evidence(
        id="EV-001",
        evidence_type=EvidenceType.LOG,
        source_resource="payment-pod",
        description="Terminated exit code 137 OOMKilled",
        relevance_score=1.0,
    )
    manager.record_evidence(ev1, supports_hyp_ids=["H2"], refutes_hyp_ids=["H1"])

    ranked = manager.get_ranked_hypotheses()
    assert ranked[0].id == "H2"
    assert ranked[0].confidence > 0.60
    assert ranked[1].id == "H1"
    assert ranked[1].confidence < 0.40


def test_hypothesis_apply_update():
    manager = HypothesisManager()
    manager.apply_update({
        "action": "create",
        "id": "H1",
        "title": "Config Error",
        "confidence": 0.4,
    })

    assert "H1" in manager.hypotheses
    assert manager.hypotheses["H1"].title == "Config Error"

    manager.apply_update({
        "action": "update",
        "id": "H1",
        "confidence": 0.95,
        "status": "supported",
        "reasoning": "Confirmed via event logs",
    })

    assert manager.hypotheses["H1"].confidence == 0.95
    assert manager.hypotheses["H1"].status == HypothesisStatus.SUPPORTED
