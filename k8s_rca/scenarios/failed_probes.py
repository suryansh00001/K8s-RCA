"""
Failed Readiness/Liveness probe benchmark incident scenario.
"""

from .base_scenario import BenchmarkScenario
from ..types import Incident, IncidentClass
from ..providers.simulator import SimulatedClusterProvider


class FailedProbesScenario(BenchmarkScenario):
    """Scenario: Readiness probe failing due to upstream database timeout, causing traffic shedding."""

    def __init__(self):
        super().__init__(
            id="sc-03-failed-probes",
            name="Inventory Service Readiness Probe Failure",
            incident_class=IncidentClass.FAILED_READINESS_PROBE,
            description="Inventory service endpoint returning 503 Service Unavailable; pods marked Not Ready by Kubelet.",
            ground_truth_root_cause="Readiness probe endpoint /healthz failed with HTTP 500 due to database ping connection timeout exceeding 1000ms threshold.",
            expected_keywords=["readiness", "probe", "healthz", "500", "unready", "timeout"],
            incident=Incident(
                id="inc-probe-003",
                title="inventory-service pods unready due to probe failure",
                description="inventory-service in namespace 'prod' is dropping traffic. Pods remain in Running phase but Ready condition is False.",
                namespace="prod",
                affected_service="inventory-service",
                symptom_class=IncidentClass.FAILED_READINESS_PROBE,
            ),
        )

    def build_cluster(self) -> SimulatedClusterProvider:
        sim = SimulatedClusterProvider(name="prod-cluster")
        ns = "prod"

        sim.add_resource("Pod", "inventory-service-pod-1", ns, {
            "apiVersion": "v1",
            "kind": "Pod",
            "metadata": {"name": "inventory-service-pod-1", "namespace": ns, "labels": {"app": "inventory-service"}},
            "spec": {
                "containers": [{
                    "name": "inventory-service",
                    "readinessProbe": {
                        "httpGet": {"path": "/healthz", "port": 8080},
                        "periodSeconds": 5,
                        "timeoutSeconds": 1,
                        "failureThreshold": 3,
                    }
                }]
            },
            "status": {
                "phase": "Running",
                "conditions": [{"type": "Ready", "status": "False", "reason": "ContainersNotReady"}],
                "containerStatuses": [{
                    "name": "inventory-service",
                    "ready": False,
                    "restartCount": 0,
                    "state": {"running": {"startedAt": "2026-09-02T11:00:00Z"}},
                }]
            }
        })

        logs = (
            "2026-09-02T11:45:10Z [INFO] HTTP GET /healthz requested\n"
            "2026-09-02T11:45:11Z [ERROR] DB Healthcheck: connection ping to postgres.internal timed out after 1000ms\n"
            "2026-09-02T11:45:11Z [WARN] /healthz returning HTTP 500 Internal Server Error: Database Unhealthy\n"
        )
        sim.add_logs("inventory-service-pod-1", ns, logs)

        sim.add_event(
            reason="Unhealthy",
            message="Readiness probe failed: HTTP probe failed with statuscode: 500",
            involved_kind="Pod",
            involved_name="inventory-service-pod-1",
            namespace=ns,
            event_type="Warning",
            count=12,
        )

        return sim
