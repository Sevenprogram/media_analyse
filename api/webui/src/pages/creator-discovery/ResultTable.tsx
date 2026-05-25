import React from "react";
import { ArrowUpDown, ArrowDown, ArrowUp, LayoutGrid, List, BadgeDollarSign, ShoppingBag, Video } from "lucide-react";
import {
  UnknownRecord,
  candidateMetric,
  creatorAvatarUrl,
  creatorDisplayName,
  creatorProfileId,
  creatorRowKey,
  formatCount,
  formatPercent,
  formatScore,
  labelPlatform,
  matchBandLabel,
  matchBandOf,
  num,
  text,
  tierOf,
} from "./utils";

export type SortKey = "match_score" | "follower_count" | "recent_post_count_30d" | "engagement_rate" | "viral_rate";
export type SortDir = "asc" | "desc";

export type SortState = { key: SortKey; dir: SortDir };

type Props = {
  rows: UnknownRecord[];
  selectedKey: string | null;
  selected: Set<string>;
  sort: SortState;
  onSort: (next: SortState) => void;
  onSelectRow: (row: UnknownRecord) => void;
  onToggleSelect: (row: UnknownRecord, next: boolean) => void;
  pageStart: number;
};

const COLUMNS: { key: SortKey | "rank" | "creator" | "platform" | "signals"; label: string; sortable: boolean; align?: "left" | "center" | "right"; width?: string }[] = [
  { key: "rank", label: "", sortable: false, width: "44px" },
  { key: "creator", label: "达人", sortable: false },
  { key: "platform", label: "平台", sortable: false, width: "92px" },
  { key: "match_score", label: "匹配分", sortable: true, align: "center", width: "120px" },
  { key: "follower_count", label: "粉丝数", sortable: true, align: "right", width: "100px" },
  { key: "recent_post_count_30d", label: "近30天发文", sortable: true, align: "right", width: "110px" },
  { key: "engagement_rate", label: "互动率", sortable: true, align: "right", width: "100px" },
  { key: "viral_rate", label: "爆款率", sortable: true, align: "right", width: "100px" },
  { key: "signals", label: "商业化信号", sortable: false, align: "center", width: "120px" },
];

function valueFor(row: UnknownRecord, key: SortKey): number {
  switch (key) {
    case "match_score":
      return num(row.match_score);
    case "follower_count":
      return num(candidateMetric(row, "follower_count"));
    case "recent_post_count_30d":
      return num(row.recent_post_count_30d);
    case "engagement_rate":
      return num(row.avg_engagement_rate || row.engagement_rate);
    case "viral_rate":
      return num(row.viral_post_rate || row.viral_rate);
  }
}

export function sortRows(rows: UnknownRecord[], sort: SortState): UnknownRecord[] {
  const sign = sort.dir === "asc" ? 1 : -1;
  return [...rows].sort((a, b) => (valueFor(a, sort.key) - valueFor(b, sort.key)) * sign);
}

function MatchScoreCircle({ score, band }: { score: number; band: ReturnType<typeof matchBandOf> }) {
  const radius = 22;
  const stroke = 4;
  const circumference = 2 * Math.PI * radius;
  const filled = Math.min(100, Math.max(0, score));
  const dashOffset = circumference * (1 - filled / 100);
  return (
    <div className={`cd-score-circle band-${band}`}>
      <svg width={56} height={56} viewBox="0 0 56 56">
        <circle cx={28} cy={28} r={radius} className="cd-score-track" strokeWidth={stroke} fill="none" />
        <circle
          cx={28}
          cy={28}
          r={radius}
          className="cd-score-fill"
          strokeWidth={stroke}
          fill="none"
          strokeDasharray={circumference}
          strokeDashoffset={dashOffset}
          strokeLinecap="round"
          transform="rotate(-90 28 28)"
        />
      </svg>
      <div className="cd-score-content">
        <strong>{score}</strong>
        <span>{matchBandLabel(band)}</span>
      </div>
    </div>
  );
}

function RankBadge({ rank }: { rank: number }) {
  if (rank <= 3) return <span className={`cd-rank cd-rank-top cd-rank-${rank}`}>{rank}</span>;
  return <span className="cd-rank">{rank}</span>;
}

function PlatformBadge({ platform }: { platform: string }) {
  return (
    <span className={`cd-platform-badge platform-${platform}`} title={labelPlatform(platform)}>
      <i className={`cd-platform-logo platform-${platform}`} aria-hidden />
    </span>
  );
}

