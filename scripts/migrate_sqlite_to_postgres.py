import argparse
import asyncio
import json
import os
import sqlite3
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from sqlalchemy import Boolean, Date, DateTime, JSON, insert, text
from sqlalchemy.ext.asyncio import create_async_engine

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from database.db_session import _normalize_postgres_url
from database.models import Base
from config.db_config import postgres_db_config, sqlite_db_config


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Copy local SQLite data into the configured PostgreSQL database."
    )
    parser.add_argument(
        "--sqlite-path",
        default=sqlite_db_config["db_path"],
        help="Source SQLite database path.",
    )
    parser.add_argument(
        "--env-file",
        default=".env",
        help="Optional env file to load before connecting to PostgreSQL.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=500,
        help="Rows inserted per batch.",
    )
    parser.add_argument(
        "--truncate",
        action="store_true",
        help="Delete existing target table data before copying.",
    )
    return parser.parse_args()


def load_env(path: str) -> None:
    env_path = Path(path)
    if env_path.exists():
        load_dotenv(env_path, override=True)


def json_columns(table) -> set[str]:
    return {column.name for column in table.columns if isinstance(column.type, JSON)}


def bool_columns(table) -> set[str]:
    return {column.name for column in table.columns if isinstance(column.type, Boolean)}


def date_columns(table) -> set[str]:
    return {column.name for column in table.columns if isinstance(column.type, Date)}


def datetime_columns(table) -> set[str]:
    return {column.name for column in table.columns if isinstance(column.type, DateTime)}


def convert_json(value: Any) -> Any:
    if value is None or not isinstance(value, str):
        return value
    return json.loads(value)


def convert_bool(value: Any) -> Any:
    if value is None or isinstance(value, bool):
        return value
    return bool(value)


def convert_date(value: Any) -> Any:
    if value is None or isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def convert_datetime(value: Any) -> Any:
    if value is None or isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def convert_row(table, row: sqlite3.Row) -> dict[str, Any]:
    json_names = json_columns(table)
    bool_names = bool_columns(table)
    date_names = date_columns(table) - datetime_columns(table)
    datetime_names = datetime_columns(table)
    converted = dict(row)
    for name in json_names:
        converted[name] = convert_json(converted.get(name))
    for name in bool_names:
        converted[name] = convert_bool(converted.get(name))
    for name in date_names:
        converted[name] = convert_date(converted.get(name))
    for name in datetime_names:
        converted[name] = convert_datetime(converted.get(name))
    return converted


def sqlite_count(conn: sqlite3.Connection, table_name: str) -> int:
    return conn.execute(f'SELECT COUNT(*) FROM "{table_name}"').fetchone()[0]


async def postgres_count(conn, table_name: str) -> int:
    return (
        await conn.execute(text(f'SELECT COUNT(*) FROM "{table_name}"'))
    ).scalar_one()


async def reset_sequence(conn, table_name: str, id_column: str) -> None:
    sequence = (
        await conn.execute(
            text("SELECT pg_get_serial_sequence(:table_name, :id_column)"),
            {"table_name": table_name, "id_column": id_column},
        )
    ).scalar()
    if not sequence:
        return
    await conn.execute(
        text(
            f"""
            SELECT setval(
                :sequence,
                COALESCE((SELECT MAX("{id_column}") FROM "{table_name}"), 1),
                (SELECT COUNT(*) > 0 FROM "{table_name}")
            )
            """
        ),
        {"sequence": sequence},
    )


async def migrate(args: argparse.Namespace) -> None:
    source_path = Path(args.sqlite_path)
    if not source_path.exists():
        raise FileNotFoundError(f"SQLite database not found: {source_path}")

    postgres_url = os.getenv("POSTGRES_DATABASE_URL") or postgres_db_config.get(
        "database_url"
    )
    if not postgres_url:
        raise RuntimeError("POSTGRES_DATABASE_URL is required")

    postgres_url, connect_args = _normalize_postgres_url(postgres_url)
    pg_engine = create_async_engine(postgres_url, connect_args=connect_args)
    sqlite_conn = sqlite3.connect(source_path)
    sqlite_conn.row_factory = sqlite3.Row

    try:
        async with pg_engine.begin() as pg_conn:
            if args.truncate:
                table_names = ", ".join(
                    f'"{table.name}"' for table in reversed(Base.metadata.sorted_tables)
                )
                await pg_conn.execute(text(f"TRUNCATE {table_names} RESTART IDENTITY CASCADE"))
            else:
                non_empty = []
                for table in Base.metadata.sorted_tables:
                    if await postgres_count(pg_conn, table.name):
                        non_empty.append(table.name)
                if non_empty:
                    raise RuntimeError(
                        "Target PostgreSQL tables are not empty. "
                        "Use --truncate to replace them: "
                        + ", ".join(non_empty[:10])
                    )

            for table in Base.metadata.sorted_tables:
                total = sqlite_count(sqlite_conn, table.name)
                if total == 0:
                    print(f"{table.name}: 0")
                    continue

                inserted = 0
                cursor = sqlite_conn.execute(f'SELECT * FROM "{table.name}"')
                while True:
                    rows = cursor.fetchmany(args.batch_size)
                    if not rows:
                        break
                    payload = [convert_row(table, row) for row in rows]
                    await pg_conn.execute(insert(table), payload)
                    inserted += len(payload)
                print(f"{table.name}: {inserted}")

            for table in Base.metadata.sorted_tables:
                id_column = table.primary_key.columns.values()[0].name if table.primary_key.columns else None
                if id_column:
                    await reset_sequence(pg_conn, table.name, id_column)

        async with pg_engine.connect() as pg_conn:
            mismatches = []
            for table in Base.metadata.sorted_tables:
                source_total = sqlite_count(sqlite_conn, table.name)
                target_total = await postgres_count(pg_conn, table.name)
                if source_total != target_total:
                    mismatches.append((table.name, source_total, target_total))
            if mismatches:
                for table_name, source_total, target_total in mismatches:
                    print(
                        f"MISMATCH {table_name}: sqlite={source_total} postgres={target_total}"
                    )
                raise RuntimeError("Migration row-count verification failed")

        print("Migration completed and row counts match.")
    finally:
        sqlite_conn.close()
        await pg_engine.dispose()


def main() -> None:
    args = parse_args()
    load_env(args.env_file)
    asyncio.run(migrate(args))


if __name__ == "__main__":
    main()
