"""
Command-Line Interface (CLI) for Kubernetes Root-Cause Analysis AI Agent.
"""

import argparse
import sys
from typing import Optional
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.tree import Tree
from rich import print as rprint

from .types import Incident, IncidentClass, RCAReport
from .config import InvestigationConfig
from .scenarios.registry import get_all_scenarios, get_scenario
from .eval.benchmark_runner import BenchmarkRunner
from .engine.agent import SREInvestigationAgent
from .llm.offline_sre import OfflineSREClient
from .llm.gemini import GeminiClient
from .llm.openai_compat import OpenAICompatClient
from .providers.live_k8s import LiveK8sClusterProvider


console = Console()


def print_rca_report(report: RCAReport) -> None:
    """Render a structured SRE RCA report in the terminal with rich visuals."""
    console.print("\n")
    console.print(Panel.fit(
        f"[bold cyan]Kubernetes Root Cause Analysis (RCA) Report[/bold cyan]\n"
        f"[dim]Incident ID:[/dim] {report.incident_id} | [dim]Elapsed Time:[/dim] {report.metadata.get('elapsed_seconds', 0)}s",
        border_style="cyan"
    ))

    # 1. Incident & Root Cause
    summary_table = Table(show_header=False, box=None)
    summary_table.add_row("[bold yellow]Incident:[/bold yellow]", report.incident_title)
    summary_table.add_row("[bold green]Root Cause:[/bold green]", f"[bold]{report.root_cause}[/bold]")
    summary_table.add_row(
        "[bold magenta]Confidence:[/bold magenta]",
        f"[{'green' if report.confidence >= 0.8 else 'yellow'}]{report.confidence * 100:.1f}%[/] - {report.confidence_rationale}"
    )
    if report.uncertainty_notes:
        summary_table.add_row("[bold red]Uncertainty:[/bold red]", f"[italic]{report.uncertainty_notes}[/italic]")
    console.print(Panel(summary_table, title="[bold]Incident Overview[/bold]", border_style="blue"))

    # 2. Causal Chain Diagram
    tree = Tree("[bold cyan]Causal Chain (Propagation Graph)[/bold cyan]")
    current_node = tree
    for step in report.causal_chain.steps:
        ev_refs = f"[dim](Evidence: {', '.join(step.evidence_ids)})[/dim]" if step.evidence_ids else ""
        step_text = f"[bold green]Step {step.step_order}:[/bold green] [{step.component}] {step.phenomenon} {ev_refs}"
        current_node = current_node.add(step_text)
    console.print(Panel(tree, title="[bold]Failure Propagation Timeline[/bold]", border_style="cyan"))

    # 3. Evidence Traceability Vault
    ev_table = Table(title="Observed Evidence Vault (Traceable)", show_lines=True)
    ev_table.add_column("ID", style="cyan", width=8)
    ev_table.add_column("Type", style="magenta", width=12)
    ev_table.add_column("Source", style="yellow", width=22)
    ev_table.add_column("Key Observation", style="white")

    for ev in report.evidence[:8]:
        raw_snippet = (ev.raw_data or "")[:120].replace("\n", " ")
        ev_table.add_row(
            ev.id,
            ev.evidence_type.value,
            ev.source_resource,
            f"{ev.description}\n[dim]{raw_snippet}...[/dim]" if raw_snippet else ev.description,
        )
    console.print(ev_table)

    # 4. Alternative Hypotheses
    if report.alternative_hypotheses:
        hyp_table = Table(title="Evaluated Competing Hypotheses", show_lines=True)
        hyp_table.add_column("ID", width=6)
        hyp_table.add_column("Hypothesis Title", width=35)
        hyp_table.add_column("Status", width=12)
        hyp_table.add_column("Confidence", width=12)
        hyp_table.add_column("Reasoning / Evaluation", style="dim")

        for h in report.alternative_hypotheses:
            status_color = "green" if h.status.value == "supported" else "red" if h.status.value == "refuted" else "yellow"
            hyp_table.add_row(
                h.id,
                h.title,
                f"[{status_color}]{h.status.value}[/{status_color}]",
                f"{h.confidence * 100:.1f}%",
                h.reasoning or "Evaluated against telemetry evidence.",
            )
        console.print(hyp_table)

    # 5. Remediation Recommendations
    rec_tree = Tree("[bold green]Actionable Remediation & Prevention[/bold green]")
    for rec in report.recommended_actions:
        rec_tree.add(f"[bold white]• {rec}[/bold white]")
    console.print(Panel(rec_tree, title="[bold]SRE Recommendations[/bold]", border_style="green"))


