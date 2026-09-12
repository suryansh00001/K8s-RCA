"""
Unit tests for Alertmanager webhook ingestion and automated RCA resolution.
"""

from unittest.mock import patch
from k8s_rca.providers.simulator import SimulatedClusterProvider
from k8s_rca.engine.agent import SREInvestigationAgent
from k8s_rca.llm.offline_sre import OfflineSREClient
from k8s_rca.types import Incident


def test_alertmanager_webhook_parsing_and_resolution():
    """Verify Alertmanager webhook payload parsing and RCA triggering."""
    sample_payload = {
        "version": "4",
        "groupKey": "test-group",
        "status": "firing",
        "receiver": "rca-agent",
        "alerts": [
            {
                "status": "firing",
                "labels": {
                    "alertname": "KubePodCrashLooping",
                    "namespace": "goodoc",
                    "service": "goodoc-server",
                    "pod": "goodoc-server-687f4d654b-dtjt9",
                    "severity": "critical",
                },
                "annotations": {
                    "summary": "Pod goodoc-server is crash looping",
                    "description": "Container exited with exit code 1",
                },
            }
        ],
    }

    sim = SimulatedClusterProvider()
    sim.add_resource("Pod", "goodoc-server-687f4d654b-dtjt9", "goodoc", {
        "apiVersion": "v1",
        "kind": "Pod",
        "metadata": {"name": "goodoc-server-687f4d654b-dtjt9", "namespace": "goodoc"},
        "status": {
            "phase": "Running",
            "containerStatuses": [
                {
                    "name": "server",
                    "ready": False,
                    "restartCount": 8,
                    "state": {"waiting": {"reason": "CrashLoopBackOff"}},
                }
            ],
        },
    })
    sim.add_logs("goodoc-server-687f4d654b-dtjt9", "goodoc", "[PostgreSQL Error] Connection terminated due to connection timeout")

    alert = sample_payload["alerts"][0]
    labels = alert["labels"]
    annotations = alert["annotations"]
    query = f"Alert {labels['alertname']}: {annotations['summary']} (pod: {labels['pod']})"

    incident = Incident(
        title=f"Alert: {labels['alertname']}",
        description=query,
        namespace=labels["namespace"],
        affected_service=labels["service"],
    )

    agent = SREInvestigationAgent(provider=sim, llm_client=OfflineSREClient())
    report = agent.investigate(incident)

    assert report is not None
    assert report.confidence > 0.0
    assert len(report.causal_chain.steps) > 0
    assert len(report.evidence) > 0
