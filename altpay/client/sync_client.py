"""The synchronous client, :class:`AltPay`.

Wraps an :class:`httpx.Client`. Resources (``invoices``, ``account``) describe calls; this
class signs, sends and parses them. It is the synchronous twin of
:class:`~altpay.client.async_client.AsyncAltPay` and shares all of its logic via
:mod:`altpay.client.base`.
"""

from __future__ import annotations

import time
from typing import Any, TypeVar

import httpx

from ..credentials import Credentials
from ..errors import AltPayTransportError, RateLimitError, ServerError
from ..methods.account import AccountResource
from ..methods.base import APICall
from ..methods.invoices import Invoices
from ..methods.withdrawals import Withdrawals
from .base import parse_response, prepare

T = TypeVar("T")

DEFAULT_BASE_URL = "https://api.altpay.money"


class AltPay:
    """Synchronous AltPay API client.

    Example::

        from decimal import Decimal
        from altpay import AltPay, Credentials

        client = AltPay(Credentials(
            merchant_id="...", api_key="vc_live_...", api_secret="...",
        ))
        invoice = client.invoices.create(
            uuid="order-1", amount=Decimal("100.00"), fiat_currency="USD",
            url_callback="https://example.com/altpay/webhook",
        )
        print(invoice.url)
        client.close()

    Use it as a context manager (``with AltPay(...) as client:``) to close the underlying
    HTTP connection pool automatically.

    Args:
        credentials: Your merchant credentials.
        base_url: API root (default ``https://api.altpay.money``). Override for staging.
        timeout: Per-request timeout in seconds (default 30).
        max_retries: How many times to retry a request that failed transiently - a network
            error, a 5xx, or a 429. Retries use exponential backoff and honor ``Retry-After``.
            Set to 0 to disable. Only idempotent reads and create-with-your-own-uuid are
            safe to retry, which is the whole public surface.
        http_client: Bring your own configured :class:`httpx.Client` (proxies, custom TLS,
            etc.). If given, ``base_url``/``timeout`` on the httpx client are used and this
            class will not close it for you.

    API reference: https://docs.altpay.money/docs
    """

    def __init__(
        self,
        credentials: Credentials,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 30.0,
        max_retries: int = 2,
        http_client: httpx.Client | None = None,
    ) -> None:
        self._credentials = credentials
        self._base_url = base_url.rstrip("/")
        self._max_retries = max_retries
        self._owns_client = http_client is None
        self._http = http_client or httpx.Client(timeout=timeout)

        #: Invoice and static-wallet operations.
        self.invoices = Invoices(self.call)
        #: Payout (withdrawal) operations.
        self.withdrawals = Withdrawals(self.call)
        #: Account identity, balance and statistics.
        self.account = AccountResource(self.call)

    def __enter__(self) -> "AltPay":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        """Close the underlying HTTP connection pool (unless you supplied your own client)."""
        if self._owns_client:
            self._http.close()

    def call(self, call: APICall[T]) -> T:
        """Execute a described :class:`~altpay.methods.base.APICall` and return its typed result.

        You normally call resource methods (``client.invoices.create(...)``) which return an
        ``APICall`` and pass it here implicitly; use :meth:`call` directly only for advanced
        or custom calls.
        """
        request = prepare(
            credentials=self._credentials,
            base_url=self._base_url,
            path=call.path,
            payload=call.payload,
        )
        attempt = 0
        while True:
            try:
                response = self._http.request(
                    request.method, request.url, headers=request.headers, content=request.content
                )
            except httpx.HTTPError as exc:
                if attempt >= self._max_retries:
                    raise AltPayTransportError(str(exc)) from exc
                time.sleep(_backoff(attempt))
                attempt += 1
                continue

            try:
                result = parse_response(
                    status_code=response.status_code,
                    body_text=response.text,
                    headers=response.headers,
                )
            except (RateLimitError, ServerError) as exc:
                if attempt >= self._max_retries:
                    raise
                time.sleep(_retry_delay(exc, attempt))
                attempt += 1
                continue
            return call.parse(result)


def _backoff(attempt: int) -> float:
    """Exponential backoff: 0.5s, 1s, 2s, ... capped at 8s."""
    return min(0.5 * (2 ** attempt), 8.0)


def _retry_delay(exc: Any, attempt: int) -> float:
    """Honor a 429's Retry-After when present, else fall back to exponential backoff."""
    retry_after = getattr(exc, "retry_after", None)
    if retry_after is not None:
        return float(retry_after)
    return _backoff(attempt)
