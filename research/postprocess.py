from typing import Any

from research.account_profiles import AccountProfileService
from research.creator_search import rebuild_creator_profiles
from research.tagging import tag_research_job


async def run_post_crawl_analysis(
    repository,
    *,
    job_id: int,
    platform: str | None = None,
    analysis_version: str = "v1",
) -> dict[str, Any]:
    required_methods = (
        "list_tag_definitions",
        "bulk_upsert_entity_tags",
        "list_all_posts",
        "list_all_comments",
        "list_all_authors",
        "list_entity_tags",
        "upsert_creator_profile",
    )
    if any(not hasattr(repository, method) for method in required_methods):
        return {
            "skipped": True,
            "reason": "postprocess_repository_methods_unavailable",
            "platform": platform,
        }
    if platform:
        capability = await repository.get_platform_capability(platform)
        if capability and (not capability["enabled"] or not capability["analysis_enabled"]):
            return {
                "skipped": True,
                "reason": "platform_analysis_disabled",
                "platform": platform,
            }
    tag_stats = await tag_research_job(
        repository,
        job_id=job_id,
        vertical_id=None,
        analysis_version=analysis_version,
        use_ai=False,
    )
    profile_stats = await rebuild_creator_profiles(
        repository,
        job_id=job_id,
        platform=platform,
        analysis_version=analysis_version,
    )
    account_profile_stats = await rebuild_account_profiles_from_posts(
        repository,
        job_id=job_id,
        platform=platform,
    )
    return {
        "skipped": False,
        "platform": platform,
        "tagging": tag_stats,
        "profiles": profile_stats,
        "account_profiles": account_profile_stats,
    }


async def rebuild_account_profiles_from_posts(
    repository,
    *,
    job_id: int,
    platform: str | None = None,
    vertical_id: int | None = None,
    scene_pack_id: int | None = None,
) -> dict[str, Any]:
    if not all(
        hasattr(repository, method)
        for method in ("list_posts", "upsert_account_profile", "upsert_account_role")
    ):
        return {"skipped": True, "reason": "account_profile_methods_unavailable"}

    service = AccountProfileService(repository)
    posts = await repository.list_posts(job_id, limit=5000)
    upserted = 0
    skipped = 0
    for post in posts:
        if platform and post.get("platform") != platform:
            continue
        engagement = post.get("engagement_json") or {}
        author_id = engagement.get("author_id") or engagement.get("user_id")
        if not author_id:
            skipped += 1
            continue
        await service.upsert_from_post_author(
            {
                "platform": post["platform"],
                "author_id": str(author_id),
                "sec_account_id": engagement.get("sec_uid"),
                "display_name": engagement.get("nickname"),
                "bio": engagement.get("signature"),
                "source": "postprocess",
            },
            vertical_id=vertical_id,
            scene_pack_id=scene_pack_id,
            role="candidate_creator",
        )
        upserted += 1
    return {"skipped": False, "upserted": upserted, "missing_author": skipped}
