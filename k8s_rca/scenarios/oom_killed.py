"""
OOMKilled benchmark incident scenario.
"""

from .base_scenario import BenchmarkScenario
from ..types import Incident, IncidentClass
from ..providers.simulator import SimulatedClusterProvider


class OOMKilledScenario(BenchmarkScenario):
    """Scenario: Container terminated by Linux OOM killer exceeding memory limits under traffic spike."""

    def __init__(self):
        super().__init__(
            id="sc-02-oomkilled",
            name="Payment Gateway OOMKilled",
            incident_class=IncidentClass.OOM_KILLED,
            description="Payment gateway container is crashing repeatedly under load, causing transaction drops.",
            ground_truth_root_cause="Memory exhaustion: in-memory cache allocation exceeded the container limit of 256Mi, triggering Linux kernel cgroup OOM killer (Exit Code 137).",
            expected_keywords=["OOMKilled", "137", "memory", "cgroup", "limit", "exhaustion"],
            incident=Incident(
                id="inc-oom-002",
                title="payment-gateway pods crashing with exit code 137",
                description="payment-gateway pods in namespace 'prod' are restarting repeatedly during peak checkout traffic.",
                namespace="prod",
                affected_service="payment-gateway",
                symptom_class=IncidentClass.OOM_KILLED,
            ),
        )

    def build_cluster(self) -> SimulatedClusterProvider:
        sim = SimulatedClusterProvider(name="prod-cluster")
        ns = "prod"

        # Deployment
        sim.add_resource("Deployment", "payment-gateway", ns, {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {"name": "payment-gateway", "namespace": ns, "labels": {"app": "payment-gateway"}},
            "spec": {
                "replicas": 2,
                "template": {
                    "spec": {
                        "containers": [{
                            "name": "payment-gateway",
                            "image": "registry.internal/payment:v3.1.0",
                            "resources": {
                                "limits": {"memory": "256Mi", "cpu": "500m"},
                                "requests": {"memory": "128Mi", "cpu": "200m"},
                            },
                        }]
                    }
                }
            },
            "status": {"replicas": 2, "readyReplicas": 1, "unavailableReplicas": 1},
        })

        # Pod 1 (Crashing with OOM)
        sim.add_resource("Pod", "payment-gateway-pod-1", ns, {
            "apiVersion": "v1",
            "kind": "Pod",
            "metadata": {"name": "payment-gateway-pod-1", "namespace": ns, "labels": {"app": "payment-gateway"}},
            "spec": {
                "containers": [{
                    "name": "payment-gateway",
                    "resources": {"limits": {"memory": "256Mi"}}
                }]
            },
            "status": {
                "phase": "Running",
                "containerStatuses": [{
                    "name": "payment-gateway",
                    "ready": False,
                    "restartCount": 5,
                    "state": {
                        "waiting": {
                            "reason": "CrashLoopBackOff",
                            "message": "back-off 2m40s restarting failed container",
                        }
                    },
                    "lastState": {
                        "terminated": {
                            "exitCode": 137,
                            "reason": "OOMKilled",
                            "message": "Container memory limit exceeded",
                        }
                    }
                }]
            }
        })

        # Logs
        logs = (
            "2026-09-02T11:50:00Z [INFO] Processing batch tokenization for 12,000 transactions...\n"
            "2026-09-02T11:51:10Z [WARN] Heap allocation reached 248MB / 256MB limit...\n"
            "2026-09-02T11:51:15Z [ERROR] Failed to allocate 12MB buffer for cipher stream: out of memory\n"
            "command terminated with exit code 137\n"
        )
        sim.add_logs("payment-gateway-pod-1", ns, logs, previous=True)
        sim.add_logs("payment-gateway-pod-1", ns, logs, previous=False)

        # Metrics
        sim.add_metrics("pod", "payment-gateway-pod-1", ns, {
            "memory_usage_mb": 256.0,
            "memory_limit_mb": 256.0,
            "cpu_usage_mcores": 210,
            "cpu_throttling_pct": 2.1,
            "restarts": 5,
        })

        # Events
        sim.add_event(
            reason="OOMKilled",
            message="Pod payment-gateway-pod-1 memory limit exceeded (256Mi). Process terminated by cgroup oom-killer.",
            involved_kind="Pod",
            involved_name="payment-gateway-pod-1",
            namespace=ns,
            event_type="Warning",
            count=5,
        )

        return sim
