"""Retries re-sign. The signature covers a nonce the server rejects on reuse inside the
TTL, so resending the original headers would 401 instead of retrying. These tests pin
that each attempt is freshly signed and that non-transient failures are not retried."""

from __future__ import annotations

import httpx
import pytest

from altpay import AltPay, AsyncAltPay, Credentials, ValidationError

CREDS = Credentials(
    merchant_id="11111111-2222-3333-4444-555555555555",
    api_key="pk_test",
    api_secret="s3cr3t",
)

_INVOICE_OK = {
    "result": {
        "order_id": "o1",
        "amount": "100.00",
        "fiat_currency": "USD",
        "url": "https://pay.altpay.money/o1",
        "status": "waiting",
        "is_final": False,
        "created_at": "2026-07-13T00:00:00Z",
        "updated_at": "2026-07-13T00:00:00Z",
    }
}


class _Recorder:
    """Serves a scripted sequence of responses and records the nonce of every attempt."""

    def __init__(self, *responses: httpx.Response) -> None:
        self._responses = list(responses)
        self.nonces: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.nonces.append(request.headers["X-Nonce"])
        return self._responses[len(self.nonces) - 1]


def _client(recorder: _Recorder) -> AltPay:
    transport = httpx.MockTransport(recorder)
    return AltPay(CREDS, http_client=httpx.Client(transport=transport), max_retries=2)


def test_retry_uses_a_fresh_nonce_each_attempt():
    rec = _Recorder(
        httpx.Response(500, json={"detail": "server_error"}),
        httpx.Response(200, json=_INVOICE_OK),
    )
    invoice = _client(rec).invoices.create(uuid="o1", amount="100.00", fiat_currency="USD")
    assert invoice.order_id == "o1"
    assert len(rec.nonces) == 2
    assert rec.nonces[0] != rec.nonces[1]


def test_429_is_retried():
    rec = _Recorder(
        httpx.Response(429, json={"detail": "rate_limited"}, headers={"Retry-After": "0"}),
        httpx.Response(200, json=_INVOICE_OK),
    )
    _client(rec).invoices.create(uuid="o1", amount="100.00", fiat_currency="USD")
    assert len(rec.nonces) == 2


def test_validation_error_is_not_retried():
    # A 400 is the callers fault, not transient. Retrying it just wastes a round-trip.
    rec = _Recorder(httpx.Response(400, json={"detail": "invalid_request"}))
    with pytest.raises(ValidationError):
        _client(rec).invoices.create(uuid="o1", amount="-1", fiat_currency="USD")
    assert len(rec.nonces) == 1


def test_retries_are_exhausted_then_the_error_surfaces():
    rec = _Recorder(*[httpx.Response(500, json={"detail": "server_error"})] * 3)
    from altpay import ServerError

    with pytest.raises(ServerError):
        _client(rec).invoices.create(uuid="o1", amount="100.00", fiat_currency="USD")
    assert len(rec.nonces) == 3  # initial attempt + max_retries=2


async def test_async_client_also_re_signs_each_retry():
    rec = _Recorder(
        httpx.Response(500, json={"detail": "server_error"}),
        httpx.Response(200, json=_INVOICE_OK),
    )
    transport = httpx.MockTransport(rec)
    async with AsyncAltPay(CREDS, http_client=httpx.AsyncClient(transport=transport)) as client:
        invoice = await client.invoices.create(uuid="o1", amount="100.00", fiat_currency="USD")
    assert invoice.order_id == "o1"
    assert rec.nonces[0] != rec.nonces[1]
