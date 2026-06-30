"""The call-description layer shared by the sync and async clients.

Each API method is described, not executed, by a resource: it returns an :class:`APICall`
that names the endpoint path, the request payload and how to parse the response into a typed
model. The client (sync or async) is the only thing that actually sends bytes, so the
resource classes contain zero transport code and zero ``async`` - one definition serves both
clients. This is the same "method object" idea aiogram uses, kept deliberately small.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Generic, TypeVar, Union

T = TypeVar("T")

#: A function that executes an :class:`APICall`. The sync client passes one returning the
#: value directly; the async client passes one returning an awaitable of the value. A
#: resource is agnostic to which it got - it just returns whatever the invoker returns, so
#: ``client.invoices.create(...)`` is a value on the sync client and an awaitable on the
#: async one, with a single resource definition serving both.
Invoker = Callable[["APICall[Any]"], Any]


@dataclass(frozen=True, slots=True)
class APICall(Generic[T]):
    """A described, not-yet-sent API call.

    Attributes:
        path: The endpoint path (e.g. ``"/api/v2/invoice/create"``).
        payload: The request body as a dict, or ``None`` for a body-less call.
        parse: A function that turns the unwrapped ``result`` payload into the typed return
            value (e.g. ``Invoice.model_validate``). Defaults to identity for raw access.
    """

    path: str
    payload: dict[str, Any] | None = None
    parse: Callable[[Any], T] = field(default=lambda x: x)  # type: ignore[assignment]


class Resource:
    """Base for the resource groups (``invoices``, ``account``).

    Holds the client's invoker. A resource builds an :class:`APICall` and hands it to
    ``self._invoke`` - so the same method body returns a value on the sync client and an
    awaitable on the async client, with no per-resource duplication.
    """

    __slots__ = ("_invoke",)

    def __init__(self, invoke: Invoker) -> None:
        self._invoke = invoke


def drop_none(payload: dict[str, Any]) -> dict[str, Any]:
    """Remove keys whose value is ``None`` so optional fields are simply omitted.

    The API treats an absent field and an explicit ``null`` differently for some optionals,
    and omitting keeps request bodies (and therefore signatures) minimal and predictable.
    """
    return {key: value for key, value in payload.items() if value is not None}
