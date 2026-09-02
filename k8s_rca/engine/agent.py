"""
Main SRE Investigation Agent orchestrator.
"""

import time
from typing import Any, Dict, List, Optional
from ..types import (
    Incident,
    RCAReport,
    Evidence,
    EvidenceType,
    ToolCallRecord,
    InvestigationAction,
)
from ..config import InvestigationConfig, DEFAULT_CONFIG
from ..providers.base import BaseClusterProvider
from ..tools.registry import ToolRegistry
from ..tools.resource_inspector import ResourceInspector
from ..tools.log_analyzer import LogAnalyzer
from ..tools.metrics_analyzer import MetricsAnalyzer
from ..tools.change_correlator import ChangeCorrelator
from ..llm.base import BaseLLMClient
from ..llm.offline_sre import OfflineSREClient
from .hypothesis import HypothesisManager
from .causal_builder import CausalGraphBuilder


class SREInvestigationAgent:
    """
    Autonomous AI SRE Agent for Kubernetes Root-Cause Analysis.
    Performs iterative hypothesis-driven investigations inside a read-only sandboxed boundary.
    """

    def __init__(
        self,
        provider: BaseClusterProvider,
        llm_client: Optional[BaseLLMClient] = None,
        config: Optional[InvestigationConfig] = None,
    ):
        self.provider = provider
        self.config = config or DEFAULT_CONFIG
        self.llm_client = llm_client or OfflineSREClient()
        
        # Initialize tools and registry
        self.tool_registry = ToolRegistry()
        self._init_tools()

        # State managers
        self.hypothesis_manager = HypothesisManager()
        self.causal_builder = CausalGraphBuilder()
        self.history: List[ToolCallRecord] = []
        self.evidence_counter = 1

    def _init_tools(self) -> None:
        """Register all SRE diagnostic tools."""
        self.tool_registry.register_instance(ResourceInspector(self.provider))
        self.tool_registry.register_instance(LogAnalyzer(self.provider))
        self.tool_registry.register_instance(MetricsAnalyzer(self.provider))
        self.tool_registry.register_instance(ChangeCorrelator(self.provider))

    def investigate(self, incident: Incident) -> RCAReport:
        """
        Execute the full autonomous SRE investigation loop for the given incident.
        """
        start_time = time.perf_counter()
        tool_schemas = self.tool_registry.get_tool_schemas()

        iteration = 0
        max_iter = self.config.max_iterations
        conclusion_rationale = None

        while iteration < max_iter:
            iteration += 1

            # 1. Ask LLM / SRE Reasoner for next decision
            current_hyps = self.hypothesis_manager.get_ranked_hypotheses()
            current_ev = list(self.hypothesis_manager.evidence_vault.values())

            action: InvestigationAction = self.llm_client.decide_next_action(
                incident=incident,
                hypotheses=current_hyps,
                evidence_list=current_ev,
                history=self.history,
                tool_schemas=tool_schemas,
                iteration=iteration,
                max_iterations=max_iter,
            )

            # 2. Apply hypothesis updates
            for update in action.hypothesis_updates:
                self.hypothesis_manager.apply_update(update, iteration=iteration)

            # 3. Check for conclusion
            if action.is_concluded:
                conclusion_rationale = action.conclusion_rationale
                break

            # 4. Execute tool call if requested
            if action.tool_name:
                record = self.tool_registry.execute(action.tool_name, action.tool_arguments)
                self.history.append(record)

                # Extract and record evidence from tool result
                self._extract_and_record_evidence(record, action.tool_name, incident)

            # 5. Check confidence early termination condition
            primary = self.hypothesis_manager.get_primary_hypothesis()
            if primary and primary.confidence >= self.config.confidence_termination_threshold:
                alts = self.hypothesis_manager.get_alternative_hypotheses()
                gap = primary.confidence - (alts[0].confidence if alts else 0.0)
                if gap >= self.config.min_confidence_diff_to_terminate:
                    conclusion_rationale = f"Primary hypothesis '{primary.title}' reached definitive confidence ({primary.confidence*100:.1f}%)."
                    break

        elapsed = time.perf_counter() - start_time

        # Conclude and build final RCA report
        primary = self.hypothesis_manager.get_primary_hypothesis()
        if not primary:
            # Fallback hypothesis if none generated
            primary = self.hypothesis_manager.add_hypothesis(
                hyp_id="H_DEFAULT",
                title="Unknown Incident Cause",
                description="Unable to definitively isolate root cause from available telemetry.",
                initial_confidence=0.3,
            )

        alts = self.hypothesis_manager.get_alternative_hypotheses()
        report = self.causal_builder.build_report(
            incident=incident,
            primary_hypothesis=primary,
            alternative_hypotheses=alts,
            evidence_vault=self.hypothesis_manager.evidence_vault,
            investigation_history=self.history,
            conclusion_rationale=conclusion_rationale,
            elapsed_seconds=elapsed,
        )

        return report

    def _extract_and_record_evidence(self, record: ToolCallRecord, tool_name: str, incident: Incident) -> None:
        """Convert tool observations into traceable Evidence records."""
        if record.is_error:
            return

        ev_id = f"EV-{self.evidence_counter:03d}"
        self.evidence_counter += 1

        ev_type = EvidenceType.RESOURCE_STATE
        desc = f"Observation from {tool_name}"
        source = str(record.arguments.get("pod_name") or record.arguments.get("name") or record.arguments.get("resource_name") or incident.affected_service or "cluster")

        if tool_name in ("query_logs", "compare_pod_logs", "search_logs_by_pattern"):
            ev_type = EvidenceType.LOG
            desc = f"Log inspection of {source}"
        elif tool_name in ("query_metrics", "detect_resource_saturation"):
            ev_type = EvidenceType.METRIC
            desc = f"Metric telemetry from {source}"
        elif tool_name in ("get_event_timeline", "correlate_incident_timeline"):
            ev_type = EvidenceType.EVENT
            desc = f"Event timeline for {source}"
        elif tool_name in ("diff_resource_changes",):
            ev_type = EvidenceType.CHANGE
            desc = f"Rollout revision history for {source}"

        ev = Evidence(
            id=ev_id,
            evidence_type=ev_type,
            source_resource=source,
            description=desc,
            raw_data=str(record.result)[:500],
            relevance_score=0.9,
        )
        self.hypothesis_manager.record_evidence(ev)
