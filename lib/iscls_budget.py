"""Budget calculations for the optional Gemini embedding arm."""

from __future__ import annotations

from dataclasses import dataclass


GEMINI_TEXT_USD_PER_MILLION_TOKENS = 0.20
DEFAULT_HARD_CAP_USD = 0.50
DEFAULT_STOP_USD = 0.40


@dataclass(frozen=True)
class BudgetEstimate:
    corpus_tokens: int
    query_tokens: int
    total_tokens: int
    estimated_cost_usd: float
    hard_cap_usd: float
    stop_usd: float

    @property
    def under_stop(self) -> bool:
        return self.estimated_cost_usd <= self.stop_usd

    @property
    def under_cap(self) -> bool:
        return self.estimated_cost_usd <= self.hard_cap_usd


def estimate_embedding_budget(
    corpus_tokens: int,
    query_tokens: int = 0,
    *,
    price_per_million: float = GEMINI_TEXT_USD_PER_MILLION_TOKENS,
    hard_cap_usd: float = DEFAULT_HARD_CAP_USD,
    stop_usd: float = DEFAULT_STOP_USD,
) -> BudgetEstimate:
    if min(corpus_tokens, query_tokens) < 0:
        raise ValueError("token counts cannot be negative")
    if not 0 <= stop_usd <= hard_cap_usd:
        raise ValueError("stop_usd must be between zero and hard_cap_usd")
    total = corpus_tokens + query_tokens
    return BudgetEstimate(
        corpus_tokens=corpus_tokens,
        query_tokens=query_tokens,
        total_tokens=total,
        estimated_cost_usd=total / 1_000_000 * price_per_million,
        hard_cap_usd=hard_cap_usd,
        stop_usd=stop_usd,
    )
