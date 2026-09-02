"""
CrashLoopBackOff benchmark incident scenario.
"""

from .base_scenario import BenchmarkScenario
from ..types import Incident, IncidentClass
from ..providers.simulator import SimulatedClusterProvider


class CrashLoopBackOffScenario(BenchmarkScenario):
    """Scenario: Application panicking on startup due to missing environment variable."""

    def __init__(self):
        super().__init__(
            id="sc-01-crashloop",
            name="Auth Service CrashLoopBackOff",
            incident_class=IncidentClass.CRASHLOOP_BACKOFF,
            description="The authentication service pods are in CrashLoopBackOff and failing to start up after a recent deployment revision.",
            ground_truth_root_cause="Application initialization panic due to missing required environment variable JWT_SIGNING_KEY in pod spec.",
            expected_keywords=["panic", "JWT_SIGNING_KEY", "CrashLoopBackOff", "exit", "code 1", "environment"],
            incident=Incident(
                id="inc-crashloop-001",
                title="auth-service pods failing in CrashLoopBackOff",
                description="auth-service pods in namespace 'prod' are restarting repeatedly with CrashLoopBackOff status.",
                namespace="prod",
                affected_service="auth-service",
                symptom_class=IncidentClass.CRASHLOOP_BACKOFF,
            ),
        )

    def build_cluster(self) -> SimulatedClusterProvider:
        sim = SimulatedClusterProvider(name="prod-cluster")
        ns = "prod"

        # Deployment
        sim.add_resource("Deployment", "auth-service", ns, {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {"name": "auth-service", "namespace": ns, "labels": {"app": "auth-service"}},
            "spec": {
                "replicas": 1,
                "template": {
                    "spec": {
                        "containers": [{
                            "name": "auth-service",
                            "image": "registry.internal/auth-service:v1.8.2",
                            "env": [{"name": "ENV", "value": "production"}],
                        }]
                    }
                }
            },
            "status": {"replicas": 1, "readyReplicas": 0, "unavailableReplicas": 1},
        })

        # Pod
        sim.add_resource("Pod", "auth-service-pod-1", ns, {
            "apiVersion": "v1",
            "kind": "Pod",
            "metadata": {"name": "auth-service-pod-1", "namespace": ns, "labels": {"app": "auth-service"}},
            "spec": {
                "containers": [{
                    "name": "auth-service",
                    "image": "registry.internal/auth-service:v1.8.2",
                }]
            },
            "status": {
                "phase": "Running",
                "containerStatuses": [{
                    "name": "auth-service",
                    "ready": False,
                    "restartCount": 8,
                    "state": {
                        "waiting": {
                            "reason": "CrashLoopBackOff",
                            "message": "back-off 5m0s restarting failed container=auth-service pod=auth-service-pod-1_prod",
                        }
                    },
                    "lastState": {
                        "terminated": {
                            "exitCode": 1,
                            "reason": "Error",
                            "finishedAt": "2026-09-02T11:58:00Z",
                        }
                    }
                }]
            }
        })

        # Logs
        crashed_logs = (
            "2026-09-02T11:57:59.102Z [INFO] Initializing auth-service v1.8.2...\n"
            "2026-09-02T11:57:59.105Z [INFO] Reading runtime configuration...\n"
            "2026-09-02T11:57:59.108Z [FATAL] panic: runtime error: missing required environment variable JWT_SIGNING_KEY\n"
            "goroutine 1 [running]:\n"
            "main.loadConfig()\n"
            "\t/app/config.go:42 +0x12a\n"
            "main.main()\n"
            "\t/app/main.go:18 +0x45\n"
        )
        sim.add_logs("auth-service-pod-1", ns, crashed_logs, container="auth-service", previous=True)
        sim.add_logs("auth-service-pod-1", ns, crashed_logs, container="auth-service", previous=False)

        # Events
        sim.add_event(
            reason="BackOff",
            message="Back-off restarting failed container auth-service in pod auth-service-pod-1_prod",
            involved_kind="Pod",
            involved_name="auth-service-pod-1",
            namespace=ns,
            event_type="Warning",
            count=8,
        )

        # Rollout history
        sim.add_rollout_revision(
            kind="Deployment",
            name="auth-service",
            namespace=ns,
            revision=2,
            change_cause="Update auth-service to v1.8.2",
            diff_summary="Updated container image to v1.8.2; removed deprecated legacy SECRET_KEY env",
        )

        return sim
