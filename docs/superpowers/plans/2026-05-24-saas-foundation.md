# SaaS Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the first SaaS foundation slice: registration, login, refresh/logout, organization membership, current user/current organization context, audit logging, and login protection for `/api/research/*`.

**Architecture:** Keep the current FastAPI modular monolith. Add a focused `saas` package for authentication, organization membership, token handling, and audit records; expose it through `api/routers/auth.py`, `api/routers/orgs.py`, and `api/deps/auth.py`. This plan deliberately stops before tenant-scoping research rows with `org_id`; that belongs to the next implementation plan because it touches most research repositories and migrations.

**Tech Stack:** FastAPI, SQLAlchemy async sessions, Pydantic v2, httpx ASGI tests, stdlib `hashlib`/`hmac`/`secrets` token and password primitives.

---

## File Structure

- Create `saas/__init__.py`: package marker.
- Create `saas/models.py`: ORM models for users, organizations, memberships, refresh tokens, platform admins, and audit logs.
- Create `saas/security.py`: password hashing, password verification, signed access token creation, access token parsing, refresh token generation, and refresh token hashing.
- Create `saas/schemas.py`: request/response DTOs for auth and organization endpoints.
- Create `saas/repository.py`: database access for SaaS auth, organization membership, refresh token rotation, and audit logging.
- Create `saas/service.py`: orchestration for register, login, refresh, logout, current user context, and audit writes.
- Create `api/deps/__init__.py`: dependency package marker.
- Create `api/deps/auth.py`: FastAPI dependencies for `require_current_user`, `get_current_user_context`, and `require_platform_admin`.
- Create `api/routers/auth.py`: `/auth/register`, `/auth/login`, `/auth/refresh`, `/auth/logout`.
- Create `api/routers/orgs.py`: `/me`, `/orgs/current`, `/orgs`.
- Modify `database/models.py`: import `saas.models` so `Base.metadata.create_all()` includes SaaS tables.
- Modify `api/main.py`: register auth and organization routers before protected business routers.
- Modify `api/routers/research.py`: add router-level auth dependency for `/api/research/*`.
- Create `tests/saas_test_utils.py`: reusable helpers for temporary DB auth tests.
- Create `tests/test_saas_security.py`: unit tests for password and access token primitives.
- Create `tests/test_saas_auth_api.py`: API tests for register, login, refresh, logout, `/api/me`, `/api/orgs/current`, and `/api/research/*` protection.
- Modify existing API test fixtures that create research jobs through `/api/research/*` so they authenticate the shared test client first.

## Scope Boundary

This plan implements a login gate and organization context. It does not add `org_id` to existing research tables. After this plan, authenticated users still see the same global research data because the tenant data migration is a separate, larger plan. The next plan must add `org_id` columns and scoped repository methods before external SaaS launch.

### Task 1: Security Primitives

**Files:**
- Create: `tests/test_saas_security.py`
- Create: `saas/__init__.py`
- Create: `saas/security.py`

- [ ] **Step 1: Write failing tests for password hashing and access tokens**

Create `tests/test_saas_security.py`:

```python
from __future__ import annotations

from datetime import timedelta

import pytest

from saas.security import (
    create_access_token,
    hash_password,
    parse_access_token,
    verify_password,
)


def test_password_hash_round_trip() -> None:
    hashed = hash_password("correct horse battery staple")

    assert hashed.startswith("pbkdf2_sha256$")
    assert verify_password("correct horse battery staple", hashed) is True
    assert verify_password("wrong password", hashed) is False


def test_password_hash_uses_unique_salt() -> None:
    first = hash_password("same-password")
    second = hash_password("same-password")

    assert first != second
    assert verify_password("same-password", first) is True
    assert verify_password("same-password", second) is True


def test_access_token_round_trip(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SAAS_AUTH_SECRET", "unit-test-secret")

    token = create_access_token(
        subject="42",
        expires_delta=timedelta(minutes=5),
        extra_claims={"email": "user@example.com"},
    )
    claims = parse_access_token(token)

    assert claims["sub"] == "42"
    assert claims["email"] == "user@example.com"
    assert claims["typ"] == "access"


def test_access_token_rejects_tampering(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SAAS_AUTH_SECRET", "unit-test-secret")

    token = create_access_token(subject="42", expires_delta=timedelta(minutes=5))
    tampered = token[:-2] + "xx"

    with pytest.raises(ValueError, match="Invalid token signature"):
        parse_access_token(tampered)
```

