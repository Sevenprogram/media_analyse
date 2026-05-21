from research.tagging import RuleTagger


def test_rule_tagger_matches_keyword_and_evidence():
    tags = [
        {
            "id": 1,
            "vertical_id": 10,
            "tag_name": "K12教育",
            "keywords": ["K12"],
            "synonyms": ["中小学"],
            "negative_keywords": [],
            "weight": 10,
        }
    ]

    result = RuleTagger().match_entity(
        entity={"title": "K12 单亲妈妈教育经验"},
        tag_definitions=tags,
        entity_type="post",
        entity_id="p1",
        platform="xhs",
    )

    assert len(result) == 1
    assert result[0].tag_id == 1
    assert result[0].evidence_json["matches"][0]["matched_term"] == "K12"


def test_rule_tagger_negative_keyword_suppresses_tag():
    tags = [
        {
            "id": 1,
            "vertical_id": 10,
            "tag_name": "K12教育",
            "keywords": ["教育"],
            "synonyms": [],
            "negative_keywords": ["成人教育"],
            "weight": 1,
        }
    ]

    result = RuleTagger().match_entity(
        entity={"content": "成人教育课程"},
        tag_definitions=tags,
        entity_type="post",
        entity_id="p1",
        platform="xhs",
    )

    assert result == []
