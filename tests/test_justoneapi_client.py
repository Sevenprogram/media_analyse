from __future__ import annotations

import sys
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from media_platform.justoneapi.client import JustOneAPIClient, JustOneAPIRateLimitError


def test_handle_response_accepts_string_success_code() -> None:
    client = object.__new__(JustOneAPIClient)
    response = httpx.Response(200, json={"code": "0", "data": {"ok": True}})

    assert client._handle_response(response) == {"ok": True}


def test_handle_response_maps_justone_rate_limit_code() -> None:
    client = object.__new__(JustOneAPIClient)
    response = httpx.Response(200, json={"code": "302", "message": "rate limit"})

    with pytest.raises(JustOneAPIRateLimitError):
        client._handle_response(response)
