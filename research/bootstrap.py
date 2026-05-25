import argparse
import asyncio

from database.db_session import create_tables


def main() -> None:
    parser = argparse.ArgumentParser(description="Initialize MediaCrawler database tables")
    parser.add_argument("--db-type", default=None)
    args = parser.parse_args()
    asyncio.run(create_tables(args.db_type))
    print("database tables initialized")


if __name__ == "__main__":
    main()
