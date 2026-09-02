"""
Resource Inspector tool for deep querying of Kubernetes resources and relationships.
"""

from typing import Any, Dict, List, Optional
from .registry import sre_tool
from ..providers.base import BaseClusterProvider


class ResourceInspector:
    """Provides tools for discovering and inspecting Kubernetes workloads and configurations."""

    def __init__(self, provider: BaseClusterProvider):
        self.provider = provider

    @sre_tool(
        name="get_cluster_overview",
        description="Fetch a high-level health overview of the cluster or specific namespace, including counts of healthy and unhealthy workloads.",
        parameters={
            "type": "object",
            "properties": {
                "namespace": {
                    "type": "string",
                    "description": "Kubernetes namespace to filter overview (optional; defaults to all namespaces).",
                }
            },
            "required": [],
        },
    )
    def get_cluster_overview(self, namespace: Optional[str] = None) -> Dict[str, Any]:
        return self.provider.get_cluster_overview(namespace=namespace)

    @sre_tool(
        name="inspect_resource",
        description="Deeply inspect a specific Kubernetes resource manifest, specification, and status (e.g., Pod, Deployment, Service, ConfigMap, Node).",
        parameters={
            "type": "object",
            "properties": {
                "kind": {
                    "type": "string",
                    "description": "Resource kind (e.g. Pod, Deployment, Service, ConfigMap, Node, StatefulSet).",
                },
                "name": {
                    "type": "string",
                    "description": "Name of the resource to inspect.",
                },
                "namespace": {
                    "type": "string",
                    "description": "Namespace of the resource (default: 'default').",
                },
            },
            "required": ["kind", "name"],
        },
    )
    def inspect_resource(self, kind: str, name: str, namespace: str = "default") -> Dict[str, Any]:
        return self.provider.inspect_resource(kind=kind, name=name, namespace=namespace)

    @sre_tool(
        name="list_resources",
        description="List Kubernetes resources of a given kind with optional label selector filtering.",
        parameters={
            "type": "object",
            "properties": {
                "kind": {
                    "type": "string",
                    "description": "Resource kind to list (e.g. Pod, Deployment, Service, ConfigMap).",
                },
                "namespace": {
                    "type": "string",
                    "description": "Namespace to list from (default: 'default').",
                },
                "label_selector": {
                    "type": "string",
                    "description": "Label selector string (e.g., 'app=checkout' or 'tier=backend').",
                },
            },
            "required": ["kind"],
        },
    )
    def list_resources(
        self,
        kind: str,
        namespace: str = "default",
        label_selector: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        return self.provider.list_resources(kind=kind, namespace=namespace, label_selector=label_selector)

    @sre_tool(
        name="inspect_workload_topology",
        description="Inspect the architectural dependency graph for a workload (Service -> Deployment -> ReplicaSets -> Pods -> ConfigMaps/Secrets metadata).",
        parameters={
            "type": "object",
            "properties": {
                "service_name": {
                    "type": "string",
                    "description": "Name of the service or deployment to trace.",
                },
                "namespace": {
                    "type": "string",
                    "description": "Namespace of the workload (default: 'default').",
                },
            },
            "required": ["service_name"],
        },
    )
    def inspect_workload_topology(self, service_name: str, namespace: str = "default") -> Dict[str, Any]:
        """Traverse the relationship hierarchy for a service."""
        svc = self.provider.inspect_resource("Service", service_name, namespace)
        dep = self.provider.inspect_resource("Deployment", service_name, namespace)
        
        # Match pods
        pods = self.provider.list_resources("Pod", namespace=namespace, label_selector=f"app={service_name}")
        if not pods:
            # Fallback to general list
            all_pods = self.provider.list_resources("Pod", namespace=namespace)
            pods = [p for p in all_pods if service_name in p.get("metadata", {}).get("name", "")]

        return {
            "target": service_name,
            "namespace": namespace,
            "service_found": "error" not in svc,
            "deployment_found": "error" not in dep,
            "associated_pods_count": len(pods),
            "pods": [
                {
                    "name": p.get("metadata", {}).get("name"),
                    "phase": p.get("status", {}).get("phase"),
                    "restart_count": sum(
                        cs.get("restartCount", 0) for cs in p.get("status", {}).get("containerStatuses", [])
                    ),
                }
                for p in pods
            ],
        }
