"""
Sensitive data masking and redactor for credentials, tokens, and secrets.
"""

import re
from typing import Any, Dict, List, Optional
from ..config import SandboxConfig, DEFAULT_CONFIG


class SensitiveDataRedactor:
    """
    Scans outputs, logs, environment variables, and manifests to mask credentials,
    bearer tokens, API keys, and secret values before they are sent to the LLM or logs.
    """

    PATTERNS = [
        # Bearer tokens & JWTs
        (re.compile(r"Bearer\s+([A-Za-z0-9\-._~+/]+=*)", re.IGNORECASE), "Bearer [REDACTED_TOKEN]"),
        (re.compile(r"eyJ[A-Za-z0-9-_=]+\.[A-Za-z0-9-_=]+\.?[A-Za-z0-9-_.+/=]*"), "[REDACTED_JWT]"),
        # AWS / Cloud Keys
        (re.compile(r"(AKIA[0-9A-Z]{16})"), "[REDACTED_AWS_KEY]"),
        (re.compile(r"(AIza[0-9A-Za-z-_]{35})"), "[REDACTED_GCP_KEY]"),
        # Connection strings with credentials e.g. postgresql://user:pass@host:5432/db
        (re.compile(r"(https?|postgresql|postgres|mysql|redis|mongodb)://([^:\s]+):([^@\s]+)@"), r"\1://\2:[REDACTED_PASSWORD]@"),
        # Generic key-value secret patterns e.g. password=xyz, api_key: "abc"
        (re.compile(r"""(?i)(password|passwd|secret|api[_-]?key|token|auth_token)\s*[:=]\s*["']?([^"'\s,;]+)["']?"""), r"\1=[REDACTED_SECRET]"),
        # PEM / Private Keys
        (re.compile(r"-----BEGIN [A-Z ]+ PRIVATE KEY-----[^-]+-----END [A-Z ]+ PRIVATE KEY-----", re.DOTALL), "[REDACTED_PRIVATE_KEY]"),
    ]

    def __init__(self, config: Optional[SandboxConfig] = None):
        self.config = config or DEFAULT_CONFIG.sandbox
        self.sensitive_keys = [k.lower() for k in self.config.sensitive_keys]

    def redact_text(self, text: str) -> str:
        """Apply regex-based masking to text."""
        if not text:
            return text
        redacted = text
        for pattern, replacement in self.PATTERNS:
            redacted = pattern.sub(replacement, redacted)
        return redacted

    def redact_data(self, data: Any) -> Any:
        """Recursively redact sensitive keys and values from dicts, lists, or strings."""
        if isinstance(data, str):
            return self.redact_text(data)
        elif isinstance(data, dict):
            new_dict = {}
            for k, v in data.items():
                k_lower = str(k).lower()
                if any(sensitive in k_lower for sensitive in self.sensitive_keys):
                    new_dict[k] = "[REDACTED_SENSITIVE_VALUE]"
                else:
                    new_dict[k] = self.redact_data(v)
            return new_dict
        elif isinstance(data, list):
            return [self.redact_data(item) for item in data]
        return data
