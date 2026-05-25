from __future__ import annotations

from typing import Annotated, Any, NoReturn

from fastapi import Depends, Header, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from saas.repository import SaaSRepository
from saas.security import parse_access_token
from saas.service import AuthService
from saas.tenant_context import (
    reset_current_org_id,
    reset_platform_admin_request,
    set_current_org_id,
    set_platform_admin_request,
)

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user_context(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    x_org_id: Annotated[int | None, Header(alias="X-Org-Id")] = None,
):
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise_auth_required()
    try:
        claims = parse_access_token(credentials.credentials)
        user_id = int(claims["sub"])
    except (ValueError, TypeError, KeyError) as exc:
        raise _auth_required_exception() from exc
    context = await AuthService().get_context(user_id=user_id, org_id=x_org_id)
    if context is None:
        raise HTTPException(
            status_code=403,
            detail={"code": "ORG_FORBIDDEN", "message": "Organization is not available"},
        )
    token = set_current_org_id(int(context["organization"]["id"]))
    try:
        yield context
    finally:
        reset_current_org_id(token)


async def require_current_user(
    context: Annotated[dict[str, Any], Depends(get_current_user_context)],
) -> dict[str, Any]:
    return context


async def require_platform_admin(
    context: Annotated[dict[str, Any], Depends(get_current_user_context)],
):
    user_id = int(context["user"]["id"])
    if not await SaaSRepository().is_platform_admin(user_id):
        raise HTTPException(
            status_code=403,
            detail={"code": "ADMIN_FORBIDDEN", "message": "Platform admin access is required"},
        )
    token = set_platform_admin_request(True)
    try:
        yield context
    finally:
        reset_platform_admin_request(token)


def raise_auth_required() -> NoReturn:
    raise _auth_required_exception()


def _auth_required_exception() -> HTTPException:
    return HTTPException(
        status_code=401,
        detail={"code": "AUTH_REQUIRED", "message": "Authentication required"},
        headers={"WWW-Authenticate": "Bearer"},
    )
