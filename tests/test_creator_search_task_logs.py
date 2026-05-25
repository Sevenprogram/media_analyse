from api.routers.creator_search import _creator_search_log_message


def test_realtime_only_task_logs_describe_realtime_search():
    payload = {
        "search_scope": "realtime_only",
        "platforms": ["xhs", "dy"],
        "limit": 10,
    }

    assert "实时搜索任务已提交" in _creator_search_log_message("queued", payload=payload)
    assert "小红书 / 抖音实时发现" in _creator_search_log_message("realtime", payload=payload)
    assert "整理实时结果" in _creator_search_log_message("merging", payload=payload)


def test_hybrid_task_logs_still_describe_local_database_stage():
    payload = {
        "search_scope": "hybrid",
        "platforms": ["xhs"],
        "limit": 10,
    }

    assert "达人搜索任务已提交" in _creator_search_log_message("queued", payload=payload)
    assert "本地达人画像" in _creator_search_log_message("database", payload=payload)
