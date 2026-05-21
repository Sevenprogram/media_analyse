import argparse
import json
from typing import Any

from research.platforms import SUPPORTED_RESEARCH_PLATFORMS


VALIDATION_STEPS = [
    "auth_profile_configured",
    "rate_limit_configured",
    "small_research_job_created",
    "crawl_units_scheduled",
    "worker_claimed_unit",
    "crawler_started",
    "research_backfill_completed",
    "charts_and_export_checked",
]


def build_validation_checklist(platforms: list[str] | None = None) -> dict[str, Any]:
    selected = platforms or sorted(SUPPORTED_RESEARCH_PLATFORMS)
    unsupported = sorted(set(selected) - SUPPORTED_RESEARCH_PLATFORMS)
    if unsupported:
        raise ValueError(f"Unsupported platform(s): {', '.join(unsupported)}")
    return {
        "mode": "small_real_collection_validation",
        "default_scope": {
            "keywords": 1,
            "platforms_per_run": 1,
            "comment_policy": "limited",
            "headless": True,
        },
        "platforms": [
            {
                "platform": platform,
                "steps": [
                    {"key": step, "status": "manual_check_required"}
                    for step in VALIDATION_STEPS
                ],
            }
            for platform in selected
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a real collection validation checklist")
    parser.add_argument("--platform", action="append", dest="platforms")
    args = parser.parse_args()
    print(json.dumps(build_validation_checklist(args.platforms), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
