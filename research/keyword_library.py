from __future__ import annotations

import csv
import io
from typing import Any


KEYWORD_TYPES = {
    "primary",
    "secondary",
    "synonym",
    "negative",
    "platform_adapted",
    "ai_suggested",
}


def normalize_keyword_item(payload: dict[str, Any]) -> dict[str, Any]:
    keyword = str(payload.get("keyword") or "").strip()
    keyword_type = str(payload.get("keyword_type") or "").strip()
    if not keyword:
        raise ValueError("keyword is required")
    if keyword_type not in KEYWORD_TYPES:
        raise ValueError(f"Unsupported keyword_type: {keyword_type}")
    return {
        "scene_pack_id": int(payload["scene_pack_id"]),
        "keyword": keyword,
        "keyword_type": keyword_type,
        "platform": payload.get("platform") or None,
        "weight": float(payload.get("weight") or 1.0),
        "reason": payload.get("reason") or None,
        "usage_flags": payload.get("usage_flags") or [],
        "platform_overrides": payload.get("platform_overrides") or {},
        "enabled": bool(payload.get("enabled", True)),
    }


def export_scene_pack_keywords_csv(items: list[dict[str, Any]]) -> str:
    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=[
            "scene_pack_id",
            "keyword",
            "keyword_type",
            "platform",
            "weight",
            "reason",
            "usage_flags",
            "enabled",
        ],
    )
    writer.writeheader()
    for item in items:
        writer.writerow(
            {
                "scene_pack_id": item["scene_pack_id"],
                "keyword": item["keyword"],
                "keyword_type": item["keyword_type"],
                "platform": item.get("platform") or "",
                "weight": item.get("weight", 1.0),
                "reason": item.get("reason") or "",
                "usage_flags": "|".join(item.get("usage_flags") or []),
                "enabled": "1" if item.get("enabled", True) else "0",
            }
        )
    return output.getvalue()


def parse_scene_pack_keywords_csv(text: str) -> list[dict[str, Any]]:
    reader = csv.DictReader(io.StringIO(text))
    items = []
    for row in reader:
        payload = {
            "scene_pack_id": row.get("scene_pack_id"),
            "keyword": row.get("keyword"),
            "keyword_type": row.get("keyword_type"),
            "platform": row.get("platform") or None,
            "weight": row.get("weight") or 1.0,
            "reason": row.get("reason") or None,
            "usage_flags": [
                item for item in (row.get("usage_flags") or "").split("|") if item
            ],
            "enabled": row.get("enabled", "1") not in {"0", "false", "False"},
        }
        items.append(normalize_keyword_item(payload))
    return items
