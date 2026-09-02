"""
ImagePullBackOff benchmark incident scenario.
"""

from .base_scenario import BenchmarkScenario
from ..types import Incident, IncidentClass
from ..providers.simulator import SimulatedClusterProvider


class ImagePullScenario(BenchmarkScenario):
    """Scenario: Deployment rollout fails because container image tag has a typo and does not exist in registry."""

    def __init__(self):
        super().__init__(
            id="sc-04-image-pull",
            name="User Profile ImagePullBackOff",
            incident_class=IncidentClass.IMAGE_PULL_FAILURE,
            description="Deployment rollout is blocked with pods stuck in ImagePullBackOff.",
            ground_truth_root_cause="Container image tag 'v2.4.9-hotfix-typo' does not exist in container registry, causing ErrImagePull / ImagePullBackOff.",
            expected_keywords=["ImagePullBackOff", "ErrImagePull", "manifest unknown", "tag", "image"],
            incident=Incident(
                id="inc-image-004",
                title="user-profile deployment blocked on ImagePullBackOff",
                description="New pods for user-profile deployment cannot start after rollout trigger.",
                namespace="prod",
                affected_service="user-profile",
                symptom_class=IncidentClass.IMAGE_PULL_FAILURE,
            ),
        )

    def build_cluster(self) -> SimulatedClusterProvider:
        sim = SimulatedClusterProvider(name="prod-cluster")
        ns = "prod"

        sim.add_resource("Pod", "user-profile-pod-1", ns, {
            "apiVersion": "v1",
            "kind": "Pod",
            "metadata": {"name": "user-profile-pod-1", "namespace": ns, "labels": {"app": "user-profile"}},
            "spec": {
                "containers": [{
                    "name": "user-profile",
                    "image": "registry.internal/user-profile:v2.4.9-hotfix-typo",
                }]
            },
            "status": {
                "phase": "Pending",
                "containerStatuses": [{
                    "name": "user-profile",
                    "ready": False,
                    "state": {
                        "waiting": {
                            "reason": "ImagePullBackOff",
                            "message": "Back-off pulling image 'registry.internal/user-profile:v2.4.9-hotfix-typo'",
                        }
                    }
                }]
            }
        })

        sim.add_event(
            reason="Failed",
            message="Failed to pull image \"registry.internal/user-profile:v2.4.9-hotfix-typo\": rpc error: code = NotFound desc = manifest unknown",
            involved_kind="Pod",
            involved_name="user-profile-pod-1",
            namespace=ns,
            event_type="Warning",
            count=6,
        )

        sim.add_rollout_revision(
            kind="Deployment",
            name="user-profile",
            namespace=ns,
            revision=5,
            change_cause="Deploy hotfix release",
            diff_summary="Updated image tag from v2.4.8 to v2.4.9-hotfix-typo",
        )

        return sim
