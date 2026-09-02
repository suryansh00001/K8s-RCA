"""
Metrics analyzer tool for checking CPU, Memory, throttling, saturation, and timeseries trends.
"""

from typing import Any, Dict, List, Optional
from .registry import sre_tool
from ..providers.base import BaseClusterProvider


class MetricsAnalyzer:
    """Tool for investigating operational metrics, saturation, and resource bottlenecks."""

    def __init__(self, provider: BaseClusterProvider):
        self.provider = provider

    @sre_tool(
        name="query_metrics",
        description="Query current and timeseries metrics for a resource (CPU usage, memory usage, CPU throttling, restart rate, request/error rate).",
        parameters={
            "type": "object",
            "properties": {
                "resource_type": {
                    "type": "string",
                    "description": "Type of resource (e.g. 'pod', 'deployment', 'service', 'node').",
                },
                "resource_name": {
                    "type": "string",
                    "description": "Name of the target resource.",
                },
                "namespace": {
                    "type": "string",
                    "description": "Namespace (default: 'default').",
                },
                "metric_names": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional subset of metric names to query (e.g. ['cpu_usage_mcores', 'memory_usage_mb', 'cpu_throttling_pct', 'restarts']).",
                },
            },
            "required": ["resource_type", "resource_name"],
        },
    )
    def query_metrics(
        self,
        resource_type: str,
        resource_name: str,
        namespace: str = "default",
        metric_names: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        return self.provider.get_metrics(
            resource_type=resource_type,
            resource_name=resource_name,
            namespace=namespace,
            metric_names=metric_names,
        )

    @sre_tool(
        name="detect_resource_saturation",
        description="Analyze resource usage against configured limits to identify CPU throttling, memory exhaustion, or network saturation.",
        parameters={
            "type": "object",
            "properties": {
                "resource_type": {
                    "type": "string",
                    "description": "Type of resource ('pod' or 'deployment').",
                },
                "resource_name": {
                    "type": "string",
                    "description": "Name of the resource.",
                },
                "namespace": {
                    "type": "string",
                    "description": "Namespace (default: 'default').",
                },
            },
            "required": ["resource_type", "resource_name"],
        },
    )
    def detect_resource_saturation(
        self,
        resource_type: str,
        resource_name: str,
        namespace: str = "default",
    ) -> Dict[str, Any]:
        metrics = self.provider.get_metrics(
            resource_type=resource_type,
            resource_name=resource_name,
            namespace=namespace,
        )

        anomalies = []
        is_saturated = False

        # Evaluate memory saturation
        mem_usage = metrics.get("memory_usage_mb")
        mem_limit = metrics.get("memory_limit_mb")
        if mem_usage is not None and mem_limit is not None and mem_limit > 0:
            pct = (mem_usage / mem_limit) * 100.0
            if pct >= 90.0:
                is_saturated = True
                anomalies.append({
                    "type": "MEMORY_SATURATION",
                    "severity": "CRITICAL" if pct >= 98.0 else "HIGH",
                    "detail": f"Memory usage is at {pct:.1f}% of limit ({mem_usage}MB / {mem_limit}MB). High risk of OOMKill.",
                })

        # Evaluate CPU throttling
        throttling_pct = metrics.get("cpu_throttling_pct")
        if throttling_pct is not None and throttling_pct > 20.0:
            is_saturated = True
            anomalies.append({
                "type": "CPU_THROTTLING",
                "severity": "CRITICAL" if throttling_pct > 50.0 else "MEDIUM",
                "detail": f"CPU throttling rate is {throttling_pct:.1f}%. Threads are being starved by cgroup CPU quota.",
            })

        # Evaluate error rates
        error_rate = metrics.get("error_rate_pct")
        if error_rate is not None and error_rate > 5.0:
            anomalies.append({
                "type": "ERROR_RATE_SPIKE",
                "severity": "CRITICAL" if error_rate > 20.0 else "HIGH",
                "detail": f"Observed error rate is {error_rate:.1f}%.",
            })

        return {
            "resource": f"{resource_type}/{resource_name}",
            "is_saturated": is_saturated,
            "anomaly_count": len(anomalies),
            "anomalies": anomalies,
            "raw_metrics_summary": metrics,
        }
