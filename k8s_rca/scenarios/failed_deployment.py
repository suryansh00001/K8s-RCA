"""
Failed Deployment / Config Error benchmark incident scenario.
"""

from .base_scenario import BenchmarkScenario
from ..types import Incident, IncidentClass
from ..providers.simulator import SimulatedClusterProvider


class FailedDeploymentScenario(BenchmarkScenario):
    """Scenario: Deployment fails to create containers due to missing ConfigMap."""

    def __init__(self):
        super().__init__(
            id="sc-05-failed-deployment",
            name="Notification Service Config Error",
            incident_class=IncidentClass.FAILED_DEPLOYMENT,
            description="Notification service rollout is stalled with CreateContainerConfigError.",
            ground_truth_root_cause="Deployment manifest references a missing ConfigMap 'notification-config-v2' in namespace 'prod', causing CreateContainerConfigError.",
            expected_keywords=["CreateContainerConfigError", "ConfigMap", "notification-config-v2", "not found", "missing"],
            incident=Incident(
                id="inc-deploy-005",
                title="notification-service rollout blocked with config error",
                description="Rollout of notification-service cannot proceed due to container config creation failure.",
                namespace="prod",
                affected_service="notification-service",
                symptom_class=IncidentClass.FAILED_DEPLOYMENT,
            ),
        )

    def build_cluster(self) -> SimulatedClusterProvider:
        sim = SimulatedClusterProvider(name="prod-cluster")
        ns = "prod"

        sim.add_resource("Pod", "notification-service-pod-1", ns, {
            "apiVersion": "v1",
            "kind": "Pod",
            "metadata": {"name": "notification-service-pod-1", "namespace": ns, "labels": {"app": "notification-service"}},
            "spec": {
                "containers": [{
                    "name": "notification-service",
                    "envFrom": [{"configMapRef": {"name": "notification-config-v2"}}],
                }]
            },
            "status": {
                "phase": "Pending",
                "containerStatuses": [{
                    "name": "notification-service",
                    "ready": False,
                    "state": {
                        "waiting": {
                            "reason": "CreateContainerConfigError",
                            "message": "configmap \"notification-config-v2\" not found",
                        }
                    }
                }]
            }
        })

        sim.add_event(
            reason="FailedMount",
            message="configmap \"notification-config-v2\" not found",
            involved_kind="Pod",
            involved_name="notification-service-pod-1",
            namespace=ns,
            event_type="Warning",
            count=10,
        )

        return sim
