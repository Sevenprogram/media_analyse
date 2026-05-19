from research.ai_analysis import parse_json_response, render_prompt


def test_render_prompt_injects_target_content():
    prompt = "平台:{platform}\n内容:{content}\n输出 JSON"
    target = {"platform": "wb", "content": "政策讨论"}

    assert render_prompt(prompt, target) == "平台:wb\n内容:政策讨论\n输出 JSON"


def test_render_prompt_keeps_unknown_placeholders():
    assert render_prompt("{unknown}", {}) == "{unknown}"


def test_parse_json_response_accepts_fenced_json():
    result = parse_json_response('```json\n{"stance": "support"}\n```')

    assert result == {"stance": "support"}


def test_parse_json_response_falls_back_to_text():
    result = parse_json_response("not json")

    assert result == {"text": "not json"}
