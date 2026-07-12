"""Account endpoints (``/api/v2/me/*``): identity, per-method balance and statistics.

API reference: https://docs.altpay.money/docs/merchant
"""

from __future__ import annotations

from ..models import Account, MethodBalance, Statistics
from .base import APICall, Resource


class AccountResource(Resource):
    """Read-only views of your merchant account. Reached via ``client.account``.

    On the sync client each method returns its result directly; on the async client it
    returns an awaitable (``await client.account.get()``).
    """

    def get(self) -> Account:
        """Get your merchant and API-key identity.

        Cheap and side-effect-free, so it works as a credential/connectivity check at
        startup: success means your credentials sign correctly and the key is active.

        Returns:
            An :class:`~altpay.models.Account`.

        API reference: https://docs.altpay.money/docs/merchant#get
        """
        return self._invoke(APICall("/api/v2/me/get", None, Account.model_validate))

    def balance(self) -> MethodBalance:
        """Get paid volume per payment method, each in its own settlement asset.

        Unlike :meth:`Invoices.balance <altpay.methods.invoices.Invoices.balance>` (which
        values everything in one fiat), this reports each method's native total: a RUB
        off-chain method totals in RUB, a USD one in USD.

        Returns:
            A :class:`~altpay.models.MethodBalance`.

        API reference: https://docs.altpay.money/docs/merchant#balance
        """
        return self._invoke(APICall("/api/v2/me/balance", None, MethodBalance.model_validate))

    def statistics(self) -> Statistics:
        """Get aggregate payment statistics (counts and USD volume).

        Returns:
            A :class:`~altpay.models.Statistics`.

        API reference: https://docs.altpay.money/docs/merchant#statistics
        """
        return self._invoke(APICall("/api/v2/me/statistics", None, Statistics.model_validate))
