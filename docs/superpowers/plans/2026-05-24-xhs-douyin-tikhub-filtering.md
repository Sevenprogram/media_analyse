# XHS + Douyin TikHub Filtering Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add TikHub-backed search controls for Xiaohongshu and Douyin: time ordering, preset and exact time ranges, per-keyword-per-platform caps, and prefer-fill behavior.

**Architecture:** Add one pure search-control module for platform mappings and time classification, then thread the normalized controls through API schemas, CLI args, research execution, and TikHub crawling. Keep fallback metadata in research `engagement_json` by annotating backfill inputs before normalization, avoiding platform table schema changes.

**Tech Stack:** Python 3.13, FastAPI, Pydantic, Typer, pytest, React 19, TypeScript, Vite.

---

## File Structure

- Create `media_platform/tikhub/search_controls.py`
  - Owns normalized search controls, XHS/Douyin native parameter mapping, timestamp parsing, exact-range classification, and fallback metadata.
- Create `tests/test_tikhub_search_controls.py`
  - Unit-tests platform mapping and exact-range classification without network calls.
- Create `tests/test_crawler_search_control_plumbing.py`
  - Unit-tests request validation, command-line argument generation, and Typer config assignment.
- Create `tests/test_tikhub_crawler_prefer_fill.py`
  - Unit-tests TikHub crawler pagination, per-keyword caps, and fallback fill with a fake TikHub client.
- Create `tests/test_research_execution_search_controls.py`
  - Unit-tests research job to `CrawlerStartRequest` propagation.
- Modify `config/base_config.py`
  - Adds default crawler search-control config fields.
- Modify `api/schemas/crawler.py`
  - Adds public API fields and validation for direct crawler runs.
- Modify `api/services/crawler_manager.py`
  - Passes the new fields to `main.py` as CLI args.
- Modify `cmd_arg/arg.py`
  - Parses new CLI args and assigns `config` values.
- Modify `research/schemas.py`
  - Adds growth-project run-now fields.
- Modify `api/routers/research.py`
  - Stores search controls in `comment_policy` when creating collection jobs.
- Modify `research/execution.py`
  - Converts `comment_policy` controls into `CrawlerStartRequest` fields.
- Modify `media_platform/tikhub/core.py`
  - Uses `search_controls.py` and changes search-mode collection to per keyword per platform.
- Modify `research/backfill.py`
  - Allows prefer-fill backfill selection and annotates records with crawl metadata.
- Modify `research/normalizer.py`
  - Copies crawl metadata into `engagement_json`.
- Modify `api/webui/src/types.ts`
  - Adds TypeScript types for search controls.
- Modify `api/webui/src/main.tsx`
  - Sends the new search-control payload when starting collection.
- Modify `api/webui/src/pages/GrowthProjectWorkbenchPage.tsx`
  - Adds a compact collection-control form for count, sort, preset range, and exact range.

---

### Task 1: Add Pure TikHub Search Control Mapping

**Files:**
- Create: `media_platform/tikhub/search_controls.py`
- Create: `tests/test_tikhub_search_controls.py`

- [ ] **Step 1: Write the failing search-control tests**

Create `tests/test_tikhub_search_controls.py`:

```python
from __future__ import annotations

from datetime import datetime, timezone

from media_platform.tikhub.search_controls import (
    SearchControls,
    apply_native_search_params,
    classify_time_range,
    effective_search_controls,
    search_controls_from_raw,
)


def test_xhs_latest_seven_day_mapping() -> None:
    controls = SearchControls(sort_mode="latest", time_preset="7d")
    effective = effective_search_controls("xhs", controls)
    params = apply_native_search_params("xhs", {"keyword": "cat food"}, effective)

    assert effective.effective_sort_mode == "latest"
    assert params["sort_type"] == "time_descending"
    assert params["filter_note_time"] == "\u4e00\u5468\u5185"


def test_douyin_latest_seven_day_mapping() -> None:
    controls = SearchControls(sort_mode="latest", time_preset="7d")
    effective = effective_search_controls("dy", controls)
    params = apply_native_search_params("dy", {"keyword": "cat food"}, effective)

    assert effective.effective_sort_mode == "latest"
    assert params["sort_type"] == "2"
    assert params["publish_time"] == "7"


def test_douyin_unsupported_sort_downgrades_to_relevance() -> None:
    controls = SearchControls(sort_mode="most_collected", time_preset="all")
    effective = effective_search_controls("dy", controls)
    params = apply_native_search_params("dy", {"keyword": "cat food"}, effective)

    assert effective.requested_sort_mode == "most_collected"
    assert effective.effective_sort_mode == "relevance"
    assert params["sort_type"] == "0"


def test_exact_range_classification_marks_inside_and_outside() -> None:
    controls = search_controls_from_raw(
        sort_mode="latest",
        time_preset="all",
        time_start="2026-05-01T00:00:00+00:00",
        time_end="2026-05-07T23:59:59+00:00",
    )

    inside = classify_time_range(1_778_112_000, controls)
    outside = classify_time_range(1_779_000_000, controls)

    assert inside.within_requested_time_range is True
    assert inside.outside_requested_time_range is False
    assert inside.fill_reason == "exact_match"
    assert outside.within_requested_time_range is False
    assert outside.outside_requested_time_range is True
    assert outside.fill_reason == "fill_to_target"


def test_missing_exact_range_time_is_available_for_fill() -> None:
    controls = SearchControls(
        sort_mode="latest",
        time_preset="all",
        time_start=datetime(2026, 5, 1, tzinfo=timezone.utc),
        time_end=datetime(2026, 5, 7, 23, 59, 59, tzinfo=timezone.utc),
    )

    result = classify_time_range(None, controls)

    assert result.within_requested_time_range is False
    assert result.outside_requested_time_range is True
    assert result.fill_reason == "fill_to_target"
```

- [ ] **Step 2: Run the tests and verify they fail**

Run: `uv run python -m pytest tests/test_tikhub_search_controls.py -q`

Expected: FAIL because `media_platform.tikhub.search_controls` does not exist.

- [ ] **Step 3: Implement the pure search-control module**

