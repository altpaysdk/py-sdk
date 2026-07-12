"""Response decoding. The wire vocabulary is lowercase on both REST and webhooks, amounts
arrive as strings to dodge float rounding, and unknown fields must not break an old SDK."""

from __future__ import annotations

from decimal import Decimal

import pytest

from altpay.enums import PaymentStatus
from altpay.errors import RateLimitError, ValidationError, error_from_status
from altpay.models import Invoice, WebhookEvent


def test_payment_status_round_trips_its_wire_value():
    assert PaymentStatus("paid") is PaymentStatus.PAID
    assert PaymentStatus.PAID == "paid"


def test_is_final_covers_exactly_the_terminal_states():
    final = {s for s in PaymentStatus if s.is_final}
    assert final == {PaymentStatus.PAID, PaymentStatus.EXPIRED, PaymentStatus.FAILED}


def test_invoice_amounts_decode_as_decimal():
    invoice = Invoice.model_validate(
        {
            "order_id": "o1",
            "amount": "100.00",
            "fiat_currency": "USD",
            "url": "https://pay/x",
            "status": "waiting",
            "is_final": False,
            "created_at": "2026-07-13T00:00:00Z",
            "updated_at": "2026-07-13T00:00:00Z",
        }
    )
    assert invoice.amount == Decimal("100.00")
    assert invoice.status is PaymentStatus.WAITING


def test_unknown_fields_are_ignored():
    # The server may add fields; an older SDK must decode the ones it knows and drop the rest.
    invoice = Invoice.model_validate(
        {
            "order_id": "o1",
            "amount": "1",
            "fiat_currency": "USD",
            "url": "https://pay/x",
            "status": "paid",
            "is_final": True,
            "created_at": "2026-07-13T00:00:00Z",
            "updated_at": "2026-07-13T00:00:00Z",
            "a_field_from_the_future": {"nested": True},
        }
    )
    assert invoice.status is PaymentStatus.PAID


def test_webhook_event_decodes_lowercase_status():
    body = b'{"event":"payment.updated","payment_id":"p","external_id":"o","status":"paid"}'
    event = WebhookEvent.model_validate_json(body)
    assert event.status is PaymentStatus.PAID
    assert event.external_id == "o"


@pytest.mark.parametrize(
    "status_code, expected",
    [(400, ValidationError), (422, ValidationError), (429, RateLimitError)],
)
def test_error_from_status_maps_to_the_specific_subclass(status_code, expected):
    err = error_from_status(status_code, detail="x")
    assert isinstance(err, expected)


def test_rate_limit_error_exposes_retry_after():
    err = error_from_status(429, detail="rate_limited", retry_after=2.5)
    assert isinstance(err, RateLimitError)
    assert err.retry_after == 2.5
