"""
Distributed tracing and microservice span analysis tool for Kubernetes Root-Cause Analysis.
"""

from typing import Any, Dict, List, Optional
from .registry import sre_tool
from ..providers.base import BaseClusterProvider


class TraceAnalyzer:
    """Tool for querying distributed traces (Jaeger/OpenTelemetry) and inspecting microservice span waterfalls."""

    def __init__(self, provider: BaseClusterProvider):
        self.provider = provider

    @sre_tool(
        name="query_traces",
        description="Query distributed traces across microservices filtered by service name, HTTP status code (e.g. 500, 504), or latency threshold.",
        parameters={
            "type": "object",
            "properties": {
                "service_name": {
                    "type": "string",
                    "description": "Microservice name involved in the trace (e.g. frontend, checkout-service, order-api).",
                },
                "status_code": {
                    "type": "integer",
                    "description": "Filter by HTTP response status code (e.g., 500, 502, 504).",
                },
                "min_duration_ms": {
                    "type": "number",
                    "description": "Filter for slow traces exceeding this latency threshold in milliseconds.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of traces to return (default: 10).",
                },
            },
            "required": [],
        },
    )
    def query_traces(
        self,
        service_name: Optional[str] = None,
        status_code: Optional[int] = None,
        min_duration_ms: Optional[float] = None,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """Query distributed traces."""
        traces = self.provider.get_traces(
            service_name=service_name,
            min_duration_ms=min_duration_ms,
            status_code=status_code,
            limit=limit,
        )
        summarized = []
        for t in traces:
            summarized.append({
                "trace_id": t.get("trace_id"),
                "root_service": t.get("root_service"),
                "root_operation": t.get("root_operation"),
                "total_duration_ms": t.get("total_duration_ms"),
                "status_code": t.get("status_code"),
                "has_error": t.get("has_error", False),
                "error_summary": t.get("error_summary"),
                "span_count": len(t.get("spans", [])),
            })
        return summarized

    @sre_tool(
        name="get_trace_spans",
        description="Retrieve the complete span breakdown/waterfall for a distributed trace ID, identifying slow or failing downstream hops.",
        parameters={
            "type": "object",
            "properties": {
                "trace_id": {
                    "type": "string",
                    "description": "The unique trace ID to inspect (e.g. tr-ord-901).",
                },
            },
            "required": ["trace_id"],
        },
    )
    def get_trace_spans(self, trace_id: str) -> Dict[str, Any]:
        """Fetch all spans for a trace and compute critical path / bottleneck."""
        traces = self.provider.get_traces(trace_id=trace_id, limit=1)
        if not traces:
            return {"error": f"Trace '{trace_id}' not found"}

        trace = traces[0]
        spans = trace.get("spans", [])
        
        # Identify bottleneck span (longest duration) and any failed spans
        bottleneck_span = None
        longest_dur = -1.0
        failing_spans = []

        for s in spans:
            dur = s.get("duration_ms", 0.0)
            if dur > longest_dur:
                longest_dur = dur
                bottleneck_span = {
                    "span_id": s.get("span_id"),
                    "service": s.get("service_name"),
                    "operation": s.get("operation_name"),
                    "duration_ms": dur,
                    "percentage_of_trace": f"{(dur / max(trace.get('total_duration_ms', 1.0), 1.0)) * 100:.1f}%",
                }
            if s.get("error") or s.get("status_code", 200) >= 400:
                failing_spans.append({
                    "span_id": s.get("span_id"),
                    "service": s.get("service_name"),
                    "operation": s.get("operation_name"),
                    "status_code": s.get("status_code"),
                    "error_message": s.get("error_message"),
                })

        return {
            "trace_id": trace_id,
            "root_service": trace.get("root_service"),
            "root_operation": trace.get("root_operation"),
            "total_duration_ms": trace.get("total_duration_ms"),
            "status_code": trace.get("status_code"),
            "has_error": trace.get("has_error", False),
            "bottleneck_span": bottleneck_span,
            "failing_spans": failing_spans,
            "spans_waterfall": spans,
        }

    @sre_tool(
        name="analyze_service_dependencies",
        description="Analyze microservice call topology, downstream dependency health, and error propagation across services.",
        parameters={
            "type": "object",
            "properties": {
                "service_name": {
                    "type": "string",
                    "description": "Root service to analyze downstream dependencies for.",
                },
            },
            "required": ["service_name"],
        },
    )
    def analyze_service_dependencies(self, service_name: str) -> Dict[str, Any]:
        """Analyze service-to-service call topology and failure rates."""
        traces = self.provider.get_traces(service_name=service_name, limit=50)
        
        downstream_calls: Dict[str, Dict[str, Any]] = {}

        for t in traces:
            spans = t.get("spans", [])
            for s in spans:
                s_name = s.get("service_name")
                if s_name != service_name:
                    if s_name not in downstream_calls:
                        downstream_calls[s_name] = {
                            "total_calls": 0,
                            "error_calls": 0,
                            "total_duration_ms": 0.0,
                        }
                    downstream_calls[s_name]["total_calls"] += 1
                    if s.get("error") or s.get("status_code", 200) >= 400:
                        downstream_calls[s_name]["error_calls"] += 1
                    downstream_calls[s_name]["total_duration_ms"] += s.get("duration_ms", 0.0)

        dependencies = []
        for target, stats in downstream_calls.items():
            tot = stats["total_calls"]
            avg_lat = stats["total_duration_ms"] / max(tot, 1)
            err_rate = (stats["error_calls"] / max(tot, 1)) * 100
            dependencies.append({
                "target_service": target,
                "total_calls_sampled": tot,
                "error_rate_pct": f"{err_rate:.1f}%",
                "avg_duration_ms": round(avg_lat, 2),
                "is_degraded": err_rate > 10.0 or avg_lat > 2000.0,
            })

        return {
            "source_service": service_name,
            "sampled_traces": len(traces),
            "dependencies": dependencies,
        }