Create `media_platform/tikhub/search_controls.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from media_platform.recent_search import unix_seconds

SORT_RELEVANCE = "relevance"
SORT_LATEST = "latest"
SORT_MOST_LIKED = "most_liked"
SORT_MOST_COMMENTED = "most_commented"
SORT_MOST_COLLECTED = "most_collected"

TIME_ALL = "all"
TIME_1D = "1d"
TIME_7D = "7d"
TIME_30D = "30d"
TIME_180D = "180d"

FILL_PREFER_FILL = "prefer_fill"

VALID_SORT_MODES = {
    SORT_RELEVANCE,
    SORT_LATEST,
    SORT_MOST_LIKED,
    SORT_MOST_COMMENTED,
    SORT_MOST_COLLECTED,
}
VALID_TIME_PRESETS = {TIME_ALL, TIME_1D, TIME_7D, TIME_30D, TIME_180D}

XHS_SORT_PARAMS = {
    SORT_RELEVANCE: "general",
    SORT_LATEST: "time_descending",
    SORT_MOST_LIKED: "popularity_descending",
    SORT_MOST_COMMENTED: "comment_descending",
    SORT_MOST_COLLECTED: "collect_descending",
}
XHS_TIME_PARAMS = {
    TIME_ALL: "\u4e0d\u9650",
    TIME_1D: "\u4e00\u5929\u5185",
    TIME_7D: "\u4e00\u5468\u5185",
    TIME_180D: "\u534a\u5e74\u5185",
}

DOUYIN_SORT_PARAMS = {
    SORT_RELEVANCE: "0",
    SORT_MOST_LIKED: "1",
    SORT_LATEST: "2",
}
DOUYIN_TIME_PARAMS = {
    TIME_ALL: "0",
    TIME_1D: "1",
    TIME_7D: "7",
    TIME_180D: "180",
}


@dataclass(frozen=True)
class SearchControls:
    sort_mode: str = SORT_RELEVANCE
    time_preset: str = TIME_ALL
    time_start: datetime | None = None
    time_end: datetime | None = None
    fill_strategy: str = FILL_PREFER_FILL
    max_extra_pages: int = 5

    @property
    def has_exact_range(self) -> bool:
        return self.time_start is not None and self.time_end is not None


@dataclass(frozen=True)
class EffectiveSearchControls:
    platform: str
    requested_sort_mode: str
    effective_sort_mode: str
    time_preset: str
    time_start: datetime | None
    time_end: datetime | None
    fill_strategy: str
    max_extra_pages: int
    downgraded: bool = False

    @property
    def has_exact_range(self) -> bool:
        return self.time_start is not None and self.time_end is not None


@dataclass(frozen=True)
class TimeRangeClassification:
    within_requested_time_range: bool
    outside_requested_time_range: bool
    fill_reason: str


def search_controls_from_raw(
    *,
    sort_mode: str = SORT_RELEVANCE,
    time_preset: str = TIME_ALL,
    time_start: str | datetime | None = None,
    time_end: str | datetime | None = None,
    fill_strategy: str = FILL_PREFER_FILL,
    max_extra_pages: int = 5,
) -> SearchControls:
    normalized_sort = sort_mode if sort_mode in VALID_SORT_MODES else SORT_RELEVANCE
    normalized_preset = time_preset if time_preset in VALID_TIME_PRESETS else TIME_ALL
    start = _parse_datetime(time_start)
    end = _parse_datetime(time_end)
    if (start is None) != (end is None):
        raise ValueError("time_start and time_end must be provided together")
    if start is not None and end is not None and start > end:
        raise ValueError("time_start must be before or equal to time_end")
    return SearchControls(
        sort_mode=normalized_sort,
        time_preset=normalized_preset,
        time_start=start,
        time_end=end,
        fill_strategy=fill_strategy or FILL_PREFER_FILL,
        max_extra_pages=max(1, int(max_extra_pages or 1)),
    )


def effective_search_controls(platform: str, controls: SearchControls) -> EffectiveSearchControls:
    requested_sort = controls.sort_mode
    if platform == "xhs":
        effective_sort = SORT_LATEST if controls.has_exact_range else requested_sort
    elif platform == "dy":
        if controls.has_exact_range:
            effective_sort = SORT_LATEST
        elif requested_sort in DOUYIN_SORT_PARAMS:
            effective_sort = requested_sort
        else:
            effective_sort = SORT_RELEVANCE
    else:
        effective_sort = requested_sort
    return EffectiveSearchControls(
        platform=platform,
        requested_sort_mode=requested_sort,
        effective_sort_mode=effective_sort,
        time_preset=controls.time_preset,
        time_start=controls.time_start,
        time_end=controls.time_end,
        fill_strategy=controls.fill_strategy,
        max_extra_pages=controls.max_extra_pages,
        downgraded=effective_sort != requested_sort,
    )


def apply_native_search_params(
    platform: str,
    params: dict[str, Any],
    controls: EffectiveSearchControls,
) -> dict[str, Any]:
    next_params = dict(params)
    if platform == "xhs":
        next_params["sort_type"] = XHS_SORT_PARAMS.get(controls.effective_sort_mode, "general")
        xhs_time = XHS_TIME_PARAMS.get(controls.time_preset)
        if controls.time_preset == TIME_30D:
            xhs_time = XHS_TIME_PARAMS[TIME_ALL]
        if xhs_time:
            next_params["filter_note_time"] = xhs_time
    elif platform == "dy":
        next_params["sort_type"] = DOUYIN_SORT_PARAMS.get(controls.effective_sort_mode, "0")
        next_params["publish_time"] = DOUYIN_TIME_PARAMS.get(controls.time_preset, "0")
    return next_params


def classify_time_range(timestamp_value: Any, controls: SearchControls | EffectiveSearchControls) -> TimeRangeClassification:
    if not controls.has_exact_range:
        return TimeRangeClassification(True, False, "exact_match")
    timestamp = unix_seconds(timestamp_value)
    if timestamp is None:
        return TimeRangeClassification(False, True, "fill_to_target")
    published = datetime.fromtimestamp(timestamp, tz=timezone.utc)
    within = controls.time_start <= published <= controls.time_end  # type: ignore[operator]
    return TimeRangeClassification(within, not within, "exact_match" if within else "fill_to_target")


def metadata_for_item(controls: EffectiveSearchControls, classification: TimeRangeClassification) -> dict[str, Any]:
    return {
        "requested_sort_mode": controls.requested_sort_mode,
        "effective_sort_mode": controls.effective_sort_mode,
        "requested_time_preset": controls.time_preset,
        "requested_time_start": controls.time_start.isoformat() if controls.time_start else None,
        "requested_time_end": controls.time_end.isoformat() if controls.time_end else None,
        "within_requested_time_range": classification.within_requested_time_range,
        "outside_requested_time_range": classification.outside_requested_time_range,
        "fill_reason": classification.fill_reason,
    }


def _parse_datetime(value: str | datetime | None) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
```

- [ ] **Step 4: Run the search-control tests**

Run: `uv run python -m pytest tests/test_tikhub_search_controls.py -q`

