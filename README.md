# altpay-py

Official Python SDK for the [AltPay](https://altpay.money) crypto-payments API. Synchronous
and asynchronous clients, typed models, request signing and webhook verification in one
package. Built on `httpx` and `pydantic` v2.

```bash
pip install altpay-py
```

```python
import altpay  # the distribution is altpay-py; the import name is altpay
```

## Quick start

```python
from decimal import Decimal
from altpay import AltPay, Credentials

client = AltPay(Credentials(
    merchant_id="YOUR_MERCHANT_ID",
    api_key="vc_live_...",
    api_secret="YOUR_API_SECRET",
))

invoice = client.invoices.create(
    uuid="order-42",                 # your idempotency key / order reference
    amount=Decimal("100.00"),
    fiat_currency="USD",
    url_callback="https://example.com/altpay/webhook",
)
print(invoice.url)                   # hosted checkout URL to redirect the payer to

# later, check on it
invoice = client.invoices.get(order_id=invoice.order_id)
print(invoice.status)                # PaymentStatus.WAITING | PAID | EXPIRED | ...
```

### Async

The async client mirrors the sync one exactly; just `await` the calls.

```python
from altpay import AsyncAltPay, Credentials

async with AsyncAltPay(creds) as client:
    invoice = await client.invoices.create(
        uuid="order-42", amount="100.00", fiat_currency="USD",
    )
    print(invoice.url)
```

## What you can do

| Resource | Method | Endpoint |
| --- | --- | --- |
| `client.invoices` | `create(...)` | create an invoice |
| | `get(order_id=... \| uuid=...)` | fetch one invoice |
| | `list(status=..., cursor=..., limit=...)` | page through invoices |
| | `services()` | available methods, limits and fees |
| | `balance(fiat_currency=...)` | balance valued in one fiat, per asset |
| | `create_wallet(network=..., order_id=...)` | static deposit wallet |
| | `list_wallets(limit=..., offset=...)` | list static wallets |
| `client.account` | `get()` | merchant + API-key identity |
| | `balance()` | paid volume per method (native asset) |
| | `statistics()` | aggregate counts and USD volume |

## Webhooks

AltPay POSTs a signed `payment.updated` event to your `url_callback` when an invoice is
paid. **Always verify the signature before trusting the body**, and pass the *raw* request
bytes (not the re-serialized JSON).

```python
from altpay import WebhookVerifier

verifier = WebhookVerifier(WEBHOOK_SECRET, target="/altpay/webhook")

# inside your handler (framework-agnostic):
event = verifier.parse(raw_body, request_headers)   # raises AuthenticationError on a bad sig
if event.status == "paid":
    fulfil_order(event.merchant_reference)
```

`verifier.verify(raw_body, headers)` returns a bool if you prefer to branch yourself.

## Errors

Every failure is an `AltPayError`. Network problems raise `AltPayTransportError`; anything the
API rejected raises an `APIError` subclass keyed by HTTP status. Each carries the server's
machine-readable `detail`, a human `hint`, and the `request_id` for support.

```python
from altpay import AuthenticationError, RateLimitError, ValidationError, NotFoundError

try:
    client.invoices.create(uuid="o1", amount="100", fiat_currency="USD")
except AuthenticationError as e:
    ...   # bad credentials / clock skew / revoked key  (HTTP 401, detail="invalid_signature")
except ValidationError as e:
    ...   # a field failed validation                   (HTTP 400, detail="invalid_request")
except RateLimitError as e:
    sleep(e.retry_after or 1)                            # HTTP 429
except NotFoundError as e:
    ...                                                  # HTTP 404
```

The full catalogue, with every `detail` value and how to fix it, is at
<https://docs.altpay.money/docs/http-codes>.

## Configuration

```python
AltPay(
    credentials,
    base_url="https://api.altpay.money",  # override for staging
    timeout=30.0,                          # per-request seconds
    max_retries=2,                         # retry transient errors (5xx, 429, network) with backoff
    http_client=my_httpx_client,           # bring your own httpx.Client (proxies, custom TLS)
)
```

## Authentication, in brief

Each request is signed with HMAC-SHA256 over a canonical string of the merchant id, API key,
timestamp, nonce, body hash, method and path. The SDK does this for you; the secret never
leaves your process. If you ever need the primitives (custom transport, testing), they live
in `altpay.signing`. Full spec: <https://docs.altpay.money/docs/authentication>.

## Requirements

- Python 3.10+
- `httpx >= 0.24`, `pydantic >= 2.0`

## License

MIT
