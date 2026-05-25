import React from "react";
import type { CompositionData } from "./types";

export interface PublishHeatmapProps {
  data: CompositionData["publish_heatmap"] | null;
}

const BUCKET_LABELS: Record<string, string> = {
  late_night: "0-6",
  morning: "6-12",
  afternoon: "12-18",
  night: "18-24",
};

export function PublishHeatmap({ data }: PublishHeatmapProps) {
  if (!isPublishHeatmap(data)) {
    return (
      <section className="cmw-card cmw-heatmap">
        <header className="cmw-card__head">
          <h3>发布时间分布</h3>
          <span className="cmw-card__hint">热力图 · UTC+8</span>
        </header>
        <div className="cmw-empty">当前没有可用的 UTC+8 发布时间分布。</div>
      </section>
    );
  }

  const buckets = data.buckets;
  const days = data.days;
  const values = data.values;
  const max = Math.max(1, ...values.flat());

  return (
    <section className="cmw-card cmw-heatmap">
      <header className="cmw-card__head">
        <h3>发布时间分布</h3>
        <span className="cmw-card__hint">热力图 · UTC+8</span>
      </header>
      <div className="cmw-heatmap__grid" style={{ gridTemplateColumns: `48px repeat(${buckets.length}, 1fr)` }}>
        <span />
        {buckets.map((bucket) => (
          <span key={bucket} className="cmw-heatmap__col-label">
            {BUCKET_LABELS[bucket] || bucket}
          </span>
        ))}
        {days.map((day, dayIndex) => (
          <React.Fragment key={day}>
            <span className="cmw-heatmap__row-label">{formatWeekday(day)}</span>
            {buckets.map((bucket, bucketIndex) => {
              const value = values[dayIndex]?.[bucketIndex] || 0;
              return (
                <span
                  key={`${dayIndex}-${bucketIndex}`}
                  className={`cmw-heatmap__cell is-l${levelFor(value, max)}`}
                  title={`${day} · ${BUCKET_LABELS[bucket] || bucket} (UTC+8): ${value}`}
                />
              );
            })}
          </React.Fragment>
        ))}
      </div>
    </section>
  );
}

function levelFor(value: number, max: number): number {
  if (value === 0) return 0;
  const ratio = value / max;
  if (ratio < 0.2) return 1;
  if (ratio < 0.4) return 2;
  if (ratio < 0.6) return 3;
  if (ratio < 0.8) return 4;
  return 5;
}

function formatWeekday(day: string): string {
  const parsed = new Date(`${day}T12:00:00+08:00`);
  if (Number.isNaN(parsed.getTime())) return day.slice(5);
  return new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    weekday: "short",
  }).format(parsed);
}

function isPublishHeatmap(value: unknown): value is CompositionData["publish_heatmap"] {
  const heatmap = value as Partial<CompositionData["publish_heatmap"]> | null | undefined;
  return Boolean(
    heatmap &&
      Array.isArray(heatmap.buckets) &&
      Array.isArray(heatmap.days) &&
      Array.isArray(heatmap.values),
  );
}
