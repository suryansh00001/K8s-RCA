"""
Self-contained HTTP server and REST API for k8s_rca Web Dashboard.
"""

import http.server
import json
import os
import socketserver
import urllib.parse
from typing import Any, Dict

from ..scenarios.registry import get_all_scenarios, get_scenario
from ..engine.agent import SREInvestigationAgent
from ..eval.benchmark_runner import BenchmarkRunner
from ..llm.offline_sre import OfflineSREClient
from ..llm.gemini import GeminiClient
from ..llm.openai_compat import OpenAICompatClient
from ..types import Incident
from ..providers.live_k8s import LiveK8sClusterProvider


STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")


class RCAApiHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=STATIC_DIR, **kwargs)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/scenarios":
            self._send_json([
                {
                    "id": s.id,
                    "name": s.name,
                    "incident_class": s.incident_class.value,
                    "description": s.description,
                    "ground_truth": s.ground_truth_root_cause,
                    "incident": s.incident.model_dump(mode="json"),
                }
                for s in get_all_scenarios()
            ])
        elif parsed.path == "/api/evaluate":
            runner = BenchmarkRunner(llm_client=OfflineSREClient())
            metrics = runner.run_all()
            self._send_json(metrics.model_dump(mode="json"))
        else:
            super().do_GET()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode("utf-8") if content_length > 0 else "{}"
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            payload = {}

        if parsed.path == "/api/run-scenario":
            scenario_id = payload.get("scenario_id", "sc-07-cascading-5xx")
            scenario = get_scenario(scenario_id)
            if not scenario:
                self._send_json({"error": f"Scenario '{scenario_id}' not found"}, status=404)
                return

            llm_type = payload.get("llm", "offline")
            if llm_type == "gemini":
                llm = GeminiClient(api_key=payload.get("api_key"))
            elif llm_type == "openai":
                llm = OpenAICompatClient(api_key=payload.get("api_key"))
            else:
                llm = OfflineSREClient()

            sim_cluster = scenario.build_cluster()
            agent = SREInvestigationAgent(provider=sim_cluster, llm_client=llm)
            report = agent.investigate(scenario.incident)

            self._send_json(report.model_dump(mode="json"))

        elif parsed.path == "/api/investigate-live":
            query = payload.get("query", "Investigate service degradation")
            namespace = payload.get("namespace", "default")
            service = payload.get("service")
            
            try:
                provider = LiveK8sClusterProvider(kubeconfig_path=payload.get("kubeconfig"))
                incident = Incident(title=query, description=query, namespace=namespace, affected_service=service)
                llm = OfflineSREClient()
                agent = SREInvestigationAgent(provider=provider, llm_client=llm)
                report = agent.investigate(incident)
                self._send_json(report.model_dump(mode="json"))
            except Exception as e:
                self._send_json({"error": str(e)}, status=500)
        else:
            self._send_json({"error": "Endpoint not found"}, status=404)

    def _send_json(self, data: Any, status: int = 200) -> None:
        raw = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(raw)


class ReusableTCPServer(socketserver.TCPServer):
    allow_reuse_address = True


def start_web_server(port: int = 8080) -> None:
    """Launch the Web Dashboard server with automatic port fallback if port is in use."""
    current_port = port
    max_attempts = 10
    httpd = None

    for attempt in range(max_attempts):
        try:
            httpd = ReusableTCPServer(("", current_port), RCAApiHandler)
            break
        except OSError as e:
            if attempt == max_attempts - 1:
                print(f"[Error] Could not bind to port {current_port} or next {max_attempts} ports: {e}")
                raise
            current_port += 1

    print(f"================================================================")
    print(f"🚀 K8s-RCA AI Agent Web Dashboard running at: http://localhost:{current_port}")
    if current_port != port:
        print(f"   (Note: Port {port} was occupied, switched to port {current_port})")
    print(f"================================================================")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down web dashboard server...")
    finally:
        httpd.server_close()

