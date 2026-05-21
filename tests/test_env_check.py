import subprocess

from fastapi.testclient import TestClient

import api.main as api_main


def test_environment_check_uses_project_root_and_local_uv_cache(monkeypatch):
    captured = {}

    def fake_run(args, **kwargs):
        captured["args"] = args
        captured.update(kwargs)
        return subprocess.CompletedProcess(args, 0, stdout="help ok", stderr="")

    monkeypatch.delenv("UV_CACHE_DIR", raising=False)
    monkeypatch.setattr(api_main.subprocess, "run", fake_run)

    result = api_main._run_environment_check()

    assert result.returncode == 0
    assert captured["args"] == ["uv", "run", "main.py", "--help"]
    assert captured["cwd"] == api_main.PROJECT_ROOT
    assert captured["env"]["UV_CACHE_DIR"] == str(api_main.PROJECT_UV_CACHE_DIR)
    assert captured["timeout"] == 30.0


def test_environment_check_route_returns_runner_output(monkeypatch):
    def fake_check():
        return subprocess.CompletedProcess(
            ["uv", "run", "main.py", "--help"],
            0,
            stdout="MediaCrawler CLI help",
            stderr="",
        )

    monkeypatch.setattr(api_main, "_run_environment_check", fake_check)
    client = TestClient(api_main.app)

    response = client.get("/api/env/check")

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "message": "MediaCrawler environment configured correctly",
        "output": "MediaCrawler CLI help",
    }
