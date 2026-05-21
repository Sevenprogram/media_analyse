import pytest

from research.account_profiles import AccountProfileService


class FakeRepository:
    def __init__(self):
        self.profiles = {}
        self.roles = []

    async def upsert_account_profile(self, payload):
        key = (payload["platform"], payload["account_id"])
        if key not in self.profiles:
            self.profiles[key] = {**payload, "id": len(self.profiles) + 1}
        else:
            self.profiles[key].update({key: value for key, value in payload.items() if value})
        return self.profiles[key]

    async def upsert_account_role(self, payload):
        self.roles.append(payload)
        return {**payload, "id": len(self.roles)}


@pytest.mark.asyncio
async def test_account_profile_reuses_same_account_for_roles():
    repo = FakeRepository()
    service = AccountProfileService(repo)

    profile = await service.upsert_from_post_author(
        {
            "platform": "xhs",
            "author_id": "u1",
            "display_name": "Teacher A",
            "bio": "K12 education creator",
        },
        vertical_id=1,
        scene_pack_id=2,
        role="candidate_creator",
    )
    competitor = await service.upsert_from_post_author(
        {
            "platform": "xhs",
            "author_id": "u1",
            "display_name": "Teacher A",
            "bio": "K12 education creator",
        },
        vertical_id=1,
        scene_pack_id=2,
        role="competitor",
    )

    assert profile["id"] == competitor["id"]
    assert len(repo.profiles) == 1
    assert [item["role"] for item in repo.roles] == [
        "candidate_creator",
        "competitor",
    ]
