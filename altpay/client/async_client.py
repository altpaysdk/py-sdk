"""The asynchronous client, :class:`AsyncAltPay`.

The async twin of :class:`~altpay.client.sync_client.AltPay`. Same API, same resources,
and the same request/response logic from :mod:`altpay.client.base`; only the I/O is awaited.
"""

from __future__ import annotations

import asyncio
from typing import Any, TypeVar

import httpx

from ..credentials import Credentials
from ..errors import AltPayTransportError, RateLimitError, ServerError
from ..methods.account import AccountResource
from ..methods.base import APICall
from ..methods.invoices import Invoices
from ..methods.withdrawals import Withdrawals
from .base import parse_response, prepare
from .sync_client import DEFAULT_BASE_URL, _backoff, _retry_delay

T = TypeVar("T")


class AsyncAltPay:
    """Asynchronous AltPay API client.

    Example::

        from decimal import Decimal
        from altpay import AsyncAltPay, Credentials

        async with AsyncAltPay(Credentials(
            merchant_id="...", api_key="vc_live_...", api_secret="...",
        )) as client:
            invoice = await client.invoices.create(
                uuid="order-1", amount=Decimal("100.00"), fiat_currency="USD",
            )
            print(invoice.url)

    Args mirror :class:`~altpay.client.sync_client.AltPay`. Here ``http_client`` is an
    :class:`httpx.AsyncClient`.

    API reference: https://docs.altpay.money/docs
    """

    def __init__(
        self,
        credentials: Credentials,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 30.0,
        max_retries: int = 2,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._credentials = credentials
        self._base_url = base_url.rstrip("/")
        self._max_retries = max_retries
        self._owns_client = http_client is None
        self._http = http_client or httpx.AsyncClient(timeout=timeout)

        #: Invoice and static-wallet operations.
        self.invoices = Invoices(self.call)
        #: Payout (withdrawal) operations.
        self.withdrawals = Withdrawals(self.call)
        #: Account identity, balance and statistics.
        self.account = AccountResource(self.call)

    async def __aenter__(self) -> "AsyncAltPay":
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        """Close the underlying HTTP connection pool, unless you supplied your own client."""
        if self._owns_client:
            await self._http.aclose()

    async def call(self, call: APICall[T]) -> T:
        """Execute a described :class:`~altpay.methods.base.APICall` and return its typed result."""
        attempt = 0
        while True:
            # Re-sign on every attempt: each request carries a fresh nonce and timestamp.
            # The server rejects a reused nonce inside the signature TTL (replay protection),
            # so a retry that resent the original headers would 401 instead of retrying.
            request = prepare(
                credentials=self._credentials,
                base_url=self._base_url,
                path=call.path,
                payload=call.payload,
            )
            try:
                response = await self._http.request(
                    request.method, request.url, headers=request.headers, content=request.content
                )
            except httpx.HTTPError as exc:
                if attempt >= self._max_retries:
                    raise AltPayTransportError(str(exc)) from exc
                await asyncio.sleep(_backoff(attempt))
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
                await asyncio.sleep(_retry_delay(exc, attempt))
                attempt += 1
                continue
            return call.parse(result)
