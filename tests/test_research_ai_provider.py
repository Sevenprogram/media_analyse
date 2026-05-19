from research.ai_provider import build_chat_completions_url


def test_build_chat_completions_url_adds_v1_path():
    assert (
        build_chat_completions_url("https://example.com")
        == "https://example.com/v1/chat/completions"
    )


def test_build_chat_completions_url_does_not_duplicate_path():
    assert (
        build_chat_completions_url("https://example.com/v1")
        == "https://example.com/v1/chat/completions"
    )
