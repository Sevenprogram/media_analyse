import React from "react";
import { isCompositionData, type CompositionData } from "./types";

const CompositionWordCloud = React.lazy(() =>
  import("./CompositionWordCloud").then((module) => ({
    default: module.CompositionWordCloud,
  })),
);

const CompositionPieChart = React.lazy(() =>
  import("./CompositionPieChart").then((module) => ({
    default: module.CompositionPieChart,
  })),
);

export interface CompositionBreakdownProps {
  data: CompositionData | null;
  loading?: boolean;
}

export function CompositionBreakdown({ data, loading = false }: CompositionBreakdownProps) {
  const source = isCompositionData(data) ? data : null;
  const keywords = source?.keywords || [];
  const contentTypes = (source?.content_types || [])
    .filter((item) => item.value > 0)
    .map((item) => ({
      ...item,
      name: normalizeContentType(item.name),
    }));

  return (
    <section className="cmw-card cmw-composition">
      <header className="cmw-card__head">
        <h3>内容组成分析</h3>
      </header>

      {!source ? (
        <div className="cmw-composition__empty">
          {loading ? "正在生成内容组成快照..." : "当前没有可用的内容组成快照。"}
        </div>
      ) : (
        <div className="cmw-composition__grid">
          <div className="cmw-composition__cell">
            <span className="cmw-composition__label">关键词分布</span>
            {keywords.length ? (
              <React.Suspense fallback={<div className="cmw-empty">Loading word cloud...</div>}>
                <CompositionWordCloud words={keywords} />
              </React.Suspense>
            ) : (
              <div className="cmw-composition__empty">
                当前没有可用的关键词分布。若要显示关键词云，需要为监控对象提供关键词或自动主题抽取结果。
              </div>
            )}
          </div>

          <div className="cmw-composition__cell">
            <span className="cmw-composition__label">内容类型分布</span>
            {contentTypes.length ? (
              <React.Suspense fallback={<div className="cmw-empty">Loading chart...</div>}>
                <CompositionPieChart contentTypes={contentTypes} />
              </React.Suspense>
            ) : (
              <div className="cmw-composition__empty">当前没有识别到可用的内容类型分布。</div>
            )}
          </div>
        </div>
      )}
    </section>
  );
}

function normalizeContentType(value: string) {
  if (value === "unknown") return "未识别";
  if (value === "video") return "视频";
  if (value === "note") return "图文";
  return value || "未识别";
}
