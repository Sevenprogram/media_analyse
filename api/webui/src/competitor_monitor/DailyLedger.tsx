import React from "react";
import { ExternalLink } from "lucide-react";
import { Drawer } from "../components/ui";
import { useEndpoint } from "../lib/useEndpoint";
import { useInView } from "../lib/useInView";
import { getMockRanking, getMockRefreshDiagnostics, getMockSummary } from "./mock";
import type {
  RefreshDiagnostics,
  SampledPostRow,
  SampledPostsResponse,
  TodaySummary,
  MonitorType,
} from "./types";

export interface DailyLedgerProps {
  accountId: number;
  date: string;
  enabled?: boolean;
  useMock?: boolean;
  monitorType?: MonitorType;
}

interface MetricCard {
  label: string;
  value: string;
  note: string;
  trend?: string;
  trendTone?: "up" | "down" | "flat";
  action?: "sampled-posts";
}

export function DailyLedger({
  accountId,
  date,
  enabled = true,
  useMock = false,
  monitorType = "competitor",
}: DailyLedgerProps) {
  const ledgerBlock = useInView<HTMLElement>();
  const shouldLoad = enabled && ledgerBlock.inView;
  const [drawerOpen, setDrawerOpen] = React.useState(false);

  const summary = useEndpoint<TodaySummary | null>(
    `/api/competitors/${accountId}/today-summary?date=${date}`,
    null,
    { enabled: shouldLoad },
  );
  const diagnosticsQuery = useEndpoint<RefreshDiagnostics | null>(
    `/api/competitors/${accountId}/refresh-diagnostics?date=${date}`,
    null,
    { enabled: shouldLoad },
  );
  const sampledPostsQuery = useEndpoint<SampledPostsResponse | null>(
    `/api/competitors/${accountId}/sampled-posts?date=${date}&limit=100`,
    null,
    { enabled: shouldLoad && drawerOpen && !useMock },
  );

  const data = useMock ? summary.data ?? getMockSummary(accountId) : summary.data;
  const diagnostics = useMock
    ? diagnosticsQuery.data ?? getMockRefreshDiagnostics(accountId)
    : diagnosticsQuery.data;
  const sampledPosts = useMock ? getMockSampledPosts(accountId, date) : sampledPostsQuery.data;

  if (!ledgerBlock.inView) {
    return (
      <section className="cmw-ledger" ref={ledgerBlock.ref}>
        <div className="cmw-empty">Scroll to load snapshot metrics.</div>
      </section>
    );
  }

  if (summary.loading && !data) {
    return (
      <section className="cmw-ledger" ref={ledgerBlock.ref}>
        <div className="cmw-empty">Loading snapshot metrics...</div>
      </section>
    );
  }

  if (!data) {
    return (
      <section className="cmw-ledger" ref={ledgerBlock.ref}>
        <div className="cmw-empty">
          {summary.error || "No snapshot summary is available for the selected date."}
        </div>
      </section>
    );
  }

  const metrics = data.metrics;
  const eligiblePosts = diagnostics?.stats.eligible_posts ?? 0;
  const displayablePosts =
    diagnostics?.stats.displayable_posts ??
    diagnostics?.stats.author_verified_posts ??
    eligiblePosts;
  const invalidUrlPosts = diagnostics?.stats.invalid_url_posts ?? 0;
  const isCreatorMonitor = monitorType === "partner_creator";

  const cards: MetricCard[] = [
    {
      label: isCreatorMonitor ? "宣发内容数" : "采集帖子数",
      value: formatNum(metrics.deduped_post_count),
      note: "本次快照",
      action: "sampled-posts",
    },
    {
      label: "可展示帖子",
      value: formatNum(displayablePosts),
      note: "已核验展示",
      trend: invalidUrlPosts > 0 ? `待补链 ${invalidUrlPosts}` : undefined,
      trendTone: invalidUrlPosts > 0 ? "flat" : "flat",
    },
    {
      label: "互动增量",
      value: formatNum(metrics.interaction_delta),
      note: "较上一快照",
      trend: formatTrend(metrics.yesterday_diff_pct.interaction, "%"),
      trendTone: trendTone(metrics.yesterday_diff_pct.interaction),
    },
    {
      label: isCreatorMonitor ? "爆文命中" : "热点内容",
      value: formatNum(metrics.new_hot_post_count),
      note: "异常识别",
    },
    {
      label: isCreatorMonitor ? "新宣发贡献" : "新内容贡献",
      value: `${metrics.new_content_contribution_pct}%`,
      note: "互动占比",
    },
    {
      label: "老内容贡献",
      value: `${metrics.old_content_contribution_pct}%`,
      note: "互动占比",
    },
    {
      label: "点赞增量",
      value: formatNum(metrics.breakdown.like.value),
      note: "较上一快照",
      trend: formatTrend(metrics.breakdown.like.delta_pct, "%"),
      trendTone: trendTone(metrics.breakdown.like.delta_pct),
    },
    {
      label: "评论增量",
      value: formatNum(metrics.breakdown.comment.value),
      note: "较上一快照",
      trend: formatTrend(metrics.breakdown.comment.delta_pct, "%"),
      trendTone: trendTone(metrics.breakdown.comment.delta_pct),
    },
  ];

  const notices = buildLedgerNotices({
    snapshotDate: data.snapshot_date,
    stale: data.stale,
    sampledPosts: metrics.deduped_post_count,
    displayablePosts,
    interactionDelta: metrics.interaction_delta,
    unmatchedPosts: data.unmatched_post_count,
  });

  return (
    <section className="cmw-ledger" ref={ledgerBlock.ref}>
      <div className="cmw-ledger__metrics-grid">
        {cards.map((card) =>
          card.action === "sampled-posts" ? (
            <button
              key={card.label}
              type="button"
              className="cmw-ledger-card cmw-ledger-card--clickable"
              onClick={() => setDrawerOpen(true)}
              aria-label={`查看${card.label}明细`}
            >
              <span className="cmw-ledger-card__label">{card.label}</span>
              <strong className="cmw-ledger-card__value">{card.value}</strong>
              <div className="cmw-ledger-card__foot">
                <span>{card.note}</span>
                <em className="is-flat">查看明细</em>
              </div>
            </button>
          ) : (
            <article key={card.label} className="cmw-ledger-card">
              <span className="cmw-ledger-card__label">{card.label}</span>
              <strong className="cmw-ledger-card__value">{card.value}</strong>
              <div className="cmw-ledger-card__foot">
                <span>{card.note}</span>
                {card.trend ? (
                  <em className={`is-${card.trendTone || "flat"}`}>{card.trend}</em>
                ) : null}
              </div>
            </article>
          ),
        )}
      </div>

      {notices.length ? (
        <div className="cmw-ledger__notes">
          {notices.map((notice) => (
            <div key={notice.message} className={`cmw-ledger__note is-${notice.tone}`}>
              {notice.message}
            </div>
          ))}
        </div>
      ) : null}

      <Drawer
        open={drawerOpen}
        onOpenChange={setDrawerOpen}
        title="采样帖子明细"
        description="展示当前快照实际参与采样的帖子。"
      >
        <div className="cmw-sampled-posts">
          <div className="cmw-sampled-posts__summary">
            <strong>{sampledPosts?.total ?? metrics.deduped_post_count}</strong>
            <span>{sampledPosts?.timezone || "Asia/Shanghai"} / UTC+8</span>
          </div>

          <div className="cmw-sampled-posts__list">
            {sampledPostsQuery.loading && !sampledPosts ? (
              <div className="cmw-empty">Loading sampled posts...</div>
            ) : sampledPosts?.rows.length ? (
              sampledPosts.rows.map((row) => <SampledPostItem key={row.post_id} row={row} />)
            ) : (
              <div className="cmw-empty">
                {sampledPostsQuery.error || "当前快照没有可展示的采样帖子明细。"}
              </div>
            )}
          </div>
        </div>
      </Drawer>
    </section>
  );
}

