"""HTTP clients: the synchronous :class:`AltPay` and asynchronous :class:`AsyncAltPay`."""

from .async_client import AsyncAltPay
from .sync_client import AltPay

__all__ = ["AltPay", "AsyncAltPay"]
