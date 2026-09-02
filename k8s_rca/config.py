"""
Configuration and settings for k8s_rca.
"""

from typing import List, Set
from pydantic import BaseModel, Field


class SandboxConfig(BaseModel):
    read_only_enforced: bool = True
    allowed_verbs: Set[str] = Field(
        default_factory=lambda: {"get", "list", "watch", "describe", "logs", "top", "diff"}
    )
    blocked_verbs: Set[str] = Field(
        default_factory=lambda: {
            "create",
            "update",
            "patch",
            "delete",
            "deletecollection",
            "exec",
            "attach",
            "port-forward",
            "proxy",
            "edit",
            "scale",
            "rollback",
            "drain",
            "cordon",
        }
    )
    mask_sensitive_data: bool = True
    sensitive_keys: List[str] = Field(
        default_factory=lambda: [
            "password",
            "secret",
            "token",
            "bearer",
            "api_key",
            "apikey",
            "private_key",
            "client_secret",
            "authorization",
            "jwt",
        ]
    )
    max_log_lines: int = 150
    max_log_bytes: int = 16384  # 16 KB max per log response to prevent LLM context blowup
    max_events_returned: int = 50


class InvestigationConfig(BaseModel):
    max_iterations: int = 8
    confidence_termination_threshold: float = 0.85
    min_confidence_diff_to_terminate: float = 0.30  # Gap between top hypothesis and #2
    enable_timeline_correlation: bool = True
    enable_metric_anomaly_detection: bool = True
    model_name: str = "gemini-2.5-flash"
    sandbox: SandboxConfig = Field(default_factory=SandboxConfig)


# Default global configuration
DEFAULT_CONFIG = InvestigationConfig()
