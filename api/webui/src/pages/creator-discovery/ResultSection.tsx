import React from "react";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "../../components/ui";
import { UnknownRecord, tierOf } from "./utils";
import { ResultTable, SortState, ViewModeToggle, sortRows } from "./ResultTable";
import { Pagination, PageSizeSelect } from "./Pagination";

export type TabKey = "all" | "A" | "B" | "C";

const TAB_DEFS: { key: TabKey; label: string }[] = [
  { key: "all", label: "推荐" },
  { key: "A", label: "A类 精准匹配" },
  { key: "B", label: "B类 高潜达人" },
  { key: "C", label: "C类 拓展达人" },
];

function filterByTab(rows: UnknownRecord[], tab: TabKey): UnknownRecord[] {
  if (tab === "all") return rows;
  return rows.filter((row) => tierOf(row) === tab);
}

export function ResultSection({
  rows,
  selectedKey,
  selected,
  onSelectRow,
  onToggleSelect,
}: {
  rows: UnknownRecord[];
  selectedKey: string | null;
  selected: Set<string>;
  onSelectRow: (row: UnknownRecord) => void;
  onToggleSelect: (row: UnknownRecord, next: boolean) => void;
}) {
  const [tab, setTab] = React.useState<TabKey>("all");
  const [sort, setSort] = React.useState<SortState>({ key: "match_score", dir: "desc" });
  const [page, setPage] = React.useState(1);
  const [pageSize, setPageSize] = React.useState(20);
  const [viewMode, setViewMode] = React.useState<"table" | "card">("table");

  const tabCounts = React.useMemo(() => {
    const base: Record<TabKey, number> = { all: rows.length, A: 0, B: 0, C: 0 };
    rows.forEach((row) => {
      base[tierOf(row)] += 1;
    });
    return base;
  }, [rows]);

  React.useEffect(() => {
    setPage(1);
  }, [tab, rows.length, sort.key, sort.dir]);

  const filtered = React.useMemo(() => filterByTab(rows, tab), [rows, tab]);
  const sorted = React.useMemo(() => sortRows(filtered, sort), [filtered, sort]);
  const total = sorted.length;
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const safePage = Math.min(page, totalPages);
  const pageStart = (safePage - 1) * pageSize;
  const pageRows = sorted.slice(pageStart, pageStart + pageSize);

  return (
    <div className="cd-result-section">
      <Tabs value={tab} onValueChange={(value) => setTab(value as TabKey)}>
        <div className="cd-tabs-bar">
          <TabsList className="cd-tabs-list">
            {TAB_DEFS.map((item) => (
              <TabsTrigger key={item.key} value={item.key} className="cd-tab-trigger">
                {item.label}
                <span className="cd-tab-count">({tabCounts[item.key]})</span>
              </TabsTrigger>
            ))}
          </TabsList>
          <div className="cd-tabs-tools">
            <select className="cd-tools-select" value="default" onChange={() => undefined} aria-label="排序">
              <option value="default">默认排序</option>
            </select>
            <ViewModeToggle mode={viewMode} onChange={setViewMode} />
          </div>
        </div>

        {TAB_DEFS.map((item) => (
          <TabsContent key={item.key} value={item.key} className="cd-tab-panel">
            {pageRows.length ? (
              viewMode === "table" ? (
                <ResultTable
                  rows={pageRows}
                  selectedKey={selectedKey}
                  selected={selected}
                  sort={sort}
                  onSort={setSort}
                  onSelectRow={onSelectRow}
                  onToggleSelect={onToggleSelect}
                  pageStart={pageStart}
                />
              ) : (
                <div className="cd-card-grid">
                  {pageRows.map((row, index) => (
                    <CompactCard
                      key={`${pageStart + index}`}
                      row={row}
                      rank={pageStart + index + 1}
                      isSelected={selectedKey === `${row.platform}:${row.creator_id || row.account_id}`}
                      onSelect={() => onSelectRow(row)}
                    />
                  ))}
                </div>
              )
            ) : (
              <div className="cd-empty">暂无结果，可调整筛选条件或切换 Tab。</div>
            )}
          </TabsContent>
        ))}
      </Tabs>

      <div className="cd-pagination-bar">
        <span className="cd-pagination-total">共 {total} 条结果</span>
        <Pagination page={safePage} totalPages={totalPages} onChange={setPage} />
        <PageSizeSelect value={pageSize} onChange={(next) => { setPageSize(next); setPage(1); }} />
      </div>
    </div>
  );
}

function CompactCard({ row, rank, isSelected, onSelect }: { row: UnknownRecord; rank: number; isSelected: boolean; onSelect: () => void }) {
  return (
    <button type="button" className={`cd-card-cell ${isSelected ? "is-selected" : ""}`} onClick={onSelect}>
      <span className="cd-card-rank">#{rank}</span>
      <strong>{String(row.display_name || row.nickname || row.creator_id || "-")}</strong>
      <span className="cd-card-meta">ID: {String(row.creator_id || "-")}</span>
    </button>
  );
}
