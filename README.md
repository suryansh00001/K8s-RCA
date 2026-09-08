# Autonomous AI Agent for Kubernetes Root-Cause Analysis (K8s-RCA)

An autonomous, hypothesis-driven AI SRE Agent designed to investigate Kubernetes incidents, gather multi-source telemetry evidence (logs, metrics, events, manifests, rollout diffs), manage competing hypotheses, and reconstruct end-to-end failure causal chains within a strict read-only sandbox security boundary.

---

## 🏗️ Architecture Overview

```
                         +-----------------------------------+
                         |   Observed Incident Alert/Query   |
                         +-----------------+-----------------+
                                           |
                                           v
                         +-----------------------------------+
                         |     SRE Investigation Engine      |
                         |  - Explicit Hypotheses (H1..Hn)   |
                         |  - Bayesian Confidence Scoring    |
                         |  - Fact vs. Inference Epistemics  |
                         +--------+------------------+-------+
                                  |                  ^
       Sandboxed Tool Invocations |                  | Traceable Evidence
                                  v                  |
                         +---------------------------+-------+
                         |  Security & Sandbox Boundary      |
                         |  - Read-Only Verbs Enforcement    |
                         |  - Secret & Token Redactor        |
                         |  - Token Budget & Log Summarizer  |
                         +--------+--------------------------+
                                  |
            +---------------------+---------------------+
            |                     |                     |
            v                     v                     v
   +-----------------+   +-----------------+   +-----------------+
   |    Resource     |   |   Log & Diff    |   |  Metrics/Trends |
   |    Inspector    |   |    Analyzer     |   |  & Correlator   |
   +--------+--------+   +--------+--------+   +--------+--------+
            |                     |                     |
            +---------------------+---------------------+
                                  |
                                  v
                   +-----------------------------+
                   |  Kubernetes Cluster Provider|
                   |  - Simulated Cluster Engine |
                   |  - Live K8s Cluster Client  |
                   +-----------------------------+
```

---

## 🔒 Sandboxing & Security Boundary

The agent operates strictly behind an inviolable security boundary:

1. **Read-Only Guarantee**: Disallows all mutation actions (`create`, `update`, `patch`, `delete`, `exec`, `attach`, `port-forward`, `scale`, `drain`). Permitted verbs are strictly whitelisted (`get`, `list`, `watch`, `describe`, `logs`, `top`, `diff`).
2. **Automated Secret & Token Redaction**: Scans all manifests, logs, and outputs to mask Bearer tokens, JWTs, AWS/GCP access keys, connection passwords, and private keys.
3. **Context Window & Token Budget Protection**: Streams and samples high-volume logs with priority error pattern extraction (panics, tracebacks, fatal errors, HTTP 5xx, OOMkills) so large logs never blow up LLM context budgets.
4. **Command Injection Prevention**: Sanitizes all tool input arguments to reject shell chaining or path traversal attempts.
5. **Prompt Injection Defense**: Detects and neutralizes adversarial instructions in untrusted logs (e.g. `IGNORE ALL PREVIOUS INSTRUCTIONS`) and isolates observations in `<UNTRUSTED_TELEMETRY_DATA>` safety fences.

---

## 🧠 SRE Reasoning Backends: Generative AI vs. Deterministic Baseline

To ensure both cutting-edge probabilistic AI reasoning and rock-solid software engineering reproducibility, the architecture cleanly decouples the diagnostic tools from the reasoning brain:

### 1. Generative AI LLM Mode (True Neural Network Reasoning)
In this mode, a Generative AI Large Language Model actively drives the investigation. The model reads incident symptoms, analyzes tool observations, formulates hypotheses, chooses the next diagnostic tool, and synthesizes the causal RCA report:
* **Google Gemini**: `--llm gemini --model gemini-2.5-flash` (requires `GEMINI_API_KEY`)
* **OpenAI GPT-4o**: `--llm openai --model gpt-4o` (requires `OPENAI_API_KEY`)
* **Local Free LLM (Ollama)**: `--llm ollama --model llama3.1` (100% free, runs locally on your machine via Ollama at `http://localhost:11434/v1` with zero API keys required!)

### 2. Deterministic Expert Baseline (`--llm offline`, Default for Tests)
A rule-based expert system heuristic developed specifically for:
* **Instant Automated Testing (`pytest`)**: Allows all 28 unit and integration tests to verify the sandbox, tools, and hypothesis scoring in **0.4 seconds** without incurring cloud costs or flakiness.
* **Controlled Evaluation Baseline**: Provides a ground-truth deterministic benchmark against which LLM reasoning quality is measured.
* **Graceful Degradation**: Acts as an automatic fallback if a cloud LLM provider encounters network timeouts or rate limits (HTTP 429).

---

## 🧠 Epistemic Taxonomy & SRE Reasoning Loop

