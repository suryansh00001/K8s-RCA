"""
Base abstract interface for Kubernetes cluster providers.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class BaseClusterProvider(ABC):
    """
    Abstract contract for communicating with Kubernetes environments (simulated or live).
    All methods are strictly read-only.
    """

    @abstractmethod
    def get_cluster_overview(self, namespace: Optional[str] = None) -> Dict[str, Any]:
        """Fetch high-level cluster health and summary across namespaces or target namespace."""
        pass

    @abstractmethod
    def inspect_resource(self, kind: str, name: str, namespace: str = "default") -> Dict[str, Any]:
        """Get full spec, status, and metadata for a specific resource."""
        pass

    @abstractmethod
    def list_resources(
        self,
        kind: str,
        namespace: str = "default",
        label_selector: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """List resources of a given kind matching optional selectors."""
        pass

    @abstractmethod
    def get_logs(
        self,
        pod_name: str,
        namespace: str = "default",
        container: Optional[str] = None,
        previous: bool = False,
        tail_lines: Optional[int] = None,
        since_seconds: Optional[int] = None,
    ) -> str:
        """Fetch container logs (current or previously crashed container)."""
        pass

    @abstractmethod
    def get_metrics(
        self,
        resource_type: str,
        resource_name: str,
        namespace: str = "default",
        metric_names: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Fetch timeseries or current operational metrics (CPU, memory, restarts, error rates)."""
        pass

    @abstractmethod
    def get_events(
        self,
        namespace: Optional[str] = None,
        involved_object_name: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Fetch Kubernetes events with chronological order."""
        pass

    @abstractmethod
    def get_rollout_history(
        self,
        kind: str,
        name: str,
        namespace: str = "default",
    ) -> List[Dict[str, Any]]:
        """Fetch rollout revisions, manifest diffs, and change history."""
        pass

    @abstractmethod
    def get_traces(
        self,
        service_name: Optional[str] = None,
        trace_id: Optional[str] = None,
        min_duration_ms: Optional[float] = None,
        status_code: Optional[int] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """Fetch distributed traces and spans (Jaeger / OpenTelemetry / simulated)."""
        pass
