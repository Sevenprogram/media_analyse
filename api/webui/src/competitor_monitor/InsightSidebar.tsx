import React from "react";
import { Crosshair, FileText, Radar, Star } from "lucide-react";
import { useEndpoint } from "../lib/useEndpoint";
import { useInView } from "../lib/useInView";
import {
  isCompositionData,
  type AnomalyFeed as AnomalyFeedData,
  type CompositionData,
  type RefreshDiagnostics,
  type TodaySummary,
} from "./types";
import { PublishHeatmap } from "./PublishHeatmap";
import { AnomalyFeed } from "./AnomalyFeed";
import {
  getMockAnomalies,
  getMockComposition,
  getMockRefreshDiagnostics,
  getMockSummary,
} from "./mock";

const CompositionBreakdown = React.lazy(() =>
  import("./CompositionBreakdown").then((module) => ({
    default: module.CompositionBreakdown,
  })),
);

export interface InsightSidebarProps {
  accountId: number;
  date: string;
  useMock?: boolean;
}

export function InsightSidebar({ accountId, date, useMock = false }: InsightSidebarProps) {
  const compositionBlock = useInView<HTMLDivElement>();
  const heatmapBlock = useInView<HTMLDivElement>();
  const anomalyBlock = useInView<HTMLElement>();
  const compositionEnabled = compositionBlock.inView || heatmapBlock.inView || anomalyBlock.inView;
  const composition = useEndpoint<CompositionData | null>(
    `/api/competitors/${accountId}/composition?date=${date}`,
    null,
    { enabled: compositionEnabled },
  );
  const anomalies = useEndpoint<AnomalyFeedData | null>(
    `/api/competitors/${accountId}/anomalies?date=${date}&limit=20`,
    null,
    { enabled: anomalyBlock.inView },
  );
  const summary = useEndpoint<TodaySummary | null>(
    `/api/competitors/${accountId}/today-summary?date=${date}`,
    null,
    { enabled: compositionEnabled },
  );
  const diagnostics = useEndpoint<RefreshDiagnostics | null>(
    `/api/competitors/${accountId}/refresh-diagnostics?date=${date}`,
    null,
    { enabled: compositionEnabled },
  );

  const compositionData = useMock
    ? (isCompositionData(composition.data) ? composition.data : getMockComposition(accountId))
    : (isCompositionData(composition.data) ? composition.data : null);
  const anomalyItems = useMock ? anomalies.data?.items || getMockAnomalies(accountId).items : anomalies.data?.items || [];
  const summaryData = useMock ? summary.data ?? getMockSummary(accountId) : summary.data;
  const diagnosticsData = useMock
    ? diagnostics.data ?? getMockRefreshDiagnostics(accountId)
    : diagnostics.data;

  const insightNotes = buildInsightNotes({
    composition: compositionData,
    summary: summaryData,
    diagnostics: diagnosticsData,
    anomalyCount: anomalyItems.length,
  });
  const anomalyEmptyMessage = buildAnomalyEmptyMessage(summaryData, diagnosticsData);

  return (
    <div className="cmw-insight">
      <section className="cmw-card cmw-insight-status">
        <header className="cmw-card__head">
          <h3>当前快照状态</h3>
        </header>
        {insightNotes.length ? (
          <ul className="cmw-insight-status__list">
            {insightNotes.map((note) => (
              <li key={note}>{note}</li>
            ))}
          </ul>
        ) : (
          <div className="cmw-empty">当前没有可解释的快照状态。</div>
        )}
      </section>

      <div ref={compositionBlock.ref}>
        {compositionBlock.inView ? (
          <React.Suspense fallback={<div className="cmw-card cmw-empty">Loading composition...</div>}>
            <CompositionBreakdown data={compositionData} loading={composition.loading} />
          </React.Suspense>
        ) : (
          <div className="cmw-card cmw-empty">Scroll to load composition chart.</div>
        )}
      </div>
      <div ref={heatmapBlock.ref}>
        {heatmapBlock.inView ? (
          <PublishHeatmap data={compositionData?.publish_heatmap || null} />
        ) : (
          <div className="cmw-card cmw-empty">Scroll to load publish heatmap.</div>
        )}
      </div>
      <section className="cmw-card cmw-actions">
        <header className="cmw-card__head">
          <h3>推荐动作</h3>
        </header>
        <div className="cmw-actions__grid">
          <button type="button" className="cmw-actions__item">
            <Star size={15} />
            关注热点内容
          </button>
          <button type="button" className="cmw-actions__item">
            <Radar size={15} />
            跟踪主题变化
          </button>
          <button type="button" className="cmw-actions__item">
            <Crosshair size={15} />
            对比内容策略
          </button>
          <button type="button" className="cmw-actions__item">
            <FileText size={15} />
            导出监控报告
          </button>
        </div>
        <button type="button" className="cmw-actions__sync">
          同步监控数据
        </button>
      </section>
      <section ref={anomalyBlock.ref}>
        {anomalyBlock.inView ? (
          <AnomalyFeed items={anomalyItems} loading={anomalies.loading} emptyMessage={anomalyEmptyMessage} />
        ) : (
          <div className="cmw-card cmw-empty">Scroll to load anomaly feed.</div>
        )}
      </section>
    </div>
  );
}

function buildInsightNotes(input: {
  composition: CompositionData | null;
  summary: TodaySummary | null;
  diagnostics: RefreshDiagnostics | null;
  anomalyCount: number;
}) {
  const notes: string[] = [];
  if (input.summary) {
    notes.push(`本次快照采集到 ${input.summary.metrics.deduped_post_count} 条帖子。`);
    if (input.summary.metrics.interaction_delta === 0) {
      notes.push("相对上一快照没有新增公开互动，所以增量指标和异常提醒会偏少。");
    }
  }
  if (input.diagnostics) {
    const displayablePosts =
      input.diagnostics.stats.displayable_posts ??
      input.diagnostics.stats.author_verified_posts ??
      input.diagnostics.stats.eligible_posts;
    if (displayablePosts === 0) {
      notes.push("当前没有已核验帖子进入贡献榜，内容贡献表会为空。");
    }
    if (input.diagnostics.stats.missing_token_posts > 0) {
      notes.push(
        `${input.diagnostics.stats.missing_token_posts} 条帖子缺少 xsec_token，已降级展示，补全前不可点击。`,
      );
    }
  }
  if (input.composition) {
    if ((input.composition.keywords || []).length === 0) {
      notes.push("当前没有提取到关键词分布，因此关键词云为空。");
    }
    const onlyUnknownType =
      input.composition.content_types.length > 0 &&
      input.composition.content_types.every((item) => item.name === "unknown");
    if (onlyUnknownType) {
      notes.push("当前帖子内容类型尚未识别，内容类型分布会统一显示为“未识别”。");
    }
  }
  if (input.anomalyCount === 0) {
    notes.push("当前快照没有触发异常，这通常意味着没有明显互动突增或热点内容。");
  }
  return notes;
}

function buildAnomalyEmptyMessage(summary: TodaySummary | null, diagnostics: RefreshDiagnostics | null) {
  if (diagnostics?.stats.eligible_posts === 0 && diagnostics?.stats.missing_token_posts) {
    return "当前没有异常项。帖子缺少 xsec_token 时会降级展示，但热点跳转链接需要等待补全。";
  }
  if (summary?.metrics.interaction_delta === 0) {
    return "当前没有异常项。相对上一快照没有新增公开互动。";
  }
  return "当前快照没有触发异常。";
}
