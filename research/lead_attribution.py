from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any


SUPPORTED_MODELS = {"first_touch", "last_touch", "linear"}
QUALIFIED_LEAD_STATUSES = {"qualified", "contacted", "dealt"}
DEFAULT_ENABLED_DIMENSIONS = ["platform", "keyword", "content", "creator"]


def setting_key_for_project(project_id: int) -> str:
    return f"research:lead-attribution:project:{project_id}:config"


def ensure_utc(value: datetime | str | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def normalize_attribution_config(config: dict[str, Any] | None) -> dict[str, Any]:
    config = dict(config or {})
    enabled_dimensions = [
        dimension
        for dimension in (config.get("enabled_dimensions") or DEFAULT_ENABLED_DIMENSIONS)
        if dimension in {"platform", "keyword", "content", "creator"}
    ]
    if not enabled_dimensions:
        enabled_dimensions = list(DEFAULT_ENABLED_DIMENSIONS)
    model = str(config.get("default_model") or "last_touch")
    if model not in SUPPORTED_MODELS:
        model = "last_touch"
    return {
        "default_model": model,
        "window_days": max(1, int(config.get("window_days") or 7)),
        "enabled_dimensions": enabled_dimensions,
        "dedupe_by": str(config.get("dedupe_by") or "external_lead_id"),
    }


def filter_touchpoints_for_window(
    conversion_event: dict[str, Any],
    touchpoints: list[dict[str, Any]],
    window_days: int,
) -> list[dict[str, Any]]:
    event_time = ensure_utc(conversion_event.get("event_time"))
    if event_time is None:
        return []
    start_time = event_time - timedelta(days=window_days)
    scoped: list[dict[str, Any]] = []
    for item in sorted(touchpoints, key=lambda row: ensure_utc(row.get("touch_time")) or datetime.min.replace(tzinfo=timezone.utc)):
        touch_time = ensure_utc(item.get("touch_time"))
        if touch_time is None:
            continue
        if start_time <= touch_time <= event_time:
            scoped.append(item)
    return scoped


def compute_attribution_rows(
    *,
    model: str,
    conversion_event: dict[str, Any],
    touchpoints: list[dict[str, Any]],
    window_days: int,
    enabled_dimensions: list[str] | None = None,
) -> list[dict[str, Any]]:
    if model not in SUPPORTED_MODELS:
        raise ValueError(f"Unsupported attribution model: {model}")
    enabled = set(enabled_dimensions or DEFAULT_ENABLED_DIMENSIONS)
    scoped = filter_touchpoints_for_window(conversion_event, touchpoints, window_days)
    if not scoped:
        return []
    if model == "first_touch":
        scoped = [scoped[0]]
        credits = [1.0]
    elif model == "last_touch":
        scoped = [scoped[-1]]
        credits = [1.0]
    else:
        credits = [1.0 / len(scoped)] * len(scoped)

    rows: list[dict[str, Any]] = []
    for touchpoint, credit in zip(scoped, credits):
        meta_json = {
            "touchpoint_id": touchpoint.get("id"),
            "touch_type": touchpoint.get("touch_type"),
        }
        if "platform" in enabled and touchpoint.get("platform"):
            rows.append(
                {
                    "dimension": "platform",
                    "dimension_key": str(touchpoint["platform"]),
                    "credit": credit,
                    "meta_json": meta_json,
                }
            )
        if "keyword" in enabled and touchpoint.get("source_keyword"):
            rows.append(
                {
                    "dimension": "keyword",
                    "dimension_key": str(touchpoint["source_keyword"]),
                    "credit": credit,
                    "meta_json": meta_json,
                }
            )
        if "content" in enabled and touchpoint.get("post_id"):
            rows.append(
                {
                    "dimension": "content",
                    "dimension_key": f"post:{touchpoint['post_id']}",
                    "credit": credit,
                    "meta_json": meta_json,
                }
            )
        if "creator" in enabled and touchpoint.get("creator_id"):
            rows.append(
                {
                    "dimension": "creator",
                    "dimension_key": str(touchpoint["creator_id"]),
                    "credit": credit,
                    "meta_json": meta_json,
                }
            )
    return rows


def group_attribution_rows(attribution_rows: list[dict[str, Any]], dimension: str) -> list[dict[str, Any]]:
    return _group_dimension_rows(attribution_rows, [], dimension)


def build_lead_attribution_summary(
    *,
    leads: list[dict[str, Any]],
    conversion_events: list[dict[str, Any]],
    attribution_rows: list[dict[str, Any]],
    spend_rows: list[dict[str, Any]] | None = None,
    model: str,
    date_from: str | None,
    date_to: str | None,
    diagnostics: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    spend_rows = spend_rows or []
    diagnostics = diagnostics or []

    qualified_lead_ids = {
        int(lead["id"])
        for lead in leads
        if lead.get("id") is not None and str(lead.get("lead_status") or "") in QUALIFIED_LEAD_STATUSES
    }
    qualified_lead_ids.update(
        int(event["lead_id"])
        for event in conversion_events
        if event.get("lead_id") is not None and str(event.get("event_type") or "") == "qualified"
    )

    lead_count = len(leads)
    qualified_lead_count = len(qualified_lead_ids)
    wechat_added_count = _count_distinct_event_leads(conversion_events, "wechat_added")
    first_reply_count = _count_distinct_event_leads(conversion_events, "first_reply")
    deal_count = _sum_event_counts(conversion_events, "deal_closed")
    deal_amount = _sum_event_values(conversion_events, "deal_closed")
    total_cost = round(sum(float(item.get("amount") or 0.0) for item in spend_rows), 4)

    summary = {
        "model": model,
        "date_from": date_from,
        "date_to": date_to,
        "lead_count": lead_count,
        "qualified_lead_count": qualified_lead_count,
        "wechat_added_count": wechat_added_count,
        "first_reply_count": first_reply_count,
        "deal_count": deal_count,
        "deal_amount": deal_amount,
        "cost": total_cost,
        "cpl": _safe_ratio(total_cost, lead_count),
        "cost_per_qualified_lead": _safe_ratio(total_cost, qualified_lead_count),
        "roi": _safe_ratio(deal_amount, total_cost),
        "lead_to_wechat_rate": _safe_ratio(wechat_added_count, lead_count),
        "wechat_to_reply_rate": _safe_ratio(first_reply_count, wechat_added_count),
        "reply_to_deal_rate": _safe_ratio(deal_count, first_reply_count),
    }

    funnel = [
        {"stage": "lead", "count": lead_count},
        {"stage": "qualified", "count": qualified_lead_count},
        {"stage": "wechat_added", "count": wechat_added_count},
        {"stage": "first_reply", "count": first_reply_count},
        {"stage": "deal_closed", "count": deal_count, "amount": deal_amount},
    ]

    return {
        "summary": summary,
        "funnel": funnel,
        "top_platforms": _group_dimension_rows(attribution_rows, spend_rows, "platform"),
        "top_keywords": _group_dimension_rows(attribution_rows, spend_rows, "keyword"),
        "top_contents": _group_dimension_rows(attribution_rows, spend_rows, "content"),
        "top_creators": _group_dimension_rows(attribution_rows, spend_rows, "creator"),
        "diagnostics": diagnostics,
    }


def build_daily_snapshot_payload(
    *,
    project_id: int,
    model: str,
    summary_payload: dict[str, Any],
) -> dict[str, Any]:
    return {
        "project_id": project_id,
        "snapshot_date": date.today(),
        "model": model,
        "funnel_json": summary_payload.get("funnel") or [],
        "platform_metrics_json": summary_payload.get("top_platforms") or [],
        "keyword_metrics_json": summary_payload.get("top_keywords") or [],
        "content_metrics_json": summary_payload.get("top_contents") or [],
        "creator_metrics_json": summary_payload.get("top_creators") or [],
        "summary_json": summary_payload.get("summary") or {},
    }


def build_lead_attribution_explanation(
    *,
    lead: dict[str, Any],
    touchpoints: list[dict[str, Any]],
    conversion_events: list[dict[str, Any]],
    attribution_rows: list[dict[str, Any]],
    config: dict[str, Any],
) -> dict[str, Any]:
    return build_lead_attribution_explanation_for_model(
        lead=lead,
        touchpoints=touchpoints,
        conversion_events=conversion_events,
        attribution_rows=attribution_rows,
        config=config,
        model=str(config.get("default_model") or "last_touch"),
    )


def build_lead_attribution_explanation_for_model(
    *,
    lead: dict[str, Any],
    touchpoints: list[dict[str, Any]],
    conversion_events: list[dict[str, Any]],
    attribution_rows: list[dict[str, Any]],
    config: dict[str, Any],
    model: str,
) -> dict[str, Any]:
    top_dimensions: dict[str, dict[str, Any] | None] = {}
    for dimension in DEFAULT_ENABLED_DIMENSIONS:
        rows = [row for row in attribution_rows if row.get("dimension") == dimension]
        if rows:
            top_dimensions[dimension] = max(rows, key=lambda row: float(row.get("credit") or 0.0))
        else:
            top_dimensions[dimension] = None

    event_types = [str(item.get("event_type") or "") for item in conversion_events]
    primary_platform = top_dimensions.get("platform") or {}
    primary_keyword = top_dimensions.get("keyword") or {}
    touch_count = len(touchpoints)
    narrative = (
        f"涓昏褰掑洜缁撹锛氬綋鍓嶇嚎绱㈤噰鐢?{model} 妯″瀷锛岃В鏋?{touch_count} 涓Е鐐广€? "
        f"鏈€楂樿础鐚钩鍙颁负 {primary_platform.get('dimension_key') or 'unknown'}锛?"
        f"鍏抽敭璇嶄负 {primary_keyword.get('dimension_key') or 'unknown'}銆?"
    )
    return {
        "model": model,
        "lead_id": lead.get("id"),
        "touchpoint_summary": {
            "touch_count": touch_count,
            "first_touch_at": ensure_utc(touchpoints[0].get("touch_time")).isoformat() if touchpoints else None,
            "last_touch_at": ensure_utc(touchpoints[-1].get("touch_time")).isoformat() if touchpoints else None,
            "conversion_count": len(conversion_events),
            "event_types": event_types,
        },
        "top_dimensions": top_dimensions,
        "narrative": narrative,
    }


def build_touchpoint_role_map(
    *,
    touchpoints: list[dict[str, Any]],
    conversion_events: list[dict[str, Any]],
    attribution_rows: list[dict[str, Any]],
    window_days: int,
) -> dict[int, dict[str, Any]]:
    role_map: dict[int, dict[str, Any]] = {}
    winning_ids: set[int] = set()
    winning_event_ids_by_touchpoint: dict[int, set[int]] = defaultdict(set)
    for row in attribution_rows:
        meta = row.get("meta_json") or {}
        touchpoint_id = meta.get("touchpoint_id")
        if touchpoint_id is None:
            continue
        touchpoint_id = int(touchpoint_id)
        winning_ids.add(touchpoint_id)
        if row.get("conversion_event_id") is not None:
            winning_event_ids_by_touchpoint[touchpoint_id].add(int(row["conversion_event_id"]))

    in_window_ids: set[int] = set()
    related_event_ids_by_touchpoint: dict[int, set[int]] = defaultdict(set)
    latest_conversion_at = None
    for event in conversion_events:
        event_id = event.get("id")
        event_time = ensure_utc(event.get("event_time"))
        if event_time is not None and (latest_conversion_at is None or event_time > latest_conversion_at):
            latest_conversion_at = event_time
        for touchpoint in filter_touchpoints_for_window(event, touchpoints, window_days):
            if touchpoint.get("id") is None:
                continue
            touchpoint_id = int(touchpoint["id"])
            in_window_ids.add(touchpoint_id)
            if event_id is not None:
                related_event_ids_by_touchpoint[touchpoint_id].add(int(event_id))

    for item in touchpoints:
        touchpoint_id = item.get("id")
        if touchpoint_id is None:
            continue
        touchpoint_id = int(touchpoint_id)
        touch_time = ensure_utc(item.get("touch_time"))
        if touchpoint_id in winning_ids:
            role = "winning"
        elif touchpoint_id in in_window_ids:
            role = "assist"
        elif latest_conversion_at is not None and touch_time is not None and touch_time > latest_conversion_at:
            role = "after_conversion"
        elif conversion_events:
            role = "out_of_window"
        else:
            role = "unattributed"
        role_map[touchpoint_id] = {
            "role": role,
            "related_conversion_event_ids": sorted(related_event_ids_by_touchpoint.get(touchpoint_id) or []),
            "winning_conversion_event_ids": sorted(winning_event_ids_by_touchpoint.get(touchpoint_id) or []),
            "window_days": window_days,
            "conversion_count": len(conversion_events),
        }
    return role_map


def _group_dimension_rows(
    attribution_rows: list[dict[str, Any]],
    spend_rows: list[dict[str, Any]],
    dimension: str,
) -> list[dict[str, Any]]:
    spend_by_key = {
        str(item.get("dimension_key")): round(sum(float(row.get("amount") or 0.0) for row in spend_rows if row.get("dimension") == dimension and str(row.get("dimension_key")) == str(item.get("dimension_key"))), 4)
        for item in spend_rows
        if item.get("dimension") == dimension
    }
    grouped: dict[str, dict[str, Any]] = {}
    for row in attribution_rows:
        if row.get("dimension") != dimension:
            continue
        key = str(row.get("dimension_key") or "")
        bucket = grouped.setdefault(
            key,
            {
                "dimension": dimension,
                "dimension_key": key,
                "credit": 0.0,
                "lead_ids": set(),
                "qualified_lead_ids": set(),
                "wechat_added_event_ids": set(),
                "first_reply_event_ids": set(),
                "deal_event_ids": set(),
                "deal_amount": 0.0,
            },
        )
        bucket["credit"] += float(row.get("credit") or 0.0)
        lead_id = row.get("lead_id")
        if lead_id is not None:
            bucket["lead_ids"].add(int(lead_id))
        if bool(row.get("lead_is_qualified")):
            if lead_id is not None:
                bucket["qualified_lead_ids"].add(int(lead_id))
        event_type = str(row.get("event_type") or "")
        conversion_event_id = row.get("conversion_event_id")
        if event_type == "wechat_added" and conversion_event_id is not None:
            bucket["wechat_added_event_ids"].add(int(conversion_event_id))
        if event_type == "first_reply" and conversion_event_id is not None:
            bucket["first_reply_event_ids"].add(int(conversion_event_id))
        if event_type == "deal_closed" and conversion_event_id is not None:
            bucket["deal_event_ids"].add(int(conversion_event_id))
            bucket["deal_amount"] += float(row.get("event_value") or 0.0) * float(row.get("event_count") or 1)

    result: list[dict[str, Any]] = []
    for key, bucket in grouped.items():
        lead_count = len(bucket["lead_ids"])
        qualified_lead_count = len(bucket["qualified_lead_ids"])
        wechat_added_count = len(bucket["wechat_added_event_ids"])
        first_reply_count = len(bucket["first_reply_event_ids"])
        deal_count = len(bucket["deal_event_ids"])
        cost = round(float(spend_by_key.get(key) or 0.0), 4)
        deal_amount = round(bucket["deal_amount"], 4)
        result.append(
            {
                "dimension": dimension,
                "dimension_key": key,
                "credit": round(bucket["credit"], 4),
                "lead_count": lead_count,
                "qualified_lead_count": qualified_lead_count,
                "wechat_added_count": wechat_added_count,
                "first_reply_count": first_reply_count,
                "deal_count": deal_count,
                "deal_amount": deal_amount,
                "cost": cost,
                "cpl": _safe_ratio(cost, lead_count),
                "cost_per_qualified_lead": _safe_ratio(cost, qualified_lead_count),
                "roi": _safe_ratio(deal_amount, cost),
            }
        )
    result.sort(key=lambda item: (item["deal_amount"], item["credit"]), reverse=True)
    return result


def _count_distinct_event_leads(conversion_events: list[dict[str, Any]], event_type: str) -> int:
    return len(
        {
            int(item["lead_id"])
            for item in conversion_events
            if item.get("lead_id") is not None and str(item.get("event_type") or "") == event_type
        }
    )


def _sum_event_counts(conversion_events: list[dict[str, Any]], event_type: str) -> int:
    total = 0
    for item in conversion_events:
        if str(item.get("event_type") or "") == event_type:
            total += int(item.get("event_count") or 1)
    return total


def _sum_event_values(conversion_events: list[dict[str, Any]], event_type: str) -> float:
    total = 0.0
    for item in conversion_events:
        if str(item.get("event_type") or "") == event_type:
            total += float(item.get("event_value") or 0.0) * float(item.get("event_count") or 1)
    return round(total, 4)


def _safe_ratio(numerator: float | int, denominator: float | int) -> float:
    if not denominator:
        return 0.0
    return round(float(numerator) / float(denominator), 4)
