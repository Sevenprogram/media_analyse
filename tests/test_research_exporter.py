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
        raw_records=[{"source_id": "p1", "payload_json": {"content": "hello"}}],
        chart_summary={"platform_counts": [{"platform": "wb", "posts": 1, "comments": 1}]},
    )

    export_dir = tmp_path / "research_job_7"
    assert result["export_dir"] == str(export_dir)
    assert (export_dir / "posts.csv").exists()
    assert (export_dir / "comments.csv").exists()
    assert (export_dir / "authors.csv").exists()
    assert (export_dir / "ai_results.jsonl").exists()
    assert (export_dir / "raw_records.jsonl").exists()
    assert (export_dir / "research_export.xlsx").exists()
    assert (export_dir / "charts" / "platform_counts.png").exists()
    assert (export_dir / "job_report.md").exists()