Expected: PASS.

- [ ] **Step 5: Commit Task 1**

```bash
git add media_platform/tikhub/search_controls.py tests/test_tikhub_search_controls.py
git commit -m "feat: add TikHub search control mapping"
```

---

### Task 2: Thread Search Controls Through API, Config, and CLI

**Files:**
- Modify: `config/base_config.py`
- Modify: `api/schemas/crawler.py`
- Modify: `api/services/crawler_manager.py`
- Modify: `cmd_arg/arg.py`
- Create: `tests/test_crawler_search_control_plumbing.py`

- [ ] **Step 1: Write plumbing tests**

Create `tests/test_crawler_search_control_plumbing.py`:

```python
from __future__ import annotations

from datetime import datetime, timezone

import pytest

import config
from api.schemas import CrawlerStartRequest
from api.services.crawler_manager import CrawlerManager
from cmd_arg.arg import parse_cmd


def test_crawler_start_request_validates_exact_range_pair() -> None:
    with pytest.raises(ValueError):
        CrawlerStartRequest(
            platform="xhs",
            time_start=datetime(2026, 5, 1, tzinfo=timezone.utc),
        )


def test_crawler_manager_passes_search_control_cli_args() -> None:
    request = CrawlerStartRequest(
        platform="dy",
        keywords="cat food",
        max_results_per_keyword_per_platform=200,
        sort_mode="latest",
        time_preset="7d",
        time_start=datetime(2026, 5, 1, tzinfo=timezone.utc),
        time_end=datetime(2026, 5, 7, 23, 59, 59, tzinfo=timezone.utc),
        max_extra_pages=8,
    )

    cmd = CrawlerManager()._build_command(request)

    assert "--max_results_per_keyword_per_platform" in cmd
    assert "200" in cmd
    assert cmd[cmd.index("--sort_mode") + 1] == "latest"
    assert cmd[cmd.index("--time_preset") + 1] == "7d"
    assert cmd[cmd.index("--max_extra_pages") + 1] == "8"
    assert cmd[cmd.index("--time_start") + 1].startswith("2026-05-01T00:00:00")
    assert cmd[cmd.index("--time_end") + 1].startswith("2026-05-07T23:59:59")


@pytest.mark.asyncio
async def test_parse_cmd_assigns_search_controls(monkeypatch) -> None:
    await parse_cmd(
        [
            "--platform",
            "dy",
            "--keywords",
            "cat food",
            "--sort_mode",
            "latest",
            "--time_preset",
            "7d",
            "--time_start",
            "2026-05-01T00:00:00+00:00",
            "--time_end",
            "2026-05-07T23:59:59+00:00",
            "--max_results_per_keyword_per_platform",
            "200",
            "--max_extra_pages",
            "8",
        ]
    )

    assert config.CRAWLER_SEARCH_SORT_MODE == "latest"
    assert config.CRAWLER_SEARCH_TIME_PRESET == "7d"
    assert config.CRAWLER_SEARCH_TIME_START == "2026-05-01T00:00:00+00:00"
    assert config.CRAWLER_SEARCH_TIME_END == "2026-05-07T23:59:59+00:00"
    assert config.CRAWLER_MAX_RESULTS_PER_KEYWORD_PER_PLATFORM == 200
    assert config.CRAWLER_MAX_EXTRA_PAGES == 8
```

- [ ] **Step 2: Run the plumbing tests and verify they fail**

Run: `uv run python -m pytest tests/test_crawler_search_control_plumbing.py -q`

Expected: FAIL because the new fields and CLI options do not exist.

- [ ] **Step 3: Add default config fields**

In `config/base_config.py`, add these fields below `CRAWLER_COLLECTION_WINDOW_DAYS`:

```python
CRAWLER_SEARCH_SORT_MODE = "relevance"
CRAWLER_SEARCH_TIME_PRESET = "all"
CRAWLER_SEARCH_TIME_START = ""
CRAWLER_SEARCH_TIME_END = ""
CRAWLER_MAX_RESULTS_PER_KEYWORD_PER_PLATFORM = None
CRAWLER_FILL_STRATEGY = "prefer_fill"
CRAWLER_MAX_EXTRA_PAGES = 5
```

- [ ] **Step 4: Extend `CrawlerStartRequest`**

In `api/schemas/crawler.py`, import `datetime`, `Field`, `field_validator`, and `model_validator`, then add fields to `CrawlerStartRequest`:

```python
    sort_mode: Literal["relevance", "latest", "most_liked", "most_commented", "most_collected"] = "relevance"
    time_preset: Literal["all", "1d", "7d", "30d", "180d"] = "all"
    time_start: datetime | None = None
    time_end: datetime | None = None
    max_results_per_keyword_per_platform: int | None = Field(default=None, ge=1, le=5000)
    fill_strategy: Literal["prefer_fill"] = "prefer_fill"
    max_extra_pages: int = Field(default=5, ge=1, le=50)

    @model_validator(mode="after")
    def validate_time_range(self):
        if (self.time_start is None) != (self.time_end is None):
            raise ValueError("time_start and time_end must be provided together")
        if self.time_start is not None and self.time_end is not None and self.time_start > self.time_end:
            raise ValueError("time_start must be before or equal to time_end")
        return self
```

- [ ] **Step 5: Pass new fields in `CrawlerManager._build_command`**

In `api/services/crawler_manager.py`, add the following after existing latest-post arguments:

```python
        if config.sort_mode != "relevance":
            cmd.extend(["--sort_mode", config.sort_mode])
        if config.time_preset != "all":
            cmd.extend(["--time_preset", config.time_preset])
        if config.time_start is not None:
            cmd.extend(["--time_start", config.time_start.isoformat()])
        if config.time_end is not None:
            cmd.extend(["--time_end", config.time_end.isoformat()])
        if config.max_results_per_keyword_per_platform:
            cmd.extend([
                "--max_results_per_keyword_per_platform",
                str(config.max_results_per_keyword_per_platform),
            ])
        if config.fill_strategy:
            cmd.extend(["--fill_strategy", config.fill_strategy])
        if config.max_extra_pages:
            cmd.extend(["--max_extra_pages", str(config.max_extra_pages)])
```

- [ ] **Step 6: Add Typer CLI options and config assignment**

In `cmd_arg/arg.py`, add callback parameters after `collection_window_days`:

