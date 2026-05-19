import csv
import json
from pathlib import Path
from typing import Any


class ResearchExporter:
    def __init__(self, base_dir: Path | str = "exports"):
        self.base_dir = Path(base_dir)

    def export_job(
        self,
        *,
        job_id: int,
        job_summary: dict[str, Any],
        posts: list[dict[str, Any]],
        comments: list[dict[str, Any]],
        authors: list[dict[str, Any]],
        ai_results: list[dict[str, Any]],
        charts: list[Path],
    ) -> dict[str, Any]:
        export_dir = self.base_dir / f"research_job_{job_id}"
        export_dir.mkdir(parents=True, exist_ok=True)
        (export_dir / "charts").mkdir(exist_ok=True)

        self._write_csv(export_dir / "posts.csv", posts)
        self._write_csv(export_dir / "comments.csv", comments)
        self._write_csv(export_dir / "authors.csv", authors)
        self._write_jsonl(export_dir / "ai_results.jsonl", ai_results)
        self._write_report(
            export_dir / "job_report.md",
            job_summary,
            posts,
            comments,
            authors,
            ai_results,
            charts,
        )

        return {"export_dir": str(export_dir)}

    def _write_csv(self, path: Path, rows: list[dict[str, Any]]) -> None:
        if not rows:
            path.write_text("", encoding="utf-8")
            return
        fieldnames = sorted({key for row in rows for key in row})
        with path.open("w", encoding="utf-8", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    def _write_jsonl(self, path: Path, rows: list[dict[str, Any]]) -> None:
        with path.open("w", encoding="utf-8") as file:
            for row in rows:
                file.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")

    def _write_report(
        self,
        path: Path,
        job_summary: dict[str, Any],
        posts: list[dict[str, Any]],
        comments: list[dict[str, Any]],
        authors: list[dict[str, Any]],
        ai_results: list[dict[str, Any]],
        charts: list[Path],
    ) -> None:
        lines = [
            f"# Research Job Report: {job_summary['name']}",
            "",
            f"- Platforms: {', '.join(job_summary['platforms'])}",
            f"- Keywords: {', '.join(job_summary['keywords'])}",
            f"- Time window: {job_summary['start_date']} to {job_summary['end_date']}",
            f"- Posts: {len(posts)}",
            f"- Comments: {len(comments)}",
            f"- Authors: {len(authors)}",
            f"- AI results: {len(ai_results)}",
            "",
            "## Charts",
        ]
        lines.extend(f"- charts/{chart.name}" for chart in charts)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
