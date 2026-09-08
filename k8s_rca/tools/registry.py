"""
Tool registry and sandboxed execution gateway for SRE diagnostic tools.
"""

import functools
import inspect
import time
from typing import Any, Callable, Dict, List, Optional
from pydantic import BaseModel, ConfigDict
from ..sandbox.boundary import SandboxBoundary, SecurityViolationError
from ..sandbox.redactor import SensitiveDataRedactor
from ..sandbox.token_budget import TokenBudgetManager
from ..types import ToolCallRecord


class ToolMetadata(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    name: str
    description: str
    parameters: Dict[str, Any]
    func: Optional[Callable] = None



def sre_tool(name: str, description: str, parameters: Dict[str, Any]):
    """Decorator to mark a function as an SRE Diagnostic Tool."""
    def decorator(func: Callable):
        setattr(func, "_sre_tool_meta", ToolMetadata(
            name=name,
            description=description,
            parameters=parameters,
            func=func,
        ))
        return func
    return decorator


class ToolRegistry:
    """
    Central registry for SRE tools that enforces sandboxing, redaction,
    and token budget guardrails on all tool invocations.
    """

    def __init__(
        self,
        boundary: Optional[SandboxBoundary] = None,
        redactor: Optional[SensitiveDataRedactor] = None,
        budget_manager: Optional[TokenBudgetManager] = None,
    ):
        self.boundary = boundary or SandboxBoundary()
        self.redactor = redactor or SensitiveDataRedactor()
        self.budget_manager = budget_manager or TokenBudgetManager()
        self.tools: Dict[str, ToolMetadata] = {}

    def register(self, tool_meta: ToolMetadata) -> None:
        """Register a tool definition."""
        self.tools[tool_meta.name] = tool_meta

    def register_instance(self, obj: Any) -> None:
        """Scan an object instance for methods decorated with @sre_tool."""
        for attr_name in dir(obj):
            attr = getattr(obj, attr_name)
            if hasattr(attr, "_sre_tool_meta"):
                meta = getattr(attr, "_sre_tool_meta")
                self.tools[meta.name] = ToolMetadata(
                    name=meta.name,
                    description=meta.description,
                    parameters=meta.parameters,
                    func=attr,
                )

    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        """Get standard JSON schema declarations for all registered tools."""
        schemas = []
        for name, meta in self.tools.items():
            schemas.append({
                "type": "function",
                "function": {
                    "name": meta.name,
                    "description": meta.description,
                    "parameters": meta.parameters,
                }
            })
        return schemas

    def execute(self, tool_name: str, arguments: Dict[str, Any]) -> ToolCallRecord:
        """
        Execute a tool within the sandbox security boundary.
        Enforces sanitization, read-only guarantees, sensitive data redaction, and timing.
        """
        start_time = time.perf_counter()

        if tool_name not in self.tools:
            return ToolCallRecord(
                tool_name=tool_name,
                arguments=arguments,
                result=f"Error: Unknown tool '{tool_name}'. Available tools: {list(self.tools.keys())}",
                is_error=True,
                duration_ms=0.0,
            )

        meta = self.tools[tool_name]

        try:
            # 1. Sanitize tool arguments through the security boundary
            sanitized_args = self.boundary.sanitize_arguments(tool_name, arguments)

            # 2. Invoke tool
            if meta.func is None:
                raise RuntimeError(f"Tool {tool_name} has no executable target function")

            raw_result = meta.func(**sanitized_args)

            # 3. Apply redaction to mask any credentials/secrets
            redacted_result = self.redactor.redact_data(raw_result)

            # 4. Apply token budget summarization if the result is text/logs
            if isinstance(redacted_result, str):
                summarized_result = self.budget_manager.summarize_logs(redacted_result)
            else:
                summarized_result = redacted_result

            # 5. Sanitize untrusted telemetry and neutralize prompt injection attempts
            final_result = self.boundary.sanitize_untrusted_telemetry(summarized_result)

            duration = (time.perf_counter() - start_time) * 1000.0

            return ToolCallRecord(
                tool_name=tool_name,
                arguments=sanitized_args,
                result=final_result,
                is_error=False,
                duration_ms=duration,
            )

        except SecurityViolationError as sec_err:
            duration = (time.perf_counter() - start_time) * 1000.0
            return ToolCallRecord(
                tool_name=tool_name,
                arguments=arguments,
                result=f"SECURITY VIOLATION BLOCKED: {str(sec_err)}",
                is_error=True,
                duration_ms=duration,
            )
        except Exception as ex:
            duration = (time.perf_counter() - start_time) * 1000.0
            return ToolCallRecord(
                tool_name=tool_name,
                arguments=arguments,
                result=f"Tool Execution Error: {type(ex).__name__}: {str(ex)}",
                is_error=True,
                duration_ms=duration,
            )
