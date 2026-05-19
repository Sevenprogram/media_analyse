import hashlib
import json


def test_raw_record_payload_hash_matches_repository_algorithm():
    payload = {"b": 2, "a": "政策"}
    payload_hash = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()

    assert payload_hash == "45c370e26b827044bd326c0fd7aa012c943a22a922da9f486cd7e8dd88776ffb"
