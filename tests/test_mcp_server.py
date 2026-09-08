"""
Unit tests for Model Context Protocol (MCP) server integration.
"""

from k8s_rca.mcp.server import MCPServer
from k8s_rca.providers.simulator import SimulatedClusterProvider


def test_mcp_initialize():
    sim = SimulatedClusterProvider()
    server = MCPServer(sim)

    req = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
    resp = server.handle_request(req)

    assert resp["jsonrpc"] == "2.0"
    assert resp["id"] == 1
    assert "tools" in resp["result"]["capabilities"]
    assert resp["result"]["serverInfo"]["name"] == "k8s-rca-mcp-server"


def test_mcp_tools_list():
    sim = SimulatedClusterProvider()
    server = MCPServer(sim)

    req = {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
    resp = server.handle_request(req)

    tools = resp["result"]["tools"]
    tool_names = [t["name"] for t in tools]
    assert "get_cluster_overview" in tool_names
    assert "inspect_resource" in tool_names
    assert "query_logs" in tool_names
    assert "query_metrics" in tool_names
    assert "query_traces" in tool_names
    assert "get_trace_spans" in tool_names


def test_mcp_tools_call_execution_and_sandboxing():
    sim = SimulatedClusterProvider()
    sim.add_resource("Pod", "test-pod", "default", {"metadata": {"name": "test-pod"}, "status": {"phase": "Running"}})
    server = MCPServer(sim)

    # 1. Valid read-only call
    call_req = {
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {
            "name": "inspect_resource",
            "arguments": {"kind": "Pod", "name": "test-pod", "namespace": "default"},
        },
    }
    resp = server.handle_request(call_req)
    assert resp["result"]["isError"] is False
    assert "test-pod" in resp["result"]["content"][0]["text"]

    # 2. Call with shell injection argument -> Intercepted and blocked
    malicious_call = {
        "jsonrpc": "2.0",
        "id": 4,
        "method": "tools/call",
        "params": {
            "name": "query_logs",
            "arguments": {"pod_name": "test-pod; rm -rf /", "namespace": "default"},
        },
    }
    resp_malicious = server.handle_request(malicious_call)
    assert resp_malicious["result"]["isError"] is True
    assert "SANDBOX VIOLATION" in resp_malicious["result"]["content"][0]["text"]
