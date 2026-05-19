from pathlib import Path

from research.exporter import ResearchExporter


def test_exporter_creates_report_and_csv_files(tmp_path: Path):
    exporter = ResearchExporter(base_dir=tmp_path)
    result = exporter.export_job(
        job_id=7,
        job_summary={
            "name": "Policy debate",
            "platforms": ["wb", "zhihu"],
            "keywords": ["公共政策"],
            "start_date": "2026-01-01",
            "end_date": "2026-01-31",
        },
        posts=[{"platform": "wb", "platform_post_id": "p1", "content": "hello"}],
        comments=[{"platform": "wb", "platform_comment_id": "c1", "content": "comment"}],
        authors=[{"platform": "wb", "author_hash": "wb_abc"}],
        ai_results=[{"target_id": "p1", "result_json": {"stance": "support"}}],
        charts=[],
    )

    export_dir = tmp_path / "research_job_7"
    assert result["export_dir"] == str(export_dir)
    assert (export_dir / "posts.csv").exists()
    assert (export_dir / "comments.csv").exists()
    assert (export_dir / "authors.csv").exists()
    assert (export_dir / "ai_results.jsonl").exists()
    assert (export_dir / "job_report.md").exists()
