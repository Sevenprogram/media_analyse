from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

from sqlalchemy import select, text

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import config
from database.db_session import close_engines, create_tables, get_async_engine, get_session
from research.schema_migration import TENANT_SCOPED_TABLES, _get_table_columns
from saas.models import AuditLog, Organization, OrganizationMembership, User
from saas.security import hash_password

DEFAULT_EMAIL = "demo@local.test"
DEFAULT_PASSWORD = "demo123456"
DEFAULT_ORG_NAME = "Local Demo Workspace"
DEFAULT_DISPLAY_NAME = "Local Demo User"


def _slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-") or "local-demo-workspace"


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


async def ensure_demo_account(
    *,
    email: str,
    password: str,
    organization_name: str,
    display_name: str,
    adopt_null_data: bool,
    reset_password: bool,
    deactivate_other_memberships: bool,
) -> dict[str, Any]:
    await create_tables(config.SAVE_DATA_OPTION)
    slug = _slugify(organization_name)

    async with get_session() as session:
        user = (
            await session.execute(select(User).where(User.email == email))
        ).scalar_one_or_none()
        user_created = user is None
        password_reset = False
        if user is None:
            user = User(
                email=email,
                password_hash=hash_password(password),
                display_name=display_name,
                status="active",
                email_verified=True,
            )
            session.add(user)
            await session.flush()
        else:
            user.status = "active"
            user.email_verified = True
            if display_name:
                user.display_name = display_name
            if reset_password:
                user.password_hash = hash_password(password)
                password_reset = True
            await session.flush()

        org = (
            await session.execute(select(Organization).where(Organization.slug == slug))
        ).scalar_one_or_none()
        org_created = org is None
        if org is None:
            org = Organization(name=organization_name, slug=slug, status="active")
            session.add(org)
            await session.flush()
        else:
            org.name = organization_name
            org.status = "active"
            await session.flush()

        membership = (
            await session.execute(
                select(OrganizationMembership).where(
                    OrganizationMembership.user_id == user.id,
                    OrganizationMembership.org_id == org.id,
                )
            )
        ).scalar_one_or_none()
        membership_created = membership is None
        if membership is None:
            membership = OrganizationMembership(
                user_id=user.id,
                org_id=org.id,
                role="member",
                status="active",
            )
            session.add(membership)
        else:
            membership.role = "member"
            membership.status = "active"

        deactivated_memberships = 0
        if deactivate_other_memberships:
            result = await session.execute(
                select(OrganizationMembership).where(
                    OrganizationMembership.user_id == user.id,
                    OrganizationMembership.org_id != org.id,
                    OrganizationMembership.status == "active",
                )
            )
            for item in result.scalars().all():
                item.status = "inactive"
                deactivated_memberships += 1

        session.add(
            AuditLog(
                org_id=org.id,
                user_id=user.id,
                action="demo_account.ensure",
                target_type="user",
                target_id=str(user.id),
                before_json={},
                after_json={
                    "email": email,
                    "org_id": org.id,
                    "adopt_null_data": adopt_null_data,
                },
                metadata_json={},
            )
        )
        await session.flush()
        await session.refresh(user)
        await session.refresh(org)
        await session.refresh(membership)

        account = {
            "email": user.email,
            "password": password,
            "user_id": int(user.id),
            "organization_id": int(org.id),
            "organization_name": org.name,
            "organization_slug": org.slug,
            "membership_id": int(membership.id),
            "role": membership.role,
            "user_created": user_created,
            "organization_created": org_created,
            "membership_created": membership_created,
            "password_reset": password_reset,
            "deactivated_memberships": deactivated_memberships,
        }

    adopted_rows = {}
    if adopt_null_data:
        adopted_rows = await adopt_null_tenant_rows(account["organization_id"])

    return {**account, "adopted_rows": adopted_rows}


async def adopt_null_tenant_rows(org_id: int) -> dict[str, int]:
    engine = get_async_engine(config.SAVE_DATA_OPTION)
    if engine is None:
        return {}

    adopted: dict[str, int] = {}
    async with engine.begin() as conn:
        for table_name in sorted(TENANT_SCOPED_TABLES):
            columns = await _get_table_columns(conn, table_name)
            if "org_id" not in columns:
                continue
            result = await conn.execute(
                text(f"UPDATE {table_name} SET org_id = :org_id WHERE org_id IS NULL"),
                {"org_id": org_id},
            )
            rowcount = int(result.rowcount or 0)
            if rowcount:
                adopted[table_name] = rowcount
    return adopted


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a local demo SaaS account and bind legacy org_id=NULL research data to it.",
    )
    parser.add_argument("--email", default=os.getenv("SAAS_DEMO_EMAIL", DEFAULT_EMAIL))
    parser.add_argument(
        "--password",
        default=os.getenv("SAAS_DEMO_PASSWORD", DEFAULT_PASSWORD),
    )
    parser.add_argument(
        "--organization-name",
        default=os.getenv("SAAS_DEMO_ORG_NAME", DEFAULT_ORG_NAME),
    )
    parser.add_argument(
        "--display-name",
        default=os.getenv("SAAS_DEMO_DISPLAY_NAME", DEFAULT_DISPLAY_NAME),
    )
    parser.add_argument(
        "--no-adopt-null-data",
        action="store_true",
        default=not _env_bool("SAAS_DEMO_ADOPT_NULL_DATA", True),
        help="Create the account without assigning org_id=NULL tenant data to the demo workspace.",
    )
    parser.add_argument(
        "--keep-existing-password",
        action="store_true",
        default=not _env_bool("SAAS_DEMO_RESET_PASSWORD", True),
        help="Do not reset the demo account password when the user already exists.",
    )
    parser.add_argument(
        "--keep-other-memberships",
        action="store_true",
        default=not _env_bool("SAAS_DEMO_DEACTIVATE_OTHER_MEMBERSHIPS", True),
        help="Keep other active memberships for this demo user.",
    )
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    result = await ensure_demo_account(
        email=args.email.strip().lower(),
        password=args.password,
        organization_name=args.organization_name.strip(),
        display_name=args.display_name.strip(),
        adopt_null_data=not args.no_adopt_null_data,
        reset_password=not args.keep_existing_password,
        deactivate_other_memberships=not args.keep_other_memberships,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    await close_engines()


if __name__ == "__main__":
    asyncio.run(main())
