"""
High-fidelity Simulated Kubernetes Cluster Provider for offline testing, benchmarks, and sandboxing.
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from .base import BaseClusterProvider


class SimulatedClusterProvider(BaseClusterProvider):
    """
    In-memory simulated Kubernetes cluster capable of executing all standard read-only
    inspections, logs, events, metrics timeseries, and rollout histories.
    """

    def __init__(self, name: str = "simulated-cluster"):
        self.name = name
        self.resources: Dict[str, Dict[str, Any]] = {}
        self.logs: Dict[str, str] = {}
        self.metrics: Dict[str, Dict[str, Any]] = {}
        self.events: List[Dict[str, Any]] = []
        self.rollouts: Dict[str, List[Dict[str, Any]]] = {}
        self.traces: List[Dict[str, Any]] = []

    def _res_key(self, kind: str, name: str, namespace: str = "default") -> str:
        return f"{kind.lower()}/{namespace}/{name}"

    def _log_key(self, pod_name: str, namespace: str, container: Optional[str], previous: bool) -> str:
        c_name = container or "main"
        return f"{namespace}/{pod_name}/{c_name}/{'prev' if previous else 'curr'}"

    def _metric_key(self, resource_type: str, resource_name: str, namespace: str) -> str:
        return f"{resource_type.lower()}/{namespace}/{resource_name}"

    def add_resource(self, kind: str, name: str, namespace: str, manifest: Dict[str, Any]) -> None:
        """Seed a Kubernetes resource manifest."""
        key = self._res_key(kind, name, namespace)
        self.resources[key] = manifest

    def add_logs(
        self,
        pod_name: str,
        namespace: str,
        logs: str,
        container: Optional[str] = None,
        previous: bool = False,
    ) -> None:
        """Seed logs for a pod container."""
        key = self._log_key(pod_name, namespace, container, previous)
        self.logs[key] = logs

    def add_metrics(
        self,
        resource_type: str,
        resource_name: str,
        namespace: str,
        metrics_data: Dict[str, Any],
    ) -> None:
        """Seed timeseries or snapshot metrics."""
        key = self._metric_key(resource_type, resource_name, namespace)
        self.metrics[key] = metrics_data

    def add_event(
        self,
        reason: str,
        message: str,
        involved_kind: str,
        involved_name: str,
        namespace: str = "default",
        event_type: str = "Warning",
        timestamp_offset_seconds: int = 0,
        count: int = 1,
    ) -> None:
        """Seed a Kubernetes Event."""
        t = datetime.utcnow() + timedelta(seconds=timestamp_offset_seconds)
        self.events.append({
            "type": event_type,
            "reason": reason,
            "message": message,
            "involvedObject": {
                "kind": involved_kind,
                "name": involved_name,
                "namespace": namespace,
            },
            "firstTimestamp": (t - timedelta(minutes=5)).isoformat(),
            "lastTimestamp": t.isoformat(),
            "count": count,
        })

    def add_rollout_revision(
        self,
        kind: str,
        name: str,
        namespace: str,
        revision: int,
        change_cause: str,
        diff_summary: str,
        applied_at: Optional[datetime] = None,
    ) -> None:
        """Seed rollout revision history."""
        key = self._res_key(kind, name, namespace)
        if key not in self.rollouts:
            self.rollouts[key] = []
        self.rollouts[key].append({
            "revision": revision,
            "change_cause": change_cause,
            "diff_summary": diff_summary,
            "applied_at": (applied_at or datetime.utcnow()).isoformat(),
        })

    def add_trace(
        self,
        trace_id: str,
        root_service: str,
        root_operation: str,
        total_duration_ms: float,
        status_code: int = 200,
        spans: Optional[List[Dict[str, Any]]] = None,
        has_error: bool = False,
        error_summary: Optional[str] = None,
    ) -> None:
        """Seed a distributed trace with span waterfall."""
        self.traces.append({
            "trace_id": trace_id,
            "root_service": root_service,
            "root_operation": root_operation,
            "total_duration_ms": total_duration_ms,
            "status_code": status_code,
            "has_error": has_error or (status_code >= 400),
            "error_summary": error_summary,
            "spans": spans or [],
            "timestamp": datetime.utcnow().isoformat(),
        })

    # --- BaseClusterProvider Implementation ---

    def get_cluster_overview(self, namespace: Optional[str] = None) -> Dict[str, Any]:
        """Summarize resources, counts, and unhealthy pods."""
        unhealthy_pods = []
        healthy_pods = []
        all_kinds = {}

        for key, res in self.resources.items():
            kind, ns, name = key.split("/", 2)
            if namespace and ns != namespace:
                continue

            all_kinds[kind] = all_kinds.get(kind, 0) + 1

            if kind.lower() == "pod":
                status = res.get("status", {})
                phase = status.get("phase", "Unknown")
                container_statuses = status.get("containerStatuses", [])
                
                is_unhealthy = False
                unhealthy_reasons = []

                if phase not in ("Running", "Succeeded"):
                    is_unhealthy = True
                    unhealthy_reasons.append(f"Phase: {phase}")

                for cs in container_statuses:
                    waiting = cs.get("state", {}).get("waiting")
                    terminated = cs.get("state", {}).get("terminated")
                    ready = cs.get("ready", False)

                    if waiting:
                        is_unhealthy = True
                        unhealthy_reasons.append(f"Waiting: {waiting.get('reason')} ({waiting.get('message', '')})")
                    if terminated and terminated.get("exitCode", 0) != 0:
                        is_unhealthy = True
                        unhealthy_reasons.append(f"Terminated: {terminated.get('reason')} (ExitCode {terminated.get('exitCode')})")
                    if not ready and phase == "Running":
                        is_unhealthy = True
                        unhealthy_reasons.append("Ready condition is False (Probe failure)")

                pod_info = {
                    "name": name,
                    "namespace": ns,
                    "phase": phase,
                    "restart_count": sum(cs.get("restartCount", 0) for cs in container_statuses),
                }

                if is_unhealthy:
                    pod_info["issues"] = unhealthy_reasons
                    unhealthy_pods.append(pod_info)
                else:
                    healthy_pods.append(pod_info)

        return {
            "cluster_name": self.name,
            "target_namespace": namespace or "all",
            "resource_counts": all_kinds,
            "unhealthy_pods_count": len(unhealthy_pods),
            "healthy_pods_count": len(healthy_pods),
            "unhealthy_pods": unhealthy_pods,
            "recent_warning_events_count": len([e for e in self.events if e.get("type") == "Warning"]),
        }

    def inspect_resource(self, kind: str, name: str, namespace: str = "default") -> Dict[str, Any]:
        """Fetch resource manifest and status."""
        key = self._res_key(kind, name, namespace)
        if key in self.resources:
            return self.resources[key]
        return {"error": f"Resource not found: {kind}/{name} in namespace {namespace}"}

    def list_resources(
        self,
        kind: str,
        namespace: str = "default",
        label_selector: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """List resources of given kind."""
        results = []
        kind_lower = kind.lower()
        for key, res in self.resources.items():
            k, ns, _ = key.split("/", 2)
            if k == kind_lower and (namespace == "all" or ns == namespace):
                # Basic label matching if specified
                if label_selector:
                    labels = res.get("metadata", {}).get("labels", {})
                    # selector format: "app=checkout"
                    if "=" in label_selector:
                        sk, sv = label_selector.split("=", 1)
                        if labels.get(sk.strip()) != sv.strip():
                            continue
                results.append(res)
        return results

    def get_logs(
        self,
        pod_name: str,
        namespace: str = "default",
        container: Optional[str] = None,
        previous: bool = False,
        tail_lines: Optional[int] = None,
        since_seconds: Optional[int] = None,
    ) -> str:
        """Fetch logs from simulated store."""
        key = self._log_key(pod_name, namespace, container, previous)
        if key in self.logs:
            logs = self.logs[key]
            if tail_lines:
                lines = logs.strip().splitlines()
                return "\n".join(lines[-tail_lines:])
            return logs

        # Fallback: check without container specified
        key_fallback = self._log_key(pod_name, namespace, None, previous)
        if key_fallback in self.logs:
            return self.logs[key_fallback]

        # Fallback: if previous requested but not found, check current logs
        if previous:
            key_curr = self._log_key(pod_name, namespace, container, False)
            if key_curr in self.logs:
                return self.logs[key_curr]
            key_curr_fb = self._log_key(pod_name, namespace, None, False)
            if key_curr_fb in self.logs:
                return self.logs[key_curr_fb]

        return f"(No {'previous ' if previous else ''}logs recorded for pod {pod_name} container {container or 'main'})"


    def get_metrics(
        self,
        resource_type: str,
        resource_name: str,
        namespace: str = "default",
        metric_names: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Fetch metrics data for resource."""
        key = self._metric_key(resource_type, resource_name, namespace)
        if key in self.metrics:
            data = self.metrics[key]
            if metric_names:
                return {k: v for k, v in data.items() if k in metric_names}
            return data
        return {
            "resource": f"{resource_type}/{resource_name}",
            "namespace": namespace,
            "status": "No metrics available for target resource",
        }

    def get_events(
        self,
        namespace: Optional[str] = None,
        involved_object_name: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Fetch chronological events."""
        matched = []
        for event in sorted(self.events, key=lambda x: x.get("lastTimestamp", ""), reverse=True):
            obj = event.get("involvedObject", {})
            if namespace and obj.get("namespace") != namespace:
                continue
            if involved_object_name and obj.get("name") != involved_object_name:
                continue
            matched.append(event)
            if len(matched) >= limit:
                break
        return matched

    def get_rollout_history(
        self,
        kind: str,
        name: str,
        namespace: str = "default",
    ) -> List[Dict[str, Any]]:
        """Fetch rollout revisions."""
        key = self._res_key(kind, name, namespace)
        return self.rollouts.get(key, [])

    def get_traces(
        self,
        service_name: Optional[str] = None,
        trace_id: Optional[str] = None,
        min_duration_ms: Optional[float] = None,
        status_code: Optional[int] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """Fetch distributed traces matching optional filters."""
        results = []
        for t in self.traces:
            if trace_id and t.get("trace_id") != trace_id:
                continue
            if min_duration_ms and t.get("total_duration_ms", 0) < min_duration_ms:
                continue
            if status_code and t.get("status_code") != status_code:
                continue
            if service_name:
                # Matches either root service or any span service
                services = {t.get("root_service")} | {s.get("service_name") for s in t.get("spans", [])}
                if service_name not in services:
                    continue
            results.append(t)
            if len(results) >= limit:
                break
        return results
