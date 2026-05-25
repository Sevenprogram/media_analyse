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
                role="member",
                status="active",
            )
        )

    async with get_session() as session:
        result = await session.execute(select(User).where(User.email == "owner@example.com"))
        assert result.scalar_one().email == "owner@example.com"

        membership_result = await session.execute(select(OrganizationMembership))
        assert membership_result.scalar_one().role == "member"

    await close_engines()
