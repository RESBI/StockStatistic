"""Retry policy — V2 §15.3 task failure retry logic.

Used by Dispatcher to decide whether to re-enqueue a failed slice
to another Worker. Implements exponential backoff with cap.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class RetryPolicy:
    """Exponential backoff retry policy.

    Attributes:
        max_retries: maximum retry attempts (0 = no retries)
        backoff_base: initial delay in seconds
        backoff_factor: multiplier per attempt (2.0 = exponential)
        max_backoff: upper bound on delay in seconds
    """
    max_retries: int = 3
    backoff_base: float = 1.0
    backoff_factor: float = 2.0
    max_backoff: float = 60.0

    def should_retry(self, error: dict, attempt: int) -> bool:
        """Decide whether to retry after an error.

        Args:
            error: error dict from Worker's dispatch.fail payload
                (must have ``retryable`` boolean field)
            attempt: current retry attempt count (0 = first failure)

        Returns:
            True if the task should be retried
        """
        if attempt >= self.max_retries:
            return False
        return error.get("retryable", False)

    def next_delay(self, attempt: int) -> float:
        """Compute the delay before the next retry.

        Args:
            attempt: current retry attempt count

        Returns:
            Delay in seconds (capped at ``max_backoff``)
        """
        delay = self.backoff_base * (self.backoff_factor ** attempt)
        return min(delay, self.max_backoff)