- [ ] **Step 2: Run the security tests and verify they fail**

Run:

```powershell
pytest tests/test_saas_security.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'saas'`.

- [ ] **Step 3: Add the SaaS package marker**

Create `saas/__init__.py`:

```python
"""SaaS authentication, organization, quota, and audit modules."""
```

- [ ] **Step 4: Implement `saas/security.py`**

Create `saas/security.py`:

```python
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

PASSWORD_ALGORITHM = "pbkdf2_sha256"
PASSWORD_ITERATIONS = 210_000
REFRESH_TOKEN_BYTES = 32


def hash_password(password: str) -> str:
    if not password:
        raise ValueError("Password must not be empty")
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PASSWORD_ITERATIONS,
    )
    return "$".join(
        [
            PASSWORD_ALGORITHM,
            str(PASSWORD_ITERATIONS),
            _b64url_encode(salt),
            _b64url_encode(digest),
        ]
    )


def verify_password(password: str, password_hash: str) -> bool:
    try:
        algorithm, iterations_raw, salt_raw, digest_raw = password_hash.split("$", 3)
        if algorithm != PASSWORD_ALGORITHM:
            return False
        iterations = int(iterations_raw)
        salt = _b64url_decode(salt_raw)
        expected = _b64url_decode(digest_raw)
    except (ValueError, TypeError):
        return False
    actual = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        iterations,
    )
    return hmac.compare_digest(actual, expected)


def create_access_token(
    *,
    subject: str,
    expires_delta: timedelta,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": subject,
        "typ": "access",
        "iat": int(now.timestamp()),
        "exp": int((now + expires_delta).timestamp()),
    }
    if extra_claims:
        payload.update(extra_claims)
    header = {"alg": "HS256", "typ": "JWT"}
    signing_input = ".".join(
        [
            _b64url_json(header),
            _b64url_json(payload),
        ]
    )
    signature = _sign(signing_input)
    return f"{signing_input}.{signature}"


def parse_access_token(token: str) -> dict[str, Any]:
    try:
        header_raw, payload_raw, signature = token.split(".", 2)
    except ValueError as exc:
        raise ValueError("Invalid token format") from exc
    signing_input = f"{header_raw}.{payload_raw}"
    expected_signature = _sign(signing_input)
    if not hmac.compare_digest(signature, expected_signature):
        raise ValueError("Invalid token signature")
    header = json.loads(_b64url_decode(header_raw))
    if header.get("alg") != "HS256":
        raise ValueError("Unsupported token algorithm")
    claims = json.loads(_b64url_decode(payload_raw))
    if claims.get("typ") != "access":
        raise ValueError("Invalid token type")
    expires_at = int(claims.get("exp") or 0)
    if expires_at <= int(datetime.now(timezone.utc).timestamp()):
        raise ValueError("Token expired")
    if not claims.get("sub"):
        raise ValueError("Token subject missing")
    return claims


def generate_refresh_token() -> str:
    return secrets.token_urlsafe(REFRESH_TOKEN_BYTES)


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _sign(value: str) -> str:
    return _b64url_encode(
        hmac.new(
            _auth_secret().encode("utf-8"),
            value.encode("utf-8"),
            hashlib.sha256,
        ).digest()
    )


def _auth_secret() -> str:
    return os.getenv("SAAS_AUTH_SECRET", "dev-only-insecure-secret-change-me")


def _b64url_json(value: dict[str, Any]) -> str:
    return _b64url_encode(
        json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")
    )


def _b64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + padding).encode("ascii"))
```

- [ ] **Step 5: Run the security tests and verify they pass**

Run:

