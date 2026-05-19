import pytest
from pydantic import ValidationError

from research.schemas import AIPromptTemplateCreate


def test_prompt_template_rejects_unknown_task_type():
    with pytest.raises(ValidationError, match="Unsupported AI task type"):
        AIPromptTemplateCreate(
            name="Bad prompt",
            task_type="unknown",
            prompt_text="Return JSON",
        )


def test_prompt_template_accepts_stance_task():
    prompt = AIPromptTemplateCreate(
        name="Stance",
        task_type="stance",
        prompt_text="Classify stance",
    )

    assert prompt.platform == "all"
    assert prompt.version == "v1"
