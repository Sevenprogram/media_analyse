import React from "react";
import { Flame, Sparkles, Star } from "lucide-react";
import type { AnomalyItem } from "./types";

export interface AnomalyFeedProps {
  items: AnomalyItem[];
  loading?: boolean;
  emptyMessage?: string;
}

const ICON_MAP: Record<string, React.ReactNode> = {
  interaction_spike: <Flame size={14} />,
  new_hot_post: <Star size={14} />,
  keyword_shift: <Sparkles size={14} />,
};

const TITLE_MAP: Record<string, string> = {
  interaction_spike: "互动突增",
  new_hot_post: "新热点内容",
  keyword_shift: "主题变化",
};

export function AnomalyFeed({
  items,
  loading = false,
  emptyMessage = "当前快照没有触发异常。",
}: AnomalyFeedProps) {
  return (
    <section className="cmw-card cmw-anomaly">
      <header className="cmw-card__head">
        <h3>异常监控</h3>
        <button type="button" className="cmw-anomaly__view-all">
          查看全部 ({items.length})
        </button>
      </header>
      <div className="cmw-anomaly__list">
        {loading && items.length === 0 ? (
          <div className="cmw-anomaly__empty">Loading anomalies...</div>
        ) : items.length === 0 ? (
          <div className="cmw-anomaly__empty">{emptyMessage}</div>
        ) : (
          items.map((item) => (
            <article key={item.id} className={"cmw-anomaly-card cmw-anomaly-card--" + (item.severity || "medium")}>
              <header className="cmw-anomaly-card__head">
                <span className="cmw-anomaly-card__icon">{ICON_MAP[item.type] || <Sparkles size={14} />}</span>
                <strong>{TITLE_MAP[item.type] || item.title || item.type}</strong>
                <span className={"cmw-anomaly-card__sev cmw-anomaly-card__sev--" + (item.severity || "medium")}>
                  {item.severity === "high" ? "高" : item.severity === "medium" ? "中" : item.severity}
                </span>
                {item.timestamp && <span className="cmw-anomaly-card__time">{formatTime(item.timestamp)}</span>}
              </header>
              <p className="cmw-anomaly-card__reason">{item.reason}</p>
              {item.post_ref && item.post_ref.title && (
                <span className="cmw-anomaly-card__ref">相关内容：{item.post_ref.title}</span>
              )}
            </article>
          ))
        )}
      </div>
    </section>
  );
}

function formatTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  const hh = String(date.getHours()).padStart(2, "0");
  const mm = String(date.getMinutes()).padStart(2, "0");
  return `${hh}:${mm}`;
}
