"""
Resource throttling / CPU starvation benchmark incident scenario.
"""

from .base_scenario import BenchmarkScenario
from ..types import Incident, IncidentClass
from ..providers.simulator import SimulatedClusterProvider


class ResourceThrottlingScenario(BenchmarkScenario):
    """Scenario: Search API experiencing severe CFS CPU throttling due to overly restrictive limits under load."""

    def __init__(self):
        super().__init__(
            id="sc-06-resource-throttling",
            name="Search API Severe CPU Throttling",
            incident_class=IncidentClass.RESOURCE_EXHAUSTION,
            description="Search API service experiencing severe response time degradation and 504 Gateway Timeouts.",
            ground_truth_root_cause="Restrictive CPU limit of 100m causing >80% CFS CPU throttling on search workers under query volume, resulting in request timeouts.",
            expected_keywords=["CPU_THROTTLING", "throttling", "cpu_throttling_pct", "limit", "starvation", "100m"],
            incident=Incident(
                id="inc-throttle-006",
                title="search-api high latency and gateway timeouts",
                description="search-api latency p99 spiked from 45ms to 4800ms with elevated 504 timeouts.",
                namespace="prod",
                affected_service="search-api",
                symptom_class=IncidentClass.RESOURCE_EXHAUSTION,
            ),
        )

    def build_cluster(self) -> SimulatedClusterProvider:
        sim = SimulatedClusterProvider(name="prod-cluster")
        ns = "prod"

        sim.add_resource("Deployment", "search-api", ns, {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {"name": "search-api", "namespace": ns, "labels": {"app": "search-api"}},
            "spec": {
                "replicas": 1,
                "template": {
                    "spec": {
                        "containers": [{
                            "name": "search-api",
                            "image": "registry.internal/search:v2.1",
                            "resources": {
                                "limits": {"cpu": "100m", "memory": "512Mi"},
                                "requests": {"cpu": "50m", "memory": "256Mi"},
                            }
                        }]
                    }
                }
            },
            "status": {"replicas": 1, "readyReplicas": 1},
        })

        sim.add_resource("Pod", "search-api-pod-1", ns, {
            "apiVersion": "v1",
            "kind": "Pod",
            "metadata": {"name": "search-api-pod-1", "namespace": ns, "labels": {"app": "search-api"}},
            "spec": {
                "containers": [{
                    "name": "search-api",
                    "resources": {"limits": {"cpu": "100m", "memory": "512Mi"}},
                }]
            },
            "status": {
                "phase": "Running",
                "containerStatuses": [{"name": "search-api", "ready": True, "restartCount": 0}],
            }
        })

        sim.add_metrics("pod", "search-api-pod-1", ns, {
            "cpu_usage_mcores": 98,
            "cpu_throttling_pct": 84.5,
            "memory_usage_mb": 220.0,
            "memory_limit_mb": 512.0,
            "error_rate_pct": 28.0,
        })

        logs = (
            "2026-09-02T11:30:00Z [INFO] Processing search query 'winter jackets'...\n"
            "2026-09-02T11:30:04Z [WARN] Query thread took 4820ms to execute token scoring (CPU starving)\n"
            "2026-09-02T11:30:05Z [ERROR] HTTP 504 Gateway Timeout sent to upstream ingress\n"
        )
        sim.add_logs("search-api-pod-1", ns, logs)

        return sim