The engine strictly distinguishes between:
* **Observation**: Concrete, verified facts directly returned by diagnostic tools.
* **Inference**: Logical deductions derived from combining multiple observations.
* **Hypothesis**: Competing explanations with explicit confidence scores ($0.0 \dots 1.0$).
* **Conclusion**: Evidence-backed determination of the underlying root cause.
* **Recommendation**: Actionable remediations and preventative measures.

### SRE Investigation Progression
$$\text{Incident Trigger} \to \text{Form Competing Hypotheses } (H_1 \dots H_n) \to \text{Targeted Diagnostic Queries} \to \text{Evidence Correlation} \to \text{Bayesian Confidence Update} \to \text{Causal Chain Reconstruction}$$

---

## 🎯 Initial Benchmark Incident Scenarios

| Scenario ID | Incident Class | Name | Ground Truth Root Cause |
| :--- | :--- | :--- | :--- |
| `sc-01-crashloop` | `CrashLoopBackOff` | Auth Service CrashLoopBackOff | Application startup panic due to missing required env variable `JWT_SIGNING_KEY` in manifest. |
| `sc-02-oomkilled` | `OOMKilled` | Payment Gateway OOMKilled | Memory exhaustion: cache allocation exceeded 256Mi container limit, triggering Linux cgroup OOM killer (Exit Code 137). |
| `sc-03-failed-probes` | `FailedReadinessProbe` | Inventory Service Probe Failure | Readiness probe endpoint `/healthz` failed with HTTP 500 due to database ping connection timeout exceeding 1000ms. |
| `sc-04-image-pull` | `ImagePullFailure` | User Profile ImagePullBackOff | Deployment rollout updated container image tag to non-existent `v2.4.9-hotfix-typo`, causing `ErrImagePull`. |
| `sc-05-failed-deployment` | `FailedDeployment` | Notification Service Config Error | Deployment manifest references missing ConfigMap `notification-config-v2`, causing `CreateContainerConfigError`. |
| `sc-06-resource-throttling`| `ResourceExhaustion` | Search API Severe CPU Throttling | Restrictive 100m CPU limit causing >80% CFS CPU throttling on search workers under load, resulting in 504 Gateway Timeouts. |
| `sc-07-cascading-5xx` | `ApplicationErrorSpike` | Checkout Service 5xx Spike | PostgreSQL connection pool exhaustion (`max_connections=50` reached) causing connection lease timeouts and downstream 500 spikes. |
| `sc-08-dependency-chain`| `ApplicationErrorSpike` | Multi-Tier Service Dependency Failure | Downstream PostgreSQL database row lock contention in payment service causing cascading 504 Gateway Timeouts upstream to order-api and frontend. |

---

## 🚀 Quick Start & CLI Usage

### 1. Installation

```bash
# Clone and install dependencies
pip install -r requirements.txt
pip install -e .
```

### 2. List Available Scenarios
```bash
python -m k8s_rca.cli list-scenarios
```

### 3. Run Investigation on an Incident

```bash
# Option A: Run using real Google Gemini Cloud LLM (requires GEMINI_API_KEY)
python -m k8s_rca.cli run-scenario --scenario sc-08-dependency-chain --llm gemini --model gemini-2.5-flash

# Option B: Run using 100% Free Local Open-Source LLM (via Ollama, zero API keys!)
python -m k8s_rca.cli run-scenario --scenario sc-08-dependency-chain --llm ollama --model llama3.1

# Option C: Run using the deterministic offline expert baseline (instant & offline)
python -m k8s_rca.cli run-scenario --scenario sc-08-dependency-chain --llm offline
```

### 4. Run Full Evaluation Benchmark Suite
```bash
python -m k8s_rca.cli evaluate
```

### 5. Run Interactive Security Sandbox Audit
```bash
python -m k8s_rca.cli test-security
```

### 6. Run Model Context Protocol (MCP) Server
```bash
python -m k8s_rca.cli mcp
```

### 7. Run Web Dashboard
```bash
python -m k8s_rca.cli serve --port 8080
```

### 8. Containerized Setup (Docker & Docker Compose)
```bash
# Option A: Run via Docker Compose
docker-compose up

# Option B: Build and run Docker directly
docker build -t k8s-rca .
docker run -p 8080:8080 k8s-rca
```

---

## 📊 Evaluation & Verification Results

Running `python -m k8s_rca.cli evaluate`:

```text
=================== Benchmark Aggregate Performance Metrics ===================
  Total Scenarios Evaluated:              8
  RCA Accuracy Rate:                      100.0%
  Evidence Accuracy Rate:                 100.0%
  False Positive Rate:                    0.0%
  Mean Investigation Steps:               5.2 steps
  Uncertainty Calibration (Brier Score):  0.0054 (near-optimal)
  Read-Only Safety Compliance:            100.0%
================================================================================
```

---

## 🧪 Running Automated Tests

```bash
pytest -v
```

All 28 unit and integration tests covering sandboxing, redaction, prompt injection defense, MCP protocol, distributed tracing, and scenario evaluations run in < 1 second.