```python
        sort_mode: Annotated[
            str,
            typer.Option("--sort_mode", help="Normalized search sort mode", rich_help_panel="Basic Configuration"),
        ] = getattr(config, "CRAWLER_SEARCH_SORT_MODE", "relevance"),
        time_preset: Annotated[
            str,
            typer.Option("--time_preset", help="Normalized search time preset", rich_help_panel="Basic Configuration"),
        ] = getattr(config, "CRAWLER_SEARCH_TIME_PRESET", "all"),
        time_start: Annotated[
            str,
            typer.Option("--time_start", help="Exact search range start as ISO datetime", rich_help_panel="Basic Configuration"),
        ] = getattr(config, "CRAWLER_SEARCH_TIME_START", ""),
        time_end: Annotated[
            str,
            typer.Option("--time_end", help="Exact search range end as ISO datetime", rich_help_panel="Basic Configuration"),
        ] = getattr(config, "CRAWLER_SEARCH_TIME_END", ""),
        max_results_per_keyword_per_platform: Annotated[
            Optional[int],
            typer.Option("--max_results_per_keyword_per_platform", help="Per keyword and platform result cap", rich_help_panel="Basic Configuration"),
        ] = getattr(config, "CRAWLER_MAX_RESULTS_PER_KEYWORD_PER_PLATFORM", None),
        fill_strategy: Annotated[
            str,
            typer.Option("--fill_strategy", help="Search fill strategy", rich_help_panel="Basic Configuration"),
        ] = getattr(config, "CRAWLER_FILL_STRATEGY", "prefer_fill"),
        max_extra_pages: Annotated[
            int,
            typer.Option("--max_extra_pages", help="Maximum extra pages used to fill exact-range searches", rich_help_panel="Basic Configuration"),
        ] = getattr(config, "CRAWLER_MAX_EXTRA_PAGES", 5),
```

Assign these values in the config override section:

```python
        config.CRAWLER_SEARCH_SORT_MODE = sort_mode
        config.CRAWLER_SEARCH_TIME_PRESET = time_preset
        config.CRAWLER_SEARCH_TIME_START = time_start
        config.CRAWLER_SEARCH_TIME_END = time_end
        config.CRAWLER_MAX_RESULTS_PER_KEYWORD_PER_PLATFORM = max_results_per_keyword_per_platform
        config.CRAWLER_FILL_STRATEGY = fill_strategy
        config.CRAWLER_MAX_EXTRA_PAGES = max_extra_pages
```

- [ ] **Step 7: Run plumbing tests**

Run: `uv run python -m pytest tests/test_crawler_search_control_plumbing.py -q`

Expected: PASS.

- [ ] **Step 8: Commit Task 2**

```bash
git add config/base_config.py api/schemas/crawler.py api/services/crawler_manager.py cmd_arg/arg.py tests/test_crawler_search_control_plumbing.py
git commit -m "feat: pass crawler search controls through API and CLI"
```

---

### Task 3: Propagate Search Controls Through Research Jobs

**Files:**
- Modify: `research/schemas.py`
- Modify: `api/routers/research.py`
- Modify: `research/execution.py`
- Create: `tests/test_research_execution_search_controls.py`

- [ ] **Step 1: Write research propagation tests**

Create `tests/test_research_execution_search_controls.py`:

```python
from __future__ import annotations

from datetime import date

from research.execution import build_crawler_start_requests, execution_plan_to_dict


def test_research_job_builds_xhs_and_douyin_search_controls() -> None:
    job = {
        "id": 1,
        "name": "pet food collection",
        "platforms": ["xhs", "dy"],
        "collection_mode": "search",
        "keywords": ["cat food", "kitten food"],
        "target_ids": [],
        "creator_ids": [],
        "start_date": date(2026, 5, 1),
        "end_date": date(2026, 5, 7),
        "comment_policy": {
            "enable_comments": False,
            "enable_sub_comments": False,
            "max_posts_per_job": 200,
            "max_results_per_keyword_per_platform": 200,
            "prefer_latest_posts": True,
            "sort_mode": "latest",
            "time_preset": "7d",
            "time_start": "2026-05-01T00:00:00+00:00",
            "time_end": "2026-05-07T23:59:59+00:00",
            "fill_strategy": "prefer_fill",
            "max_extra_pages": 8,
        },
    }

    requests = build_crawler_start_requests(job)
    plan = execution_plan_to_dict(requests)

    assert [item["platform"] for item in plan] == ["xhs", "dy"]
    assert all(item["sort_mode"] == "latest" for item in plan)
    assert all(item["time_preset"] == "7d" for item in plan)
    assert all(item["max_results_per_keyword_per_platform"] == 200 for item in plan)
    assert all(item["fill_strategy"] == "prefer_fill" for item in plan)
    assert all(item["max_extra_pages"] == 8 for item in plan)
```

- [ ] **Step 2: Run the research propagation test and verify it fails**

Run: `uv run python -m pytest tests/test_research_execution_search_controls.py -q`

Expected: FAIL because `build_crawler_start_requests` does not populate the new fields.

- [ ] **Step 3: Extend growth project run-now schema**

In `research/schemas.py`, update `GrowthProjectRunNowRequest`:

```python
class GrowthProjectRunNowRequest(BaseModel):
    target_posts_per_platform: int = Field(default=50, ge=10, le=500)
    collection_window_days: int | None = Field(default=3, ge=1, le=365)
    prefer_latest_posts: bool = False
    sort_mode: Literal["relevance", "latest", "most_liked", "most_commented", "most_collected"] = "relevance"
    time_preset: Literal["all", "1d", "7d", "30d", "180d"] = "all"
    time_start: datetime | None = None
    time_end: datetime | None = None
    max_results_per_keyword_per_platform: int | None = Field(default=None, ge=1, le=5000)
    fill_strategy: Literal["prefer_fill"] = "prefer_fill"
    max_extra_pages: int = Field(default=5, ge=1, le=50)

    @model_validator(mode="after")
    def validate_time_range(self):
        if (self.time_start is None) != (self.time_end is None):
            raise ValueError("time_start and time_end must be provided together")
        if self.time_start is not None and self.time_end is not None and self.time_start > self.time_end:
            raise ValueError("time_start must be before or equal to time_end")
        return self
```

- [ ] **Step 4: Store run-now controls in `comment_policy`**

In `api/routers/research.py`, inside `run_growth_project_collection_now`, assign these fields after the existing `comment_policy.prefer_latest_posts` assignment:

```python
    comment_policy.max_results_per_keyword_per_platform = (
        request.max_results_per_keyword_per_platform or request.target_posts_per_platform
    )
    comment_policy.sort_mode = request.sort_mode
    comment_policy.time_preset = request.time_preset
    comment_policy.time_start = request.time_start.isoformat() if request.time_start else None
    comment_policy.time_end = request.time_end.isoformat() if request.time_end else None
    comment_policy.fill_strategy = request.fill_strategy
    comment_policy.max_extra_pages = request.max_extra_pages
```

