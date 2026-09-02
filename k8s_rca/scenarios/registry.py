"""
Scenario registry for managing and loading incident scenarios.
"""

from typing import Dict, List, Optional
from .base_scenario import BenchmarkScenario
from .crashloop_backoff import CrashLoopBackOffScenario
from .oom_killed import OOMKilledScenario
from .failed_probes import FailedProbesScenario
from .image_pull import ImagePullScenario
from .failed_deployment import FailedDeploymentScenario
from .resource_throttling import ResourceThrottlingScenario
from .cascading_5xx import Cascading5xxScenario


class ScenarioRegistry:
    """Registry providing access to all built-in benchmark incident scenarios."""

    def __init__(self):
        self._scenarios: Dict[str, BenchmarkScenario] = {}
        self._register_defaults()

    def _register_defaults(self) -> None:
        defaults = [
            CrashLoopBackOffScenario(),
            OOMKilledScenario(),
            FailedProbesScenario(),
            ImagePullScenario(),
            FailedDeploymentScenario(),
            ResourceThrottlingScenario(),
            Cascading5xxScenario(),
        ]
        for s in defaults:
            self._scenarios[s.id] = s
            # Also index by short name
            short_name = s.id.split("-", 2)[-1].replace("-", "_")
            self._scenarios[short_name] = s

    def get(self, identifier: str) -> Optional[BenchmarkScenario]:
        """Get scenario by ID or short name."""
        return self._scenarios.get(identifier) or self._scenarios.get(identifier.replace("-", "_"))

    def list_all(self) -> List[BenchmarkScenario]:
        """Get unique list of all registered scenarios."""
        unique_ids = set()
        result = []
        for s in self._scenarios.values():
            if s.id not in unique_ids:
                unique_ids.add(s.id)
                result.append(s)
        return result


_REGISTRY = ScenarioRegistry()


def get_scenario(identifier: str) -> Optional[BenchmarkScenario]:
    return _REGISTRY.get(identifier)


def get_all_scenarios() -> List[BenchmarkScenario]:
    return _REGISTRY.list_all()
