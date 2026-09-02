"""
Hypothesis state management, evidence linkage, and confidence calibration.
"""

from typing import Any, Dict, List, Optional
from ..types import Hypothesis, HypothesisStatus, Evidence


class HypothesisManager:
    """
    Maintains and updates competing hypotheses throughout the investigation lifecycle.
    Supports Bayesian-like confidence updates based on supporting and contradicting evidence.
    """

    def __init__(self):
        self.hypotheses: Dict[str, Hypothesis] = {}
        self.evidence_vault: Dict[str, Evidence] = {}

    def add_hypothesis(
        self,
        hyp_id: str,
        title: str,
        description: str,
        initial_confidence: float = 0.5,
        iteration: int = 0,
    ) -> Hypothesis:
        """Register a new hypothesis."""
        hyp = Hypothesis(
            id=hyp_id,
            title=title,
            description=description,
            status=HypothesisStatus.PROPOSED,
            confidence=max(0.01, min(0.99, initial_confidence)),
            created_iteration=iteration,
            last_updated_iteration=iteration,
        )
        self.hypotheses[hyp_id] = hyp
        return hyp

    def record_evidence(
        self,
        evidence: Evidence,
        supports_hyp_ids: Optional[List[str]] = None,
        refutes_hyp_ids: Optional[List[str]] = None,
    ) -> None:
        """Store evidence and link to supporting/refuting hypotheses."""
        self.evidence_vault[evidence.id] = evidence

        supports = supports_hyp_ids or evidence.supports_hypotheses
        for hid in supports:
            if hid in self.hypotheses:
                if evidence.id not in self.hypotheses[hid].supporting_evidence_ids:
                    self.hypotheses[hid].supporting_evidence_ids.append(evidence.id)
                self.boost_confidence(hid, weight=0.25 * evidence.relevance_score)

        refutes = refutes_hyp_ids or evidence.refutes_hypotheses
        for hid in refutes:
            if hid in self.hypotheses:
                if evidence.id not in self.hypotheses[hid].refuting_evidence_ids:
                    self.hypotheses[hid].refuting_evidence_ids.append(evidence.id)
                self.penalize_confidence(hid, weight=0.40 * evidence.relevance_score)

    def boost_confidence(self, hyp_id: str, weight: float = 0.2) -> None:
        """Increase confidence using logistic update."""
        if hyp_id in self.hypotheses:
            h = self.hypotheses[hyp_id]
            # Logistic confidence update
            current = h.confidence
            h.confidence = min(0.98, current + (1.0 - current) * weight)
            if h.confidence > 0.70:
                h.status = HypothesisStatus.SUPPORTED

    def penalize_confidence(self, hyp_id: str, weight: float = 0.3) -> None:
        """Decrease confidence when contradicted by evidence."""
        if hyp_id in self.hypotheses:
            h = self.hypotheses[hyp_id]
            current = h.confidence
            h.confidence = max(0.02, current * (1.0 - weight))
            if h.confidence < 0.25:
                h.status = HypothesisStatus.REFUTED

    def apply_update(self, update_dict: Dict[str, Any], iteration: int = 0) -> None:
        """Apply updates from LLM / agent decision."""
        action = update_dict.get("action", "update")
        hid = update_dict.get("id")

        if not hid:
            return

        if action == "create" or hid not in self.hypotheses:
            self.add_hypothesis(
                hyp_id=hid,
                title=update_dict.get("title", f"Hypothesis {hid}"),
                description=update_dict.get("description", ""),
                initial_confidence=float(update_dict.get("confidence", 0.5)),
                iteration=iteration,
            )
        else:
            h = self.hypotheses[hid]
            if "confidence" in update_dict:
                h.confidence = max(0.01, min(0.99, float(update_dict["confidence"])))
            if "status" in update_dict:
                status_str = str(update_dict["status"]).lower()
                for s in HypothesisStatus:
                    if s.value == status_str:
                        h.status = s
            if "reasoning" in update_dict:
                h.reasoning = update_dict["reasoning"]
            h.last_updated_iteration = iteration

    def get_ranked_hypotheses(self) -> List[Hypothesis]:
        """Return hypotheses sorted by descending confidence."""
        return sorted(self.hypotheses.values(), key=lambda h: h.confidence, reverse=True)

    def get_primary_hypothesis(self) -> Optional[Hypothesis]:
        """Return top confidence hypothesis."""
        ranked = self.get_ranked_hypotheses()
        return ranked[0] if ranked else None

    def get_alternative_hypotheses(self) -> List[Hypothesis]:
        """Return secondary competing hypotheses."""
        ranked = self.get_ranked_hypotheses()
        return ranked[1:] if len(ranked) > 1 else []
