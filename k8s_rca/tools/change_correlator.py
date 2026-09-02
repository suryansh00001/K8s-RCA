"""
Change correlator and incident timeline tool for Kubernetes Root-Cause Analysis.
"""

from typing import Any, Dict, List, Optional
from .registry import sre_tool
from ..providers.base import BaseClusterProvider


class ChangeCorrelator:
    """Tool for correlating Kubernetes events, deployment rollouts, and temporal changes."""

    def __init__(self, provider: BaseClusterProvider):
        self.provider = provider

    @sre_tool(
        name="get_event_timeline",
        description="Fetch a chronological list of Kubernetes events (Warnings and Normal) for a namespace or specific resource.",
        parameters={
            "type": "object",
            "properties": {
                "namespace": {
                    "type": "string",
                    "description": "Namespace to filter events (optional).",
                },
                "involved_object_name": {
                    "type": "string",
                    "description": "Specific pod, deployment, or service name to filter events for.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of events to retrieve (default: 30).",
                },
            },
            "required": [],
        },
    )
    def get_event_timeline(
        self,
        namespace: Optional[str] = None,
        involved_object_name: Optional[str] = None,
        limit: int = 30,
    ) -> List[Dict[str, Any]]:
        events = self.provider.get_events(
            namespace=namespace,
            involved_object_name=involved_object_name,
            limit=limit,
        )
        # Format events into readable temporal entries
        formatted = []
        for ev in events:
            obj = ev.get("involvedObject", {})
            formatted.append({
                "timestamp": ev.get("lastTimestamp") or ev.get("firstTimestamp"),
                "type": ev.get("type", "Normal"),
                "reason": ev.get("reason", "Unknown"),
                "resource": f"{obj.get('kind', '')}/{obj.get('name', '')}",
                "count": ev.get("count", 1),
                "message": ev.get("message", ""),
            })
        return formatted

    @sre_tool(
        name="diff_resource_changes",
        description="Inspect rollout revision history and manifest changes for a deployment or daemonset.",
        parameters={
            "type": "object",
            "properties": {
                "kind": {
                    "type": "string",
                    "description": "Resource kind (default: 'Deployment').",
                },
                "name": {
                    "type": "string",
                    "description": "Resource name.",
                },
                "namespace": {
                    "type": "string",
                    "description": "Namespace (default: 'default').",
                },
            },
            "required": ["name"],
        },
    )
    def diff_resource_changes(
        self,
        name: str,
        kind: str = "Deployment",
        namespace: str = "default",
    ) -> Dict[str, Any]:
        history = self.provider.get_rollout_history(kind=kind, name=name, namespace=namespace)
        return {
            "resource": f"{kind}/{name}",
            "namespace": namespace,
            "total_revisions": len(history),
            "revisions": history,
        }

    @sre_tool(
        name="correlate_incident_timeline",
        description="Construct a unified temporal timeline combining rollout changes, pod restarts, warning events, and health probe failures.",
        parameters={
            "type": "object",
            "properties": {
                "service_name": {
                    "type": "string",
                    "description": "Service or deployment name to correlate.",
                },
                "namespace": {
                    "type": "string",
                    "description": "Namespace (default: 'default').",
                },
            },
            "required": ["service_name"],
        },
    )
    def correlate_incident_timeline(
        self,
        service_name: str,
        namespace: str = "default",
    ) -> Dict[str, Any]:
        events = self.provider.get_events(namespace=namespace, involved_object_name=service_name, limit=20)
        rollouts = self.provider.get_rollout_history(kind="Deployment", name=service_name, namespace=namespace)

        timeline_entries = []

        for r in rollouts:
            timeline_entries.append({
                "source": "Rollout",
                "timestamp": r.get("applied_at"),
                "summary": f"Deployment updated (Rev {r.get('revision')}): {r.get('diff_summary')}",
            })

        for ev in events:
            timeline_entries.append({
                "source": "K8sEvent",
                "timestamp": ev.get("lastTimestamp"),
                "summary": f"[{ev.get('type')}] {ev.get('reason')}: {ev.get('message')}",
            })

        return {
            "target": f"{namespace}/{service_name}",
            "timeline_entry_count": len(timeline_entries),
            "timeline": sorted(timeline_entries, key=lambda x: str(x.get("timestamp", "")), reverse=False),
        }
