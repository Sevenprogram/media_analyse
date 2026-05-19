import csv
import json
from pathlib import Path
from typing import Any

import pandas as pd


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
        raw_records: list[dict[str, Any]] | None = None,
        chart_summary: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        export_dir = self.base_dir / f"research_job_{job_id}"
        export_dir.mkdir(parents=True, exist_ok=True)
        (export_dir / "charts").mkdir(exist_ok=True)

        self._write_csv(export_dir / "posts.csv", posts)
        self._write_csv(export_dir / "comments.csv", comments)
        self._write_csv(export_dir / "authors.csv", authors)
        self._write_jsonl(export_dir / "ai_results.jsonl", ai_results)
        self._write_jsonl(export_dir / "raw_records.jsonl", raw_records or [])
        self._write_excel(
            export_dir / "research_export.xlsx",
            posts=posts,
            comments=comments,
            authors=authors,
            ai_results=ai_results,
        )
        generated_charts = self._write_chart_images(export_dir / "charts", chart_summary or {})
        charts = [*charts, *generated_charts]
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

    def _write_excel(
        self,
        path: Path,
        *,
        posts: list[dict[str, Any]],
        comments: list[dict[str, Any]],
        authors: list[dict[str, Any]],
        ai_results: list[dict[str, Any]],
    ) -> None:
        with pd.ExcelWriter(path) as writer:
            pd.DataFrame(posts).to_excel(writer, sheet_name="posts", index=False)
            pd.DataFrame(comments).to_excel(writer, sheet_name="comments", index=False)
            pd.DataFrame(authors).to_excel(writer, sheet_name="authors", index=False)
            pd.DataFrame(ai_results).to_excel(writer, sheet_name="ai_results", index=False)

    def _write_chart_images(self, charts_dir: Path, chart_summary: dict[str, Any]) -> list[Path]:
        if not chart_summary:
            return []
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        generated: list[Path] = []
        for name, rows in chart_summary.items():
            if not rows:
                continue
            path = charts_dir / f"{name}.png"
            labels, values = _labels_and_values(name, rows)
            if not labels or not values:
                continue
            fig, ax = plt.subplots(figsize=(8, 4.5))
            ax.bar(labels, values, color="#2f6f73")
            ax.set_title(name.replace("_", " ").title())
            ax.tick_params(axis="x", labelrotation=30)
            fig.tight_layout()
            fig.savefig(path, dpi=150)
            plt.close(fig)
            generated.append(path)
        return generated

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


def _labels_and_values(name: str, rows: list[dict[str, Any]]) -> tuple[list[str], list[int]]:
    label_keys = {
        "platform_counts": "platform",
        "post_trend": "date",
        "comment_trend": "date",
        "keyword_ranking": "keyword",
        "sentiment_distribution": "name",
        "stance_distribution": "name",
        "topic_tag_ranking": "name",
    }
    value_keys = {
        "platform_counts": "posts",
        "post_trend": "posts",
        "comment_trend": "comments",
        "keyword_ranking": "count",
        "sentiment_distribution": "value",
        "stance_distribution": "value",
        "topic_tag_ranking": "value",
    }
    label_key = label_keys.get(name)
    value_key = value_keys.get(name)
    if not label_key or not value_key:
        return [], []
    return [str(row[label_key]) for row in rows], [int(row[value_key] or 0) for row in rows]
