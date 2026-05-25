from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

from saas.repository import SaaSRepository
from saas.security import (
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)

ACCESS_TOKEN_MINUTES = 30
REFRESH_TOKEN_DAYS = 30


class AuthError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class AuthService:
    def __init__(self, repository: SaaSRepository | None = None):
        self.repository = repository or SaaSRepository()

    async def register(
        self,
        *,
        email: str,
        password: str,
        organization_name: str,
        display_name: str | None = None,
    ) -> dict[str, Any]:
        normalized_email = email.strip().lower()
        if await self.repository.get_user_by_email(normalized_email):
            raise AuthError("EMAIL_ALREADY_REGISTERED", "Email is already registered")
        refresh_token = generate_refresh_token()
        context = await self.repository.create_registration(
            email=normalized_email,
            password_hash=hash_password(password),
            organization_name=organization_name.strip(),
            display_name=display_name.strip() if display_name else None,
            refresh_token_hash=hash_refresh_token(refresh_token),
            refresh_expires_at=_refresh_expires_at(),
        )
        if _is_configured_platform_admin(normalized_email):
            await self.repository.ensure_platform_admin(int(context["user"]["id"]))
        return await self._with_tokens(context, refresh_token=refresh_token)

    async def login(self, *, email: str, password: str) -> dict[str, Any]:
        normalized_email = email.strip().lower()
        user = await self.repository.get_user_by_email(normalized_email)
        if not user or user["status"] != "active":
            raise AuthError("INVALID_CREDENTIALS", "Invalid email or password")
        if not verify_password(password, user["password_hash"]):
            raise AuthError("INVALID_CREDENTIALS", "Invalid email or password")
        context = await self.repository.get_user_context(int(user["id"]))
        if context is None:
            raise AuthError("NO_ACTIVE_ORGANIZATION", "No active organization is available")
        if _is_configured_platform_admin(normalized_email):
            await self.repository.ensure_platform_admin(int(user["id"]))
        refresh_token = generate_refresh_token()
        await self.repository.create_refresh_token(
            user_id=int(user["id"]),
            token_hash=hash_refresh_token(refresh_token),
            expires_at=_refresh_expires_at(),
        )
        await self.repository.create_audit_log(
            action="auth.login",
            user_id=int(user["id"]),
            org_id=int(context["organization"]["id"]),
            target_type="user",
            target_id=str(user["id"]),
        )
        return await self._with_tokens(context, refresh_token=refresh_token)

    async def refresh(self, refresh_token: str) -> dict[str, Any]:
        next_refresh_token = generate_refresh_token()
        context = await self.repository.rotate_refresh_token(
            old_token_hash=hash_refresh_token(refresh_token),
            new_token_hash=hash_refresh_token(next_refresh_token),
            expires_at=_refresh_expires_at(),
        )
        if context is None:
            raise AuthError("INVALID_REFRESH_TOKEN", "Refresh token is invalid or expired")
        return await self._with_tokens(context, refresh_token=next_refresh_token)

    async def logout(self, refresh_token: str) -> dict[str, bool]:
        revoked = await self.repository.revoke_refresh_token(hash_refresh_token(refresh_token))
        return {"revoked": revoked}

    async def get_context(
        self, *, user_id: int, org_id: int | None = None
    ) -> dict[str, Any] | None:
        context = await self.repository.get_user_context(user_id, org_id=org_id)
        if context is None:
            return None
        context["user"] = _public_user(context["user"])
        context["permissions"] = {
            "is_platform_admin": await self.repository.is_platform_admin(user_id)
        }
        return context

    async def _with_tokens(self, context: dict[str, Any], *, refresh_token: str) -> dict[str, Any]:
        user_id = int(context["user"]["id"])
        public_context = {
            "user": _public_user(context["user"]),
            "organization": context["organization"],
            "membership": context["membership"],
            "permissions": {
                "is_platform_admin": await self.repository.is_platform_admin(user_id),
            },
        }
        return {
            **public_context,
            "access_token": create_access_token(
                subject=str(context["user"]["id"]),
                expires_delta=timedelta(minutes=ACCESS_TOKEN_MINUTES),
                extra_claims={"email": context["user"]["email"]},
            ),
            "refresh_token": refresh_token,
            "token_type": "bearer",
        }


def _public_user(user: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in user.items() if key != "password_hash"}


def _refresh_expires_at() -> datetime:
    return datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_DAYS)


def _is_configured_platform_admin(email: str) -> bool:
    raw = os.getenv("SAAS_PLATFORM_ADMIN_EMAILS", "")
    configured = {
        item.strip().lower()
        for chunk in raw.split(";")
        for item in chunk.split(",")
        if item.strip()
    }
    return email.strip().lower() in configured
