"""
Automated benchmark suite runner for executing batch RCA incident evaluations.
"""

from typing import List, Optional
from .evaluator import ScenarioEvaluator, BenchmarkAggregateMetrics, ScenarioEvalResult
from ..scenarios.base_scenario import BenchmarkScenario
from ..scenarios.registry import get_all_scenarios, get_scenario
from ..engine.agent import SREInvestigationAgent
from ..llm.base import BaseLLMClient
from ..llm.offline_sre import OfflineSREClient
from ..config import InvestigationConfig, DEFAULT_CONFIG


class BenchmarkRunner:
    """Runs automated batch evaluations across benchmark incident classes."""

    def __init__(
        self,
        llm_client: Optional[BaseLLMClient] = None,
        config: Optional[InvestigationConfig] = None,
    ):
        self.llm_client = llm_client or OfflineSREClient()
        self.config = config or DEFAULT_CONFIG
        self.evaluator = ScenarioEvaluator()

    def run_single(self, scenario: BenchmarkScenario) -> ScenarioEvalResult:
        """Run RCA on a single benchmark scenario and evaluate result."""
        sim_cluster = scenario.build_cluster()
        agent = SREInvestigationAgent(
            provider=sim_cluster,
            llm_client=self.llm_client,
            config=self.config,
        )
        report = agent.investigate(scenario.incident)
        return self.evaluator.evaluate_scenario(scenario, report)

    def run_all(self, scenarios: Optional[List[BenchmarkScenario]] = None) -> BenchmarkAggregateMetrics:
        """Run all benchmark scenarios and aggregate performance metrics."""
        target_scenarios = scenarios or get_all_scenarios()
        results: List[ScenarioEvalResult] = []

        for sc in target_scenarios:
            res = self.run_single(sc)
            results.append(res)

        return self.evaluator.aggregate_benchmark(results)
