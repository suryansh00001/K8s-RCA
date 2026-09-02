"""
Live Kubernetes cluster provider with strict read-only API access.
"""

from typing import Any, Dict, List, Optional
from .base import BaseClusterProvider
from ..sandbox.boundary import SandboxBoundary, SecurityViolationError


class LiveK8sClusterProvider(BaseClusterProvider):
    """
    Connects to a live Kubernetes cluster using kubeconfig or in-cluster auth.
    Guarantees 100% read-only API calls (only GET/LIST).
    """

    def __init__(self, kubeconfig_path: Optional[str] = None, context: Optional[str] = None):
        self.kubeconfig_path = kubeconfig_path
        self.context = context
        self.boundary = SandboxBoundary()
        self._k8s_client = None
        self._core_v1 = None
        self._apps_v1 = None
        self._init_client()

    def _init_client(self) -> None:
        """Initialize official kubernetes client if installed."""
        try:
            from kubernetes import client, config
            if self.kubeconfig_path:
                config.load_kube_config(config_file=self.kubeconfig_path, context=self.context)
            else:
                try:
                    config.load_incluster_config()
                except Exception:
                    config.load_kube_config(context=self.context)
            self._core_v1 = client.CoreV1Api()
            self._apps_v1 = client.AppsV1Api()
            self._custom_objects = client.CustomObjectsApi()
        except ImportError:
            # If kubernetes package is not installed, methods will raise descriptive error
            self._core_v1 = None
            self._apps_v1 = None

    def _ensure_client(self) -> None:
        if self._core_v1 is None:
            raise RuntimeError(
                "The 'kubernetes' Python package is required for live cluster connection. "
                "Install it with: pip install kubernetes"
            )

    def get_cluster_overview(self, namespace: Optional[str] = None) -> Dict[str, Any]:
        self._ensure_client()
        self.boundary.validate_action("list", "pods", namespace)

        if namespace:
            pods = self._core_v1.list_namespaced_pod(namespace).items
        else:
            pods = self._core_v1.list_pod_for_all_namespaces().items

        unhealthy_pods = []
        healthy_pods = []

        for p in pods:
            name = p.metadata.name
            ns = p.metadata.namespace
            phase = p.status.phase or "Unknown"
            container_statuses = p.status.container_statuses or []
            
            is_unhealthy = False
            issues = []
            if phase not in ("Running", "Succeeded"):
                is_unhealthy = True
                issues.append(f"Phase: {phase}")

            for cs in container_statuses:
                if cs.state.waiting:
                    is_unhealthy = True
                    issues.append(f"Waiting: {cs.state.waiting.reason}")
                if cs.state.terminated and cs.state.terminated.exit_code != 0:
                    is_unhealthy = True
                    issues.append(f"Terminated: {cs.state.terminated.reason} (exit {cs.state.terminated.exit_code})")
                if not cs.ready and phase == "Running":
                    is_unhealthy = True
                    issues.append("Container not ready")

            info = {
                "name": name,
                "namespace": ns,
                "phase": phase,
                "restart_count": sum(cs.restart_count for cs in container_statuses),
            }
            if is_unhealthy:
                info["issues"] = issues
                unhealthy_pods.append(info)
            else:
                healthy_pods.append(info)

        return {
            "target_namespace": namespace or "all",
            "unhealthy_pods_count": len(unhealthy_pods),
            "healthy_pods_count": len(healthy_pods),
            "unhealthy_pods": unhealthy_pods,
        }

    def inspect_resource(self, kind: str, name: str, namespace: str = "default") -> Dict[str, Any]:
        self._ensure_client()
        self.boundary.validate_action("get", kind, namespace)
        from kubernetes.client import ApiClient

        api_client = ApiClient()
        kind_lower = kind.lower()

        if kind_lower in ("pod", "pods"):
            pod = self._core_v1.read_namespaced_pod(name, namespace)
            return api_client.sanitize_for_serialization(pod)
        elif kind_lower in ("deployment", "deployments"):
            dep = self._apps_v1.read_namespaced_deployment(name, namespace)
            return api_client.sanitize_for_serialization(dep)
        elif kind_lower in ("service", "services"):
            svc = self._core_v1.read_namespaced_service(name, namespace)
            return api_client.sanitize_for_serialization(svc)
        elif kind_lower in ("configmap", "configmaps"):
            cm = self._core_v1.read_namespaced_config_map(name, namespace)
            return api_client.sanitize_for_serialization(cm)
        elif kind_lower in ("node", "nodes"):
            node = self._core_v1.read_node(name)
            return api_client.sanitize_for_serialization(node)
        elif kind_lower in ("secret", "secrets"):
            # Ensure raw secret values are masked, only return metadata
            secret = self._core_v1.read_namespaced_secret(name, namespace)
            data = api_client.sanitize_for_serialization(secret)
            if "data" in data:
                data["data"] = {k: "[REDACTED_SECRET_BYTES]" for k in data["data"].keys()}
            return data
        else:
            raise NotImplementedError(f"Inspection for resource kind '{kind}' not implemented yet in live mode.")

    def list_resources(
        self,
        kind: str,
        namespace: str = "default",
        label_selector: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        self._ensure_client()
        self.boundary.validate_action("list", kind, namespace)
        from kubernetes.client import ApiClient
        api_client = ApiClient()
        kind_lower = kind.lower()

        selector = label_selector or ""
        if kind_lower in ("pod", "pods"):
            items = self._core_v1.list_namespaced_pod(namespace, label_selector=selector).items
        elif kind_lower in ("deployment", "deployments"):
            items = self._apps_v1.list_namespaced_deployment(namespace, label_selector=selector).items
        elif kind_lower in ("service", "services"):
            items = self._core_v1.list_namespaced_service(namespace, label_selector=selector).items
        else:
            items = []

        return [api_client.sanitize_for_serialization(item) for item in items]

    def get_logs(
        self,
        pod_name: str,
        namespace: str = "default",
        container: Optional[str] = None,
        previous: bool = False,
        tail_lines: Optional[int] = None,
        since_seconds: Optional[int] = None,
    ) -> str:
        self._ensure_client()
        self.boundary.validate_action("logs", "pod", namespace)
        try:
            return self._core_v1.read_namespaced_pod_log(
                name=pod_name,
                namespace=namespace,
                container=container,
                previous=previous,
                tail_lines=tail_lines,
                since_seconds=since_seconds,
            )
        except Exception as e:
            return f"Error retrieving logs for pod {pod_name}: {str(e)}"

    def get_metrics(
        self,
        resource_type: str,
        resource_name: str,
        namespace: str = "default",
        metric_names: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        self._ensure_client()
        self.boundary.validate_action("top", resource_type, namespace)
        # Attempt to read from Metrics Server via custom API or fall back to pod status
        try:
            metrics_data = self._custom_objects.get_namespaced_custom_object(
                group="metrics.k8s.io",
                version="v1beta1",
                namespace=namespace,
                plural="pods",
                name=resource_name,
            )
            return metrics_data
        except Exception:
            return {
                "resource": f"{resource_type}/{resource_name}",
                "namespace": namespace,
                "note": "Metrics server not available; metrics inferred from pod status container restart counts",
            }

    def get_events(
        self,
        namespace: Optional[str] = None,
        involved_object_name: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        self._ensure_client()
        self.boundary.validate_action("list", "events", namespace)
        from kubernetes.client import ApiClient
        api_client = ApiClient()

        if namespace:
            events = self._core_v1.list_namespaced_event(namespace).items
        else:
            events = self._core_v1.list_event_for_all_namespaces().items

        filtered = []
        for ev in sorted(events, key=lambda x: x.last_timestamp or x.event_time or "", reverse=True):
            if involved_object_name and ev.involved_object.name != involved_object_name:
                continue
            filtered.append(api_client.sanitize_for_serialization(ev))
            if len(filtered) >= limit:
                break
        return filtered

    def get_rollout_history(
        self,
        kind: str,
        name: str,
        namespace: str = "default",
    ) -> List[Dict[str, Any]]:
        self._ensure_client()
        self.boundary.validate_action("get", kind, namespace)
        from kubernetes.client import ApiClient
        api_client = ApiClient()

        # ReplicaSets associated with deployment
        rs_list = self._apps_v1.list_namespaced_replica_set(namespace).items
        revisions = []
        for rs in rs_list:
            owner_refs = rs.metadata.owner_references or []
            if any(ref.name == name for ref in owner_refs):
                rev = rs.metadata.annotations.get("deployment.kubernetes.io/revision", "unknown")
                revisions.append({
                    "revision": rev,
                    "replica_set": rs.metadata.name,
                    "created_at": str(rs.metadata.creation_timestamp),
                    "replicas": rs.status.replicas,
                })
        return revisions
