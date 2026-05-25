import React from "react";
import { useEndpoint } from "../lib/useEndpoint";
import { useInView } from "../lib/useInView";
import { getMockComposition, getMockRefreshDiagnostics, getMockSummary } from "./mock";
import { isCompositionData, type CompositionData, type RefreshDiagnostics, type TodaySummary } from "./types";

export interface MonitoringPulseProps {
  accountId: number;
  date: string;
  useMock?: boolean;
}

export function MonitoringPulse({ accountId, date, useMock = false }: MonitoringPulseProps) {
  const pulseBlock = useInView<HTMLElement>();
  const enabled = pulseBlock.inView;
  const compositionQuery = useEndpoint<CompositionData | null>(
    `/api/competitors/${accountId}/composition?date=${date}`,
    null,
    { enabled },
  );
  const summaryQuery = useEndpoint<TodaySummary | null>(
    `/api/competitors/${accountId}/today-summary?date=${date}`,
    null,
    { enabled },
  );
  const diagnosticsQuery = useEndpoint<RefreshDiagnostics | null>(
    `/api/competitors/${accountId}/refresh-diagnostics?date=${date}`,
    null,
    { enabled },
  );

  const composition = useMock
    ? (isCompositionData(compositionQuery.data) ? compositionQuery.data : getMockComposition(accountId))
    : (isCompositionData(compositionQuery.data) ? compositionQuery.data : null);
  const summary = useMock ? summaryQuery.data ?? getMockSummary(accountId) : summaryQuery.data;
  const diagnostics = useMock
    ? diagnosticsQuery.data ?? getMockRefreshDiagnostics(accountId)
    : diagnosticsQuery.data;

  if (!pulseBlock.inView) {
    return (
      <section className="cmw-pulse" ref={pulseBlock.ref}>
        <div className="cmw-empty">Scroll to load monitoring pulse.</div>
      </section>
    );
  }

  if ((compositionQuery.loading || summaryQuery.loading) && (!composition || !summary)) {
    return (
      <section className="cmw-pulse" ref={pulseBlock.ref}>
        <div className="cmw-empty">Loading monitoring pulse...</div>
      </section>
    );
  }

  if (!composition || !summary) {
    return (
      <section className="cmw-pulse" ref={pulseBlock.ref}>
        <div className="cmw-empty">
          {compositionQuery.error || summaryQuery.error || "No monitoring pulse snapshot is available."}
        </div>
      </section>
    );
  }

  const days = composition.publish_heatmap.days;
  const values = composition.publish_heatmap.values;
  const series = days.map((day, index) => ({
    day: day.slice(5),
    value: (values[index] || []).reduce((sum, item) => sum + item, 0),
  }));
  const hasActivity = series.some((item) => item.value > 0);
  const max = Math.max(1, ...series.map((item) => item.value));
  const points = series
    .map((item, index) => {
      const x = series.length === 1 ? 0 : (index / (series.length - 1)) * 100;
      const y = 100 - (item.value / max) * 100;
      return `${x},${y}`;
    })
    .join(" ");
  const displayablePosts =
    diagnostics?.stats.displayable_posts ??
    diagnostics?.stats.author_verified_posts ??
    diagnostics?.stats.eligible_posts ??
    0;
  const currentStats = [
    { label: "快照帖子", value: formatCount(summary.metrics.deduped_post_count) },
    { label: "可展示帖子", value: formatCount(displayablePosts) },
    { label: "互动增量", value: formatCount(summary.metrics.interaction_delta) },
    { label: "热点内容", value: formatCount(summary.metrics.new_hot_post_count) },
  ];

  return (
    <section className="cmw-pulse" ref={pulseBlock.ref}>
      <header className="cmw-pulse__head">
        <div>
          <h3>近 7 日发帖总量趋势</h3>
          <p>曲线展示近 7 天每日发帖总量，右侧数值使用当前快照摘要。</p>
        </div>
        <div className="cmw-pulse__stats">
          {currentStats.map((item) => (
            <span key={item.label}>
              <strong>{item.value}</strong> {item.label}
            </span>
          ))}
        </div>
      </header>

      {hasActivity ? (
        <div className="cmw-pulse__chart">
          <svg viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
            <polyline className="cmw-pulse__line-shadow" points={points} />
            <polygon className="cmw-pulse__area" points={`0,100 ${points} 100,100`} />
            <polyline className="cmw-pulse__line" points={points} />
          </svg>
          <div className="cmw-pulse__labels">
            {series.map((item) => (
              <span key={item.day}>{item.day}</span>
            ))}
          </div>
        </div>
      ) : (
        <div className="cmw-pulse__empty">近 7 天没有可用的发帖总量分布。</div>
      )}
    </section>
  );
}

function formatCount(value: number): string {
  if (value >= 10000) return (value / 10000).toFixed(1).replace(/\.0$/, "") + "w";
  if (value >= 1000) return (value / 1000).toFixed(1).replace(/\.0$/, "") + "k";
  return String(value);
}
