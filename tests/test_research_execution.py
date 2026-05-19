from research.execution import (
    ResearchExecutionOptions,
    build_crawler_start_requests,
    execution_plan_to_dict,
)


def test_build_crawler_start_requests_uses_backend_keywords():
    job = {
        "id": 1,
        "platforms": ["wb", "zhihu"],
        "keywords": ["政策", "治理"],
        "comment_policy": {
            "enable_comments": True,
            "enable_sub_comments": False,
        },
    }

    requests = build_crawler_start_requests(job)

    assert [request.platform.value for request in requests] == ["wb", "zhihu"]
    assert requests[0].keywords == "政策,治理"
    assert requests[0].save_option.value == "postgres"


def test_execution_plan_to_dict_hides_cookies():
    job = {
        "id": 1,
        "platforms": ["wb"],
        "keywords": ["政策"],
        "comment_policy": {"enable_comments": False, "enable_sub_comments": False},
    }
    options = ResearchExecutionOptions(cookies="secret-cookie", headless=True)

    plan = execution_plan_to_dict(build_crawler_start_requests(job, options=options))

    assert plan == [
        {
            "platform": "wb",
            "crawler_type": "search",
            "keywords": "政策",
            "start_page": 1,
            "enable_comments": False,
            "enable_sub_comments": False,
            "save_option": "postgres",
            "headless": True,
            "login_type": "qrcode",
        }
    ]
