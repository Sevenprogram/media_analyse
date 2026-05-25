from __future__ import annotations

import argparse
import asyncio
import json
import os
import sqlite3
import sys
from collections.abc import Iterable
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy import Boolean, Date, DateTime, Float, Integer, func, select, text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.types import JSON


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SQLITE_PATH = ROOT / "database" / "sqlite_tables.db"
sys.path.insert(0, str(ROOT))


def read_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def load_local_env() -> dict[str, str]:
    values = {
        **read_env_file(ROOT / ".env.example"),
        **read_env_file(ROOT / ".env"),
    }
    for key, value in values.items():
        os.environ.setdefault(key, value)
    return values


def normalize_postgres_url(db_url: str) -> tuple[str, dict[str, Any]]:
    connect_args: dict[str, Any] = {}
    parsed = urlsplit(db_url)
    scheme = parsed.scheme
    if scheme in {"postgres", "postgresql"}:
        scheme = "postgresql+asyncpg"

    query_items = parse_qsl(parsed.query, keep_blank_values=True)
    filtered_query_items = []
    for key, value in query_items:
        if key.lower() in {"ssl", "sslmode"} and value.lower() in {
            "1",
            "true",
            "require",
        }:
            connect_args["ssl"] = True
            continue
        filtered_query_items.append((key, value))

    if parsed.hostname and parsed.hostname.endswith(".render.com"):
        connect_args.setdefault("ssl", True)

    normalized_url = urlunsplit(
        (
            scheme,
            parsed.netloc,
            parsed.path,
            urlencode(filtered_query_items),
            parsed.fragment,
        )
    )
    return normalized_url, connect_args


