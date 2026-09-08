import re
from typing import Any, Dict, List, Optional, Set, Tuple
from ..config import SandboxConfig, DEFAULT_CONFIG


class SecurityViolationError(Exception):
    """Raised when an operation violates sandbox read-only boundaries."""
    pass


class SandboxBoundary:
    """
    Enforces strict read-only guarantees and prompt injection defenses on all agent operations.
    Acts as an inviolable proxy between the AI agent and the Kubernetes cluster.
    """

    ADVERSARIAL_INJECTION_PATTERNS = [
        re.compile(r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions?", re.IGNORECASE),
        re.compile(r"system\s*prompt\s*(override|reset|injection)", re.IGNORECASE),
        re.compile(r"you\s+are\s+now\s+in\s+developer\s+mode", re.IGNORECASE),
        re.compile(r"disregard\s+(all\s+)?safety\s+(guidelines|filters|boundaries)", re.IGNORECASE),
        re.compile(r"run\s+this\s+command\s+on\s+the\s+cluster", re.IGNORECASE),
        re.compile(r"execute\s+(the\s+following\s+)?command", re.IGNORECASE),
        re.compile(r"kubectl\s+(delete|apply|patch|create|exec|scale|drain|cordon)", re.IGNORECASE),
        re.compile(r"rm\s+-rf\s+[/~]", re.IGNORECASE),
        re.compile(r"drop\s+database\s+[a-z0-9_]+", re.IGNORECASE),
    ]

    def __init__(self, config: Optional[SandboxConfig] = None):
        self.config = config or DEFAULT_CONFIG.sandbox
        self._blocked_verbs: Set[str] = self.config.blocked_verbs
        self._allowed_verbs: Set[str] = self.config.allowed_verbs

    def validate_action(self, verb: str, resource_type: str, namespace: Optional[str] = None, details: Optional[Dict[str, Any]] = None) -> None:
        """
        Validate that the requested action is strictly read-only and safe.
        Raises SecurityViolationError on any mutation or dangerous attempt.
        """
        verb_lower = verb.lower().strip()
        
        # Check against explicitly blocked verbs
        if verb_lower in self._blocked_verbs:
            raise SecurityViolationError(
                f"SANDBOX VIOLATION: Mutation/destructive verb '{verb}' is strictly prohibited. "
                f"The RCA agent operates in 100% read-only mode."
            )

        # Check against allowed read-only whitelist
        if verb_lower not in self._allowed_verbs:
            raise SecurityViolationError(
                f"SANDBOX VIOLATION: Action '{verb}' is not in the permitted read-only whitelist ({', '.join(sorted(self._allowed_verbs))})."
            )

        # Check resource safety: Secrets metadata is allowed, but secret raw data extraction is blocked
        if resource_type.lower() in ("secrets", "secret") and details:
            if details.get("include_data") is True:
                raise SecurityViolationError(
                    "SANDBOX VIOLATION: Accessing raw Secret data values is prohibited. Only metadata is permitted."
                )

    def sanitize_arguments(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Check and sanitize tool arguments to prevent command injection, directory traversal, etc.
        """
        sanitized = {}
        for key, value in arguments.items():
            if isinstance(value, str):
                # Guard against shell chaining or path traversal attempts
                if any(inj in value for inj in [";", "&&", "||", "`", "$("]):
                    raise SecurityViolationError(
                        f"SANDBOX VIOLATION: Disallowed shell metacharacters detected in argument '{key}': {value}"
                    )
                if "../" in value or "..\\" in value:
                    raise SecurityViolationError(
                        f"SANDBOX VIOLATION: Path traversal sequence detected in argument '{key}'"
                    )
            sanitized[key] = value
        return sanitized

    def detect_prompt_injection(self, text: str) -> Tuple[bool, List[str]]:
        """
        Scan incoming telemetry (logs, events, traces, manifests) for adversarial prompt injection triggers.
        """
        if not text or not isinstance(text, str):
            return False, []
        detected_patterns = []
        for pattern in self.ADVERSARIAL_INJECTION_PATTERNS:
            matches = pattern.findall(text)
            if matches:
                detected_patterns.append(pattern.pattern)
        return len(detected_patterns) > 0, detected_patterns

    def sanitize_untrusted_telemetry(self, data: Any, fence: bool = True) -> Any:
        """
        Neutralizes adversarial instructions embedded in observability telemetry
        and optionally encloses telemetry in strict untrusted data fences.
        """
        if isinstance(data, str):
            is_injected, _ = self.detect_prompt_injection(data)
            sanitized_text = data
            if is_injected:
                for pattern in self.ADVERSARIAL_INJECTION_PATTERNS:
                    sanitized_text = pattern.sub("[INJECTION_ATTEMPT_NEUTRALIZED]", sanitized_text)
                sanitized_text = (
                    f"[SECURITY NOTICE: Adversarial prompt injection attempt detected and neutralized in untrusted telemetry]\n"
                    + sanitized_text
                )
            if fence and not sanitized_text.startswith("<UNTRUSTED_TELEMETRY_DATA"):
                return f"<UNTRUSTED_TELEMETRY_DATA source='cluster_observability'>\n{sanitized_text}\n</UNTRUSTED_TELEMETRY_DATA>"
            return sanitized_text
        elif isinstance(data, dict):
            return {k: self.sanitize_untrusted_telemetry(v, fence=False) for k, v in data.items()}
        elif isinstance(data, list):
            return [self.sanitize_untrusted_telemetry(item, fence=False) for item in data]
        return data