```powershell
pytest tests/test_saas_security.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit security primitives**

Run:

```powershell
git add saas/__init__.py saas/security.py tests/test_saas_security.py
git commit -m "feat: add SaaS auth security primitives"
```

### Task 2: SaaS ORM Models

**Files:**
- Create: `saas/models.py`
- Modify: `database/models.py`
- Create: `tests/test_saas_models.py`

- [ ] **Step 1: Write failing table-creation tests**

Create `tests/test_saas_models.py`:

```python
from __future__ import annotations

from pathlib import Path
import sys

import pytest
from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import config
from config.db_config import sqlite_db_config
from database.db_session import close_engines, create_tables, get_session
from saas.models import Organization, OrganizationMembership, User


@pytest.mark.asyncio
async def test_saas_tables_are_created(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "saas-models.db"
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "sqlite", raising=False)
    monkeypatch.setitem(sqlite_db_config, "db_path", str(db_path))

    await close_engines()
    await create_tables("sqlite")

    async with get_session() as session:
        user = User(email="owner@example.com", password_hash="hash", status="active")
        org = Organization(name="Owner Workspace", slug="owner-workspace", status="active")
        session.add_all([user, org])
        await session.flush()
        session.add(
            OrganizationMembership(
                user_id=user.id,
                org_id=org.id,
                role="owner",
                status="active",
            )
        )

    async with get_session() as session:
        result = await session.execute(select(User).where(User.email == "owner@example.com"))
        assert result.scalar_one().email == "owner@example.com"

        membership_result = await session.execute(select(OrganizationMembership))
        assert membership_result.scalar_one().role == "owner"

    await close_engines()
```

- [ ] **Step 2: Run the model test and verify it fails**

Run:

```powershell
pytest tests/test_saas_models.py -q
```

Expected: FAIL because `saas.models` does not exist or SaaS tables are not included in metadata.

- [ ] **Step 3: Implement SaaS ORM models**

Create `saas/models.py`:

```python
from __future__ import annotations

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)

