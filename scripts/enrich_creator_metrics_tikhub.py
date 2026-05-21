import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config
from research.creator_search import search_creators
from research.repository import ResearchRepository
from research.tikhub_creator_metrics import enrich_creator_metrics_from_tikhub


async def main() -> None:
    parser = argparse.ArgumentParser(description="Enrich current creator search results with TikHub profile metrics.")
    parser.add_argument("--query", default="K12教育 + 单亲妈妈")
    parser.add_argument("--platforms", default="xhs,dy")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--recent-activity-min", type=int, default=1)
    args = parser.parse_args()

    config.SAVE_DATA_OPTION = "sqlite"
    repository = ResearchRepository()
    search = await search_creators(
        repository,
        {
            "raw_query": args.query,
            "platforms": [item.strip() for item in args.platforms.split(",") if item.strip()],
            "recent_activity_min": args.recent_activity_min,
            "limit": args.limit,
        },
    )
    result = await enrich_creator_metrics_from_tikhub(
        repository,
        search.get("results") or [],
    )
    print(json.dumps({"query": args.query, "search_count": len(search.get("results") or []), **result}, ensure_ascii=False, default=str, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