function SampledPostItem({ row }: { row: SampledPostRow }) {
  const hasDirectLink = Boolean(row.platform_url && row.has_valid_url);
  const sourceUrl = hasDirectLink ? row.platform_url : row.source_url || row.platform_url || "";

  return (
    <article className="cmw-sampled-post">
      <div className="cmw-sampled-post__head">
        <div className="cmw-sampled-post__title-wrap">
          {sourceUrl ? (
            <a
              href={sourceUrl}
              target="_blank"
              rel="noreferrer"
              className={"cmw-sampled-post__title" + (hasDirectLink ? "" : " is-degraded")}
              title={hasDirectLink ? "打开原帖" : row.link_status}
            >
              {row.title || row.post_id}
            </a>
          ) : (
            <strong className="cmw-sampled-post__title">{row.title || row.post_id}</strong>
          )}
          <span className={`cmw-sampled-post__status ${row.has_valid_url ? "is-ok" : "is-warn"}`}>
            {row.link_status}
          </span>
        </div>
        {sourceUrl ? (
          <a
            href={sourceUrl}
            target="_blank"
            rel="noreferrer"
            className={"cmw-sampled-post__open" + (hasDirectLink ? "" : " is-degraded")}
            aria-label={hasDirectLink ? "打开原帖" : "尝试打开原始链接"}
            title={hasDirectLink ? "打开原帖" : row.link_status}
          >
            <ExternalLink size={14} />
          </a>
        ) : null}
      </div>

      <div className="cmw-sampled-post__meta">
        <span>{formatPublishTime(row.publish_time)}</span>
        <span>{contentTypeLabel(row.content_type)}</span>
        <span>{row.author_verified ? "作者已核验" : "作者待核验"}</span>
      </div>

      <div className="cmw-sampled-post__metrics">
        <span>总互动 {formatNum(row.interaction_total)}</span>
        <span>增量 {formatNum(row.interaction_delta)}</span>
        <span>赞 {formatNum(row.like_count)}</span>
        <span>评 {formatNum(row.comment_count)}</span>
        <span>藏 {formatNum(row.collect_count)}</span>
        <span>转 {formatNum(row.share_count)}</span>
      </div>
    </article>
  );
}