def cmd_list_scenarios(args) -> None:
    """List all available benchmark incident scenarios."""
    scenarios = get_all_scenarios()
    table = Table(title="Available Benchmark Incident Scenarios", show_lines=True)
    table.add_column("ID", style="cyan")
    table.add_column("Incident Class", style="magenta")
    table.add_column("Scenario Name", style="green")
    table.add_column("Description")

    for s in scenarios:
        table.add_row(s.id, s.incident_class.value, s.name, s.description)
    console.print(table)


def cmd_run_scenario(args) -> None:
    """Run RCA investigation on a simulated benchmark scenario."""
    scenario = get_scenario(args.scenario)
    if not scenario:
        console.print(f"[bold red]Error: Scenario '{args.scenario}' not found. Use 'list-scenarios' to view available scenarios.[/bold red]")
        sys.exit(1)

    console.print(f"[bold green]Starting Autonomous SRE RCA on Scenario:[/bold green] {scenario.name} ({scenario.id})")
    
    # Select LLM backend
    if args.llm == "gemini":
        llm = GeminiClient(model_name=args.model)
    elif args.llm == "openai":
        llm = OpenAICompatClient(model_name=args.model)
    else:
        llm = OfflineSREClient()

    sim_cluster = scenario.build_cluster()
    agent = SREInvestigationAgent(provider=sim_cluster, llm_client=llm)
    report = agent.investigate(scenario.incident)

    print_rca_report(report)


def cmd_evaluate(args) -> None:
    """Run full benchmark evaluation across all incident classes."""
    console.print("[bold cyan]Running Full Benchmark Evaluation Suite Across All Incident Classes...[/bold cyan]\n")

    if args.llm == "gemini":
        llm = GeminiClient(model_name=args.model)
    elif args.llm == "openai":
        llm = OpenAICompatClient(model_name=args.model)
    else:
        llm = OfflineSREClient()

    runner = BenchmarkRunner(llm_client=llm)
    metrics = runner.run_all()

    # Detailed results table
    res_table = Table(title="Benchmark Evaluation Results per Incident Scenario", show_lines=True)
    res_table.add_column("Scenario ID", style="cyan")
    res_table.add_column("Scenario Name", style="white")
    res_table.add_column("RCA Correct", justify="center")
    res_table.add_column("Confidence", justify="right")
    res_table.add_column("Evidence Acc.", justify="right")
    res_table.add_column("Steps", justify="right")
    res_table.add_column("Safety", justify="center")

    for r in metrics.scenario_results:
        correct_badge = "[bold green]PASS[/bold green]" if r.is_correct else "[bold red]FAIL[/bold red]"
        safety_badge = "[bold green]SAFE[/bold green]" if r.safety_passed else "[bold red]BREACH[/bold red]"
        res_table.add_row(
            r.scenario_id,
            r.scenario_name,
            correct_badge,
            f"{r.confidence * 100:.1f}%",
            f"{r.evidence_accuracy_score * 100:.1f}%",
            str(r.investigation_steps),
            safety_badge,
        )
    console.print(res_table)

    # Aggregate metrics summary panel
    agg_table = Table(show_header=False, box=None)
    agg_table.add_row("[bold cyan]Total Scenarios Evaluated:[/bold cyan]", str(metrics.total_scenarios))
    agg_table.add_row("[bold green]RCA Accuracy Rate:[/bold green]", f"[bold green]{metrics.rca_accuracy_pct:.1f}%[/bold green]")
    agg_table.add_row("[bold green]Evidence Accuracy Rate:[/bold green]", f"{metrics.evidence_accuracy_pct:.1f}%")
    agg_table.add_row("[bold magenta]False Positive Rate:[/bold magenta]", f"{metrics.false_positive_rate_pct:.1f}%")
    agg_table.add_row("[bold yellow]Mean Investigation Steps:[/bold yellow]", f"{metrics.mean_investigation_steps:.1f} steps")
    agg_table.add_row("[bold blue]Uncertainty Calibration (Brier Score):[/bold blue]", f"{metrics.calibration_brier_score:.4f} [dim](lower is better)[/dim]")
    agg_table.add_row("[bold green]Read-Only Safety Compliance:[/bold green]", f"[bold green]{metrics.safety_compliance_pct:.1f}%[/bold green]")

    console.print(Panel(agg_table, title="[bold]Benchmark Aggregate Performance Metrics[/bold]", border_style="cyan"))


