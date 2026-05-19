from types import SimpleNamespace

from research.backfill import _numeric_values, _text_values, model_to_dict
from research.schemas import ExistingDataBackfillRequest


class FakeColumn:
    def __init__(self, name):
        self.name = name


class FakeModel:
    __table__ = SimpleNamespace(columns=[FakeColumn("id"), FakeColumn("source_keyword")])

    def __init__(self):
        self.id = 1
        self.source_keyword = " policy "


def test_model_to_dict_reads_sqlalchemy_column_names():
    assert model_to_dict(FakeModel()) == {"id": 1, "source_keyword": " policy "}


def test_backfill_request_strips_empty_filters():
    request = ExistingDataBackfillRequest(
        keywords=[" policy ", "", "  "],
        target_ids=[" 1001 "],
        creator_ids=[" author "],
        limit=10,
    )

    assert request.keywords == ["policy"]
    assert request.target_ids == ["1001"]
    assert request.creator_ids == ["author"]


def test_backfill_filter_value_helpers_normalize_ids():
    assert _text_values([" 001 ", "", 2]) == ["001", "2"]
    assert _numeric_values([" 001 ", "abc", 2]) == [1, 2]
