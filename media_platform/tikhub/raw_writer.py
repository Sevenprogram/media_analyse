import json
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import aiofiles

import config
from store.d1_store import store_raw_record


class TikHubRawWriter:
    def __init__(self, base_dir: Optional[str | Path] = None) -> None:
        configured = config.SAVE_DATA_PATH or "data"
        self.base_dir = Path(base_dir or configured)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    async def write(
        self,
        *,
        platform: str,
        crawler_type: str,
        entity_type: str,
        payload: Any,
        source_keyword: str = "",
        entity_id: str = "",
    ) -> None:
        if config.SAVE_DATA_OPTION == "d1":
            await store_raw_record(
                platform=platform,
                crawler_type=crawler_type,
                entity_type=entity_type,
                payload=payload,
                source_keyword=source_keyword,
                entity_id=entity_id,
            )
            return

        now = datetime.now()
        file_name = f"tikhub_{platform}_{crawler_type}_raw_{now:%Y-%m-%d}.jsonl"
        record = {
            "platform": platform,
            "crawler_type": crawler_type,
            "source_keyword": source_keyword,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "fetched_at": now.isoformat(),
            "raw": payload,
        }
        async with aiofiles.open(self.base_dir / file_name, "a", encoding="utf-8") as f:
            await f.write(json.dumps(record, ensure_ascii=False) + "\n")
