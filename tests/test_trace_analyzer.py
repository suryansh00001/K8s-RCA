"""
Unit tests for TraceAnalyzer distributed tracing diagnostic tool.
"""

from k8s_rca.providers.simulator import SimulatedClusterProvider
from k8s_rca.tools.trace_analyzer import TraceAnalyzer


def test_trace_analyzer_query_and_spans():
    sim = SimulatedClusterProvider()
    sim.add_trace(
        trace_id="tr-test-01",
        root_service="web-gateway",
        root_operation="GET /api/data",
        total_duration_ms=3500.0,
        status_code=504,
        has_error=True,
        error_summary="Upstream gateway timeout",
        spans=[
            {
                "span_id": "sp-1",
                "service_name": "web-gateway",
                "operation_name": "GET /api/data",
                "duration_ms": 3500.0,
                "status_code": 504,
                "error": True,
            },
            {
                "span_id": "sp-2",
                "service_name": "backend-service",
                "operation_name": "POST /internal/query",
                "duration_ms": 3200.0,
                "status_code": 504,
                "error": True,
                "error_message": "Database query timeout",
            },
        ],
    )

    analyzer = TraceAnalyzer(sim)

    # 1. Query traces
    traces = analyzer.query_traces(service_name="web-gateway", status_code=504)
    assert len(traces) == 1
    assert traces[0]["trace_id"] == "tr-test-01"
    assert traces[0]["has_error"] is True

    # 2. Get trace spans waterfall and bottleneck identification
    spans_detail = analyzer.get_trace_spans(trace_id="tr-test-01")
    assert spans_detail["trace_id"] == "tr-test-01"
    assert spans_detail["bottleneck_span"] is not None
    assert spans_detail["bottleneck_span"]["duration_ms"] == 3500.0
    assert len(spans_detail["failing_spans"]) == 2

    # 3. Analyze service dependencies
    dep_analysis = analyzer.analyze_service_dependencies(service_name="web-gateway")
    assert dep_analysis["source_service"] == "web-gateway"
    assert len(dep_analysis["dependencies"]) == 1
    dep = dep_analysis["dependencies"][0]
    assert dep["target_service"] == "backend-service"
    assert dep["is_degraded"] is True
