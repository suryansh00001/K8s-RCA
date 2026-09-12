"""
PersistentVolumeClaim Volume Mount Contention incident scenario.
"""

from .base_scenario import BenchmarkScenario
from ..types import Incident, IncidentClass
from ..providers.simulator import SimulatedClusterProvider


class PVCMountContentionScenario(BenchmarkScenario):
    """
    Scenario: Pod stuck in ContainerCreating due to ReadWriteOnce PVC volume mount contention
    across multiple cluster nodes.
    """

    def __init__(self):
        super().__init__(
            id="sc-09-pvc-mount-contention",
            name="Analytics Worker PVC Multi-Attach Contention",
            incident_class=IncidentClass.STORAGE_FAILURE,
            description="Analytics worker pod is stuck in ContainerCreating waiting for persistent volume attachment.",
            ground_truth_root_cause="PersistentVolumeClaim 'analytics-data-pvc' has ReadWriteOnce access mode and remains locked by old terminating pod on node-worker-1, blocking node-worker-2 from attaching the volume.",
            expected_keywords=["PersistentVolumeClaim", "FailedAttachVolume", "Multi-Attach", "ReadWriteOnce", "analytics-data-pvc"],
            incident=Incident(
                id="inc-storage-009",
                title="analytics-worker pod stuck in ContainerCreating",
                description="Analytics worker pod is failing to start with volume attachment timeout.",
                namespace="analytics",
                affected_service="analytics-worker",
                symptom_class=IncidentClass.STORAGE_FAILURE,
            ),
        )

    def build_cluster(self) -> SimulatedClusterProvider:
        sim = SimulatedClusterProvider(name="prod-cluster")
        ns = "analytics"

        # The stuck pod
        sim.add_resource("Pod", "analytics-worker-pod-1", ns, {
            "apiVersion": "v1",
            "kind": "Pod",
            "metadata": {
                "name": "analytics-worker-pod-1",
                "namespace": ns,
                "labels": {"app": "analytics-worker"},
            },
            "spec": {
                "nodeName": "node-worker-2",
                "volumes": [
                    {
                        "name": "data-volume",
                        "persistentVolumeClaim": {"claimName": "analytics-data-pvc"},
                    }
                ],
                "containers": [
                    {
                        "name": "worker",
                        "image": "analytics-worker:v1.8.0",
                        "volumeMounts": [{"name": "data-volume", "mountPath": "/var/data"}],
                    }
                ],
            },
            "status": {
                "phase": "Pending",
                "containerStatuses": [
                    {
                        "name": "worker",
                        "ready": False,
                        "state": {
                            "waiting": {
                                "reason": "ContainerCreating",
                                "message": "waiting for volume attachment",
                            }
                        },
                    }
                ],
            },
        })

        # The PVC manifest
        sim.add_resource("PersistentVolumeClaim", "analytics-data-pvc", ns, {
            "apiVersion": "v1",
            "kind": "PersistentVolumeClaim",
            "metadata": {
                "name": "analytics-data-pvc",
                "namespace": ns,
            },
            "spec": {
                "accessModes": ["ReadWriteOnce"],
                "resources": {"requests": {"storage": "100Gi"}},
                "storageClassName": "standard-rwo",
                "volumeName": "pvc-analytics-100gb",
            },
            "status": {
                "phase": "Bound",
            },
        })

        # Warning Events from attachdetach-controller and kubelet
        sim.add_event(
            reason="FailedAttachVolume",
            message="Multi-Attach error for volume \"pvc-analytics-100gb\" Volume is already exclusively attached to one node (node-worker-1) and can't be attached to another (node-worker-2)",
            involved_kind="Pod",
            involved_name="analytics-worker-pod-1",
            namespace=ns,
            event_type="Warning",
            count=8,
        )

        sim.add_event(
            reason="FailedMount",
            message="Unable to attach or mount volumes: timed out waiting for the condition",
            involved_kind="Pod",
            involved_name="analytics-worker-pod-1",
            namespace=ns,
            event_type="Warning",
            count=5,
        )

        sim.add_logs("analytics-worker-pod-1", ns, "Error from server (BadRequest): container \"worker\" in pod \"analytics-worker-pod-1\" is waiting to start: ContainerCreating")

        return sim
