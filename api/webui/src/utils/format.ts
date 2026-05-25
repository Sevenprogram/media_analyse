import type {
  DashboardConfidence,
  DashboardOpportunity,
  DashboardSampleStatus,
  OpportunityRiskTag,
} from "../types";

export const PLATFORM_LABELS: Record<string, string> = {
  xhs: "小红书",
  dy: "抖音",
  ks: "快手",
  bili: "B站",
  wb: "微博",
  weibo: "微博",
  tieba: "贴吧",
  zhihu: "知乎",
};

export const RISK_LABELS: Record<OpportunityRiskTag, string> = {
  small_sample_spike: "小样本突增",
  single_platform_signal: "平台单一",
  stale_data: "数据过旧",
  overheated_competition: "竞争过热",
  missing_execution_parameters: "执行参数缺失",
  high_cost: "成本较高",
};

export const SCORE_PARTS = [
  ["heat_growth", "热度增长"],
  ["sample_confidence", "样本可信度"],
  ["competition_gap", "竞争空档"],
  ["actionability", "可执行性"],
] as const;

export function formatNumber(value?: number) {
  return new Intl.NumberFormat("zh-CN").format(value || 0);
}

export function labelPlatform(platform?: string | null) {
  return PLATFORM_LABELS[platform || ""] || platform || "-";
}

export function labelOpportunityType(value: DashboardOpportunity["type"]) {
  return { creator: "达人", keyword: "关键词", competitor: "友商动作", content: "内容" }[value];
}

export function labelConfidence(value: DashboardConfidence) {
  return { low: "低", medium: "中", high: "高" }[value];
}

export function labelSampleStatus(value: DashboardSampleStatus) {
  return { insufficient: "样本不足", limited: "样本有限", enough: "样本充足" }[value];
}

export function formatSigned(value?: number) {
  const number = Number(value || 0);
  return `${number > 0 ? "+" : ""}${number.toFixed(1)}`;
}

export function parseDateTime(value?: string | null) {
  if (!value) return null;
  const raw = String(value).trim();
  if (!raw) return null;

  let normalized = raw;
  const hasTimezone = /(?:[zZ]|[+-]\d{2}:?\d{2})$/.test(raw);
  const hasTime = /\d{2}:\d{2}/.test(raw);

  // Back-end sqlite timestamps are often emitted without timezone.
  // Treat those values as UTC, then render in Asia/Shanghai.
  if (hasTime && !hasTimezone) {
    normalized = `${raw.replace(" ", "T")}Z`;
  }

  const parsed = new Date(normalized);
  if (!Number.isNaN(parsed.getTime())) {
    return parsed;
  }

  const fallback = new Date(raw);
  if (!Number.isNaN(fallback.getTime())) {
    return fallback;
  }

  return null;
}

export function formatDateTime(value?: string | null) {
  if (!value) return "-";
  const date = parseDateTime(value);
  if (!date) return String(value);
  return date.toLocaleString("zh-CN", {
    timeZone: "Asia/Shanghai",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

export function compactJson(value?: Record<string, unknown> | null) {
  if (!value || !Object.keys(value).length) return "-";
  return Object.entries(value)
    .slice(0, 4)
    .map(([key, item]) => `${key}: ${typeof item === "object" ? JSON.stringify(item).slice(0, 42) : String(item)}`)
    .join(" / ");
}
