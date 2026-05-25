import React from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";

export function Pagination({ page, totalPages, onChange }: { page: number; totalPages: number; onChange: (next: number) => void }) {
  const pages = buildPageList(page, totalPages);
  return (
    <div className="cd-pagination">
      <button type="button" className="cd-page-btn" disabled={page <= 1} onClick={() => onChange(page - 1)} aria-label="上一页">
        <ChevronLeft size={14} />
      </button>
      {pages.map((entry, index) =>
        entry === "..." ? (
          <span key={`gap-${index}`} className="cd-page-gap">…</span>
        ) : (
          <button
            type="button"
            key={entry}
            className={`cd-page-btn ${entry === page ? "is-active" : ""}`}
            onClick={() => onChange(entry)}
          >
            {entry}
          </button>
        ),
      )}
      <button type="button" className="cd-page-btn" disabled={page >= totalPages} onClick={() => onChange(page + 1)} aria-label="下一页">
        <ChevronRight size={14} />
      </button>
    </div>
  );
}

function buildPageList(page: number, totalPages: number): (number | "...")[] {
  if (totalPages <= 7) {
    return Array.from({ length: totalPages }, (_, i) => i + 1);
  }
  const pages: (number | "...")[] = [1];
  const start = Math.max(2, page - 1);
  const end = Math.min(totalPages - 1, page + 1);
  if (start > 2) pages.push("...");
  for (let i = start; i <= end; i++) pages.push(i);
  if (end < totalPages - 1) pages.push("...");
  pages.push(totalPages);
  return pages;
}

export function PageSizeSelect({ value, onChange }: { value: number; onChange: (next: number) => void }) {
  return (
    <label className="cd-page-size">
      <select value={value} onChange={(event) => onChange(Number(event.target.value))}>
        <option value={10}>10 条/页</option>
        <option value={20}>20 条/页</option>
        <option value={50}>50 条/页</option>
        <option value={100}>100 条/页</option>
      </select>
    </label>
  );
}
