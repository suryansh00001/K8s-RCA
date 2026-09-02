"""
Base interface for LLM clients.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from ..types import InvestigationAction, Incident, Hypothesis, Evidence, ToolCallRecord


class BaseLLMClient(ABC):
    """Abstract interface for LLM backends driving the SRE investigation."""

    @abstractmethod
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
        """
        Reason over current evidence, update hypotheses, and select the next tool
        or conclude the investigation.
        """
        pass
