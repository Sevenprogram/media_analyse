from typing import Any, Protocol


class AccountProfileRepository(Protocol):
    async def upsert_account_profile(self, payload: dict[str, Any]) -> dict[str, Any]:
        ...

    async def upsert_account_role(self, payload: dict[str, Any]) -> dict[str, Any]:
        ...


class AccountProfileService:
    def __init__(self, repository: AccountProfileRepository):
        self.repository = repository

    async def upsert_from_post_author(
        self,
        author: dict[str, Any],
        *,
        vertical_id: int | None,
        scene_pack_id: int | None,
        role: str,
        monitor_pool_id: int | None = None,
    ) -> dict[str, Any]:
        account_id = str(
            author.get("account_id")
            or author.get("author_id")
            or author.get("user_id")
            or author.get("creator_id")
            or ""
        ).strip()
        if not account_id:
            raise ValueError("account_id is required to upsert an account profile")

        profile = await self.repository.upsert_account_profile(
            {
                "platform": author["platform"],
                "account_id": account_id,
                "sec_account_id": author.get("sec_account_id") or author.get("sec_uid"),
                "display_name": author.get("display_name") or author.get("nickname"),
                "avatar_url": author.get("avatar_url") or author.get("avatar"),
                "profile_url": author.get("profile_url"),
                "bio": author.get("bio") or author.get("signature"),
                "verified": bool(author.get("verified", False)),
                "region": author.get("region") or author.get("ip_location"),
                "follower_count": author.get("follower_count") or author.get("fans"),
                "following_count": author.get("following_count") or author.get("follows"),
                "post_count": author.get("post_count") or author.get("videos_count"),
                "avg_engagement_rate": author.get("avg_engagement_rate"),
                "hot_post_rate": author.get("hot_post_rate"),
                "recent_post_count_30d": author.get("recent_post_count_30d"),
                "latest_post_time": author.get("latest_post_time"),
                "contact_clues": author.get("contact_clues") or [],
                "tag_summary": author.get("tag_summary") or {},
                "last_crawled_at": author.get("last_crawled_at"),
            }
        )
        await self.repository.upsert_account_role(
            {
                "account_profile_id": profile["id"],
                "role": role,
                "vertical_id": vertical_id,
                "scene_pack_id": scene_pack_id,
                "monitor_pool_id": monitor_pool_id,
                "source": author.get("source", "postprocess"),
                "status": "active",
            }
        )
        return profile
