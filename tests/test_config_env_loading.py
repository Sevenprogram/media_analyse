from pathlib import Path

import config


def test_read_env_file_parses_key_values(tmp_path: Path):
    env_file = tmp_path / ".env.example"
    env_file.write_text(
        """
# comment
TIKHUB_API_KEY=example-key
TIKHUB_BASE_URL="https://api.example.test"
ENABLE_TIKHUB=true
""".strip(),
        encoding="utf-8",
    )

    values = config._read_env_file(env_file)

    assert values["TIKHUB_API_KEY"] == "example-key"
    assert values["TIKHUB_BASE_URL"] == "https://api.example.test"
    assert values["ENABLE_TIKHUB"] == "true"
