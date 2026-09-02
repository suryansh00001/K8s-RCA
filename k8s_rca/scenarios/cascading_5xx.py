"""
Cascading 5xx Application Error Spike benchmark scenario.
"""

from .base_scenario import BenchmarkScenario
from ..types import Incident, IncidentClass
from ..providers.simulator import SimulatedClusterProvider


class Cascading5xxScenario(BenchmarkScenario):
    """
    Scenario matching the specification exemplar:
    "The checkout service has experienced a sudden increase in 5xx errors."
    Underlying root cause: Database connection pool exhaustion.
    """

    def __init__(self):
        super().__init__(
            id="sc-07-cascading-5xx",
            name="Checkout Service 5xx Error Spike",
            incident_class=IncidentClass.APPLICATION_ERROR_SPIKE,
            description="The checkout service has experienced a sudden increase in 5xx errors.",
            ground_truth_root_cause="PostgreSQL database connection pool exhaustion (max_connections=50 reached) causing connection lease timeouts and downstream HTTP 500 error spikes in checkout service.",
            expected_keywords=["database", "connection", "pool", "exhausted", "500", "checkout"],
            incident=Incident(
                id="inc-checkout-5xx",
                title="The checkout service has experienced a sudden increase in 5xx errors",
                description="Elevated rate of HTTP 500 responses detected across all checkout service pods in namespace 'prod'.",
                namespace="prod",
                affected_service="checkout-service",
                symptom_class=IncidentClass.APPLICATION_ERROR_SPIKE,
            ),
        )

    def build_cluster(self) -> SimulatedClusterProvider:
        sim = SimulatedClusterProvider(name="prod-cluster")
        ns = "prod"

        sim.add_resource("Deployment", "checkout-service", ns, {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {"name": "checkout-service", "namespace": ns, "labels": {"app": "checkout-service"}},
            "spec": {
                "replicas": 2,
                "template": {
                    "spec": {
                        "containers": [{
                            "name": "checkout-service",
                            "image": "registry.internal/checkout:v4.2.0",
                        }]
                    }
                }
            },
            "status": {"replicas": 2, "readyReplicas": 2},
        })

        sim.add_resource("Pod", "checkout-service-pod-1", ns, {
            "apiVersion": "v1",
            "kind": "Pod",
            "metadata": {"name": "checkout-service-pod-1", "namespace": ns, "labels": {"app": "checkout-service"}},
            "spec": {"containers": [{"name": "checkout-service"}]},
            "status": {
                "phase": "Running",
                "containerStatuses": [{"name": "checkout-service", "ready": True, "restartCount": 0}],
            }
        })

        sim.add_resource("Pod", "checkout-service-pod-2", ns, {
            "apiVersion": "v1",
            "kind": "Pod",
            "metadata": {"name": "checkout-service-pod-2", "namespace": ns, "labels": {"app": "checkout-service"}},
            "spec": {"containers": [{"name": "checkout-service"}]},
            "status": {
                "phase": "Running",
                "containerStatuses": [{"name": "checkout-service", "ready": True, "restartCount": 0}],
            }
        })

        logs = (
            "2026-09-02T11:40:00Z [INFO] POST /api/checkout/pay - order #94821\n"
            "2026-09-02T11:40:02Z [WARN] DB connection pool active leases: 50/50 (all acquired)\n"
            "2026-09-02T11:40:05Z [ERROR] HTTP 500 Internal Server Error: Database connection pool exhausted (max_connections=50 reached). Connection lease acquisition timed out after 3000ms.\n"
            "2026-09-02T11:40:06Z [ERROR] Transaction rollback failed: No active connection\n"
        )
        sim.add_logs("checkout-service-pod-1", ns, logs)
        sim.add_logs("checkout-service-pod-2", ns, logs)

        sim.add_metrics("pod", "checkout-service-pod-1", ns, {
            "error_rate_pct": 34.2,
            "requests_per_sec": 450,
            "cpu_usage_mcores": 180,
            "memory_usage_mb": 310.0,
        })

        sim.add_event(
            reason="Unhealthy",
            message="Readiness probe warning: connection latency degraded",
            involved_kind="Pod",
            involved_name="checkout-service-pod-1",
            namespace=ns,
            event_type="Warning",
            count=3,
        )

        return sim
