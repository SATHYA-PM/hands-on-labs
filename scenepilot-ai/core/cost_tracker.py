"""
Token budget enforcement. Raises BudgetExceeded if the spend ceiling is hit.
"""
from __future__ import annotations

import os
from core.telemetry import AGENT_TOKEN_SPEND, BUDGET_HALTS


class BudgetExceeded(Exception):
    pass


class CostTracker:
    """
    Per-request token tracker.
    Ceiling is read from the TOKEN_BUDGET_LIMIT env var (default 10 000).
    """

    def __init__(self) -> None:
        self.ceiling: int = int(os.environ.get("TOKEN_BUDGET_LIMIT", 10_000))
        self._spent: int = 0

    def add(self, tokens: int) -> None:
        self._spent += tokens
        AGENT_TOKEN_SPEND.inc(tokens)
        if self._spent > self.ceiling:
            BUDGET_HALTS.inc()
            raise BudgetExceeded(
                f"Token budget exceeded: {self._spent} > {self.ceiling}"
            )

    @property
    def spent(self) -> int:
        return self._spent

    @property
    def remaining(self) -> int:
        return max(0, self.ceiling - self._spent)

    def summary(self) -> dict:
        return {
            "spent": self._spent,
            "ceiling": self.ceiling,
            "remaining": self.remaining,
            "percent_used": round(self._spent / self.ceiling * 100, 1) if self.ceiling else 0,
        }
