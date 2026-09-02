"""
Security boundary enforcing read-only cluster access and tool constraints.
"""

from typing import Any, Dict, Optional, Set
from ..config import SandboxConfig, DEFAULT_CONFIG


class SecurityViolationError(Exception):
    """Raised when an operation violates sandbox read-only boundaries."""
    pass


class SandboxBoundary:
    """
    Enforces strict read-only guarantees on all agent operations.
    Acts as an inviolable proxy between the AI agent and the Kubernetes cluster.
    """

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