Include these fields in the JSON response:

```python
        "sort_mode": request.sort_mode,
        "time_preset": request.time_preset,
        "time_start": request.time_start.isoformat() if request.time_start else None,
        "time_end": request.time_end.isoformat() if request.time_end else None,
        "max_results_per_keyword_per_platform": request.max_results_per_keyword_per_platform or request.target_posts_per_platform,
        "fill_strategy": request.fill_strategy,
        "max_extra_pages": request.max_extra_pages,
```

Replace the existing relative-date block with exact-range-aware dates:

```python
    end_date = date.today()
    if request.time_start and request.time_end:
        start_date = request.time_start.date()
        end_date = request.time_end.date()
    elif request.collection_window_days is None:
        start_date = date(1970, 1, 1)
        comment_policy.disable_time_window = True
    else:
        start_date = end_date - timedelta(days=request.collection_window_days - 1)
```

- [ ] **Step 5: Populate crawler request fields from `comment_policy`**

In `research/execution.py`, read fields from `comment_policy`:

```python
    sort_mode = str(comment_policy.get("sort_mode") or "relevance")
    time_preset = str(comment_policy.get("time_preset") or "all")
    time_start = comment_policy.get("time_start")
    time_end = comment_policy.get("time_end")
    per_keyword_cap = _positive_int(comment_policy.get("max_results_per_keyword_per_platform")) or max_notes_count
    fill_strategy = str(comment_policy.get("fill_strategy") or "prefer_fill")
    max_extra_pages = _positive_int(comment_policy.get("max_extra_pages")) or 5
```

Pass the fields to each `CrawlerStartRequest` in both `build_crawler_start_requests` and `build_crawler_start_request_for_unit`:

```python
                sort_mode=sort_mode,
                time_preset=time_preset,
                time_start=time_start,
                time_end=time_end,
                max_results_per_keyword_per_platform=per_keyword_cap,
                fill_strategy=fill_strategy,
                max_extra_pages=max_extra_pages,
```

Add the fields to `execution_plan_to_dict`:

```python
            "sort_mode": request.sort_mode,
            "time_preset": request.time_preset,
            "time_start": request.time_start.isoformat() if request.time_start else None,
            "time_end": request.time_end.isoformat() if request.time_end else None,
            "max_results_per_keyword_per_platform": request.max_results_per_keyword_per_platform,
            "fill_strategy": request.fill_strategy,
            "max_extra_pages": request.max_extra_pages,
```

- [ ] **Step 6: Run research propagation tests**

Run: `uv run python -m pytest tests/test_research_execution_search_controls.py -q`

Expected: PASS.

- [ ] **Step 7: Commit Task 3**

```bash
git add research/schemas.py api/routers/research.py research/execution.py tests/test_research_execution_search_controls.py
git commit -m "feat: propagate search controls into research execution"
```

---

### Task 4: Implement TikHub Per-Keyword Prefer-Fill Search

**Files:**
- Modify: `media_platform/tikhub/core.py`
- Create: `tests/test_tikhub_crawler_prefer_fill.py`

- [ ] **Step 1: Write crawler behavior tests**

Create `tests/test_tikhub_crawler_prefer_fill.py`:

```python
from __future__ import annotations

import pytest

import config
from media_platform.tikhub.core import TikHubCrawler


class FakeTikHubClient:
    def __init__(self, pages):
        self.pages = list(pages)
        self.requests = []

    async def request(self, method, path, *, json=None, params=None):
        self.requests.append({"method": method, "path": path, "json": json, "params": params})
        return self.pages.pop(0)

    async def close(self):
        return None


class SavingTikHubCrawler(TikHubCrawler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.saved = []

    async def _save_content(self, item):
        self.saved.append(item)

    async def _fetch_and_save_comments(self, mapped_content):
        return None


@pytest.mark.asyncio
async def test_search_uses_per_keyword_cap_and_fallback_fill(monkeypatch) -> None:
    monkeypatch.setattr(config, "CRAWLER_TYPE", "search", raising=False)
    monkeypatch.setattr(config, "KEYWORDS", "alpha,beta", raising=False)
    monkeypatch.setattr(config, "CRAWLER_MAX_NOTES_COUNT", 999, raising=False)
    monkeypatch.setattr(config, "CRAWLER_MAX_RESULTS_PER_KEYWORD_PER_PLATFORM", 2, raising=False)
    monkeypatch.setattr(config, "CRAWLER_SEARCH_SORT_MODE", "latest", raising=False)
    monkeypatch.setattr(config, "CRAWLER_SEARCH_TIME_PRESET", "all", raising=False)
    monkeypatch.setattr(config, "CRAWLER_SEARCH_TIME_START", "2026-05-01T00:00:00+00:00", raising=False)
    monkeypatch.setattr(config, "CRAWLER_SEARCH_TIME_END", "2026-05-07T23:59:59+00:00", raising=False)
    monkeypatch.setattr(config, "CRAWLER_FILL_STRATEGY", "prefer_fill", raising=False)
    monkeypatch.setattr(config, "CRAWLER_MAX_EXTRA_PAGES", 2, raising=False)
    monkeypatch.setattr(config, "ENABLE_GET_COMMENTS", False, raising=False)
    monkeypatch.setattr(config, "CRAWLER_MAX_SLEEP_SEC", 0, raising=False)

    inside_time = 1_778_112_000
    outside_time = 1_779_000_000
    client = FakeTikHubClient(
        [
            {"data": [{"note_id": "a1", "title": "a1", "time": inside_time}, {"note_id": "a2", "title": "a2", "time": outside_time}], "has_more": False},
            {"data": [{"note_id": "b1", "title": "b1", "time": inside_time}, {"note_id": "b2", "title": "b2", "time": outside_time}], "has_more": False},
        ]
    )
    crawler = SavingTikHubCrawler("xhs", client=client)

    await crawler.search()

    assert [item["note_id"] for item in crawler.saved] == ["a1", "a2", "b1", "b2"]
    assert [item["source_keyword"] for item in crawler.saved] == ["alpha", "alpha", "beta", "beta"]
    assert crawler.saved[0]["crawl_meta"]["within_requested_time_range"] is True
    assert crawler.saved[1]["crawl_meta"]["outside_requested_time_range"] is True
    assert len(client.requests) == 2
```

- [ ] **Step 2: Run the crawler behavior test and verify it fails**

Run: `uv run python -m pytest tests/test_tikhub_crawler_prefer_fill.py -q`

