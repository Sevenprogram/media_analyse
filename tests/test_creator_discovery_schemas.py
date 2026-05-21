import pytest
from pydantic import ValidationError

from research.schemas import (
    CompetitorAccountCreate,
    CreatorSearchRequest,
    PlatformCapabilityUpsert,
    TagDefinitionCreate,
    VerticalCreate,
)


def test_platform_capability_rejects_unknown_platform():
    with pytest.raises(ValidationError, match="Unsupported platform"):
        PlatformCapabilityUpsert(platform="unknown")


def test_vertical_code_is_normalized():
    payload = VerticalCreate(code=" Education ", name="Education")

    assert payload.code == "education"


def test_tag_definition_strips_terms():
    payload = TagDefinitionCreate(
        vertical_id=1,
        group_id=1,
        tag_name="K12",
        keywords=[" K12 ", ""],
        synonyms=["中小学 "],
    )

    assert payload.keywords == ["K12"]
    assert payload.synonyms == ["中小学"]


def test_creator_search_requires_query_or_tags():
    with pytest.raises(ValidationError, match="creator search requires"):
        CreatorSearchRequest()


def test_competitor_account_validates_platform():
    with pytest.raises(ValidationError, match="Unsupported platform"):
        CompetitorAccountCreate(platform="bad", creator_id="1")
