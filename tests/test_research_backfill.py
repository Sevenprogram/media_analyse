from types import SimpleNamespace

from research.backfill import model_to_dict
from research.schemas import ExistingDataBackfillRequest


class FakeColumn:
    def __init__(self, name):
        self.name = name


class FakeModel:
    __table__ = SimpleNamespace(columns=[FakeColumn("id"), FakeColumn("source_keyword")])

    def __init__(self):
        self.id = 1
        self.source_keyword = " 政策 "


def test_model_to_dict_reads_sqlalchemy_column_names():
    assert model_to_dict(FakeModel()) == {"id": 1, "source_keyword": " 政策 "}


def test_backfill_request_strips_empty_keywords():
    request = ExistingDataBackfillRequest(keywords=[" 政策 ", "", "  "], limit=10)

    assert request.keywords == ["政策"]