Expected: FAIL because `TikHubCrawler.search` still uses a run-level counter and has no fallback-fill metadata.

- [ ] **Step 3: Refactor `TikHubCrawler.search`**

In `media_platform/tikhub/core.py`, import search control helpers:

```python
from .search_controls import (
    apply_native_search_params,
    classify_time_range,
    effective_search_controls,
    metadata_for_item,
    search_controls_from_raw,
)
```

Replace the current `search` method body with this structure:

```python
    async def search(self) -> None:
        endpoint = get_endpoint(self.platform, Capability.SEARCH)
        per_keyword_limit = max(
            int(getattr(config, "CRAWLER_MAX_RESULTS_PER_KEYWORD_PER_PLATFORM", None) or config.CRAWLER_MAX_NOTES_COUNT),
            1,
        )
        controls = search_controls_from_raw(
            sort_mode=getattr(config, "CRAWLER_SEARCH_SORT_MODE", "relevance"),
            time_preset=getattr(config, "CRAWLER_SEARCH_TIME_PRESET", "all"),
            time_start=getattr(config, "CRAWLER_SEARCH_TIME_START", ""),
            time_end=getattr(config, "CRAWLER_SEARCH_TIME_END", ""),
            fill_strategy=getattr(config, "CRAWLER_FILL_STRATEGY", "prefer_fill"),
            max_extra_pages=getattr(config, "CRAWLER_MAX_EXTRA_PAGES", 5),
        )
        effective_controls = effective_search_controls(self.platform, controls)

        for keyword in [item.strip() for item in config.KEYWORDS.split(",") if item.strip()]:
            source_keyword_var.set(keyword)
            exact_items: list[Any] = []
            fill_items: list[Any] = []
            page = int(config.START_PAGE)
            cursor = ""
            pages_seen = 0

            while len(exact_items) < per_keyword_limit and pages_seen < max(1, effective_controls.max_extra_pages):
                params = self._search_params(endpoint, keyword, page, cursor, effective_controls)
                data = await self.client.request(
                    endpoint.method,
                    endpoint.path,
                    json=params if endpoint.json_body else None,
                    params=None if endpoint.json_body else params,
                )
                items = self._extract_items(data)
                if not items:
                    break

                for item in items:
                    mapped = self.mapper.map_content(item, source_keyword=keyword)
                    timestamp = self._publish_timestamp(mapped)
                    classification = classify_time_range(timestamp, effective_controls)
                    mapped["crawl_meta"] = metadata_for_item(effective_controls, classification)
                    if classification.within_requested_time_range:
                        exact_items.append(mapped)
                    else:
                        fill_items.append(mapped)

                cursor = self._next_cursor(data)
                pages_seen += 1
                if not cursor and not self._has_more(data):
                    break
                page += 1
                await asyncio.sleep(config.CRAWLER_MAX_SLEEP_SEC)

            selected = exact_items[:per_keyword_limit]
            if len(selected) < per_keyword_limit:
                selected.extend(fill_items[: per_keyword_limit - len(selected)])

            for mapped in selected:
                await self._save_content(mapped)
                if config.ENABLE_GET_COMMENTS:
                    await self._fetch_and_save_comments(mapped)
```

Add a small timestamp helper in the class:

```python
    def _publish_timestamp(self, mapped_content: Any) -> Any:
        if not isinstance(mapped_content, dict):
            return None
        if self.platform == "dy":
            return mapped_content.get("create_time")
        return mapped_content.get("time") or mapped_content.get("create_time")
```

Update `_search_params` to accept `effective_controls` and apply native params:

```python
    def _search_params(
        self,
        endpoint: EndpointSpec,
        keyword: str,
        page: int,
        cursor: str,
        effective_controls: Any | None = None,
    ) -> dict[str, Any]:
        params = dict(endpoint.default_params)
        params[endpoint.keyword_param] = keyword
        if effective_controls is not None:
            params = apply_native_search_params(self.platform, params, effective_controls)
        elif self.platform == "xhs" and bool(getattr(config, "CRAWLER_PREFER_LATEST_POSTS", False)):
            params["sort_type"] = getattr(config, "CRAWLER_SORT_TYPE", "") or "time_descending"
            filter_note_time = getattr(config, "CRAWLER_FILTER_NOTE_TIME", "") or xhs_filter_note_time(
                getattr(config, "CRAWLER_COLLECTION_WINDOW_DAYS", None)
            )
            if filter_note_time:
                params["filter_note_time"] = filter_note_time
        if endpoint.cursor_param and cursor:
            params[endpoint.cursor_param] = cursor
        elif endpoint.cursor_param:
            params.setdefault(endpoint.cursor_param, 0)
        elif endpoint.page_param:
            params[endpoint.page_param] = page
        return params
```

- [ ] **Step 4: Run crawler behavior tests**

Run: `uv run python -m pytest tests/test_tikhub_crawler_prefer_fill.py tests/test_tikhub_search_controls.py -q`

Expected: PASS.

- [ ] **Step 5: Commit Task 4**

```bash
git add media_platform/tikhub/core.py tests/test_tikhub_crawler_prefer_fill.py
git commit -m "feat: add prefer-fill TikHub search execution"
```

---

### Task 5: Preserve Prefer-Fill Metadata During Research Backfill

**Files:**
- Modify: `research/backfill.py`
- Modify: `research/normalizer.py`
- Create or extend: `tests/test_tikhub_search_controls.py`

- [ ] **Step 1: Write backfill selection and normalizer tests**

Append to `tests/test_tikhub_search_controls.py`:

```python
from research.backfill import annotate_prefer_fill_records
from research.normalizer import normalize_douyin_aweme, normalize_xhs_note


def test_annotate_prefer_fill_records_prefers_exact_then_fill() -> None:
    records = [
        {"id": "inside", "time": 1_778_112_000},
        {"id": "outside", "time": 1_779_000_000},
    ]
    controls = search_controls_from_raw(
        sort_mode="latest",
        time_preset="all",
        time_start="2026-05-01T00:00:00+00:00",
        time_end="2026-05-07T23:59:59+00:00",
    )

    selected = annotate_prefer_fill_records(
        records,
        platform="xhs",
        controls=effective_search_controls("xhs", controls),
        timestamp_key="time",
        limit=2,
    )

    assert [item["id"] for item in selected] == ["inside", "outside"]
    assert selected[0]["crawl_meta"]["within_requested_time_range"] is True
    assert selected[1]["crawl_meta"]["outside_requested_time_range"] is True


def test_normalizers_copy_crawl_meta_to_engagement_json() -> None:
    crawl_meta = {"outside_requested_time_range": True, "fill_reason": "fill_to_target"}
    xhs = normalize_xhs_note(
        {
            "note_id": "n1",
            "user_id": "u1",
            "title": "title",
            "desc": "desc",
            "time": 1_778_112_000,
            "crawl_meta": crawl_meta,
        },
        job_id=1,
        salt="salt",
    )
    dy = normalize_douyin_aweme(
        {
            "aweme_id": 123,
            "user_id": "u1",
            "title": "title",
            "desc": "desc",
            "create_time": 1_778_112_000,
            "crawl_meta": crawl_meta,
        },
        job_id=1,
        salt="salt",
    )

    assert xhs["engagement_json"]["outside_requested_time_range"] is True
    assert dy["engagement_json"]["fill_reason"] == "fill_to_target"
```

