from __future__ import annotations

from contextvars import ContextVar, Token

_current_org_id: ContextVar[int | None] = ContextVar("current_org_id", default=None)
_platform_admin_request: ContextVar[bool] = ContextVar(
    "platform_admin_request",
    default=False,
)


def get_current_org_id() -> int | None:
    return _current_org_id.get()


def set_current_org_id(org_id: int | None) -> Token[int | None]:
    return _current_org_id.set(int(org_id) if org_id is not None else None)


def reset_current_org_id(token: Token[int | None]) -> None:
    _current_org_id.reset(token)


def is_platform_admin_request() -> bool:
    return _platform_admin_request.get()


def set_platform_admin_request(value: bool) -> Token[bool]:
    return _platform_admin_request.set(bool(value))


def reset_platform_admin_request(token: Token[bool]) -> None:
    _platform_admin_request.reset(token)
