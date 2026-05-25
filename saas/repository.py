from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from database.db_session import get_session
from saas.models import (
    AuditLog,
    Organization,
    OrganizationMembership,
    PlatformAdmin,
    RefreshToken,
    User,
)


class SaaSRepository:
    async def get_user_by_email(self, email: str) -> dict[str, Any] | None:
        async with get_session() as session:
            result = await session.execute(select(User).where(User.email == email))
            user = result.scalar_one_or_none()
            return self._user_to_dict(user) if user else None

    async def get_user_by_id(self, user_id: int) -> dict[str, Any] | None:
        async with get_session() as session:
            user = await session.get(User, user_id)
            return self._user_to_dict(user) if user else None

    async def create_registration(
        self,
        *,
        email: str,
        password_hash: str,
        organization_name: str,
        display_name: str | None,
        refresh_token_hash: str,
        refresh_expires_at: datetime,
    ) -> dict[str, Any]:
        async with get_session() as session:
            user = User(
                email=email,
                password_hash=password_hash,
                display_name=display_name,
                status="active",
                email_verified=False,
            )
            session.add(user)
            await session.flush()

            org = Organization(
                name=organization_name,
                slug=await self._unique_slug(session, organization_name),
                status="active",
            )
            session.add(org)
            await session.flush()

            membership = OrganizationMembership(
                user_id=user.id,
                org_id=org.id,
                role="member",
                status="active",
            )
            session.add(membership)

            refresh = RefreshToken(
                user_id=user.id,
                token_hash=refresh_token_hash,
                expires_at=refresh_expires_at,
            )
            session.add(refresh)

            session.add(
                AuditLog(
                    org_id=org.id,
                    user_id=user.id,
                    action="auth.register",
                    target_type="user",
                    target_id=str(user.id),
                    before_json={},
                    after_json={"email": email, "org_id": org.id},
                    metadata_json={},
                )
            )
            await session.flush()
            await session.refresh(user)
            await session.refresh(org)
            await session.refresh(membership)
            return {
                "user": self._user_to_dict(user),
                "organization": self._organization_to_dict(org),
                "membership": self._membership_to_dict(membership),
            }

    async def create_refresh_token(
        self,
        *,
        user_id: int,
        token_hash: str,
        expires_at: datetime,
    ) -> None:
        async with get_session() as session:
            session.add(
                RefreshToken(
                    user_id=user_id,
                    token_hash=token_hash,
                    expires_at=expires_at,
                )
            )

    async def rotate_refresh_token(
        self,
        *,
        old_token_hash: str,
        new_token_hash: str,
        expires_at: datetime,
    ) -> dict[str, Any] | None:
        now = datetime.now(timezone.utc)
        async with get_session() as session:
            result = await session.execute(
                select(RefreshToken).where(RefreshToken.token_hash == old_token_hash)
            )
            token = result.scalar_one_or_none()
            if token is None or token.revoked_at is not None:
                return None
            if _as_utc(token.expires_at) <= now:
                return None
            token.revoked_at = now
            user = await session.get(User, token.user_id)
            if user is None or user.status != "active":
                return None
            session.add(
                RefreshToken(
                    user_id=user.id,
                    token_hash=new_token_hash,
                    expires_at=expires_at,
                )
            )
            await session.flush()
            return await self._context_for_user_id(session, int(user.id))

    async def revoke_refresh_token(self, token_hash: str) -> bool:
        now = datetime.now(timezone.utc)
        async with get_session() as session:
            result = await session.execute(
                select(RefreshToken).where(RefreshToken.token_hash == token_hash)
            )
            token = result.scalar_one_or_none()
            if token is None or token.revoked_at is not None:
                return False
            token.revoked_at = now
            return True

    async def get_user_context(
        self, user_id: int, org_id: int | None = None
    ) -> dict[str, Any] | None:
        async with get_session() as session:
            return await self._context_for_user_id(session, user_id, org_id=org_id)

    async def is_platform_admin(self, user_id: int) -> bool:
        async with get_session() as session:
            result = await session.execute(
                select(PlatformAdmin).where(
                    PlatformAdmin.user_id == user_id,
                    PlatformAdmin.status == "active",
                )
            )
            return result.scalar_one_or_none() is not None

    async def ensure_platform_admin(self, user_id: int, role: str = "admin") -> None:
        async with get_session() as session:
            result = await session.execute(
                select(PlatformAdmin).where(PlatformAdmin.user_id == user_id)
            )
            existing = result.scalar_one_or_none()
            if existing is None:
                session.add(PlatformAdmin(user_id=user_id, role=role, status="active"))
                return
            existing.role = role
            existing.status = "active"

    async def create_audit_log(
        self,
        *,
        action: str,
        user_id: int | None = None,
        org_id: int | None = None,
        target_type: str | None = None,
        target_id: str | None = None,
        before: dict[str, Any] | None = None,
        after: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        async with get_session() as session:
            session.add(
                AuditLog(
                    org_id=org_id,
                    user_id=user_id,
                    action=action,
                    target_type=target_type,
                    target_id=target_id,
                    before_json=before or {},
                    after_json=after or {},
                    metadata_json=metadata or {},
                )
            )

    async def _context_for_user_id(
        self, session, user_id: int, org_id: int | None = None
    ) -> dict[str, Any] | None:
        user = await session.get(User, user_id)
        if user is None or user.status != "active":
            return None
        stmt = (
            select(OrganizationMembership, Organization)
            .join(Organization, Organization.id == OrganizationMembership.org_id)
            .where(
                OrganizationMembership.user_id == user_id,
                OrganizationMembership.status == "active",
                Organization.status == "active",
            )
            .order_by(OrganizationMembership.id.asc())
        )
        if org_id is not None:
            stmt = stmt.where(OrganizationMembership.org_id == org_id)
        result = await session.execute(stmt)
        row = result.first()
        if row is None:
            return None
        membership, organization = row
        return {
            "user": self._user_to_dict(user),
            "organization": self._organization_to_dict(organization),
            "membership": self._membership_to_dict(membership),
        }

    async def _unique_slug(self, session, name: str) -> str:
        base = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-") or "workspace"
        candidate = base
        counter = 2
        while True:
            result = await session.execute(
                select(Organization.id).where(Organization.slug == candidate)
            )
            if result.scalar_one_or_none() is None:
                return candidate
            candidate = f"{base}-{counter}"
            counter += 1

    def _user_to_dict(self, user: User) -> dict[str, Any]:
        return {
            "id": user.id,
            "email": user.email,
            "display_name": user.display_name,
            "status": user.status,
            "email_verified": bool(user.email_verified),
            "created_at": user.created_at,
            "password_hash": user.password_hash,
        }

    def _organization_to_dict(self, org: Organization) -> dict[str, Any]:
        return {
            "id": org.id,
            "name": org.name,
            "slug": org.slug,
            "status": org.status,
        }

    def _membership_to_dict(self, membership: OrganizationMembership) -> dict[str, Any]:
        return {
            "id": membership.id,
            "user_id": membership.user_id,
            "org_id": membership.org_id,
            "role": membership.role,
            "status": membership.status,
        }


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