function buildLedgerNotices(input: {
  snapshotDate?: string | null;
  stale: boolean;
  sampledPosts: number;
  displayablePosts: number;
  interactionDelta: number;
  unmatchedPosts: number;
}) {
  const notices: Array<{ tone: "info" | "warn"; message: string }> = [];

  if (input.stale && input.snapshotDate) {
    notices.push({
      tone: "warn",
      message: `当前展示的是 ${input.snapshotDate} 的快照，不是所选日期当天的数据。`,
    });
  }

  if (input.sampledPosts > 0 && input.interactionDelta === 0) {
    notices.push({
      tone: "info",
      message: `本次快照已采集 ${input.sampledPosts} 条帖子，但相对上一快照没有新增公开互动，所以增量指标为 0。`,
    });
  }

  if (input.sampledPosts > 0 && input.displayablePosts === 0) {
    notices.push({
      tone: "warn",
      message: "当前快照没有可展示帖子，贡献榜和异常分析会为空。",
    });
  }

  if (input.unmatchedPosts > 0) {
    notices.push({
      tone: "warn",
      message: `${input.unmatchedPosts} 条帖子无法匹配发布时间，贡献占比按老内容处理。`,
    });
  }

  return notices;
}

function getMockSampledPosts(accountId: number, date: string): SampledPostsResponse {
  const ranking = getMockRanking(accountId);
  return {
    account_id: accountId,
    date,
    stale: false,
    timezone: "Asia/Shanghai",
    total: ranking.rows.length,
    rows: ranking.rows.map((row) => ({
      post_id: row.post_id,
      title: row.title,
      publish_time: row.publish_time,
      platform_url: row.platform_url,
      source_url: row.source_url || row.platform_url,
      content_type: row.content_type || "note",
      author_verified: true,
      has_valid_url: Boolean(row.platform_url),
      link_status: row.platform_url ? "链接可用" : "链接待补全",
      interaction_total: row.interaction_delta,
      interaction_delta: row.interaction_delta,
      like_count: row.interaction_delta,
      comment_count: 0,
      collect_count: 0,
      share_count: 0,
    })),
  };
}

function formatNum(value: number): string {
  if (value >= 10000) return `${(value / 10000).toFixed(1).replace(/\.0$/, "")}w`;
  if (value >= 1000) return `${(value / 1000).toFixed(1).replace(/\.0$/, "")}k`;
  return String(value);
}

function formatTrend(value: number, suffix = "") {
  if (!Number.isFinite(value) || value === 0) return `0${suffix}`;
  return `${value > 0 ? "↑" : "↓"} ${Math.abs(value)}${suffix}`;
}

function trendTone(value: number): "up" | "down" | "flat" {
  if (!Number.isFinite(value) || value === 0) return "flat";
  return value > 0 ? "up" : "down";
}

function formatPublishTime(value: string | null) {
  if (!value) return "--";
  let text = value.trim();
  if (!text) return "--";
  if (/^\d{4}-\d{2}-\d{2} \d{2}:/.test(text)) {
    text = text.replace(" ", "T");
  }
  if (!/[zZ]$|[+-]\d{2}:\d{2}$/.test(text)) {
    text = `${text}Z`;
  }
  const parsed = new Date(text);
  if (Number.isNaN(parsed.getTime())) return value;
  const parts = new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).formatToParts(parsed);
  const map = new Map(parts.map((part) => [part.type, part.value]));
  const month = map.get("month");
  const day = map.get("day");
  const hour = map.get("hour");
  const minute = map.get("minute");
  return month && day && hour && minute ? `${month}-${day} ${hour}:${minute}` : value;
}

function contentTypeLabel(value: string) {
  if (value === "video") return "视频";
  if (value === "note") return "图文";
  if (!value) return "未知";
  return value;
}
