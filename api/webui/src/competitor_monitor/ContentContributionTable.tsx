import React from "react";
import { ChevronDown, ExternalLink } from "lucide-react";
import { useEndpoint } from "../lib/useEndpoint";
import { useInView } from "../lib/useInView";
import { getMockRanking, getMockRefreshDiagnostics } from "./mock";
import type {
  ContributionRanking,
  ContributionRow,
  ContributionScope,
  RefreshDiagnostics,
  MonitorType,
} from "./types";

export interface ContentContributionTableProps {
  accountId: number;
  date: string;
  enabled?: boolean;
  useMock?: boolean;
  monitorType?: MonitorType;
}

const SCOPES: Array<{ id: ContributionScope; label: string }> = [
  { id: "all", label: "全部内容" },
  { id: "new", label: "新内容" },
  { id: "old", label: "存量内容" },
];

export function ContentContributionTable({
  accountId,
  date,
  enabled = true,
  useMock = false,
  monitorType = "competitor",
}: ContentContributionTableProps) {
  const tableBlock = useInView<HTMLElement>();
  const shouldLoad = enabled && tableBlock.inView;
  const [scope, setScope] = React.useState<ContributionScope>("all");
  const rankingQuery = useEndpoint<ContributionRanking | null>(
    `/api/competitors/${accountId}/contribution-ranking?date=${date}&scope=${scope}&limit=20`,
    null,
    { enabled: shouldLoad },
  );
  const diagnosticsQuery = useEndpoint<RefreshDiagnostics | null>(
    `/api/competitors/${accountId}/refresh-diagnostics?date=${date}`,
    null,
    { enabled: shouldLoad },
  );
  const ranking = useMock ? rankingQuery.data ?? getMockRanking(accountId) : rankingQuery.data;
  const diagnostics = useMock
    ? diagnosticsQuery.data ?? getMockRefreshDiagnostics(accountId)
    : diagnosticsQuery.data;
  const rows = ranking?.rows || [];
  const isCreatorMonitor = monitorType === "partner_creator";
  const displayablePosts =
    diagnostics?.stats.displayable_posts ??
    diagnostics?.stats.author_verified_posts ??
    diagnostics?.stats.eligible_posts ??
    0;
  const degradedLinkPosts = diagnostics?.stats.degraded_link_posts ?? diagnostics?.stats.missing_token_posts ?? 0;
  const hasZeroDeltaRows = rows.length > 0 && rows.every((row) => row.interaction_delta <= 0);

  return (
    <section className="cmw-contrib" ref={tableBlock.ref}>
      <header className="cmw-contrib__head">
        <div>
          <h3>{isCreatorMonitor ? "宣发内容贡献排行" : "内容贡献排行"}</h3>
          <p className="cmw-contrib__sub">
            {isCreatorMonitor ? "宣发内容按互动增量排序" : "按互动增量排序"}
          </p>
        </div>
        <div className="cmw-contrib__toolbar">
          <div className="cmw-contrib__tabs">
            {SCOPES.map((scopeItem) => (
              <button
                key={scopeItem.id}
                type="button"
                className={"cmw-contrib__tab" + (scope === scopeItem.id ? " is-active" : "")}
                onClick={() => setScope(scopeItem.id)}
              >
                {scopeItem.label}
              </button>
            ))}
          </div>
          <button type="button" className="cmw-contrib__filter">
            全部内容
            <ChevronDown size={14} />
          </button>
        </div>
      </header>

      {tableBlock.inView ? (
        <>
          <section className="cmw-contrib__log-panel" aria-label="刷新日志">
            <div className="cmw-contrib__log-head">
              <div className="cmw-contrib__log-title">
                <strong>刷新日志</strong>
                <span>{diagnostics?.timezone || "Asia/Shanghai"} / UTC+8</span>
              </div>
              <div className="cmw-contrib__log-stats">
                <span>候选 {diagnostics?.stats.raw_matched_posts ?? 0}</span>
                <span>核验 {diagnostics?.stats.author_verified_posts ?? 0}</span>
                <span>可展示 {displayablePosts}</span>
                <span>直达 {diagnostics?.stats.eligible_posts ?? 0}</span>
                {degradedLinkPosts > 0 ? <span>可尝试 {degradedLinkPosts}</span> : null}
              </div>
            </div>
            {hasZeroDeltaRows ? (
              <div className="cmw-contrib__zero-note">
                当前快照相对上一快照没有新增公开互动，所以新增互动和增量贡献暂为 0。
              </div>
            ) : null}
            <div className="cmw-contrib__log-list">
              {diagnosticsQuery.loading && !diagnostics ? (
                <div className="cmw-contrib__log-empty">正在加载刷新日志...</div>
              ) : diagnostics?.entries.length ? (
                diagnostics.entries.map((entry) => (
                  <article
                    key={entry.id}
                    className={"cmw-contrib__log-item is-" + (entry.level || "info")}
                  >
                    <time>{formatShanghaiTime(entry.timestamp)}</time>
                    <p>{entry.message}</p>
                  </article>
                ))
              ) : (
                <div className="cmw-contrib__log-empty">
                  {diagnosticsQuery.error || "暂无刷新日志。"}
                </div>
              )}
            </div>
          </section>

          <div className="cmw-contrib__table-wrap">
            <table className="cmw-contrib__table">
              <thead>
                <tr>
                  <th>排名</th>
                  <th>内容</th>
                  <th>发布时间</th>
                  <th>新增互动</th>
                  <th>增量贡献</th>
                  <th>标签</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {rankingQuery.loading && !ranking ? (
                  <tr>
                    <td className="cmw-contrib__empty-row" colSpan={7}>
                      正在加载内容贡献排行...
                    </td>
                  </tr>
                ) : rows.length ? (
                  rows.map((row) => (
                    <ContributionTableRow key={row.post_id || row.rank} row={row} />
                  ))
                ) : (
                  <tr>
                    <td className="cmw-contrib__empty-row" colSpan={7}>
                      {rankingQuery.error || "暂无可核验的帖子链接，请查看上方日志定位过滤原因。"}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </>
      ) : (
        <div className="cmw-empty">滚动到此处后加载内容贡献排行。</div>
      )}
    </section>
  );
}

function ContributionTableRow({ row }: { row: ContributionRow }) {
  const sourceUrl = row.platform_url || row.source_url || "";
  const hasDirectLink = Boolean(row.platform_url);
  const hasSourceLink = Boolean(sourceUrl);
  const linkStatus = row.link_status || (hasDirectLink ? "链接可用" : hasSourceLink ? "可尝试打开原始链接" : "链接待补全");

  return (
    <tr>
      <td className={"cmw-contrib__rank" + (row.rank <= 3 ? ` cmw-contrib__rank--${row.rank}` : "")}>
        {row.rank}
      </td>
      <td>
        <div className="cmw-contrib__content">
          <span className="cmw-contrib__thumb">
            {row.thumbnail_url ? (
              <img src={row.thumbnail_url} alt="" loading="lazy" />
            ) : (
              (row.title || "?").slice(0, 1)
            )}
          </span>
          <div className="cmw-contrib__content-meta">
            {hasSourceLink ? (
              <a
                href={sourceUrl}
                target="_blank"
                rel="noreferrer"
                className={hasDirectLink ? undefined : "is-degraded"}
                title={hasDirectLink ? undefined : linkStatus}
              >
                {row.title || row.post_id}
              </a>
            ) : (
              <strong>{row.title || row.post_id}</strong>
            )}
            <span>
              {contentTypeLabel(row.content_type)} {row.duration_sec ? `· ${row.duration_sec}s` : ""}
            </span>
            {!hasDirectLink ? (
              <em className="cmw-contrib__link-status is-warn">{linkStatus}</em>
            ) : null}
          </div>
        </div>
      </td>
      <td>{formatPublishTime(row.publish_time)}</td>
      <td>
        <div className="cmw-contrib__delta">
          <strong>{formatNum(row.interaction_delta)}</strong>
          <span className={"cmw-contrib__delta-pct " + deltaTone(row.interaction_delta, row.delta_pct)}>
            {formatDeltaPct(row.interaction_delta, row.delta_pct)}
          </span>
          {row.interaction_delta <= 0 && typeof row.interaction_total === "number" && row.interaction_total > 0 ? (
            <em>总互动 {formatNum(row.interaction_total)}</em>
          ) : null}
        </div>
      </td>
      <td>{row.contribution_share}%</td>
      <td>
        <div className="cmw-contrib__tags">
          {row.tags.slice(0, 3).map((tag) => (
            <span key={tag} className="cmw-contrib__tag">
              {tag}
            </span>
          ))}
        </div>
      </td>
      <td>
        <div className="cmw-contrib__ops">
          {hasSourceLink ? (
            <a
              href={sourceUrl}
              target="_blank"
              rel="noreferrer"
              className={"cmw-contrib__op-primary" + (hasDirectLink ? "" : " is-degraded")}
              title={hasDirectLink ? "打开原帖" : linkStatus}
            >
              {hasDirectLink ? "打开原帖" : "尝试打开"}
              <ExternalLink size={12} />
            </a>
          ) : (
            <button type="button" className="cmw-contrib__op-primary" disabled title={linkStatus}>
              待补链
            </button>
          )}
        </div>
      </td>
    </tr>
  );
}

function contentTypeLabel(value?: string | null): string {
  const normalized = (value || "").trim().toLowerCase();
  if (!normalized) return "内容";
  if (["note", "image", "图文"].includes(normalized)) return "图文";
  if (["video", "short_video", "短视频"].includes(normalized)) return "视频";
  return value || "内容";
}

function formatNum(value: number): string {
  if (value >= 10000) return (value / 10000).toFixed(1).replace(/\.0$/, "") + "w";
  if (value >= 1000) return (value / 1000).toFixed(1).replace(/\.0$/, "") + "k";
  return String(value);
}

function formatDeltaPct(delta: number, value: number): string {
  if (!Number.isFinite(delta) || delta <= 0) return "无新增";
  if (!Number.isFinite(value) || value === 0) return "持平";
  return `${value > 0 ? "+" : ""}${value}%`;
}

function deltaTone(delta: number, value: number): "is-up" | "is-down" | "is-flat" {
  if (!Number.isFinite(delta) || delta <= 0 || !Number.isFinite(value) || value === 0) return "is-flat";
  return value > 0 ? "is-up" : "is-down";
}

function formatPublishTime(value: string | null): string {
  if (!value) return "--";
  const date = parseUtcLikeDate(value);
  if (!date) return value;
  const parts = new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).formatToParts(date);
  const byType = new Map(parts.map((part) => [part.type, part.value]));
  const mm = byType.get("month");
  const dd = byType.get("day");
  const hh = byType.get("hour");
  const mi = byType.get("minute");
  if (!mm || !dd || !hh || !mi) return value;
  return `${mm}-${dd} ${hh}:${mi}`;
}

function formatShanghaiTime(value: string | null): string {
  if (!value) return "--";
  const parsed = parseUtcLikeDate(value);
  if (!parsed) return value;
  const parts = new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).formatToParts(parsed);
  const byType = new Map(parts.map((part) => [part.type, part.value]));
  const mm = byType.get("month");
  const dd = byType.get("day");
  const hh = byType.get("hour");
  const mi = byType.get("minute");
  if (!mm || !dd || !hh || !mi) return value;
  return `${mm}-${dd} ${hh}:${mi}`;
}

function parseUtcLikeDate(value: string): Date | null {
  let normalized = value.trim();
  if (!normalized) return null;
  if (/^\d{4}-\d{2}-\d{2} \d{2}:/.test(normalized)) {
    normalized = normalized.replace(" ", "T");
  }
  if (!/[zZ]$|[+-]\d{2}:\d{2}$/.test(normalized)) {
    normalized = `${normalized}Z`;
  }
  const parsed = new Date(normalized);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}
