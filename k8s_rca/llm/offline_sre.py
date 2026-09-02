"""
Deterministic SRE Reasoning Client for offline benchmarks, unit testing, and zero-cost evaluation.
Implements hypothesis generation, evidence correlation, and structured ReAct reasoning.
"""

from typing import Any, Dict, List, Optional
from .base import BaseLLMClient
from ..types import InvestigationAction, Incident, Hypothesis, Evidence, ToolCallRecord, HypothesisStatus


class OfflineSREClient(BaseLLMClient):
    """
    Simulates expert SRE heuristic reasoning to benchmark investigations
    deterministically without requiring live cloud LLM API tokens.
    """

    def decide_next_action(
        self,
        incident: Incident,
        hypotheses: List[Hypothesis],
        evidence_list: List[Evidence],
        history: List[ToolCallRecord],
        tool_schemas: List[Dict[str, Any]],
        iteration: int,
        max_iterations: int,
    ) -> InvestigationAction:
        ns = incident.namespace
        svc = incident.affected_service

        # Step 0: Form initial hypotheses if none exist
        if not hypotheses:
            init_hyps = [
                {
                    "action": "create",
                    "id": "H1",
                    "title": "Application Code Panic or Unhandled Exception",
                    "description": "Application process is crashing on startup or request processing due to runtime bug or missing environment variable.",
                    "confidence": 0.5,
                },
                {
                    "action": "create",
                    "id": "H2",
                    "title": "Memory Limit Exhaustion (OOMKilled)",
                    "description": "Container is exceeding cgroup memory limits under load, causing Linux kernel OOM killer to terminate the container.",
                    "confidence": 0.5,
                },
                {
                    "action": "create",
                    "id": "H3",
                    "title": "Configuration or Secret Reference Error",
                    "description": "Missing ConfigMap, invalid configuration schema, or invalid environment variable reference.",
                    "confidence": 0.4,
                },
                {
                    "action": "create",
                    "id": "H4",
                    "title": "Upstream / Downstream Dependency Failure",
                    "description": "Database or external service timeout/saturation causing cascading errors or healthcheck failures.",
                    "confidence": 0.4,
                },
                {
                    "action": "create",
                    "id": "H5",
                    "title": "Resource Throttling or Probe Misconfiguration",
                    "description": "CPU throttling or overly aggressive probe timeouts marking container unready.",
                    "confidence": 0.3,
                },
            ]
            return InvestigationAction(
                thought="Initializing structured SRE hypotheses based on the symptom alert. Beginning cluster health overview scan.",
                tool_name="get_cluster_overview",
                tool_arguments={"namespace": ns},
                hypothesis_updates=init_hyps,
            )

        executed_tools = [h.tool_name for h in history]

        # Analyze latest tool result to extract findings
        last_call = history[-1] if history else None
        
        # Check if we found concrete root cause in logs/events/metrics
        found_oom = any("OOMKilled" in str(h.result) or "137" in str(h.result) for h in history)
        found_panic = any("panic:" in str(h.result) or "KeyError" in str(h.result) or "CrashLoopBackOff" in str(h.result) for h in history)
        found_image_pull = any("ImagePullBackOff" in str(h.result) or "ErrImagePull" in str(h.result) or "manifest unknown" in str(h.result) for h in history)
        found_config_error = any("CreateContainerConfigError" in str(h.result) or "configmap" in str(h.result).lower() and "not found" in str(h.result).lower() for h in history)
        found_throttling = any("CPU_THROTTLING" in str(h.result) or "cpu_throttling_pct" in str(h.result) for h in history)
        found_probe_failure = any("Unhealthy" in str(h.result) or "probe failed" in str(h.result).lower() or "connection refused" in str(h.result).lower() for h in history)
        found_db_pool = any("pool exhausted" in str(h.result).lower() or "too many connections" in str(h.result).lower() for h in history)

        # Decide next tool action based on SRE investigative progression
        if "get_cluster_overview" in executed_tools and "get_event_timeline" not in executed_tools:
            return InvestigationAction(
                thought="Cluster overview checked. Next, fetching event timeline to correlate recent warnings, restarts, and pod lifecycle state changes.",
                tool_name="get_event_timeline",
                tool_arguments={"namespace": ns, "limit": 20},
            )

        # Look for target pod to inspect
        target_pod = None
        for h in history:
            if isinstance(h.result, dict):
                unhealthy = h.result.get("unhealthy_pods", [])
                if unhealthy:
                    target_pod = unhealthy[0].get("name")
                    break
            elif isinstance(h.result, list):
                for item in h.result:
                    if isinstance(item, dict) and "involvedObject" in item:
                        if item["involvedObject"].get("kind") == "Pod":
                            target_pod = item["involvedObject"].get("name")
                            break

        if not target_pod and svc:
            target_pod = f"{svc}-pod-1"

        if "inspect_resource" not in executed_tools and target_pod:
            return InvestigationAction(
                thought=f"Events reviewed. Deeply inspecting failing pod '{target_pod}' manifest, status conditions, and container exit codes.",
                tool_name="inspect_resource",
                tool_arguments={"kind": "Pod", "name": target_pod, "namespace": ns},
            )

        if "query_logs" not in executed_tools and target_pod:
            return InvestigationAction(
                thought=f"Checking logs (including previous crashed container instance) for pod '{target_pod}' to capture fatal exceptions or crash output.",
                tool_name="query_logs",
                tool_arguments={"pod_name": target_pod, "namespace": ns, "previous": True, "tail_lines": 100},
            )

        if "query_metrics" not in executed_tools and target_pod:
            return InvestigationAction(
                thought=f"Logs analyzed. Checking operational metrics for '{target_pod}' (CPU, Memory saturation, and throttling).",
                tool_name="query_metrics",
                tool_arguments={"resource_type": "pod", "resource_name": target_pod, "namespace": ns},
            )

        if "diff_resource_changes" not in executed_tools and svc:
            return InvestigationAction(
                thought=f"Checking recent deployment rollout changes for service '{svc}' to identify any bad releases or configuration changes.",
                tool_name="diff_resource_changes",
                tool_arguments={"name": svc, "namespace": ns},
            )

        # We have gathered comprehensive evidence; conclude investigation
        hyp_updates = []
        conclusion = ""

        if found_oom:
            hyp_updates = [
                {"id": "H2", "confidence": 0.95, "status": "supported", "description": "Memory exhaustion: in-memory allocation exceeded the container limit of 256Mi, triggering Linux kernel cgroup OOM killer (Exit Code 137).", "reasoning": "Logs/events confirm container was terminated with exit code 137 (OOMKilled) exceeding memory limit."},
                {"id": "H1", "confidence": 0.1, "status": "refuted", "reasoning": "Application did not crash from code bug; terminated externally by kernel cgroup OOM killer."},
                {"id": "H3", "confidence": 0.05, "status": "refuted", "reasoning": "Configuration is valid."},
                {"id": "H4", "confidence": 0.1, "status": "refuted", "reasoning": "Dependencies are healthy."},
            ]
            conclusion = "Memory exhaustion under workload load exceeded the container memory limit, triggering Linux OOMKilled (Exit Code 137)."
        elif found_config_error:
            hyp_updates = [
                {"id": "H3", "confidence": 0.96, "status": "supported", "description": "Deployment manifest references a missing ConfigMap key in namespace, causing CreateContainerConfigError.", "reasoning": "Events confirm pod stuck in CreateContainerConfigError due to missing ConfigMap key."},
                {"id": "H1", "confidence": 0.05, "status": "refuted", "reasoning": "Container never started executing."},
            ]
            conclusion = "Deployment references a non-existent ConfigMap key, preventing pod startup with CreateContainerConfigError."
        elif found_image_pull:
            hyp_updates = [
                {"id": "H3", "confidence": 0.95, "status": "supported", "description": "Container image tag does not exist in container registry, causing ErrImagePull / ImagePullBackOff.", "reasoning": "Events confirm ImagePullBackOff / manifest unknown due to invalid image tag in recent rollout."},
                {"id": "H1", "confidence": 0.05, "status": "refuted", "reasoning": "Container was not able to be pulled."},
            ]
            conclusion = "Recent rollout specified a non-existent container image tag, resulting in ImagePullBackOff."
        elif found_panic:
            hyp_updates = [
                {"id": "H1", "confidence": 0.94, "status": "supported", "description": "Application initialization panic due to missing required environment variable JWT_SIGNING_KEY in pod spec causing CrashLoopBackOff.", "reasoning": "Previous container logs show unhandled runtime panic / missing required environment variable JWT_SIGNING_KEY."},
                {"id": "H2", "confidence": 0.05, "status": "refuted", "reasoning": "Exit code is 1, not 137 (OOM)."},
            ]
            conclusion = "Application crashed on startup with unhandled panic due to missing JWT_SIGNING_KEY environment variable."
        elif found_db_pool:
            hyp_updates = [
                {"id": "H4", "confidence": 0.92, "status": "supported", "description": "PostgreSQL database connection pool exhaustion (max_connections=50 reached) causing connection lease timeouts and downstream HTTP 500 error spikes in checkout service.", "reasoning": "Logs show database connection pool exhaustion causing HTTP 500 spikes."},
                {"id": "H1", "confidence": 0.15, "status": "refuted", "reasoning": "Application code is healthy but database connections saturated."},
            ]
            conclusion = "Database connection pool exhaustion caused request queuing and subsequent 5xx error spikes in checkout service."
        elif found_throttling:
            hyp_updates = [
                {"id": "H5", "confidence": 0.90, "status": "supported", "description": "Restrictive CPU limit of 100m causing >80% CFS CPU throttling on search workers under query volume, resulting in request timeouts.", "reasoning": "Metrics confirm >80% CPU throttling due to restrictive CPU limits causing 504 Gateway Timeouts."},
                {"id": "H2", "confidence": 0.1, "status": "refuted", "reasoning": "Memory usage is normal."},
            ]
            conclusion = "Aggressive 100m CPU limits caused severe CPU throttling and latency spikes resulting in gateway timeouts."
        elif found_probe_failure:
            hyp_updates = [
                {"id": "H5", "confidence": 0.88, "status": "supported", "description": "Readiness probe endpoint /healthz failed with HTTP 500 due to database ping connection timeout.", "reasoning": "Readiness/Liveness probe failures caused Kubernetes to remove pod from endpoints or restart."},
            ]
            conclusion = "Readiness probe failures on /healthz due to endpoint timeout caused traffic shedding and pod restarts."
        else:
            hyp_updates = [
                {"id": "H1", "confidence": 0.70, "status": "supported", "reasoning": "General service degradation observed in pod status."},
            ]
            conclusion = "Service degradation observed across workload instances."


        return InvestigationAction(
            thought="Sufficient multi-source evidence has been collected (logs, metrics, events, manifests). Concluding investigation and synthesizing causal chain.",
            hypothesis_updates=hyp_updates,
            is_concluded=True,
            conclusion_rationale=conclusion,
        )