- [ ] **Step 2: Run the tests and verify they fail**

Run: `uv run python -m pytest tests/test_tikhub_search_controls.py -q`

Expected: FAIL because `annotate_prefer_fill_records` and metadata copying do not exist.

- [ ] **Step 3: Implement backfill annotation helper**

In `research/backfill.py`, import helpers:

```python
from media_platform.tikhub.search_controls import (
    EffectiveSearchControls,
    classify_time_range,
    effective_search_controls,
    metadata_for_item,
    search_controls_from_raw,
)
```

Add module-level helper:

```python
def controls_from_job(job: dict[str, Any] | None, platform: str) -> EffectiveSearchControls:
    policy = (job or {}).get("comment_policy") or {}
    controls = search_controls_from_raw(
        sort_mode=str(policy.get("sort_mode") or "relevance"),
        time_preset=str(policy.get("time_preset") or "all"),
        time_start=policy.get("time_start"),
        time_end=policy.get("time_end"),
        fill_strategy=str(policy.get("fill_strategy") or "prefer_fill"),
        max_extra_pages=int(policy.get("max_extra_pages") or 5),
    )
    return effective_search_controls(platform, controls)


def annotate_prefer_fill_records(
    records: list[dict[str, Any]],
    *,
    platform: str,
    controls: EffectiveSearchControls,
    timestamp_key: str,
    limit: int | None,
) -> list[dict[str, Any]]:
    exact: list[dict[str, Any]] = []
    fill: list[dict[str, Any]] = []
    for record in records:
        item = dict(record)
        classification = classify_time_range(item.get(timestamp_key), controls)
        item["crawl_meta"] = metadata_for_item(controls, classification)
        if classification.within_requested_time_range:
            exact.append(item)
        else:
            fill.append(item)
    target = max(1, int(limit)) if limit else len(records)
    return [*exact[:target], *fill[: max(0, target - len(exact))]]
```

In `backfill_xhs`, skip the current SQL `timestamp_bounds(time_window)` filter when `comment_policy.fill_strategy == "prefer_fill"` so fallback records remain available:

```python
            prefer_fill = ((job or {}).get("comment_policy") or {}).get("fill_strategy") == "prefer_fill"
            bounds = timestamp_bounds(time_window)
            if bounds and not prefer_fill:
                start_ts, end_ts = bounds
                note_stmt = note_stmt.where(XhsNote.time >= start_ts, XhsNote.time <= end_ts)
```

In `backfill_xhs` and `backfill_douyin`, after reading models into dicts and before calling `ingest_*_batch`, apply the helper:

```python
        controls = controls_from_job(job, "xhs")
        note_payloads = [model_to_dict(item) for item in notes]
        note_payloads = annotate_prefer_fill_records(
            note_payloads,
            platform="xhs",
            controls=controls,
            timestamp_key="time",
            limit=limit,
        )
```

Use `note_payloads` in `ingest_xhs_batch`. Do the same for Douyin with `timestamp_key="create_time"` and `aweme_payloads`.

- [ ] **Step 4: Copy crawl metadata in normalizers**

In `research/normalizer.py`, add helper near the bottom:

```python
def _crawl_meta(item: dict[str, Any]) -> dict[str, Any]:
    meta = item.get("crawl_meta")
    return dict(meta) if isinstance(meta, dict) else {}
```

In `normalize_xhs_note`, add to `engagement_json`:

```python
            **_crawl_meta(item),
```

In `normalize_douyin_aweme`, add to `engagement_json`:

```python
            **_crawl_meta(item),
```

- [ ] **Step 5: Run metadata tests**

Run: `uv run python -m pytest tests/test_tikhub_search_controls.py -q`

Expected: PASS.

- [ ] **Step 6: Commit Task 5**

```bash
git add research/backfill.py research/normalizer.py tests/test_tikhub_search_controls.py
git commit -m "feat: preserve prefer-fill crawl metadata"
```

---

### Task 6: Add Frontend Collection Controls

**Files:**
- Modify: `api/webui/src/types.ts`
- Modify: `api/webui/src/main.tsx`
- Modify: `api/webui/src/pages/GrowthProjectWorkbenchPage.tsx`

- [ ] **Step 1: Extend frontend types**

In `api/webui/src/types.ts`, add:

```ts
export type CollectionSortMode = "relevance" | "latest" | "most_liked" | "most_commented" | "most_collected";
export type CollectionTimePreset = "all" | "1d" | "7d" | "30d" | "180d";

export type CollectionRunControls = {
  targetPostsPerPlatform: number;
  sortMode: CollectionSortMode;
  timePreset: CollectionTimePreset;
  timeStart?: string;
  timeEnd?: string;
  maxResultsPerKeywordPerPlatform?: number;
  maxExtraPages: number;
};
```

- [ ] **Step 2: Change `onStartCollection` prop shape**

In `GrowthProjectWorkbenchPage.tsx`, import `CollectionRunControls` and replace the positional `onStartCollection` type with:

```ts
  onStartCollection: (projectId: string, controls: CollectionRunControls) => Promise<void>;
```

Create default controls near the top of the file:

```ts
const DEFAULT_COLLECTION_CONTROLS: CollectionRunControls = {
  targetPostsPerPlatform: 200,
  sortMode: "latest",
  timePreset: "7d",
  timeStart: "",
  timeEnd: "",
  maxResultsPerKeywordPerPlatform: 200,
  maxExtraPages: 5,
};
```

- [ ] **Step 3: Add form state and submit payload**

Inside `GrowthProjectWorkbenchPage`, add state:

```ts
  const [collectionControls, setCollectionControls] = React.useState<CollectionRunControls>(DEFAULT_COLLECTION_CONTROLS);
```

Replace `if (action === "start") await onStartCollection(selected.id, 1200, 7, true);` with:

