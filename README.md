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
# Run on the Checkout Service 5xx cascading failure scenario
python -m k8s_rca.cli run-scenario --scenario sc-07-cascading-5xx

# Or run using Google Gemini / OpenAI LLM (requires API key)
python -m k8s_rca.cli run-scenario --scenario sc-02-oomkilled --llm gemini --model gemini-2.5-flash
```

### 4. Run Full Evaluation Benchmark Suite
```bash
python -m k8s_rca.cli evaluate
```

### 5. Investigate a Live Kubernetes Cluster (Read-Only)
```bash
python -m k8s_rca.cli investigate \
  --query "The checkout service has experienced a sudden increase in 5xx errors." \
  --namespace prod \
  --service checkout-service \
  --kubeconfig ~/.kube/config
```

---

## 📊 Evaluation & Verification Results

Running `python -m k8s_rca.cli evaluate` or `pytest`:

```text
=================== Benchmark Aggregate Performance Metrics ===================
  Total Scenarios Evaluated:              7
  RCA Accuracy Rate:                      100.0%
  Evidence Accuracy Rate:                 100.0%
  False Positive Rate:                    0.0%
  Mean Investigation Steps:               6.0 steps
  Uncertainty Calibration (Brier Score):  0.0059 (near-optimal)
  Read-Only Safety Compliance:            100.0%
================================================================================
```

---

## 🧪 Running Automated Tests

```bash
pytest -v
```

All 19 unit and integration tests covering sandboxing, redaction, hypothesis scoring, diagnostic tools, and scenario evaluations run in < 1 second.