def cmd_investigate_live(args) -> None:
    """Run RCA on a live Kubernetes cluster."""
    console.print(f"[bold green]Connecting to Kubernetes Cluster (Read-Only Mode)...[/bold green]")
    provider = LiveK8sClusterProvider(kubeconfig_path=args.kubeconfig, context=args.context)

    incident = Incident(
        title=args.query,
        description=args.query,
        namespace=args.namespace,
        affected_service=args.service,
    )

    if args.llm == "gemini":
        llm = GeminiClient(model_name=args.model)
    elif args.llm == "openai":
        llm = OpenAICompatClient(model_name=args.model)
    else:
        llm = OfflineSREClient()

    agent = SREInvestigationAgent(provider=provider, llm_client=llm)
    report = agent.investigate(incident)
    print_rca_report(report)


def cmd_serve(args) -> None:
    """Launch the Web Frontend Dashboard."""
    from .web.server import start_web_server
    start_web_server(port=args.port)


def main() -> None:
    parser = argparse.ArgumentParser(description="Autonomous AI Agent for Kubernetes Root-Cause Analysis (K8s-RCA)")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # serve web UI
    serve_parser = subparsers.add_parser("serve", help="Launch the interactive Web Frontend Dashboard")
    serve_parser.add_argument("--port", "-p", type=int, default=8080, help="Web dashboard server port (default: 8080)")

    # list-scenarios
    subparsers.add_parser("list-scenarios", help="List all available benchmark incident scenarios")


    # run-scenario
    run_parser = subparsers.add_parser("run-scenario", help="Run RCA on a simulated benchmark incident")
    run_parser.add_argument("--scenario", "-s", required=True, help="Scenario ID (e.g., sc-07-cascading-5xx or cascading_5xx)")
    run_parser.add_argument("--llm", choices=["offline", "gemini", "openai"], default="offline", help="LLM backend to use")
    run_parser.add_argument("--model", default="gemini-2.5-flash", help="Model name if using cloud LLM")

    # evaluate
    eval_parser = subparsers.add_parser("evaluate", help="Run full benchmark evaluation across all scenarios")
    eval_parser.add_argument("--llm", choices=["offline", "gemini", "openai"], default="offline", help="LLM backend to use")
    eval_parser.add_argument("--model", default="gemini-2.5-flash", help="Model name if using cloud LLM")

    # live investigate
    live_parser = subparsers.add_parser("investigate", help="Investigate an incident on a live Kubernetes cluster")
    live_parser.add_argument("--query", "-q", required=True, help="Incident symptom or alert query")
    live_parser.add_argument("--namespace", "-n", default="default", help="Kubernetes namespace")
    live_parser.add_argument("--service", help="Affected service name (optional)")
    live_parser.add_argument("--kubeconfig", help="Path to kubeconfig file")
    live_parser.add_argument("--context", help="Kubeconfig context")
    live_parser.add_argument("--llm", choices=["offline", "gemini", "openai"], default="offline", help="LLM backend")
    live_parser.add_argument("--model", default="gemini-2.5-flash", help="Model name")

    args = parser.parse_args()

    if args.command == "serve":
        cmd_serve(args)
    elif args.command == "list-scenarios":
        cmd_list_scenarios(args)
    elif args.command == "run-scenario":
        cmd_run_scenario(args)
    elif args.command == "evaluate":
        cmd_evaluate(args)
    elif args.command == "investigate":
        cmd_investigate_live(args)
    else:
        parser.print_help()



if __name__ == "__main__":
    main()
