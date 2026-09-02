"""
Token budget management, intelligent log truncation, and error snippet extraction.
"""

import re
from typing import List, Optional
from ..config import SandboxConfig, DEFAULT_CONFIG


class TokenBudgetManager:
    """
    Ensures log lines, manifests, and metrics data remain within safe token and character limits,
    while prioritizing critical error lines (tracebacks, panics, fatal errors, HTTP 5xx, OOM, restarts).
    """

    ERROR_PRIORITY_PATTERNS = [
        re.compile(r"(?i)panic:"),
        re.compile(r"(?i)fatal\b"),
        re.compile(r"(?i)exception\b"),
        re.compile(r"(?i)error\b"),
        re.compile(r"(?i)oomkilled"),
        re.compile(r"(?i)killed process"),
        re.compile(r"(?i)connection refused"),
        re.compile(r"(?i)timeout\b"),
        re.compile(r"(?i)status\s*50[0-9]"),
        re.compile(r"(?i)traceback"),
        re.compile(r"(?i)crashloopbackoff"),
        re.compile(r"(?i)back-off restarting"),
        re.compile(r"(?i)unhealthy"),
        re.compile(r"(?i)probe failed"),
    ]

    def __init__(self, config: Optional[SandboxConfig] = None):
        self.config = config or DEFAULT_CONFIG.sandbox

    def is_error_line(self, line: str) -> bool:
        """Check if a log line matches high-signal error patterns."""
        return any(pattern.search(line) for pattern in self.ERROR_PRIORITY_PATTERNS)

    def summarize_logs(
        self,
        raw_logs: str,
        max_lines: Optional[int] = None,
        max_bytes: Optional[int] = None,
        tail_lines: int = 50,
    ) -> str:
        """
        Intelligently sample and summarize logs:
        - Prioritizes error and exception lines
        - Keeps recent tail lines
        - Truncates within byte and line budgets with descriptive omission markers
        """
        if not raw_logs:
            return "(No logs found)"

        max_lines = max_lines or self.config.max_log_lines
        max_bytes = max_bytes or self.config.max_log_bytes

        lines = raw_logs.strip().splitlines()
        total_lines = len(lines)

        if total_lines <= max_lines and len(raw_logs) <= max_bytes:
            return raw_logs

        # Identify high-priority error lines
        error_lines = [(idx, line) for idx, line in enumerate(lines) if self.is_error_line(line)]
        
        # Tail lines (recent events are critical in RCA)
        tail_start_idx = max(0, total_lines - tail_lines)
        tail_indices = set(range(tail_start_idx, total_lines))

        selected_indices = set()
        
        # Add tail lines first
        selected_indices.update(tail_indices)

        # Add error lines (up to remaining quota)
        remaining_quota = max_lines - len(selected_indices)
        for idx, _ in error_lines:
            if len(selected_indices) >= max_lines:
                break
            selected_indices.add(idx)

        # Sort selected indices chronologically
        sorted_indices = sorted(selected_indices)

        result_lines: List[str] = []
        last_idx = -1

        for idx in sorted_indices:
            if last_idx != -1 and idx > last_idx + 1:
                omitted_count = idx - last_idx - 1
                result_lines.append(f"... [Skipped {omitted_count} non-error lines] ...")
            result_lines.append(lines[idx])
            last_idx = idx

        formatted = "\n".join(result_lines)

        # Ensure byte boundary
        if len(formatted) > max_bytes:
            formatted = formatted[:max_bytes] + f"\n... [Truncated {len(formatted) - max_bytes} bytes for token budget] ..."

        header = f"=== Log Summary (Total: {total_lines} lines | Sampled: {len(result_lines)} lines | Found {len(error_lines)} error patterns) ===\n"
        return header + formatted
