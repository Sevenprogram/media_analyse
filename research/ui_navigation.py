from __future__ import annotations

from typing import Any

SIDE_NAV_CONFIG_KEY = "research:ui:side-nav-config"

CONFIGURABLE_SIDE_NAV_TABS: tuple[str, ...] = (
    "today",
    "projects",
    "key_insights",
    "content_production",
    "content_tracking",
    "lead_attribution",
    "competitors",
    "creators",
    "account_analysis",
    "reports_center",
)


def default_side_nav_config() -> dict[str, list[dict[str, object]]]:
    return {
        "items": [
            {"tab": tab, "visible": True, "sort_order": index * 10}
            for index, tab in enumerate(CONFIGURABLE_SIDE_NAV_TABS)
        ]
    }


def normalize_side_nav_config(value: Any) -> dict[str, list[dict[str, object]]]:
    raw_items = value.get("items") if isinstance(value, dict) else None
    if not isinstance(raw_items, list) or not raw_items:
        return default_side_nav_config()

    default_index = {tab: index for index, tab in enumerate(CONFIGURABLE_SIDE_NAV_TABS)}
    configured: dict[str, dict[str, object]] = {}
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        tab = str(item.get("tab") or "").strip()
        if tab not in default_index or tab in configured:
            continue
        try:
            sort_order = int(item.get("sort_order"))
        except (TypeError, ValueError):
            sort_order = default_index[tab] * 10
        configured[tab] = {
            "tab": tab,
            "visible": bool(item.get("visible", True)),
            "sort_order": sort_order,
        }

    next_sort_order = (
        max((int(item["sort_order"]) for item in configured.values()), default=-10) + 10
    )
    for tab in CONFIGURABLE_SIDE_NAV_TABS:
        if tab in configured:
            continue
        configured[tab] = {
            "tab": tab,
            "visible": True,
            "sort_order": next_sort_order,
        }
        next_sort_order += 10

    items = sorted(
        configured.values(),
        key=lambda item: (
            int(item["sort_order"]),
            default_index[str(item["tab"])],
        ),
    )
    normalized_items = [
        {
            "tab": str(item["tab"]),
            "visible": bool(item["visible"]),
            "sort_order": index * 10,
        }
        for index, item in enumerate(items)
    ]
    if normalized_items and not any(bool(item["visible"]) for item in normalized_items):
        normalized_items[0]["visible"] = True
    return {"items": normalized_items}
