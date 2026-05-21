from research.growth_projects import build_growth_project_detail, build_growth_project_summaries


def test_groups_jobs_by_topic_and_generates_project_summary():
    jobs = [
        {
            "id": 1,
            "name": "TikHub backfill Douyin education keywords 2026-05-20",
            "topic": "education_summer_2026",
            "platforms": ["dy"],
            "keywords": ["K12 education", "summer childcare"],
            "status": "completed",
            "collection_mode": "search",
            "updated_at": "2026-05-20T14:20:00Z",
        },
        {
            "id": 2,
            "name": "TikHub backfill Xiaohongshu education keywords 2026-05-20",
            "topic": "education_summer_2026",
            "platforms": ["xhs"],
            "keywords": ["K12 education", "enrollment"],
            "status": "completed",
            "collection_mode": "search",
            "updated_at": "2026-05-20T15:00:00Z",
        },
    ]
    stats = {
        1: {"posts": 120, "comments": 0, "raw_records": 80, "authors": 15},
        2: {"posts": 24, "comments": 0, "raw_records": 20, "authors": 3},
    }

    projects = build_growth_project_summaries(jobs, stats)

    assert len(projects) == 1
    project = projects[0]
    assert project["id"] == "education_summer_2026"
    assert project["name"] == "Education Summer 2026"
    assert project["primary_goal"] == "topic_discovery"
    assert project["platforms"] == ["dy", "xhs"]
    assert project["metrics"] == {
        "jobs": 2,
        "posts": 144,
        "comments": 0,
        "raw_records": 100,
        "creators": 18,
        "failed_jobs": 0,
        "running_jobs": 0,
        "pending_jobs": 0,
    }
    assert project["sample_status"]["kind"] == "comment_insufficient"
    assert project["recommended_action"]["kind"] == "backfill_comments"
    assert project["recommended_action"]["label"] == "Backfill comments"


def test_failed_jobs_take_priority_over_ai_recommendations():
    jobs = [
        {
            "id": 3,
            "name": "Failed competitor creator crawl",
            "topic": "education_competitors",
            "platforms": ["dy"],
            "keywords": ["education"],
            "status": "failed",
            "collection_mode": "creator",
            "updated_at": "2026-05-20T12:00:00Z",
        }
    ]
    stats = {3: {"posts": 200, "comments": 50, "raw_records": 100, "authors": 20}}

    projects = build_growth_project_summaries(jobs, stats)

    assert projects[0]["sample_status"]["kind"] == "collection_issue"
    assert projects[0]["recommended_action"]["kind"] == "view_failed_jobs"
    assert projects[0]["opportunity_score"] is None


def test_detail_contains_jobs_keywords_and_status_bar():
    jobs = [
        {
            "id": 5,
            "name": "Douyin keyword search",
            "topic": "ai_tools_keyword_expansion",
            "platforms": ["dy"],
            "keywords": ["AI tools", "workflow automation"],
            "status": "completed",
            "collection_mode": "search",
            "updated_at": "2026-05-20T09:00:00Z",
        }
    ]
    stats = {5: {"posts": 80, "comments": 15, "raw_records": 70, "authors": 10}}

    detail = build_growth_project_detail("ai_tools_keyword_expansion", jobs, stats)

    assert detail["project"]["id"] == "ai_tools_keyword_expansion"
    assert detail["status_bar"]["sample_status"] == "Sample is ready for preliminary analysis"
    assert detail["keywords"] == [
        {"keyword": "AI tools", "type": "core", "source": "research_job"},
        {"keyword": "workflow automation", "type": "core", "source": "research_job"},
    ]
    assert detail["collection_records"][0]["id"] == 5