```ts
      if (action === "start") await onStartCollection(selected.id, collectionControls);
```

- [ ] **Step 4: Render compact controls in the plan tab**

Add this panel above the existing `CollectionPlanTable`:

```tsx
<div className="collection-controls">
  <label>
    <span>单关键词单平台条数</span>
    <input
      type="number"
      min={10}
      max={500}
      value={collectionControls.targetPostsPerPlatform}
      onChange={(event) => {
        const value = Number(event.target.value);
        setCollectionControls((current) => ({
          ...current,
          targetPostsPerPlatform: value,
          maxResultsPerKeywordPerPlatform: value,
        }));
      }}
    />
  </label>
  <label>
    <span>排序</span>
    <select
      value={collectionControls.sortMode}
      onChange={(event) => setCollectionControls((current) => ({ ...current, sortMode: event.target.value as CollectionRunControls["sortMode"] }))}
    >
      <option value="relevance">综合相关</option>
      <option value="latest">最新发布</option>
      <option value="most_liked">点赞优先</option>
      <option value="most_commented">评论优先</option>
      <option value="most_collected">收藏优先</option>
    </select>
  </label>
  <label>
    <span>时间范围</span>
    <select
      value={collectionControls.timePreset}
      onChange={(event) => setCollectionControls((current) => ({ ...current, timePreset: event.target.value as CollectionRunControls["timePreset"] }))}
    >
      <option value="all">不限</option>
      <option value="1d">近 1 天</option>
      <option value="7d">近 7 天</option>
      <option value="30d">近 30 天</option>
      <option value="180d">近 180 天</option>
    </select>
  </label>
  <label>
    <span>开始时间</span>
    <input
      type="datetime-local"
      value={collectionControls.timeStart || ""}
      onChange={(event) => setCollectionControls((current) => ({ ...current, timeStart: event.target.value }))}
    />
  </label>
  <label>
    <span>结束时间</span>
    <input
      type="datetime-local"
      value={collectionControls.timeEnd || ""}
      onChange={(event) => setCollectionControls((current) => ({ ...current, timeEnd: event.target.value }))}
    />
  </label>
</div>
```

- [ ] **Step 5: Send the new payload from `main.tsx`**

In `api/webui/src/main.tsx`, import `CollectionRunControls`. Replace the positional callback with:

```tsx
                onStartCollection={(projectId, controls: CollectionRunControls) =>
                  controlGrowthProject(projectId, "run-now", {
                    target_posts_per_platform: controls.targetPostsPerPlatform,
                    collection_window_days: collectionWindowDaysForPreset(controls.timePreset, controls.timeStart),
                    prefer_latest_posts: controls.sortMode === "latest",
                    sort_mode: controls.sortMode,
                    time_preset: controls.timePreset,
                    time_start: controls.timeStart ? new Date(controls.timeStart).toISOString() : undefined,
                    time_end: controls.timeEnd ? new Date(controls.timeEnd).toISOString() : undefined,
                    max_results_per_keyword_per_platform:
                      controls.maxResultsPerKeywordPerPlatform || controls.targetPostsPerPlatform,
                    fill_strategy: "prefer_fill",
                    max_extra_pages: controls.maxExtraPages,
                  })}
```

Add this helper near the component code in `main.tsx`:

```ts
function collectionWindowDaysForPreset(preset: CollectionTimePreset, exactStart?: string) {
  if (exactStart) return undefined;
  if (preset === "1d") return 1;
  if (preset === "7d") return 7;
  if (preset === "30d") return 30;
  if (preset === "180d") return 180;
  return null;
}
```

- [ ] **Step 6: Add CSS for `.collection-controls`**

In `api/webui/src/styles.css`, add:

```css
.collection-controls {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 12px;
  margin: 0 0 16px;
  padding: 12px;
  border: 1px solid var(--line-soft);
  border-radius: 8px;
  background: #ffffff;
}

.collection-controls label {
  display: grid;
  gap: 6px;
  font-size: 12px;
  color: var(--muted);
}

.collection-controls input,
.collection-controls select {
  min-height: 36px;
  border: 1px solid var(--line-soft);
  border-radius: 6px;
  padding: 0 10px;
  color: var(--text);
  background: #fff;
}
```

- [ ] **Step 7: Run frontend build**

Run: `npm.cmd run build`

Expected: PASS.

- [ ] **Step 8: Commit Task 6**

```bash
git add api/webui/src/types.ts api/webui/src/main.tsx api/webui/src/pages/GrowthProjectWorkbenchPage.tsx api/webui/src/styles.css
git commit -m "feat: add collection search controls to project UI"
```

---

### Task 7: Integration Verification

**Files:**
- No new source files expected.

- [ ] **Step 1: Run focused backend tests**

Run:

```bash
uv run python -m pytest tests/test_tikhub_search_controls.py tests/test_crawler_search_control_plumbing.py tests/test_research_execution_search_controls.py tests/test_tikhub_crawler_prefer_fill.py -q
```

Expected: PASS.

- [ ] **Step 2: Run existing backend regression tests**

Run:

```bash
uv run python -m pytest tests -q
```

Expected: PASS.

- [ ] **Step 3: Run frontend build**

Run:

```bash
npm.cmd run build
```

Expected: PASS.

- [ ] **Step 4: Verify execution plan API output manually**

Start the API if needed, create or use a growth project with `xhs` and `dy`, then call the execution plan endpoint with a job id from the project collection flow.

Expected JSON fields in each step:

```json
{
  "platform": "xhs",
  "sort_mode": "latest",
  "time_preset": "7d",
  "max_results_per_keyword_per_platform": 200,
  "fill_strategy": "prefer_fill",
  "max_extra_pages": 5
}
```

- [ ] **Step 5: Commit final verification notes if any docs change**

If no docs or code change during verification, do not create an empty commit.

---

## Self-Review

Spec coverage:

- Time-ordered retrieval is covered by Tasks 1, 3, and 4.
- Preset and exact ranges are covered by Tasks 1, 2, 3, and 4.
- Per-keyword-per-platform caps are covered by Task 4.
- Prefer-fill behavior is covered by Tasks 4 and 5.
- Frontend controls are covered by Task 6.
- Verification is covered by Task 7.

Unresolved-marker scan:

- No unresolved marker is left in the plan.
- Every code-bearing task names the target file and provides the concrete code shape.

Type consistency:

- `sort_mode`, `time_preset`, `time_start`, `time_end`, `max_results_per_keyword_per_platform`, `fill_strategy`, and `max_extra_pages` are used consistently across API, CLI, research execution, TikHub crawler, and frontend payloads.