def quote_sqlite_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def sqlite_tables(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    return {str(row[0]) for row in rows}


def sqlite_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({quote_sqlite_identifier(table_name)})").fetchall()
    return {str(row[1]) for row in rows}


def parse_datetime(value: Any, timezone_aware: bool) -> Any:
    if value is None or isinstance(value, datetime):
        return value
    if isinstance(value, date):
        parsed = datetime.combine(value, datetime.min.time())
    elif isinstance(value, (int, float)):
        parsed = datetime.fromtimestamp(value, tz=timezone.utc if timezone_aware else None)
    elif isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        parsed = datetime.fromisoformat(stripped.replace("Z", "+00:00"))
    else:
        return value

    if timezone_aware and parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def parse_date(value: Any) -> Any:
    if value is None or isinstance(value, date):
        return value
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        return date.fromisoformat(stripped[:10])
    return value


def parse_json(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, bytes):
        value = value.decode("utf-8")
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            return stripped
    return value


def parse_bool(value: Any) -> Any:
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        stripped = value.strip().lower()
        if not stripped:
            return None
        return stripped in {"1", "true", "yes", "on"}
    return value


def parse_number(value: Any, parser) -> Any:
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    return parser(value)


def convert_value(column, value: Any) -> Any:
    column_type = column.type
    if isinstance(column_type, JSON):
        return parse_json(value)
    if isinstance(column_type, Boolean):
        return parse_bool(value)
    if isinstance(column_type, DateTime):
        return parse_datetime(value, bool(column_type.timezone))
    if isinstance(column_type, Date):
        return parse_date(value)
    if isinstance(column_type, Integer):
        return parse_number(value, int)
    if isinstance(column_type, Float):
        return parse_number(value, float)
    return value


def row_batches(
    conn: sqlite3.Connection,
    table_name: str,
    column_names: list[str],
    batch_size: int,
) -> Iterable[list[sqlite3.Row]]:
    quoted_table = quote_sqlite_identifier(table_name)
    quoted_columns = ", ".join(quote_sqlite_identifier(name) for name in column_names)
    cursor = conn.execute(f"SELECT {quoted_columns} FROM {quoted_table}")
    while True:
        batch = cursor.fetchmany(batch_size)
        if not batch:
            break
        yield batch


async def target_counts(conn, tables) -> dict[str, int]:
    counts: dict[str, int] = {}
    for table in tables:
        result = await conn.execute(select(func.count()).select_from(table))
        counts[table.name] = int(result.scalar_one())
    return counts


async def reset_sequences(conn, tables) -> None:
    for table in tables:
        if "id" not in table.c:
            continue
        await conn.execute(
            text(
                f"""
                SELECT setval(
                    pg_get_serial_sequence('{table.name}', 'id'),
                    COALESCE((SELECT MAX(id) FROM {table.name}), 1),
                    EXISTS(SELECT 1 FROM {table.name})
                )
                """
            )
        )


def is_deadlock_error(exc: BaseException) -> bool:
    message = str(exc).lower()
    return "deadlock detected" in message or "deadlockdetectederror" in message


async def ensure_schema_with_retries(normalized_url: str, connect_args: dict[str, Any]) -> None:
    from research.schema_migration import ensure_research_schema

    for attempt in range(1, 6):
        schema_engine = create_async_engine(
            normalized_url,
            echo=False,
            connect_args=connect_args,
            isolation_level="AUTOCOMMIT",
        )
        try:
            async with schema_engine.connect() as conn:
                await ensure_research_schema(conn)
            return
        except Exception as exc:
            if not is_deadlock_error(exc) or attempt == 5:
                raise
            delay = attempt * 5
            print(f"Schema lock conflict, retrying in {delay}s (attempt {attempt}/5).")
            await asyncio.sleep(delay)
        finally:
            await schema_engine.dispose()


async def migrate(args: argparse.Namespace) -> None:
    env_values = load_local_env()
    postgres_url = args.postgres_url or env_values.get("POSTGRES_DATABASE_URL") or ""
    if not postgres_url:
        raise SystemExit("POSTGRES_DATABASE_URL is not set in .env.example, .env, or CLI args.")

    sqlite_path = Path(args.sqlite_path)
    if not sqlite_path.exists():
        raise SystemExit(f"SQLite database does not exist: {sqlite_path}")

    # Import after loading env so project modules that read os.environ see local values.
    from database.models import Base
    normalized_url, connect_args = normalize_postgres_url(postgres_url)
    engine = create_async_engine(normalized_url, echo=False, connect_args=connect_args)

    sqlite_conn = sqlite3.connect(f"file:{sqlite_path}?mode=ro", uri=True)
    sqlite_conn.row_factory = sqlite3.Row
    source_tables = sqlite_tables(sqlite_conn)
    metadata_tables = [
        table for table in Base.metadata.sorted_tables if table.name in source_tables
    ]

    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await ensure_schema_with_retries(normalized_url, connect_args)

        async with engine.begin() as conn:
            counts_before = await target_counts(conn, metadata_tables)
            non_empty = {name: count for name, count in counts_before.items() if count}
            if non_empty and not args.replace:
                details = ", ".join(
                    f"{name}={count}" for name, count in sorted(non_empty.items())[:20]
                )
                raise SystemExit(
                    "Target Postgres already has data. "
                    f"Refusing to merge automatically: {details}. "
                    "Rerun with --replace only if you intend to wipe target tables first."
                )

            if non_empty and args.replace:
                table_names = ", ".join(table.name for table in reversed(metadata_tables))
                await conn.execute(text(f"TRUNCATE {table_names} RESTART IDENTITY CASCADE"))

            copied: dict[str, int] = {}
            for table in metadata_tables:
                available_columns = sqlite_columns(sqlite_conn, table.name)
                columns = [column for column in table.columns if column.name in available_columns]
                if not columns:
                    copied[table.name] = 0
                    continue

                column_names = [column.name for column in columns]
                copied_count = 0
                for batch in row_batches(sqlite_conn, table.name, column_names, args.batch_size):
                    rows = [
                        {
                            column.name: convert_value(column, row[column.name])
                            for column in columns
                        }
                        for row in batch
                    ]
                    await conn.execute(table.insert(), rows)
                    copied_count += len(rows)
                copied[table.name] = copied_count
                print(f"{table.name}: {copied_count}")

            await reset_sequences(conn, metadata_tables)

        async with engine.connect() as conn:
            counts_after = await target_counts(conn, metadata_tables)

        mismatches = [
            (name, copied[name], counts_after[name])
            for name in copied
            if copied[name] != counts_after[name]
        ]
        if mismatches:
            for name, copied_count, target_count in mismatches:
                print(f"MISMATCH {name}: copied={copied_count}, target={target_count}")
            raise SystemExit("Migration finished with row-count mismatches.")

        total_rows = sum(copied.values())
        print(f"Migration complete: {len(copied)} tables, {total_rows} rows copied.")
    finally:
        sqlite_conn.close()
        await engine.dispose()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Copy the local SQLite database into a Render/Postgres database."
    )
    parser.add_argument(
        "--sqlite-path",
        default=str(DEFAULT_SQLITE_PATH),
        help="Path to the source SQLite database.",
    )
    parser.add_argument(
        "--postgres-url",
        default="",
        help="Target Postgres URL. Defaults to POSTGRES_DATABASE_URL from .env.example/.env.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=500,
        help="Rows to insert per batch.",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Truncate existing target rows before importing.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    asyncio.run(migrate(parse_args()))
