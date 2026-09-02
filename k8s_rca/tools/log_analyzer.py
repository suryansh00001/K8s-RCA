"""
Log analyzer tool for fetching, pattern filtering, and diffing healthy vs unhealthy pods.
"""

import re
from typing import Any, Dict, List, Optional
from .registry import sre_tool
from ..providers.base import BaseClusterProvider


class LogAnalyzer:
    """Tool for investigating container logs, error patterns, and comparative log diffs."""

    def __init__(self, provider: BaseClusterProvider):
        self.provider = provider

    @sre_tool(
        name="query_logs",
        description="Fetch logs for a pod container. Use previous=True to inspect the logs of a crashed or restarted container.",
        parameters={
            "type": "object",
            "properties": {
                "pod_name": {
                    "type": "string",
                    "description": "Name of the pod.",
                },
                "namespace": {
                    "type": "string",
                    "description": "Namespace of the pod (default: 'default').",
                },
                "container": {
                    "type": "string",
                    "description": "Container name within the pod (optional).",
                },
                "previous": {
                    "type": "boolean",
                    "description": "Whether to fetch logs from previous crashed instance of the container (default: false).",
                },
                "tail_lines": {
                    "type": "integer",
                    "description": "Number of most recent log lines to retrieve (default: 100).",
                },
            },
            "required": ["pod_name"],
        },
    )
    def query_logs(
        self,
        pod_name: str,
        namespace: str = "default",
        container: Optional[str] = None,
        previous: bool = False,
        tail_lines: int = 100,
    ) -> str:
        return self.provider.get_logs(
            pod_name=pod_name,
            namespace=namespace,
            container=container,
            previous=previous,
            tail_lines=tail_lines,
        )

    @sre_tool(
        name="compare_pod_logs",
        description="Compare logs between two pods (e.g., a failing pod vs a healthy replica) to identify distinct failure signatures.",
        parameters={
            "type": "object",
            "properties": {
                "failing_pod_name": {
                    "type": "string",
                    "description": "Name of the unhealthy / failing pod.",
                },
                "healthy_pod_name": {
                    "type": "string",
                    "description": "Name of the healthy baseline pod.",
                },
                "namespace": {
                    "type": "string",
                    "description": "Namespace of the pods (default: 'default').",
                },
            },
            "required": ["failing_pod_name", "healthy_pod_name"],
        },
    )
    def compare_pod_logs(
        self,
        failing_pod_name: str,
        healthy_pod_name: str,
        namespace: str = "default",
    ) -> Dict[str, Any]:
        failing_logs = self.provider.get_logs(pod_name=failing_pod_name, namespace=namespace, tail_lines=50)
        healthy_logs = self.provider.get_logs(pod_name=healthy_pod_name, namespace=namespace, tail_lines=50)

        failing_lines = set(failing_logs.splitlines())
        healthy_lines = set(healthy_logs.splitlines())

        unique_to_failing = [line for line in failing_logs.splitlines() if line not in healthy_lines]

        return {
            "failing_pod": failing_pod_name,
            "healthy_pod": healthy_pod_name,
            "unique_lines_in_failing_count": len(unique_to_failing),
            "unique_failing_sample": unique_to_failing[:20],
        }

    @sre_tool(
        name="search_logs_by_pattern",
        description="Search for a regex or keyword pattern across logs of pods matching a given app label or service name.",
        parameters={
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Regex or substring to match (e.g., 'timeout', '500', 'panic', 'OOM').",
                },
                "app_label": {
                    "type": "string",
                    "description": "App label or workload name to search across.",
                },
                "namespace": {
                    "type": "string",
                    "description": "Namespace (default: 'default').",
                },
            },
            "required": ["pattern", "app_label"],
        },
    )
    def search_logs_by_pattern(
        self,
        pattern: str,
        app_label: str,
        namespace: str = "default",
    ) -> Dict[str, Any]:
        pods = self.provider.list_resources("Pod", namespace=namespace, label_selector=f"app={app_label}")
        if not pods:
            all_pods = self.provider.list_resources("Pod", namespace=namespace)
            pods = [p for p in all_pods if app_label in p.get("metadata", {}).get("name", "")]

        matches_by_pod = {}
        regex = re.compile(pattern, re.IGNORECASE)

        for pod in pods:
            pod_name = pod.get("metadata", {}).get("name")
            if not pod_name:
                continue
            logs = self.provider.get_logs(pod_name=pod_name, namespace=namespace, tail_lines=100)
            matched_lines = [l for l in logs.splitlines() if regex.search(l)]
            if matched_lines:
                matches_by_pod[pod_name] = matched_lines[:10]

        return {
            "pattern": pattern,
            "app": app_label,
            "matching_pods_count": len(matches_by_pod),
            "results": matches_by_pod,
        }
