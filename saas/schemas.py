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


class PermissionsRead(BaseModel):
    is_platform_admin: bool = False


class AuthResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserRead
    organization: OrganizationRead
    membership: MembershipRead
    permissions: PermissionsRead = Field(default_factory=PermissionsRead)