function SortIcon({ active, dir }: { active: boolean; dir: SortDir }) {
  if (!active) return <ArrowUpDown size={12} className="cd-sort-icon" />;
  return dir === "desc" ? <ArrowDown size={12} className="cd-sort-icon active" /> : <ArrowUp size={12} className="cd-sort-icon active" />;
}

export function ResultTable({ rows, selectedKey, selected, sort, onSort, onSelectRow, onToggleSelect, pageStart }: Props) {
  const handleSort = (key: SortKey) => {
    if (sort.key === key) {
      onSort({ key, dir: sort.dir === "asc" ? "desc" : "asc" });
    } else {
      onSort({ key, dir: "desc" });
    }
  };

  return (
    <div className="cd-table-wrap">
      <table className="cd-table">
        <thead>
          <tr>
            <th className="cd-col-check">
              <input
                type="checkbox"
                aria-label="全选"
                checked={rows.length > 0 && rows.every((row) => selected.has(creatorRowKey(row)))}
                onChange={(event) => {
                  rows.forEach((row) => onToggleSelect(row, event.target.checked));
                }}
              />
            </th>
            {COLUMNS.map((col) => (
              <th
                key={col.key}
                style={{ width: col.width, textAlign: col.align || "left" }}
                className={col.sortable ? "cd-th-sortable" : ""}
                onClick={() => col.sortable && handleSort(col.key as SortKey)}
              >
                <span className="cd-th-inner">
                  {col.label}
                  {col.sortable && <SortIcon active={sort.key === col.key} dir={sort.dir} />}
                </span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => {
            const key = creatorRowKey(row);
            const score = formatScore(row.match_score);
            const band = matchBandOf(row);
            const tier = tierOf(row);
            const platform = text(row.platform, "");
            const name = creatorDisplayName(row);
            const profileId = creatorProfileId(row);
            const avatar = creatorAvatarUrl(row);
            const isSelectedRow = selectedKey === key;
            return (
              <tr
                key={key}
                className={`cd-row ${isSelectedRow ? "is-selected" : ""}`}
                onClick={() => onSelectRow(row)}
              >
                <td className="cd-col-check" onClick={(event) => event.stopPropagation()}>
                  <input
                    type="checkbox"
                    aria-label={`选择 ${name}`}
                    checked={selected.has(key)}
                    onChange={(event) => onToggleSelect(row, event.target.checked)}
                  />
                </td>
                <td>
                  <RankBadge rank={pageStart + index + 1} />
                </td>
                <td>
                  <div className="cd-creator-cell">
                    <div className="cd-avatar" aria-hidden>
                      {avatar ? <img src={avatar} alt="" /> : <span>{name.slice(0, 1)}</span>}
                    </div>
                    <div className="cd-creator-info">
                      <div className="cd-creator-name">
                        <strong>{name}</strong>
                        <span className="cd-tag-muted">{tier === "A" ? "新手养猫" : tier === "B" ? "高潜达人" : "拓展达人"}</span>
                      </div>
                      <div className="cd-creator-meta">
                        ID: {profileId || "-"}
                        {row.bio ? <span className="cd-creator-bio">{text(row.bio)}</span> : null}
                      </div>
                    </div>
                  </div>
                </td>
                <td>
                  <PlatformBadge platform={platform} />
                </td>
                <td style={{ textAlign: "center" }}>
                  <MatchScoreCircle score={score} band={band} />
                </td>
                <td style={{ textAlign: "right" }}>{formatCount(candidateMetric(row, "follower_count"))}</td>
                <td style={{ textAlign: "right" }}>{text(row.recent_post_count_30d, "-")}</td>
                <td style={{ textAlign: "right" }}>{formatPercent(row.avg_engagement_rate || row.engagement_rate)}</td>
                <td style={{ textAlign: "right" }}>{formatPercent(row.viral_post_rate || row.viral_rate)}</td>
                <td>
                  <div className="cd-signal-row">
                    <span className="cd-signal" title="报价"><BadgeDollarSign size={14} /></span>
                    <span className="cd-signal" title="带货"><ShoppingBag size={14} /></span>
                    <span className="cd-signal" title="直播"><Video size={14} /></span>
                    <span className="cd-signal-more">...</span>
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export function ViewModeToggle({ mode, onChange }: { mode: "table" | "card"; onChange: (next: "table" | "card") => void }) {
  return (
    <div className="cd-view-toggle">
      <button type="button" className={mode === "table" ? "is-active" : ""} onClick={() => onChange("table")} aria-label="表格视图">
        <List size={14} />
      </button>
      <button type="button" className={mode === "card" ? "is-active" : ""} onClick={() => onChange("card")} aria-label="卡片视图">
        <LayoutGrid size={14} />
      </button>
    </div>
  );
}
