"""Payout (withdrawal) endpoints (``/api/v2/withdrawal/*``).

For safety, the public API can only pay out to a TRUSTED address - one you added to your
account in the dashboard, which requires your 2FA. A leaked API key therefore cannot move
funds to a new, attacker-controlled address; the most it can do is repeat a payout to an
address you already trust. To pay a new address, add it in the dashboard first.

API reference: https://docs.altpay.money/docs/withdrawals
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from ..models import Withdrawal, WithdrawalFee
from .base import APICall, Resource, drop_none


class Withdrawals(Resource):
    """Payout operations. Reached via ``client.withdrawals``.

    On the sync client each method returns its result directly; on the async client it
    returns an awaitable.
    """

    def estimate_fee(self, *, asset: str, network: str | None = None) -> WithdrawalFee:
        """Preview the fees a withdrawal would incur (service percent + estimated network fee).

        Args:
            asset: The asset to withdraw (e.g. ``"USDT"``).
            network: The settlement network (e.g. ``"USDT_TRC20"``), or ``None`` to let the
                API pick the asset's default.

        Returns:
            A :class:`~altpay.models.WithdrawalFee`.

        API reference: https://docs.altpay.money/docs/withdrawals#estimate-fee
        """
        payload = drop_none({"asset": asset, "network": network})
        return self._invoke(
            APICall("/api/v2/withdrawal/estimate-fee", payload, WithdrawalFee.model_validate)
        )

    def create(
        self,
        *,
        asset: str,
        amount: Decimal | str | int | float,
        address: str,
        network: str | None = None,
        idempotency_key: str | None = None,
    ) -> Withdrawal:
        """Request a payout of ``amount`` of ``asset`` to a TRUSTED ``address``.

        The address must already be trusted for this asset in your dashboard, or the API
        rejects the request with 403 ``address_not_trusted`` - regardless of any account
        whitelist toggle. This is the safety property: a leaked key cannot invent a new payout
        destination.

        Args:
            asset: The asset to withdraw (e.g. ``"USDT"``).
            amount: The gross amount to withdraw, greater than zero. Prefer a Decimal.
            address: The destination address. Must be a trusted address for ``asset``.
            network: The settlement network to use (metadata for the operator), or ``None``.
            idempotency_key: A unique key so a retried request returns the original payout
                instead of creating a second one. Strongly recommended.

        Returns:
            The created :class:`~altpay.models.Withdrawal` (status ``PENDING``). The gross
            amount is reserved from your balance immediately.

        Raises:
            altpay.Forbidden: The address is not trusted (``address_not_trusted``), or the
                merchant is not approved.
            altpay.ValidationError: The asset is unsupported or the amount is not positive.

        API reference: https://docs.altpay.money/docs/withdrawals#create
        """
        payload = drop_none(
            {
                "asset": asset,
                "amount": _amount_str(amount),
                "address": address,
                "network": network,
                "idempotency_key": idempotency_key,
            }
        )
        return self._invoke(
            APICall("/api/v2/withdrawal/create", payload, Withdrawal.model_validate)
        )

    def list(self, *, limit: int = 20, offset: int = 0) -> list[Withdrawal]:
        """List your payout requests, newest first.

        Args:
            limit: Page size, 1-200 (default 20).
            offset: Number of requests to skip (default 0).

        Returns:
            A list of :class:`~altpay.models.Withdrawal`.

        API reference: https://docs.altpay.money/docs/withdrawals#list
        """
        payload = {"limit": limit, "offset": offset}
        return self._invoke(
            APICall(
                "/api/v2/withdrawal/list",
                payload,
                lambda result: [Withdrawal.model_validate(item) for item in result["items"]],
            )
        )


def _amount_str(amount: Decimal | str | int | float) -> str:
    """Render an amount as a plain decimal string (no scientific notation)."""
    if isinstance(amount, str):
        return amount
    return format(Decimal(str(amount)), "f")
