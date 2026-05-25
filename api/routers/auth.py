from __future__ import annotations

from fastapi import APIRouter, HTTPException

from saas.schemas import AuthResponse, LoginRequest, LogoutRequest, RefreshRequest, RegisterRequest
from saas.service import AuthError, AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=AuthResponse)
async def register(request: RegisterRequest):
    try:
        return await AuthService().register(
            email=request.email,
            password=request.password,
            organization_name=request.organization_name,
            display_name=request.display_name,
        )
    except AuthError as exc:
        raise _auth_http_error(exc) from exc


@router.post("/login", response_model=AuthResponse)
async def login(request: LoginRequest):
    try:
        return await AuthService().login(email=request.email, password=request.password)
    except AuthError as exc:
        raise _auth_http_error(exc) from exc


@router.post("/refresh", response_model=AuthResponse)
async def refresh(request: RefreshRequest):
    try:
        return await AuthService().refresh(request.refresh_token)
    except AuthError as exc:
        raise _auth_http_error(exc) from exc


@router.post("/logout")
async def logout(request: LogoutRequest):
    return await AuthService().logout(request.refresh_token)


def _auth_http_error(exc: AuthError) -> HTTPException:
    status = 409 if exc.code == "EMAIL_ALREADY_REGISTERED" else 401
    return HTTPException(
        status_code=status,
        detail={"code": exc.code, "message": exc.message},
    )
