import pytest

from research.tagging import AITaggingService


class FakeProvider:
    model = "fake"

    async def chat_json(self, messages, params):
        return {
            "choices": [
                {
                    "message": {
                        "content": '{"tags":[{"tag_id":1,"confidence":0.8,"evidence":"profile text"},{"tag_id":999,"confidence":1,"evidence":"bad"}]}'
                    }
                }
            ]
        }


@pytest.mark.asyncio
async def test_ai_tagger_discards_unconfigured_tags():
    result = await AITaggingService(FakeProvider()).tag_entity(
        entity={"content": "K12 education"},
        tag_definitions=[{"id": 1, "vertical_id": 2, "tag_name": "K12"}],
        entity_type="post",
        entity_id="p1",
        platform="xhs",
    )

    assert len(result) == 1
    assert result[0].tag_id == 1
    assert result[0].source == "ai"