from database.models import Base
from research.models import json_column


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    email = Column(String(255), nullable=False, unique=True, index=True)
    password_hash = Column(Text, nullable=False)
    display_name = Column(String(128), nullable=True)
    status = Column(String(32), nullable=False, default="active", index=True)
    email_verified = Column(Boolean, nullable=False, default=False)
    last_login_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class Organization(Base):
    __tablename__ = "organizations"

    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    slug = Column(String(220), nullable=False, unique=True, index=True)
    status = Column(String(32), nullable=False, default="active", index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class OrganizationMembership(Base):
    __tablename__ = "organization_memberships"
    __table_args__ = (
        UniqueConstraint("user_id", "org_id", name="uq_organization_membership_user_org"),
    )

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    org_id = Column(Integer, ForeignKey("organizations.id"), nullable=False, index=True)
    role = Column(String(32), nullable=False, default="member", index=True)
    status = Column(String(32), nullable=False, default="active", index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    token_hash = Column(String(128), nullable=False, unique=True, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class PlatformAdmin(Base):
    __tablename__ = "platform_admins"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_platform_admin_user"),
    )

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    role = Column(String(32), nullable=False, default="admin", index=True)
    status = Column(String(32), nullable=False, default="active", index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True)
    org_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    action = Column(String(128), nullable=False, index=True)
    target_type = Column(String(64), nullable=True, index=True)
    target_id = Column(String(128), nullable=True, index=True)
    before_json = Column(json_column(), nullable=False, default=dict)
    after_json = Column(json_column(), nullable=False, default=dict)
    metadata_json = Column(json_column(), nullable=False, default=dict)
    ip_address = Column(String(128), nullable=True)
    user_agent = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)
```

- [ ] **Step 4: Import SaaS models into metadata**

Modify the bottom of `database/models.py`:

```python
# Import research and SaaS extension models so Base.metadata includes them during init_db.
import research.models  # noqa: E402,F401
import saas.models  # noqa: E402,F401
```

- [ ] **Step 5: Run the model test and verify it passes**

Run:

```powershell
pytest tests/test_saas_models.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit SaaS models**

Run:

```powershell
git add saas/models.py database/models.py tests/test_saas_models.py
git commit -m "feat: add SaaS account models"
```

### Task 3: Repository And Auth Service

**Files:**
- Create: `saas/schemas.py`
- Create: `saas/repository.py`
- Create: `saas/service.py`
- Create: `tests/test_saas_auth_service.py`

- [ ] **Step 1: Write failing service tests**

Create `tests/test_saas_auth_service.py`:

```python
from __future__ import annotations

from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import config
from config.db_config import sqlite_db_config
from database.db_session import close_engines, create_tables
from saas.service import AuthError, AuthService


@pytest.mark.asyncio
async def test_register_creates_user_org_membership_and_tokens(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SAAS_AUTH_SECRET", "service-test-secret")
    db_path = tmp_path / "saas-service.db"
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "sqlite", raising=False)
    monkeypatch.setitem(sqlite_db_config, "db_path", str(db_path))
    await close_engines()
    await create_tables("sqlite")

    result = await AuthService().register(
        email="Owner@Example.COM ",
        password="secure-password",
        organization_name="Owner Workspace",
    )

    assert result["user"]["email"] == "owner@example.com"
    assert result["organization"]["name"] == "Owner Workspace"
    assert result["membership"]["role"] == "owner"
    assert result["access_token"]
    assert result["refresh_token"]

    await close_engines()


@pytest.mark.asyncio
async def test_register_rejects_duplicate_email(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SAAS_AUTH_SECRET", "service-test-secret")
    db_path = tmp_path / "saas-duplicate.db"
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "sqlite", raising=False)
    monkeypatch.setitem(sqlite_db_config, "db_path", str(db_path))
    await close_engines()
    await create_tables("sqlite")

    service = AuthService()
    await service.register(
        email="owner@example.com",
        password="secure-password",
        organization_name="Owner Workspace",
    )

    with pytest.raises(AuthError) as exc_info:
        await service.register(
            email="OWNER@example.com",
            password="secure-password",
            organization_name="Second Workspace",
        )

    assert exc_info.value.code == "EMAIL_ALREADY_REGISTERED"
    await close_engines()


@pytest.mark.asyncio
async def test_login_and_refresh_token_rotation(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SAAS_AUTH_SECRET", "service-test-secret")
    db_path = tmp_path / "saas-login.db"
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "sqlite", raising=False)
    monkeypatch.setitem(sqlite_db_config, "db_path", str(db_path))
    await close_engines()
    await create_tables("sqlite")

    service = AuthService()
    await service.register(
        email="owner@example.com",
        password="secure-password",
        organization_name="Owner Workspace",
    )

    login = await service.login(email="owner@example.com", password="secure-password")
    refreshed = await service.refresh(login["refresh_token"])

    assert refreshed["access_token"]
    assert refreshed["refresh_token"] != login["refresh_token"]

    with pytest.raises(AuthError) as exc_info:
        await service.refresh(login["refresh_token"])

    assert exc_info.value.code == "INVALID_REFRESH_TOKEN"
    await close_engines()
```

- [ ] **Step 2: Run service tests and verify they fail**

Run:

```powershell
pytest tests/test_saas_auth_service.py -q
```

Expected: FAIL because `saas.service` does not exist.

- [ ] **Step 3: Add request and response schemas**

Create `saas/schemas.py`:

```python
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class RegisterRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=8, max_length=200)
    organization_name: str = Field(min_length=1, max_length=200)
    display_name: str | None = Field(default=None, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("organization_name")
    @classmethod
    def strip_organization_name(cls, value: str) -> str:
        return value.strip()


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=200)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=20)


class LogoutRequest(BaseModel):
    refresh_token: str = Field(min_length=20)


class UserRead(BaseModel):
    id: int
    email: str
    display_name: str | None = None
    status: str
    email_verified: bool
    created_at: datetime | None = None


class OrganizationRead(BaseModel):
    id: int
    name: str
    slug: str
    status: str


class MembershipRead(BaseModel):
    id: int
    user_id: int
    org_id: int
    role: str
    status: str


class AuthResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserRead
    organization: OrganizationRead
    membership: MembershipRead
```

- [ ] **Step 4: Implement repository methods**

Create `saas/repository.py`:

```python
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
                role="owner",
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

    async def get_user_context(self, user_id: int, org_id: int | None = None) -> dict[str, Any] | None:
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

    async def _context_for_user_id(self, session, user_id: int, org_id: int | None = None) -> dict[str, Any] | None:
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
```

- [ ] **Step 5: Implement auth service**

Create `saas/service.py`:

```python
from __future__ import annotations

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
        return self._with_tokens(context, refresh_token=refresh_token)

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
        return self._with_tokens(context, refresh_token=refresh_token)

    async def refresh(self, refresh_token: str) -> dict[str, Any]:
        next_refresh_token = generate_refresh_token()
        context = await self.repository.rotate_refresh_token(
            old_token_hash=hash_refresh_token(refresh_token),
            new_token_hash=hash_refresh_token(next_refresh_token),
            expires_at=_refresh_expires_at(),
        )
        if context is None:
            raise AuthError("INVALID_REFRESH_TOKEN", "Refresh token is invalid or expired")
        return self._with_tokens(context, refresh_token=next_refresh_token)

    async def logout(self, refresh_token: str) -> dict[str, bool]:
        revoked = await self.repository.revoke_refresh_token(hash_refresh_token(refresh_token))
        return {"revoked": revoked}

    async def get_context(self, *, user_id: int, org_id: int | None = None) -> dict[str, Any] | None:
        return await self.repository.get_user_context(user_id, org_id=org_id)

    def _with_tokens(self, context: dict[str, Any], *, refresh_token: str) -> dict[str, Any]:
        public_context = {
            "user": _public_user(context["user"]),
            "organization": context["organization"],
            "membership": context["membership"],
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
```

- [ ] **Step 6: Run service tests and verify they pass**

Run:

```powershell
pytest tests/test_saas_auth_service.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit service layer**

Run:

```powershell
git add saas/schemas.py saas/repository.py saas/service.py tests/test_saas_auth_service.py
git commit -m "feat: add SaaS auth service"
```

### Task 4: Auth API

**Files:**
- Create: `api/routers/auth.py`
- Modify: `api/main.py`
- Create: `tests/test_saas_auth_api.py`

- [ ] **Step 1: Write failing API tests for register, login, refresh, and logout**

Create `tests/test_saas_auth_api.py`:

```python
from __future__ import annotations

from pathlib import Path
import sys

import pytest
from httpx import ASGITransport, AsyncClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import config
from config.db_config import sqlite_db_config
from database.db_session import close_engines, create_tables


@pytest.fixture(autouse=True)
def auth_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SAAS_AUTH_SECRET", "api-test-secret")


@pytest.mark.asyncio
async def test_register_login_refresh_logout(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "saas-auth-api.db"
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "sqlite", raising=False)
    monkeypatch.setitem(sqlite_db_config, "db_path", str(db_path))
    await close_engines()
    await create_tables("sqlite")

    from api.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        register_response = await client.post(
            "/api/auth/register",
            json={
                "email": "owner@example.com",
                "password": "secure-password",
                "organization_name": "Owner Workspace",
            },
        )
        assert register_response.status_code == 200
        registered = register_response.json()
        assert registered["token_type"] == "bearer"
        assert registered["access_token"]
        assert registered["refresh_token"]
        assert registered["user"]["email"] == "owner@example.com"
        assert registered["organization"]["name"] == "Owner Workspace"
        assert registered["membership"]["role"] == "owner"

        duplicate_response = await client.post(
            "/api/auth/register",
            json={
                "email": "owner@example.com",
                "password": "secure-password",
                "organization_name": "Duplicate Workspace",
            },
        )
        assert duplicate_response.status_code == 409
        assert duplicate_response.json()["detail"]["code"] == "EMAIL_ALREADY_REGISTERED"

        login_response = await client.post(
            "/api/auth/login",
            json={"email": "owner@example.com", "password": "secure-password"},
        )
        assert login_response.status_code == 200
        logged_in = login_response.json()
        assert logged_in["refresh_token"] != registered["refresh_token"]

        refresh_response = await client.post(
            "/api/auth/refresh",
            json={"refresh_token": logged_in["refresh_token"]},
        )
        assert refresh_response.status_code == 200
        refreshed = refresh_response.json()
        assert refreshed["refresh_token"] != logged_in["refresh_token"]

        stale_refresh_response = await client.post(
            "/api/auth/refresh",
            json={"refresh_token": logged_in["refresh_token"]},
        )
        assert stale_refresh_response.status_code == 401
        assert stale_refresh_response.json()["detail"]["code"] == "INVALID_REFRESH_TOKEN"

        logout_response = await client.post(
            "/api/auth/logout",
            json={"refresh_token": refreshed["refresh_token"]},
        )
        assert logout_response.status_code == 200
        assert logout_response.json()["revoked"] is True

    await close_engines()
```

- [ ] **Step 2: Run the API test and verify it fails**

Run:

```powershell
pytest tests/test_saas_auth_api.py::test_register_login_refresh_logout -q
```

Expected: FAIL with 404 for `/api/auth/register`.

- [ ] **Step 3: Implement auth router**

Create `api/routers/auth.py`:

```python
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
```

- [ ] **Step 4: Register auth router in app startup**

Modify `api/main.py` imports:

```python
from .routers.auth import router as auth_router
```

Modify router registration before business routers:

```python
app.include_router(auth_router, prefix="/api")
app.include_router(crawler_router, prefix="/api")
```

- [ ] **Step 5: Run auth API test and verify it passes**

Run:

```powershell
pytest tests/test_saas_auth_api.py::test_register_login_refresh_logout -q
```

Expected: PASS.

- [ ] **Step 6: Commit auth API**

Run:

```powershell
git add api/routers/auth.py api/main.py tests/test_saas_auth_api.py
git commit -m "feat: expose SaaS auth endpoints"
```

### Task 5: Current User And Organization Context

**Files:**
- Create: `api/deps/__init__.py`
- Create: `api/deps/auth.py`
- Create: `api/routers/orgs.py`
- Modify: `api/main.py`
- Modify: `tests/test_saas_auth_api.py`

- [ ] **Step 1: Add failing API tests for `/api/me` and `/api/orgs/current`**

Append to `tests/test_saas_auth_api.py`:

```python
@pytest.mark.asyncio
async def test_me_and_current_org_require_bearer_token(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "saas-current-org.db"
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "sqlite", raising=False)
    monkeypatch.setitem(sqlite_db_config, "db_path", str(db_path))
    await close_engines()
    await create_tables("sqlite")

    from api.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        unauthenticated = await client.get("/api/me")
        assert unauthenticated.status_code == 401
        assert unauthenticated.json()["detail"]["code"] == "AUTH_REQUIRED"

        register_response = await client.post(
            "/api/auth/register",
            json={
                "email": "owner@example.com",
                "password": "secure-password",
                "organization_name": "Owner Workspace",
            },
        )
        access_token = register_response.json()["access_token"]

        me_response = await client.get(
            "/api/me",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert me_response.status_code == 200
        assert me_response.json()["user"]["email"] == "owner@example.com"
        assert me_response.json()["organization"]["name"] == "Owner Workspace"
        assert me_response.json()["membership"]["role"] == "owner"

        org_response = await client.get(
            "/api/orgs/current",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert org_response.status_code == 200
        assert org_response.json()["organization"]["slug"] == "owner-workspace"

    await close_engines()
```

- [ ] **Step 2: Run the new test and verify it fails**

Run:

```powershell
pytest tests/test_saas_auth_api.py::test_me_and_current_org_require_bearer_token -q
```

Expected: FAIL with 404 for `/api/me`.

- [ ] **Step 3: Add auth dependency package marker**

Create `api/deps/__init__.py`:

```python
"""FastAPI dependency helpers."""
```

- [ ] **Step 4: Implement auth dependencies**

Create `api/deps/auth.py`:

```python
from __future__ import annotations

from typing import Annotated, Any

from fastapi import Depends, Header, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from saas.repository import SaaSRepository
from saas.security import parse_access_token
from saas.service import AuthService

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user_context(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    x_org_id: Annotated[int | None, Header(alias="X-Org-Id")] = None,
) -> dict[str, Any]:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise_auth_required()
    try:
        claims = parse_access_token(credentials.credentials)
        user_id = int(claims["sub"])
    except (ValueError, TypeError, KeyError) as exc:
        raise_auth_required() from exc
    context = await AuthService().get_context(user_id=user_id, org_id=x_org_id)
    if context is None:
        raise HTTPException(
            status_code=403,
            detail={"code": "ORG_FORBIDDEN", "message": "Organization is not available"},
        )
    return context


async def require_current_user(
    context: Annotated[dict[str, Any], Depends(get_current_user_context)],
) -> dict[str, Any]:
    return context


async def require_platform_admin(
    context: Annotated[dict[str, Any], Depends(get_current_user_context)],
) -> dict[str, Any]:
    user_id = int(context["user"]["id"])
    if not await SaaSRepository().is_platform_admin(user_id):
        raise HTTPException(
            status_code=403,
            detail={"code": "ADMIN_FORBIDDEN", "message": "Platform admin access is required"},
        )
    return context


def raise_auth_required() -> None:
    raise HTTPException(
        status_code=401,
        detail={"code": "AUTH_REQUIRED", "message": "Authentication required"},
        headers={"WWW-Authenticate": "Bearer"},
    )
```

- [ ] **Step 5: Implement organization context router**

Create `api/routers/orgs.py`:

```python
from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends

from api.deps.auth import get_current_user_context

router = APIRouter(tags=["orgs"])


@router.get("/me")
async def get_me(
    context: Annotated[dict[str, Any], Depends(get_current_user_context)],
):
    return context


@router.get("/orgs/current")
async def get_current_org(
    context: Annotated[dict[str, Any], Depends(get_current_user_context)],
):
    return {
        "organization": context["organization"],
        "membership": context["membership"],
    }


@router.get("/orgs")
async def list_current_orgs(
    context: Annotated[dict[str, Any], Depends(get_current_user_context)],
):
    return {
        "organizations": [
            {
                "organization": context["organization"],
                "membership": context["membership"],
            }
        ]
    }
```

- [ ] **Step 6: Register organization router**

Modify `api/main.py` imports:

```python
from .routers.orgs import router as orgs_router
```

Modify router registration:

```python
app.include_router(auth_router, prefix="/api")
app.include_router(orgs_router, prefix="/api")
app.include_router(crawler_router, prefix="/api")
```

- [ ] **Step 7: Run context API test and verify it passes**

Run:

```powershell
pytest tests/test_saas_auth_api.py::test_me_and_current_org_require_bearer_token -q
```

Expected: PASS.

- [ ] **Step 8: Commit current context endpoints**

Run:

```powershell
git add api/deps/__init__.py api/deps/auth.py api/routers/orgs.py api/main.py tests/test_saas_auth_api.py
git commit -m "feat: add current SaaS user context"
```

### Task 6: Protect `/api/research/*`

**Files:**
- Create: `tests/saas_test_utils.py`
- Modify: `api/routers/research.py`
- Modify: `tests/test_saas_auth_api.py`
- Modify: `tests/test_lead_attribution_api.py`

- [ ] **Step 1: Add failing test for research auth requirement**

Append to `tests/test_saas_auth_api.py`:

```python
@pytest.mark.asyncio
async def test_research_endpoints_require_login(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "saas-research-protected.db"
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "sqlite", raising=False)
    monkeypatch.setitem(sqlite_db_config, "db_path", str(db_path))
    await close_engines()
    await create_tables("sqlite")

    from api.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/research/jobs")
        assert response.status_code == 401
        assert response.json()["detail"]["code"] == "AUTH_REQUIRED"

    await close_engines()
```

- [ ] **Step 2: Run the protection test and verify it fails**

Run:

```powershell
pytest tests/test_saas_auth_api.py::test_research_endpoints_require_login -q
```

Expected: FAIL because `/api/research/jobs` currently returns a non-401 response.

- [ ] **Step 3: Create authenticated test helper**

Create `tests/saas_test_utils.py`:

```python
from __future__ import annotations

from httpx import AsyncClient


async def authenticate_test_client(
    client: AsyncClient,
    *,
    email: str = "test-user@example.com",
    organization_name: str = "Test Workspace",
) -> dict:
    response = await client.post(
        "/api/auth/register",
        json={
            "email": email,
            "password": "secure-password",
            "organization_name": organization_name,
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    client.headers.update({"Authorization": f"Bearer {payload['access_token']}"})
    return payload
```

- [ ] **Step 4: Protect the research router**

Modify the imports at the top of `api/routers/research.py`:

```python
from fastapi import APIRouter, Depends, HTTPException, Query
from api.deps.auth import require_current_user
```

Modify the router definition:

```python
router = APIRouter(
    prefix="/research",
    tags=["research"],
    dependencies=[Depends(require_current_user)],
)
```

- [ ] **Step 5: Update existing research API test fixtures to authenticate**

Modify `tests/test_lead_attribution_api.py` imports:

```python
from tests.saas_test_utils import authenticate_test_client
```

In the `lead_attribution_client` fixture, immediately after creating `AsyncClient`, add:

```python
        await authenticate_test_client(
            client,
            email="lead-attribution@example.com",
            organization_name="Lead Attribution Workspace",
        )
```

The fixture block should start like this:

```python
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        await authenticate_test_client(
            client,
            email="lead-attribution@example.com",
            organization_name="Lead Attribution Workspace",
        )
        create_response = await client.post(
            "/api/research/growth-projects",
            json={
                "name": "Pet Food Growth",
                "primary_goal": "keyword_expansion",
                "platforms": ["xhs", "dy"],
                "keywords": ["cat food", "kitten food"],
                "collection_depth": "standard",
                "refresh_cadence": "off",
                "auto_ai_analysis": False,
                "start_immediately": False,
            },
        )
```

- [ ] **Step 6: Run the focused protection and lead attribution tests**

Run:

```powershell
pytest tests/test_saas_auth_api.py::test_research_endpoints_require_login tests/test_lead_attribution_api.py -q
```

Expected: PASS.

- [ ] **Step 7: Confirm there are no other unauthenticated `/api/research/*` test clients**

Run:

```powershell
rg -n "/api/research" tests
```

Expected output only references `tests/test_lead_attribution_api.py`, because this plan already authenticated the `lead_attribution_client` fixture. If the command returns another file, stop and add `authenticate_test_client(...)` to that file's `AsyncClient` fixture before the first `/api/research/*` request, using the exact same pattern from Step 5.

- [ ] **Step 8: Run all Python tests**

Run:

```powershell
pytest tests -q
```

Expected: PASS.

- [ ] **Step 9: Commit research auth protection**

Run:

```powershell
git add api/routers/research.py tests/saas_test_utils.py tests/test_saas_auth_api.py tests/test_lead_attribution_api.py
git add tests
git commit -m "feat: require auth for research API"
```

### Task 7: Final Verification

**Files:**
- Verify only; no new files.

- [ ] **Step 1: Run SaaS-focused tests**

Run:

```powershell
pytest tests/test_saas_security.py tests/test_saas_models.py tests/test_saas_auth_service.py tests/test_saas_auth_api.py -q
```

Expected: PASS.

- [ ] **Step 2: Run the existing API regression tests**

Run:

```powershell
pytest tests -q
```

Expected: PASS.

- [ ] **Step 3: Run backend import smoke test**

Run:

```powershell
python -c "from api.main import app; print(app.title)"
```

Expected output includes:

```text
MediaCrawler WebUI API
```

- [ ] **Step 4: Check git status**

Run:

```powershell
git status --short
```

Expected: only unrelated pre-existing untracked files remain. The SaaS foundation files should be committed.

## Self-Review

Spec coverage for this plan:

- Self-serve registration and login: covered in Tasks 3 and 4.
- Organization-level tenancy foundation: covered in Tasks 2, 3, and 5.
- Refresh/logout sessions: covered in Tasks 3 and 4.
- Current user/current organization context: covered in Task 5.
- Platform admin table foundation: covered in Task 2.
- Audit log table foundation and register/login audit writes: covered in Tasks 2 and 3.
- Login protection for `/api/research/*`: covered in Task 6.

Deferred to later plans:

- Adding `org_id` to research tables.
- Tenant-scoped repository methods.
- Admin dashboard and detailed admin pages.
- Plans, subscriptions, usage events, and quotas.
- Persistent task queue and workers.
- System and tenant-scoped vertical/scene-pack templates.
