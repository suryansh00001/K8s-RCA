"""
Unit tests for Sandboxing and Security Boundary.
"""

import pytest
from k8s_rca.sandbox.boundary import SandboxBoundary, SecurityViolationError
from k8s_rca.sandbox.redactor import SensitiveDataRedactor
from k8s_rca.sandbox.token_budget import TokenBudgetManager


def test_sandbox_blocks_destructive_verbs():
    boundary = SandboxBoundary()

    # Mutation verbs must be blocked
    for verb in ["create", "delete", "patch", "exec", "update", "scale", "drain"]:
        with pytest.raises(SecurityViolationError):
            boundary.validate_action(verb, "pod", "default")


def test_sandbox_permits_read_only_verbs():
    boundary = SandboxBoundary()

    # Read-only verbs must pass
    for verb in ["get", "list", "logs", "top", "describe", "diff"]:
        boundary.validate_action(verb, "pod", "default")


def test_sandbox_blocks_raw_secret_data():
    boundary = SandboxBoundary()
    with pytest.raises(SecurityViolationError):
        boundary.validate_action("get", "Secret", "default", details={"include_data": True})


def test_sandbox_sanitizes_injection_arguments():
    boundary = SandboxBoundary()
    with pytest.raises(SecurityViolationError):
        boundary.sanitize_arguments("query_logs", {"pod_name": "checkout-pod; rm -rf /"})

    with pytest.raises(SecurityViolationError):
        boundary.sanitize_arguments("inspect_resource", {"name": "../../etc/passwd"})


def test_redactor_masks_sensitive_tokens_and_passwords():
    redactor = SensitiveDataRedactor()
    
    sample_text = (
        "Connected to postgresql://admin:SuperSecretPass123!@db.internal:5432/main with Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.e30.t-ID "
        "and api_key='AIzaSyD-abc123xyz' and password=MySecretPassword"
    )
    redacted = redactor.redact_text(sample_text)

    assert "SuperSecretPass123" not in redacted
    assert "[REDACTED_PASSWORD]" in redacted
    assert "[REDACTED_TOKEN]" in redacted or "[REDACTED_JWT]" in redacted
    assert "MySecretPassword" not in redacted


def test_token_budget_smart_summarization():
    manager = TokenBudgetManager()
    
    # 500 lines of logs with one critical panic in the middle
    lines = [f"2026-09-02 INFO line {i}: routine healthcheck OK" for i in range(250)]
    lines.append("2026-09-02 FATAL panic: runtime error: index out of range [5] with length 0")
    lines.extend([f"2026-09-02 INFO line {i}: shutting down..." for i in range(250, 500)])
    
    raw_logs = "\n".join(lines)
    summary = manager.summarize_logs(raw_logs, max_lines=40, tail_lines=10)

    assert "panic: runtime error" in summary
    assert "Log Summary" in summary
    assert len(summary.splitlines()) <= 50
