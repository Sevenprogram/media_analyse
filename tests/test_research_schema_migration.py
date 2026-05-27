from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research import schema_migration


class _FakeConnection:
    def __init__(self):
        self.statements: list[str] = []

    async def execute(self, statement, params=None):
        self.statements.append(str(statement))
        return None


@pytest.mark.asyncio
async def test_postgres_tenant_unique_constraint_migration_replaces_legacy_definition(monkeypatch):
    legacy_entity_tag_columns = (
        "entity_type",
        "entity_id",
        "platform",
        "vertical_id",
        "tag_id",
        "source",
        "analysis_version",
    )

    async def fake_columns(conn, *, table_name: str, constraint_name: str):
        if constraint_name == "uq_research_entity_tag":
            return legacy_entity_tag_columns
        return schema_migration.POSTGRES_TENANT_UNIQUE_CONSTRAINTS[constraint_name][1]

    monkeypatch.setattr(
        schema_migration,
        "_get_postgres_unique_constraint_columns",
        fake_columns,
    )

    conn = _FakeConnection()
    await schema_migration._ensure_postgres_tenant_unique_constraints(conn)

    assert conn.statements == [
        'ALTER TABLE "research_entity_tags" DROP CONSTRAINT IF EXISTS "uq_research_entity_tag"',
        'ALTER TABLE "research_entity_tags" ADD CONSTRAINT "uq_research_entity_tag" UNIQUE ("org_id", "entity_type", "entity_id", "platform", "vertical_id", "tag_id", "source", "analysis_version")',
    ]


@pytest.mark.asyncio
async def test_postgres_tenant_unique_constraint_migration_skips_current_definitions(monkeypatch):
    async def fake_columns(conn, *, table_name: str, constraint_name: str):
        return schema_migration.POSTGRES_TENANT_UNIQUE_CONSTRAINTS[constraint_name][1]

    monkeypatch.setattr(
        schema_migration,
        "_get_postgres_unique_constraint_columns",
        fake_columns,
    )

    conn = _FakeConnection()
    await schema_migration._ensure_postgres_tenant_unique_constraints(conn)

    assert conn.statements == []
