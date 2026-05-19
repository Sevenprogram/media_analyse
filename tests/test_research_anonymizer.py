import pytest

from research.anonymizer import hash_author_id, hash_optional_text


def test_hash_author_id_is_deterministic_for_same_platform_and_salt():
    first = hash_author_id(platform="wb", raw_author_id="12345", salt="test-salt")
    second = hash_author_id(platform="wb", raw_author_id="12345", salt="test-salt")

    assert first == second
    assert first.startswith("wb_")


def test_hash_author_id_changes_by_platform():
    wb_hash = hash_author_id(platform="wb", raw_author_id="12345", salt="test-salt")
    zhihu_hash = hash_author_id(
        platform="zhihu", raw_author_id="12345", salt="test-salt"
    )

    assert wb_hash != zhihu_hash


def test_hash_author_id_requires_salt():
    with pytest.raises(ValueError, match="salt is required"):
        hash_author_id(platform="wb", raw_author_id="12345", salt="")


def test_hash_optional_text_keeps_none_as_none():
    assert hash_optional_text(None, salt="test-salt") is None
