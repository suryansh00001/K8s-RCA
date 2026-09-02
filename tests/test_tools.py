"""
Unit tests for SRE Diagnostic Tools and ToolRegistry.
"""

from k8s_rca.providers.simulator import SimulatedClusterProvider
from k8s_rca.tools.registry import ToolRegistry
from k8s_rca.tools.resource_inspector import ResourceInspector
from k8s_rca.tools.log_analyzer import LogAnalyzer
from k8s_rca.tools.metrics_analyzer import MetricsAnalyzer
from k8s_rca.tools.change_correlator import ChangeCorrelator


def test_tool_registry_and_execution():
    sim = SimulatedClusterProvider()
    sim.add_resource("Pod", "test-pod", "default", {
        "apiVersion": "v1",
        "kind": "Pod",
        "metadata": {"name": "test-pod", "namespace": "default"},
        "status": {"phase": "Running"},
    })
    sim.add_logs("test-pod", "default", "Sample log output\nERROR: timeout connection")

    registry = ToolRegistry()
    registry.register_instance(ResourceInspector(sim))
    registry.register_instance(LogAnalyzer(sim))
    registry.register_instance(MetricsAnalyzer(sim))
    registry.register_instance(ChangeCorrelator(sim))

    # Test inspect_resource
    res = registry.execute("inspect_resource", {"kind": "Pod", "name": "test-pod", "namespace": "default"})
    assert not res.is_error
    assert res.result.get("metadata", {}).get("name") == "test-pod"

    # Test query_logs
    res_logs = registry.execute("query_logs", {"pod_name": "test-pod", "namespace": "default"})
    assert not res_logs.is_error
    assert "timeout connection" in res_logs.result

    # Test unknown tool
    unknown = registry.execute("non_existent_tool", {})
    assert unknown.is_error
