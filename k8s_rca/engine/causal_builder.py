"""
Causal chain reconstruction and RCA report synthesizer.
"""

from typing import Any, Dict, List, Optional
from ..types import (
    Incident,
    Hypothesis,
    Evidence,
    RCAReport,
    CausalChain,
    CausalStep,
    ToolCallRecord,
)


class CausalGraphBuilder:
    """
    Constructs the end-to-end causal chain from underlying root cause to downstream symptoms,
    linking concrete evidence IDs to each step in the failure propagation graph.
    """

    def build_report(
        self,
        incident: Incident,
        primary_hypothesis: Hypothesis,
        alternative_hypotheses: List[Hypothesis],
        evidence_vault: Dict[str, Evidence],
        investigation_history: List[ToolCallRecord],
        conclusion_rationale: Optional[str] = None,
        elapsed_seconds: float = 0.0,
    ) -> RCAReport:
        # Construct causal steps based on primary hypothesis and incident details
        steps = self._construct_causal_steps(incident, primary_hypothesis, evidence_vault)
        causal_chain = CausalChain(
            steps=steps,
            narrative=" -> ".join(s.phenomenon for s in steps),
        )

        # Derive recommended remediation actions based on root cause
        recommendations = self._derive_recommendations(primary_hypothesis, incident)

        # Assess confidence rationale and uncertainty
        conf = primary_hypothesis.confidence
        if conf >= 0.85:
            conf_rationale = f"High confidence ({conf*100:.1f}%). Verified through multiple correlated sources: {', '.join([e.source_resource for e in evidence_vault.values()][:3])}."
            uncertainty_notes = None
        elif conf >= 0.65:
            conf_rationale = f"Moderate confidence ({conf*100:.1f}%). Primary hypothesis is strongly indicated, but additional verification under load may be helpful."
            uncertainty_notes = "Metrics and logs point to this cause, though secondary effects cannot be completely ruled out without isolated load testing."
        else:
            conf_rationale = f"Low confidence ({conf*100:.1f}%). Available evidence is incomplete."
            uncertainty_notes = "Insufficient telemetry available to definitively eliminate competing hypotheses."

        all_evidence = list(evidence_vault.values())

        report = RCAReport(
            incident_id=incident.id,
            incident_title=incident.title,
            summary=incident.description,
            root_cause=conclusion_rationale or primary_hypothesis.description or primary_hypothesis.title,
            causal_chain=causal_chain,
            primary_hypothesis=primary_hypothesis,
            alternative_hypotheses=alternative_hypotheses,
            evidence=all_evidence,
            confidence=conf,

            confidence_rationale=conf_rationale,
            uncertainty_notes=uncertainty_notes,
            recommended_actions=recommendations,
            investigation_timeline=[
                {
                    "step": idx + 1,
                    "tool": h.tool_name,
                    "arguments": h.arguments,
                    "is_error": h.is_error,
                    "duration_ms": h.duration_ms,
                }
                for idx, h in enumerate(investigation_history)
            ],
            metadata={
                "total_investigation_steps": len(investigation_history),
                "total_evidence_pieces": len(all_evidence),
                "elapsed_seconds": round(elapsed_seconds, 2),
                "target_namespace": incident.namespace,
                "affected_service": incident.affected_service,
            },
        )
        return report

    def _construct_causal_steps(
        self,
        incident: Incident,
        hyp: Hypothesis,
        evidence: Dict[str, Evidence],
    ) -> List[CausalStep]:
        """Synthesize chronological failure propagation steps."""
        ev_ids = list(evidence.keys())
        title_lower = hyp.title.lower()

        if "oom" in title_lower or "memory" in title_lower:
            return [
                CausalStep(step_order=1, component="Deployment/Workload", phenomenon="High memory allocation or cache leak under incoming request volume", evidence_ids=ev_ids[:1]),
                CausalStep(step_order=2, component="cgroup / Kernel", phenomenon="Process resident set size (RSS) exceeded configured container memory limit", evidence_ids=ev_ids[:2]),
                CausalStep(step_order=3, component="Linux OOM Killer", phenomenon="Kernel invoked OOM killer to terminate container process (Exit Code 137)", evidence_ids=ev_ids),
                CausalStep(step_order=4, component="Kubelet", phenomenon="Kubelet detected container termination and initiated restart backoff loop", evidence_ids=ev_ids),
                CausalStep(step_order=5, component="Service/Ingress", phenomenon="Endpoint unavailable causing connection resets and elevated error rate", evidence_ids=ev_ids),
            ]
        elif "config" in title_lower or "secret" in title_lower or "not found" in title_lower:
            return [
                CausalStep(step_order=1, component="Manifest / Config", phenomenon="Deployment manifest updated with missing or misnamed ConfigMap/Secret key", evidence_ids=ev_ids[:1]),
                CausalStep(step_order=2, component="Kubelet Pod Lifecycle", phenomenon="Kubelet failed container creation with CreateContainerConfigError", evidence_ids=ev_ids),
                CausalStep(step_order=3, component="ReplicaSet / Service", phenomenon="Pod never reached Ready state, preventing deployment rollout from completing", evidence_ids=ev_ids),
            ]
        elif "image" in title_lower or "pull" in title_lower:
            return [
                CausalStep(step_order=1, component="CI/CD Release", phenomenon="Deployment updated with invalid image tag or unreachable registry repository", evidence_ids=ev_ids[:1]),
                CausalStep(step_order=2, component="Container Runtime / Kubelet", phenomenon="Failed to pull image from registry with ErrImagePull / ImagePullBackOff", evidence_ids=ev_ids),
                CausalStep(step_order=3, component="Deployment Controller", phenomenon="New replica pods fail to start; old pods may be terminated during rolling update", evidence_ids=ev_ids),
            ]
        elif "panic" in title_lower or "exception" in title_lower or "crash" in title_lower:
            return [
                CausalStep(step_order=1, component="Application Code", phenomenon="Application initialization encountered unhandled exception / fatal panic", evidence_ids=ev_ids[:1]),
                CausalStep(step_order=2, component="Container Process", phenomenon="Main process exited immediately with non-zero exit code (Exit Code 1)", evidence_ids=ev_ids),
                CausalStep(step_order=3, component="Kubelet", phenomenon="Kubelet entered CrashLoopBackOff with exponential retry delay", evidence_ids=ev_ids),
            ]
        elif "throttl" in title_lower or "cpu" in title_lower:
            return [
                CausalStep(step_order=1, component="Workload Limits", phenomenon="CPU limits configured too low for workload concurrency requirements", evidence_ids=ev_ids[:1]),
                CausalStep(step_order=2, component="CFS Quota / Kernel", phenomenon="Linux Completely Fair Scheduler throttled thread execution (>50% throttled time)", evidence_ids=ev_ids),
                CausalStep(step_order=3, component="Application Latency", phenomenon="Processing latency increased exponentially, triggering upstream 504 Gateway Timeouts", evidence_ids=ev_ids),
            ]
        elif "dependency" in title_lower or "database" in title_lower or "pool" in title_lower:
            return [
                CausalStep(step_order=1, component="Upstream Database", phenomenon="Database connection pool saturated under elevated transaction load", evidence_ids=ev_ids[:1]),
                CausalStep(step_order=2, component="Application Backend", phenomenon="Worker threads blocked waiting on available connection leases", evidence_ids=ev_ids),
                CausalStep(step_order=3, component="HTTP Gateway", phenomenon="Incoming client requests timed out, generating sudden spike in HTTP 500/503 responses", evidence_ids=ev_ids),
            ]
        else:
            return [
                CausalStep(step_order=1, component="Target Workload", phenomenon=hyp.title, evidence_ids=ev_ids[:1]),
                CausalStep(step_order=2, component="Kubernetes Cluster", phenomenon=hyp.description, evidence_ids=ev_ids),
                CausalStep(step_order=3, component="Production Service", phenomenon=incident.description, evidence_ids=ev_ids),
            ]

    def _derive_recommendations(self, hyp: Hypothesis, incident: Incident) -> List[str]:
        """Generate actionable SRE remediation recommendations."""
        title_lower = hyp.title.lower()
        if "oom" in title_lower or "memory" in title_lower:
            return [
                "Increase container `resources.limits.memory` in the Deployment specification.",
                "Profile application memory allocations to identify cache leaks or unconstrained heap growth.",
                "Configure Vertical Pod Autoscaler (VPA) in recommendation mode to calibrate memory requests.",
            ]
        elif "config" in title_lower or "secret" in title_lower:
            return [
                "Verify and create the missing ConfigMap or Secret in the target namespace.",
                "Ensure CI/CD manifest validation (e.g. `kubeconform` or `helm lint`) validates configmap key bindings before deployment.",
            ]
        elif "image" in title_lower or "pull" in title_lower:
            return [
                "Correct the container image repository and tag in the Deployment manifest.",
                "Verify that `imagePullSecrets` has valid registry credentials if using a private container registry.",
            ]
        elif "panic" in title_lower or "exception" in title_lower:
            return [
                "Check application startup logs and provide missing environment variables or configuration files.",
                "Roll back the deployment to the previous stable revision while the software bug is patched.",
            ]
        elif "throttl" in title_lower or "cpu" in title_lower:
            return [
                "Increase or remove restrictive CPU limits (`resources.limits.cpu`) to avoid CFS quota throttling.",
                "Scale out the number of replicas horizontally via Horizontal Pod Autoscaler (HPA).",
            ]
        elif "dependency" in title_lower or "database" in title_lower:
            return [
                "Increase the database connection pool maximum size or scale database read replicas.",
                "Implement circuit breaking and request timeouts to prevent cascading connection starvation.",
            ]
        else:
            return [
                "Review recent deployment changes and inspect application health telemetry.",
                "Verify pod health check probe parameters (`initialDelaySeconds`, `timeoutSeconds`, `failureThreshold`).",
            ]
