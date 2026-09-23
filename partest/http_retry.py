"""Retry policy helpers for ApiClient / SecHttp (L5.2)."""

from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass
from typing import Optional, Tuple

from partest.tls import is_certificate_error


@dataclass
class RetryPolicy:
    """Retry only transient failures — never silent-retry business 4xx by default."""

    max_retries: int = 0
    retry_statuses: Tuple[int, ...] = (429, 502, 503)
    retry_on_network: bool = True
    backoff_base: float = 0.4
    backoff_max: float = 8.0
    jitter: float = 0.2

    def should_retry_status(self, status: int, attempt: int) -> bool:
        if attempt >= self.max_retries:
            return False
        return int(status) in self.retry_statuses

    def should_retry_network(
        self, attempt: int, exc: Optional[BaseException] = None
    ) -> bool:
        """Whether to try again after a transport failure.

        *exc* is optional for callers written before certificates were verified, but pass
        it: a rejected certificate arrives as ``httpx.ConnectError`` — indistinguishable
        here from a refused connection — and it is never transient. Retrying one costs the
        backoff of every attempt on every test and still ends in the same failure.
        """
        if not (self.retry_on_network and attempt < self.max_retries):
            return False
        return not (exc is not None and is_certificate_error(exc))

    async def sleep(self, attempt: int) -> None:
        # attempt 0 = first retry after failure
        delay = min(self.backoff_max, self.backoff_base * (2 ** attempt))
        if self.jitter:
            delay = delay * (1.0 + random.uniform(-self.jitter, self.jitter))
        await asyncio.sleep(max(delay, 0.0))


DEFAULT_NO_RETRY = RetryPolicy(max_retries=0)
