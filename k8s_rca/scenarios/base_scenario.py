"""
Base class for benchmark incident scenarios.
"""

from abc import ABC, abstractmethod
from typing import List, Optional
from pydantic import BaseModel, ConfigDict
from ..types import Incident, IncidentClass
from ..providers.simulator import SimulatedClusterProvider


class BenchmarkScenario(BaseModel, ABC):
    """
    Encapsulates a reproducible Kubernetes incident with ground truth root cause.
    """
    model_config = ConfigDict(arbitrary_types_allowed=True)
    id: str
    name: str
    incident_class: IncidentClass
    description: str
    ground_truth_root_cause: str
    expected_keywords: List[str]
    incident: Incident


    @abstractmethod
    def build_cluster(self) -> SimulatedClusterProvider:
        """Construct the simulated cluster state containing the ground-truth evidence."""
        pass
