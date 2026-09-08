"""
Model Context Protocol (MCP) JSON-RPC 2.0 Server for K8s-RCA.
Exposes sandboxed Kubernetes SRE diagnostic tools to any MCP-compliant AI client
(Anthropic Claude Desktop, Google Antigravity, Cursor, etc.).
"""

import json
import sys
from typing import Any, Dict, Optional
from ..providers.base import BaseClusterProvider
from ..tools.registry import ToolRegistry
from ..tools.resource_inspector import ResourceInspector
from ..tools.log_analyzer import LogAnalyzer
from ..tools.metrics_analyzer import MetricsAnalyzer
from ..tools.change_correlator import ChangeCorrelator
from ..tools.trace_analyzer import TraceAnalyzer


class MCPServer:
    """
    Standard MCP JSON-RPC 2.0 server operating over stdio.
    Every tool call is strictly checked by the SandboxBoundary and SensitiveDataRedactor.
    """

    PROTOCOL_VERSION = "2024-11-05"

    def __init__(self, provider: BaseClusterProvider):
        self.provider = provider
        self.registry = ToolRegistry()
        self._init_tools()

    def _init_tools(self) -> None:
        self.registry.register_instance(ResourceInspector(self.provider))
        self.registry.register_instance(LogAnalyzer(self.provider))
        self.registry.register_instance(MetricsAnalyzer(self.provider))
        self.registry.register_instance(ChangeCorrelator(self.provider))
        self.registry.register_instance(TraceAnalyzer(self.provider))

    def handle_request(self, request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Process a single JSON-RPC 2.0 request."""
        msg_id = request.get("id")
        method = request.get("method")
        params = request.get("params", {})

        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "protocolVersion": self.PROTOCOL_VERSION,
                    "serverInfo": {
                        "name": "k8s-rca-mcp-server",
                        "version": "1.0.0",
                        "description": "Read-Only Sandboxed Kubernetes SRE Root Cause Analysis Diagnostic Server",
                    },
                    "capabilities": {
                        "tools": {
                            "listChanged": False,
                        }
                    },
                },
            }

        elif method == "notifications/initialized":
            return None

        elif method == "tools/list":
            tools_list = []
            for name, meta in self.registry.tools.items():
                tools_list.append({
                    "name": name,
                    "description": meta.description,
                    "inputSchema": meta.parameters,
                })
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "tools": tools_list,
                },
            }

        elif method == "tools/call":
            tool_name = params.get("name")
            tool_args = params.get("arguments", {})
            record = self.registry.execute(tool_name, tool_args)

            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(record.result, indent=2, default=str) if not isinstance(record.result, str) else record.result,
                        }
                    ],
                    "isError": record.is_error,
                },
            }

        else:
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {
                    "code": -32601,
                    "message": f"Method '{method}' not found",
                },
            }

    def run_stdio(self) -> None:
        """Run standard I/O loop processing JSON-RPC messages from stdin."""
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                req = json.loads(line)
                resp = self.handle_request(req)
                if resp is not None:
                    sys.stdout.write(json.dumps(resp) + "\n")
                    sys.stdout.flush()
            except json.JSONDecodeError:
                err_resp = {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32700, "message": "Parse error: Invalid JSON"},
                }
                sys.stdout.write(json.dumps(err_resp) + "\n")
                sys.stdout.flush()


def start_mcp_server(provider: Optional[BaseClusterProvider] = None) -> None:
    """Start MCP stdio server with simulated cluster or live provider."""
    if provider is None:
        from ..scenarios.registry import get_scenario
        default_scenario = get_scenario("sc-07-cascading-5xx")
        provider = default_scenario.build_cluster() if default_scenario else None

    if provider is None:
        from ..providers.simulator import SimulatedClusterProvider
        provider = SimulatedClusterProvider()

    server = MCPServer(provider=provider)
    server.run_stdio()
