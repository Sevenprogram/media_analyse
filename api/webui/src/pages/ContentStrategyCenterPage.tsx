import React from "react";
import {
  AlertTriangle,
  ArrowRight,
  Bot,
  CheckCircle2,
  ChevronRight,
  ClipboardList,
  Copy,
  Download,
  Eye,
  FileSearch,
  FileText,
  Flame,
  LayoutTemplate,
  Loader2,
  Plus,
  RefreshCw,
  Search,
  ShieldAlert,
  Sparkles,
  TrendingDown,
  TrendingUp,
  Users,
  X,
} from "lucide-react";
import { Button, Card, Drawer, Select } from "../components/ui";
import type { GrowthProjectCollectionProgress, GrowthProjectDetail } from "../types";
import { api } from "../utils/api";
import { formatDateTime } from "../utils/format";

type FilterOption = { value: string; label: string };

type DistributionItem = {
  label: string;
  value: number;
  count?: number;
  color: string;
};

type MetricKey = "high_opportunity" | "high_interaction" | "low_competition" | "trending_up";

type MetricItem = {
  key: MetricKey;
  label: string;
  value: string;
  hint: string;
  accent: "danger" | "orange" | "green" | "teal" | string;
};

type KeywordTrend = {
  rank: number;
  keyword: string;
  platform?: string | null;
  platform_label?: string;
  heat: string;
  score: number;
  direction: "up" | "down";
  points: number[];
  evidence?: Record<string, unknown>;
};

type FrameworkRow = {
  title: string;
  tags: string[];
  posts: number;
  interactions: string;
  leads: number;
  samples?: Array<Record<string, unknown>>;
};

type SuggestionRow = {
  id: string;
  title: string;
  audience: string;
  chance: number;
  risk: "低风险" | "中风险" | "高风险";
  direction: string;
  platform?: string | null;
  keywords?: string[];
  outline?: string[];
  reason?: string;
  evidence?: Record<string, unknown>;
  samples?: Array<Record<string, unknown>>;
  source?: "ai" | "rules" | string;
  risk_notes?: string[];
};

type CompetitorSample = {
  platform: string;
  platform_key?: string | null;
  badge: string;
  title: string;
  interaction: string;
  likes: string;
  comments: string;
  favorites: string;
  url?: string | null;
  publish_time?: string | null;
};

type RiskRow = {
  title: string;
  detail: string;
  level: "高风险" | "中风险";
  count: number;
};

type WeeklyMixRow = {
  label: string;
  percent: number;
  pieces: number;
  exposure: string;
  leads: number;
  color: string;
};

type TrafficRow = {
  platform: string;
  platform_key?: string | null;
  percent: number;
  traffic: string;
  sample_count: number;
  color: string;
};

type EvidenceItem = {
  type: string;
  title: string;
  platform?: string | null;
  reason?: string;
  payload?: Record<string, unknown>;
};

type StrategySectionKey = "hero" | "keyword_trends" | "frameworks" | "suggestions" | "risks" | "weekly_mix";
type StrategyAiSectionKey = StrategySectionKey | "overview";

type AiSectionStatus = {
  status?: string;
  source?: string;
  generated_at?: string | null;
  error?: string | null;
};

type ContentStrategySummary = {
  generated_at: string;
  filters: Record<string, unknown>;
  hero: {
    headline: string;
    sample_summary: string;
    confidence: "low" | "medium" | "high" | string;
    updated_at?: string | null;
    evidence_count: number;
  };
  ai_status: {
    enabled: boolean;
    source: string;
    run?: Record<string, unknown> | null;
    status?: string;
    generated_at?: string | null;
    provider?: { name?: string; model?: string } | null;
    error?: string | null;
    strategy_summary_source?: string;
    section_statuses?: Partial<Record<StrategyAiSectionKey, AiSectionStatus>>;
  };
  strategy_note?: string;
  section_sources?: Partial<Record<StrategySectionKey, string>>;
  metrics: MetricItem[];
  pain_distribution: DistributionItem[];
  keyword_trends: KeywordTrend[];
  frameworks: FrameworkRow[];
  suggestions: SuggestionRow[];
  competitor_samples: CompetitorSample[];
  risks: RiskRow[];
  weekly_mix: WeeklyMixRow[];
  traffic_share: {
    estimated_exposure: string;
    estimated_leads: number;
    estimated_orders: number;
    rows: TrafficRow[];
  };
  evidence_pack: {
    items: EvidenceItem[];
    risks: RiskRow[];
    total: number;
  };
  diagnostics: Array<{ code: string; title: string; body: string; action?: string }>;
  project_context?: {
    project_id: string;
    project_record_id: number;
    project_name: string;
    platforms: string[];
    keywords: string[];
    primary_goal?: string | null;
    comment_collection_enabled?: boolean;
    refresh_cadence: string;
    custom_interval_value?: number | null;
    custom_interval_unit?: "hours" | "days" | null;
  };
  source_tracker?: {
    id: number;
    name: string;
    description?: string | null;
    platforms: string[];
    included_keywords: string[];
    excluded_keywords: string[];
    enabled: boolean;
    latest_headline?: string | null;
    latest_status?: string | null;
    sample_quality_score?: number | null;
    trend_strength_score?: number | null;
    updated_at?: string | null;
  };
  refresh_status?: {
    cadence: {
      value: string;
      interval_minutes?: number | null;
      custom_interval_value?: number | null;
      custom_interval_unit?: "hours" | "days" | null;
    };
    scheduled_refresh: {
      status: string;
      trigger?: string;
      last_started_at?: string | null;
      last_completed_at?: string | null;
      last_collection_completed_at?: string | null;
      last_collection_job_id?: number | null;
      last_error?: string | null;
    };
    manual_analysis: {
      last_refreshed_at?: string | null;
    };
    ai_insights: {
      mode: string;
      status: string;
      generated_at?: string | null;
      provider?: { name?: string; model?: string } | null;
      executive_summary?: string;
      strategy_summary_source?: string;
      section_statuses?: Partial<Record<StrategyAiSectionKey, AiSectionStatus>>;
      error?: string | null;
    };
    updated_at?: string | null;
  };
};

type StrategyDraft = {
  title: string;
  summary: string;
  sections: Array<{ heading: string; items: string[] }>;
  body: string;
  checklist: string[];
  risk_notes: string[];
  source_payload?: Record<string, unknown>;
};

type DraftResponse = {
  status: "completed" | "fallback";
  mode: "ai" | "rules";
  provider?: { name?: string; model?: string } | null;
  error?: string;
  draft: StrategyDraft;
};

type EvidenceDrawerState = {
  title: string;
  items: EvidenceItem[];
  raw?: unknown;
};

type TopicDrawerState = {
  metricKey: MetricKey;
  title: string;
  description: string;
  items: SuggestionRow[];
  emptyLabel: string;
};

type ContentStrategyCenterPageProps = {
  selectedProjectId: string | null;
  selectedProjectDetail: GrowthProjectDetail | null;
  selectedProjectProgress?: GrowthProjectCollectionProgress | null;
  sourceTrackerId?: number | null;
  onClearSourceTracker?: () => void;
  onOpenSourceTracker?: (trackerId: number) => void;
};

const PLATFORM_OPTIONS: FilterOption[] = [
  { value: "all", label: "全部平台" },
  { value: "dy", label: "抖音" },
  { value: "xhs", label: "小红书" },
  { value: "bili", label: "B站" },
  { value: "wb", label: "微博" },
];

const RANGE_OPTIONS: FilterOption[] = [
  { value: "7d", label: "近7天" },
  { value: "30d", label: "近30天" },
  { value: "90d", label: "近90天" },
];

const GOAL_OPTIONS: FilterOption[] = [
  { value: "conversion", label: "获客转化" },
  { value: "engagement", label: "种草互动" },
  { value: "awareness", label: "品牌声量" },
];

const AUDIENCE_OPTIONS: FilterOption[] = [
  { value: "all", label: "泛目标人群" },
  { value: "moms", label: "宝妈 / 家长" },
  { value: "pet", label: "新手养宠" },
  { value: "ingredient", label: "成分党" },
];

const STAGE_OPTIONS: FilterOption[] = [
  { value: "boost", label: "高潜筛选" },
  { value: "launch", label: "冷启动" },
  { value: "review", label: "复盘优化" },
];

const metricIcons: Record<string, React.ReactNode> = {
  danger: <Flame size={16} />,
  orange: <Sparkles size={16} />,
  green: <Users size={16} />,
  teal: <TrendingUp size={16} />,
};

function Sparkline({ points, color }: { points: number[]; color: string }) {
  const safePoints = points.length >= 2 ? points : [0, 0];
  const max = Math.max(...safePoints);
  const min = Math.min(...safePoints);
  const span = Math.max(1, max - min);
  const path = safePoints
    .map((point, index) => {
      const x = (index / (safePoints.length - 1)) * 100;
      const y = 22 - ((point - min) / span) * 18;
      return `${index === 0 ? "M" : "L"} ${x} ${y}`;
    })
    .join(" ");

  return (
    <svg viewBox="0 0 100 24" className="ks-sparkline" aria-hidden="true">
      <path d={path} fill="none" stroke={color} strokeWidth="2.1" strokeLinecap="round" />
    </svg>
  );
}

function Donut({
  value,
  label,
  segments,
}: {
  value: string;
  label: string;
  segments: DistributionItem[];
}) {
  const total = segments.reduce((sum, item) => sum + Number(item.value || 0), 0);
  const conic = total > 0
    ? segments
        .map((segment, index) => {
          const start = segments.slice(0, index).reduce((sum, item) => sum + Number(item.value || 0), 0);
          const end = start + Number(segment.value || 0);
          return `${segment.color} ${start}% ${end}%`;
        })
        .join(", ")
    : "#e7efec 0% 100%";

  return (
    <div className="ks-donut-wrap">
      <div className="ks-donut" style={{ background: `conic-gradient(${conic})` }}>
        <div className="ks-donut__center">
          <span>{label}</span>
          <strong>{value}</strong>
        </div>
      </div>
    </div>
  );
}

function riskClass(level: SuggestionRow["risk"] | RiskRow["level"]) {
  if (level === "低风险") return "is-safe";
  if (level === "中风险") return "is-warn";
  return "is-danger";
}

function formatDate(value?: string | null) {
  if (!value) return "暂无更新";
  const formatted = formatDateTime(value);
  if (formatted === "-" || formatted === value) return value;
  return `${formatted} UTC+8`;
}

function platformLabel(value?: string | null) {
  return PLATFORM_OPTIONS.find((item) => item.value === value)?.label || value || "全部平台";
}

function formatCadenceLabel(
  value?: string | null,
  customValue?: number | null,
  customUnit?: "hours" | "days" | null,
) {
  if (value === "daily") return "每天 1 次";
  if (value === "three_days") return "每 3 天 1 次";
  if (value === "weekly") return "每周 1 次";
  if (value === "custom_hours") return `每 ${Math.max(1, customValue || 1)} 小时 1 次`;
  if (value === "custom_days") return `每 ${Math.max(1, customValue || 1)} 天 1 次`;
  if (customValue && customUnit) {
    return `每 ${Math.max(1, customValue)} ${customUnit === "hours" ? "小时" : "天"} 1 次`;
  }
  return "已关闭";
}

function scheduledRefreshStatusLabel(status?: string | null) {
  switch (status) {
    case "collecting":
      return "采集中";
    case "ai_analyzing":
      return "AI 分析中";
    case "completed":
      return "已完成";
    case "partial":
      return "AI 部分完成";
    case "fallback":
      return "规则托底";
    case "failed":
      return "刷新失败";
    case "paused":
      return "已暂停";
    default:
      return "空闲";
  }
}

function scheduledRefreshStatusClass(status?: string | null) {
  switch (status) {
    case "collecting":
    case "ai_analyzing":
    case "partial":
      return "is-warn";
    case "completed":
    case "fallback":
      return "is-safe";
    case "failed":
      return "is-danger";
    default:
      return "";
  }
}

function buildSummaryMarkdown(summary: ContentStrategySummary) {
  const lines = [
    `# 内容策略中心报告`,
    ``,
    `生成时间：${formatDate(summary.generated_at)}`,
    ...(summary.project_context?.project_name ? [`项目：${summary.project_context.project_name}`] : []),
    ...(summary.source_tracker?.name ? [`来源追踪器：${summary.source_tracker.name}`] : []),
    `策略判断：${summary.hero.headline}`,
    `样本摘要：${summary.hero.sample_summary}`,
    ...(summary.strategy_note ? [`AI 策略说明：${summary.strategy_note}`, ""] : []),
    ``,
    `## 重点选题`,
    ...summary.suggestions.slice(0, 8).map((item, index) => `${index + 1}. ${item.title}｜机会值 ${item.chance}｜${item.risk}`),
    ``,
    `## 关键词趋势`,
    ...summary.keyword_trends.slice(0, 8).map((item) => `- ${item.keyword}：${item.score}（${item.direction === "up" ? "上升" : "下降"}）`),
    ``,
    `## 风险提醒`,
    ...summary.risks.map((item) => `- ${item.level}：${item.title} - ${item.detail}`),
  ];
  return lines.join("\n");
}

function sectionSource(summary: ContentStrategySummary | null, key: StrategySectionKey) {
  return summary?.section_sources?.[key] === "ai" ? "ai" : "rules";
}

function sourceBadgeClass(source: string) {
  return source === "ai" ? "is-safe" : "is-warn";
}

function sourceBadgeLabel(source: string) {
  return source === "ai" ? "AI 分析" : "规则托底";
}

const AI_SECTION_LABELS: Record<StrategyAiSectionKey, string> = {
  overview: "总览",
  hero: "头部",
  keyword_trends: "关键词",
  frameworks: "框架",
  suggestions: "选题",
  risks: "风险",
  weekly_mix: "周计划",
};

function aiModeLabel(summary: ContentStrategySummary | null) {
  const status = summary?.ai_status;
  if (status?.status === "partial" || status?.strategy_summary_source === "partial_ai") return "AI 部分增强";
  if (!status?.enabled) return "规则分析";
  if (status.status === "fallback" || status.source === "project_ai_fallback") return "规则托底";
  if (status.status === "failed") return "AI 失败";
  if (status.strategy_summary_source === "ai") return "AI 主导";
  if (status.source === "latest_ai_topic_ideas") return "AI 选题";
  return "AI 增强";
}

function aiModeClass(summary: ContentStrategySummary | null) {
  const status = summary?.ai_status;
  if (status?.status === "partial" || status?.strategy_summary_source === "partial_ai") return "is-warn";
  if (!status?.enabled) return "is-warn";
  if (status.status === "fallback" || status.source === "project_ai_fallback") return "is-warn";
  if (status.status === "failed") return "is-danger";
  if (status.strategy_summary_source === "ai") return "is-safe";
  return "is-warn";
}

function aiProviderLabel(summary: ContentStrategySummary | null) {
  const provider = summary?.ai_status.provider;
  if (provider?.name || provider?.model) {
    return [provider.name, provider.model].filter(Boolean).join(" / ");
  }
  if (summary?.ai_status.source === "deterministic_rules") return "未启用 AI";
  return "等待 AI 结果";
}

function aiStatusDetail(summary: ContentStrategySummary | null) {
  const status = summary?.ai_status;
  if (status?.status === "partial" || status?.strategy_summary_source === "partial_ai") {
    return status.error
      ? `AI 已完成部分模块，未完成模块使用规则托底：${formatAiError(status.error)}`
      : "AI 已完成部分模块，其余模块使用规则托底";
  }
  if (!status) return "等待策略数据";
  if (status.error) return status.error;
  if (status.strategy_summary_source === "ai") return `AI 生成于 ${formatDate(status.generated_at)}`;
  if (status.status === "fallback" || status.source === "project_ai_fallback") return "AI 不可用，当前展示规则托底";
  if (status.source === "latest_ai_topic_ideas") return "使用最近一次 AI 选题结果";
  return "使用规则引擎计算";
}

function aiSectionStatusItems(summary: ContentStrategySummary | null) {
  const statuses = summary?.ai_status.section_statuses || summary?.refresh_status?.ai_insights.section_statuses || {};
  return (Object.keys(AI_SECTION_LABELS) as StrategyAiSectionKey[])
    .filter((key) => statuses[key])
    .map((key) => ({ key, label: AI_SECTION_LABELS[key], status: statuses[key] as AiSectionStatus }));
}

function aiSectionStatusLabel(status?: AiSectionStatus) {
  if (status?.status === "completed") return "AI";
  if (status?.status === "fallback") return "规则";
  return "等待";
}

function aiSectionStatusClass(status?: AiSectionStatus) {
  if (status?.status === "completed") return "is-safe";
  if (status?.status === "fallback") return "is-warn";
  return "is-muted";
}

function formatAiError(value: string) {
  const text = String(value || "").trim();
  return text.length > 140 ? `${text.slice(0, 140)}...` : text;
}

function buildSuggestionEvidenceItem(item: SuggestionRow): EvidenceItem {
  return {
    type: "suggestion",
    title: item.title,
    platform: item.platform,
    reason: item.reason || item.direction,
    payload: item as unknown as Record<string, unknown>,
  };
}

function buildTrendSuggestion(trend: KeywordTrend, audience: string): SuggestionRow {
  return {
    id: `metric-trend:${trend.platform || "all"}:${trend.keyword}`,
    title: `${trend.keyword}可以怎么讲？先做一轮低成本测试`,
    audience,
    chance: trend.score,
    risk: trend.score >= 70 ? "低风险" : "中风险",
    direction: "趋势上升",
    platform: trend.platform,
    keywords: [trend.keyword],
    outline: ["开头给出判断标准", "中段拆解当前趋势信号", "结尾安排评论区验证动作"],
    reason: `${platformLabel(trend.platform)} 关键词机会值 ${trend.score}`,
    evidence: trend.evidence,
    source: "rules",
    risk_notes: [],
  };
}

function dedupeSuggestions(items: SuggestionRow[]) {
  const seen = new Set<string>();
  return items.filter((item) => {
    const key = `${item.platform || "all"}:${item.title}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function metricItemLimit(metric: MetricItem, fallback = 8) {
  const parsed = Number.parseInt(metric.value, 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

function isKeywordTrendSuggestion(item: SuggestionRow) {
  return item.id.startsWith("keyword-trend:");
}

function buildMetricTopicDrawer(metric: MetricItem, summary: ContentStrategySummary): TopicDrawerState {
  const suggestions = summary.suggestions || [];
  const audienceLabel = AUDIENCE_OPTIONS.find((item) => item.value === summary.filters.audience)?.label || "泛目标人群";
  const upTrends = summary.keyword_trends.filter((item) => item.direction === "up");
  const upKeywords = new Set(upTrends.map((item) => item.keyword));
  const trendTopicRows = upTrends.map((item) => buildTrendSuggestion(item, audienceLabel));
  const byChance = [...suggestions].sort((left, right) => right.chance - left.chance);

  if (metric.key === "high_opportunity") {
    const items = byChance
      .filter((item) => item.chance >= 75 && !isKeywordTrendSuggestion(item))
      .slice(0, metricItemLimit(metric));
    return {
      metricKey: metric.key,
      title: "高机会选题",
      description: "机会值超过 75，适合优先进入执行评估。",
      items,
      emptyLabel: "当前没有机会值超过 75 的候选选题。",
    };
  }

  if (metric.key === "high_interaction") {
    const items = dedupeSuggestions([
      ...suggestions.filter((item) => {
        const text = [item.direction, item.reason, item.title].filter(Boolean).join(" ");
        return item.chance >= 70 || item.source === "ai" || /互动|评论|收藏|热度|爆文|讨论/.test(text);
      }),
      ...trendTopicRows.slice(0, 4),
    ]).slice(0, 8);
    return {
      metricKey: metric.key,
      title: "高互动选题",
      description: "优先看互动潜力更强、适合放大评论和收藏的题目。",
      items,
      emptyLabel: "当前没有明显的高互动候选选题。",
    };
  }

  if (metric.key === "low_competition") {
    return {
      metricKey: metric.key,
      title: "低竞争选题",
      description: "供给缺口更明显，适合低成本测试差异化角度。",
      items: byChance.filter((item) => riskClass(item.risk) !== "is-danger").slice(0, 8),
      emptyLabel: "当前没有可优先测试的低竞争候选选题。",
    };
  }

  return {
    metricKey: metric.key,
    title: "趋势上升选题",
    description: "关键词处于上升阶段，适合先做小样本验证。",
    items: dedupeSuggestions([
      ...suggestions.filter((item) => item.keywords?.some((keyword) => upKeywords.has(keyword))),
      ...trendTopicRows,
    ]).slice(0, 8),
    emptyLabel: "当前没有可用的趋势上升选题。",
  };
}

export function ContentStrategyCenterPage({
  selectedProjectId,
  selectedProjectDetail,
  selectedProjectProgress,
  sourceTrackerId = null,
  onClearSourceTracker,
  onOpenSourceTracker,
}: ContentStrategyCenterPageProps) {
  const [platform, setPlatform] = React.useState("all");
  const [range, setRange] = React.useState("30d");
  const [goal, setGoal] = React.useState("conversion");
  const [audience, setAudience] = React.useState("all");
  const [stage, setStage] = React.useState("boost");
  const [advancedOpen, setAdvancedOpen] = React.useState(false);
  const [strategyNote, setStrategyNote] = React.useState("");
  const [summary, setSummary] = React.useState<ContentStrategySummary | null>(null);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [notice, setNotice] = React.useState<string | null>(null);
  const [evidenceDrawer, setEvidenceDrawer] = React.useState<EvidenceDrawerState | null>(null);
  const [topicDrawer, setTopicDrawer] = React.useState<TopicDrawerState | null>(null);
  const [draftOpen, setDraftOpen] = React.useState(false);
  const [draftLoading, setDraftLoading] = React.useState(false);
  const [draftResponse, setDraftResponse] = React.useState<DraftResponse | null>(null);
  const [draftError, setDraftError] = React.useState<string | null>(null);
  const [drafts, setDrafts] = React.useState<SuggestionRow[]>([]);

  const filters = React.useMemo(
    () => ({ platform, range, goal, audience, stage, note: strategyNote }),
    [platform, range, goal, audience, stage, strategyNote],
  );
  const aiRefreshRunning = summary?.refresh_status?.scheduled_refresh?.status === "ai_analyzing";

  const loadSummary = React.useCallback(async () => {
    if (!selectedProjectId) {
      setSummary(null);
      setLoading(false);
      setError(null);
      return;
    }
    const params = new URLSearchParams({
      project_id: selectedProjectId,
      range,
      goal,
      audience,
      stage,
    });
    if (platform !== "all") {
      params.set("platform", platform);
    }
    if (sourceTrackerId) {
      params.set("tracker_id", String(sourceTrackerId));
    }
    setLoading(true);
    setError(null);
    try {
      const data = await api<ContentStrategySummary>(`/api/reports/content-strategy/summary?${params.toString()}`);
      setSummary(data);
      setNotice(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, [goal, audience, platform, range, selectedProjectId, sourceTrackerId, stage]);

  const refreshSummary = React.useCallback(async () => {
    if (!selectedProjectId) return;
    const params = new URLSearchParams({
      project_id: selectedProjectId,
      range,
      goal,
      audience,
      stage,
    });
    if (platform !== "all") {
      params.set("platform", platform);
    }
    if (sourceTrackerId) {
      params.set("tracker_id", String(sourceTrackerId));
    }
    setLoading(true);
    setError(null);
    try {
      const data = await api<ContentStrategySummary>(`/api/reports/content-strategy/summary/refresh?${params.toString()}`, {
        method: "POST",
      });
      setSummary(data);
      if (data.refresh_status?.scheduled_refresh.status === "ai_analyzing") {
        setNotice("AI 分段分析已启动，页面会自动刷新结果。");
      } else if (data.ai_status.strategy_summary_source === "partial_ai") {
        setNotice("AI 已完成部分模块，未完成模块已使用规则托底。");
      } else if (data.ai_status.strategy_summary_source === "ai") {
        setNotice(`AI 策略刷新完成：${aiProviderLabel(data)}。`);
      } else if (data.ai_status.error) {
        setNotice("AI 刷新失败，已保留规则托底策略。");
      } else {
        setNotice("已基于当前数据库完成一次实时重算。");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, [goal, audience, platform, range, selectedProjectId, sourceTrackerId, stage]);

  React.useEffect(() => {
    if (!selectedProjectId) {
      setSummary(null);
      setError(null);
      setNotice(null);
      return;
    }
    void loadSummary();
  }, [loadSummary, selectedProjectId]);

  React.useEffect(() => {
    if (!selectedProjectId || !aiRefreshRunning) return;
    const timer = window.setInterval(() => {
      void loadSummary();
    }, 2500);
    return () => window.clearInterval(timer);
  }, [aiRefreshRunning, loadSummary, selectedProjectId]);

  React.useEffect(() => {
    if (!selectedProjectDetail) return;
    const currentPlatforms = selectedProjectDetail.settings.platforms || [];
    if (platform !== "all" && currentPlatforms.length > 0 && !currentPlatforms.includes(platform)) {
      setPlatform("all");
    }
  }, [platform, selectedProjectDetail]);

  React.useEffect(() => {
    setSummary(null);
    setError(null);
    setDrafts([]);
    setNotice(null);
    setEvidenceDrawer(null);
    setTopicDrawer(null);
    setDraftOpen(false);
    setDraftResponse(null);
    setDraftError(null);
  }, [selectedProjectId, sourceTrackerId]);

  function openEvidence(title: string, items: EvidenceItem[], raw?: unknown) {
    setEvidenceDrawer({ title, items, raw });
  }

  function openMetricTopics(metric: MetricItem) {
    if (!summary) return;
    setTopicDrawer(buildMetricTopicDrawer(metric, summary));
  }

  function openTopicEvidence(item: SuggestionRow) {
    setTopicDrawer(null);
    openEvidence(item.title, [buildSuggestionEvidenceItem(item)], item);
  }

  function addSuggestionDraft(item: SuggestionRow) {
    setDrafts((current) => {
      if (current.some((draft) => draft.id === item.id)) return current;
      return [item, ...current].slice(0, 12);
    });
    setNotice(`已加入草稿：${item.title}`);
  }

  async function generateDraft(kind: ContentStrategyDraftRequestKind, payload: Record<string, unknown>) {
    setDraftOpen(true);
    setDraftLoading(true);
    setDraftError(null);
    setDraftResponse(null);
    try {
      const result = await api<DraftResponse>("/api/reports/content-strategy/draft", {
        method: "POST",
        body: JSON.stringify({
          kind,
          payload,
          filters,
          context: {
            hero: summary?.hero,
            top_suggestions: summary?.suggestions.slice(0, 6),
            keyword_trends: summary?.keyword_trends.slice(0, 6),
            weekly_mix: summary?.weekly_mix,
            risks: summary?.risks,
            source_tracker: summary?.source_tracker,
            note: strategyNote,
          },
        }),
      });
      setDraftResponse(result);
      if (result.status === "fallback" && result.error) {
        setDraftError(result.error);
      }
    } catch (err) {
      setDraftError(err instanceof Error ? err.message : String(err));
    } finally {
      setDraftLoading(false);
    }
  }

  function exportReport() {
    if (!summary) return;
    const blob = new Blob([buildSummaryMarkdown(summary)], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `content-strategy-${new Date().toISOString().slice(0, 10)}.md`;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  function copyDraft() {
    if (!draftResponse?.draft) return;
    const draft = draftResponse.draft;
    const text = [
      draft.title,
      draft.summary,
      draft.body,
      ...draft.sections.map((section) => `${section.heading}\n${section.items.map((item) => `- ${item}`).join("\n")}`),
      draft.checklist.length ? `执行清单\n${draft.checklist.map((item) => `- ${item}`).join("\n")}` : "",
    ].filter(Boolean).join("\n\n");
    void navigator.clipboard?.writeText(text);
    setNotice("草稿已复制到剪贴板");
  }

  const evidenceItems = summary?.evidence_pack.items || [];
  const metrics = summary?.metrics || [];
  const painTotal = summary?.pain_distribution.reduce((sum, item) => sum + Number(item.count || 0), 0) || 0;
  const trendColor = (direction: "up" | "down") => (direction === "up" ? "#0f8f85" : "#e35d5d");
  const projectContext = summary?.project_context;
  const sourceTracker = summary?.source_tracker;
  const refreshStatus = summary?.refresh_status;
  const fallbackKeywords = (selectedProjectDetail?.keywords || [])
    .filter((item) => item.status !== "excluded")
    .map((item) => item.keyword)
    .slice(0, 6);
  const noProjectSelected = !selectedProjectId;
  const displayProjectName = projectContext?.project_name || selectedProjectDetail?.project.name || "未选择项目";
  const strategyTitle = noProjectSelected ? "内容策略中心" : `内容策略中心 · ${displayProjectName}`;
  const cadenceLabel = formatCadenceLabel(
    refreshStatus?.cadence?.value || projectContext?.refresh_cadence || selectedProjectDetail?.settings.refresh_cadence,
    refreshStatus?.cadence?.custom_interval_value
    ?? projectContext?.custom_interval_value
    ?? selectedProjectDetail?.settings.custom_interval_value,
    refreshStatus?.cadence?.custom_interval_unit
    ?? projectContext?.custom_interval_unit
    ?? selectedProjectDetail?.settings.custom_interval_unit,
  );
  const collectionBusy = selectedProjectProgress?.status === "running" || selectedProjectProgress?.status === "queued";
  const effectiveScheduledStatus = collectionBusy
    ? "collecting"
    : refreshStatus?.scheduled_refresh?.status || "idle";
  const effectiveKeywords = (projectContext?.keywords?.length ? projectContext.keywords : fallbackKeywords).slice(0, 6);
  const aiSummarySource = sectionSource(summary, "hero");
  const aiModeText = aiModeLabel(summary);
  const aiProviderText = aiProviderLabel(summary);
  const aiDetailText = aiStatusDetail(summary);
  const aiError = summary?.ai_status.error;
  const showAiFallbackWarning = Boolean(
    aiError &&
      summary?.ai_status.status !== "partial" &&
      summary?.ai_status.strategy_summary_source !== "partial_ai",
  );
  const aiSectionItems = aiSectionStatusItems(summary);

  return (
    <section className="ks-page">
      <div className="ks-hero">
        <div className="ks-hero__main">
          <span className="ks-kicker">Strategy Center</span>
          <h1>{strategyTitle}</h1>
          <p>{summary?.hero.headline || "正在读取策略样本..."}</p>
        </div>
        <div className="ks-hero__aside">
          <div className="ks-hero__meta">
            <span>更新时间：{formatDate(summary?.hero.updated_at)}</span>
            <span>证据 {summary?.hero.evidence_count ?? 0} 条</span>
            <span className={`ks-badge ${aiModeClass(summary)}`}>{aiModeText}</span>
            {sourceTracker && <span>来源追踪器：{sourceTracker.name}</span>}
            <span className={`ks-badge ${sourceBadgeClass(aiSummarySource)}`}>{sourceBadgeLabel(aiSummarySource)}</span>
          </div>
          <div className="ks-hero__actions">
            <Button variant="ghost" onClick={refreshSummary} disabled={loading || aiRefreshRunning || noProjectSelected}>
              {loading || aiRefreshRunning ? <Loader2 size={15} className="spin" /> : <RefreshCw size={15} />}
              {loading || aiRefreshRunning ? "AI 分段分析中" : "AI 刷新策略"}
            </Button>
            <Button
              variant="ghost"
              onClick={() => generateDraft("evidence_summary", { title: "内容策略摘要", evidence: evidenceItems.slice(0, 12) })}
              disabled={!summary || draftLoading || noProjectSelected}
            >
              <Bot size={15} />
              AI 助手
            </Button>
            <Button variant="primary" onClick={exportReport} disabled={!summary || noProjectSelected}>
              <Download size={15} />
              导出报告
            </Button>
          </div>
        </div>
      </div>

      <Card className="ks-filter-card ks-project-strip">
        <div className="ks-project-strip__head">
          <div>
            <strong>{displayProjectName}</strong>
            <p>{effectiveKeywords.length ? `关键词：${effectiveKeywords.join(" / ")}` : "当前项目还没有可用关键词。"}</p>
          </div>
          <span className={`ks-badge ${scheduledRefreshStatusClass(effectiveScheduledStatus)}`}>
            {scheduledRefreshStatusLabel(effectiveScheduledStatus)}
          </span>
        </div>
        <div className="ks-project-strip__meta">
          <div>
            <span>刷新频率</span>
            <strong>{cadenceLabel}</strong>
          </div>
          <div>
            <span>上次定时刷新</span>
            <strong>{formatDate(refreshStatus?.scheduled_refresh?.last_completed_at)}</strong>
          </div>
          <div>
            <span>上次手动分析</span>
            <strong>{formatDate(refreshStatus?.manual_analysis?.last_refreshed_at)}</strong>
          </div>
          <div>
            <span>AI 状态</span>
            <strong>{aiModeText}</strong>
          </div>
          <div>
            <span>AI 引擎</span>
            <strong>{aiProviderText}</strong>
          </div>
          <div>
            <span>AI 生成</span>
            <strong>{formatDate(refreshStatus?.ai_insights?.generated_at)}</strong>
          </div>
        </div>
        <div className={`ks-ai-status-strip ${aiError ? "is-warning" : ""}`}>
          <Bot size={15} />
          <span>{aiDetailText}</span>
        </div>
        {aiSectionItems.length > 0 && (
          <div className="ks-ai-section-strip">
            {aiSectionItems.map((item) => (
              <span key={item.key} className={`ks-ai-section-pill ${aiSectionStatusClass(item.status)}`} title={item.status?.error || undefined}>
                <b>{item.label}</b>
                {aiSectionStatusLabel(item.status)}
              </span>
            ))}
          </div>
        )}
      </Card>

      {!noProjectSelected && (sourceTracker || sourceTrackerId) && (
        <Card className="ks-filter-card ks-source-tracker-card">
          <div className="ks-source-tracker-card__icon">
            <FileSearch size={18} />
          </div>
          <div className="ks-source-tracker-card__main">
            <span>来源追踪器</span>
            <strong>{sourceTracker?.name || `追踪器 #${sourceTrackerId}`}</strong>
            <p>
              {sourceTracker?.latest_headline ||
                sourceTracker?.description ||
                "该追踪器作为本次项目策略分析的辅助信号，策略结论仍以项目为主上下文。"}
            </p>
            <div className="ks-chip-row">
              {(sourceTracker?.included_keywords || []).slice(0, 6).map((keyword) => (
                <span key={keyword}>{keyword}</span>
              ))}
              {sourceTracker?.latest_status && <span>{sourceTracker.latest_status}</span>}
              {sourceTracker?.updated_at && <span>{formatDate(sourceTracker.updated_at)}</span>}
            </div>
          </div>
          <div className="ks-source-tracker-card__actions">
            {sourceTrackerId && onOpenSourceTracker && (
              <Button variant="ghost" size="sm" onClick={() => onOpenSourceTracker(sourceTrackerId)}>
                <Eye size={14} />
                查看追踪分析
              </Button>
            )}
            {onClearSourceTracker && (
              <Button variant="ghost" size="sm" onClick={onClearSourceTracker}>
                <X size={14} />
                清除来源
              </Button>
            )}
          </div>
        </Card>
      )}

      {!noProjectSelected && summary?.strategy_note && (
        <div className="ks-notice">
          <Bot size={16} />
          <span>{summary.strategy_note}</span>
        </div>
      )}

      {!noProjectSelected && showAiFallbackWarning && (
        <div className="ks-notice is-warning">
          <AlertTriangle size={16} />
          <span>AI 中转站返回异常，当前页面已使用规则托底：{aiError}</span>
        </div>
      )}

      {error && (
        <div className="ks-notice is-error">
          <AlertTriangle size={16} />
          <span>{error}</span>
        </div>
      )}
      {notice && (
        <div className="ks-notice">
          <CheckCircle2 size={16} />
          <span>{notice}</span>
        </div>
      )}

      {noProjectSelected && (
        <Card className="ks-panel">
          <EmptyState label="请先选择一个增长项目，再查看项目级内容策略。" />
        </Card>
      )}

      {!noProjectSelected && <Card className="ks-filter-card">
        <div className="ks-filter-row">
          <div className="ks-filter-item">
            <span>平台</span>
            <Select value={platform} onValueChange={setPlatform} options={PLATFORM_OPTIONS} label="平台" />
          </div>
          <div className="ks-filter-item">
            <span>时间范围</span>
            <Select value={range} onValueChange={setRange} options={RANGE_OPTIONS} label="时间范围" />
          </div>
          <div className="ks-filter-item">
            <span>内容目标</span>
            <Select value={goal} onValueChange={setGoal} options={GOAL_OPTIONS} label="内容目标" />
          </div>
          <div className="ks-filter-item">
            <span>目标人群</span>
            <Select value={audience} onValueChange={setAudience} options={AUDIENCE_OPTIONS} label="目标人群" />
          </div>
          <div className="ks-filter-item">
            <span>内容阶段</span>
            <Select value={stage} onValueChange={setStage} options={STAGE_OPTIONS} label="内容阶段" />
          </div>
          <button type="button" className="ks-advanced-btn" onClick={() => setAdvancedOpen((value) => !value)}>
            <Search size={14} />
            高级筛选
          </button>
        </div>
        {advancedOpen && (
          <div className="ks-advanced-panel">
            <label>
              <span>策略备注</span>
              <input
                value={strategyNote}
                onChange={(event) => setStrategyNote(event.target.value)}
                placeholder="例如：优先做低成本测试，规避绝对化标题"
              />
            </label>
            <Button
              variant="ghost"
              onClick={() => generateDraft("topic_pack", { title: "按当前筛选生成选题包", note: strategyNote })}
              disabled={!summary || draftLoading}
            >
              <Sparkles size={15} />
              生成选题包
            </Button>
          </div>
        )}
      </Card>}

      {!noProjectSelected && <div className="ks-grid ks-grid--top">
        <Card className="ks-panel">
          <div className="ks-panel__head">
            <div>
              <h2>今日重点选题</h2>
              <p>{summary?.hero.sample_summary || "等待样本分析结果"}</p>
            </div>
            <span className="ks-panel__total">共 {summary?.suggestions.length ?? 0} 个</span>
          </div>
          <div className="ks-metric-grid">
            {metrics.length ? metrics.map((item) => (
              <button
                type="button"
                key={item.key}
                className={`ks-metric-card ks-metric-card--button ${item.accent}`}
                onClick={() => openMetricTopics(item)}
              >
                <div className="ks-metric-card__icon">{metricIcons[item.accent] || <Sparkles size={16} />}</div>
                <span>{item.label}</span>
                <strong>{item.value}</strong>
                <small>{item.hint}</small>
              </button>
            )) : <EmptyState label={loading ? "策略计算中" : "暂无指标"} />}
          </div>
        </Card>

        <Card className="ks-panel">
          <div className="ks-panel__head">
            <div>
              <h2>人群痛点分布</h2>
              <p>按标题、正文、选题和机会证据归类</p>
            </div>
          </div>
          {summary?.pain_distribution.length ? (
            <div className="ks-distribution">
              <Donut value={painTotal ? `${painTotal}` : `${summary.pain_distribution.length}`} label="痛点样本" segments={summary.pain_distribution} />
              <div className="ks-legend">
                {summary.pain_distribution.map((item) => (
                  <div key={item.label} className="ks-legend__row">
                    <span><i style={{ background: item.color }} />{item.label}</span>
                    <strong>{item.value}%</strong>
                  </div>
                ))}
              </div>
            </div>
          ) : <EmptyState label={loading ? "正在归类痛点" : "暂无痛点样本"} />}
        </Card>

        <Card className="ks-panel">
          <div className="ks-panel__head">
            <div>
              <h2>热门关键词趋势榜</h2>
              <p>热度、趋势与机会值综合排序</p>
              <span className={`ks-badge ${sourceBadgeClass(sectionSource(summary, "keyword_trends"))}`}>
                {sourceBadgeLabel(sectionSource(summary, "keyword_trends"))}
              </span>
            </div>
            <button type="button" className="ks-link-btn" onClick={() => openEvidence("关键词证据", evidenceItems.filter((item) => item.type === "keyword"))}>
              查看全部 <ChevronRight size={14} />
            </button>
          </div>
          {summary?.keyword_trends.length ? (
            <div className="ks-table ks-table--compact">
              <div className="ks-table__head">
                <span>排名</span>
                <span>关键词</span>
                <span>热度</span>
                <span>趋势</span>
                <span>机会值</span>
              </div>
              {summary.keyword_trends.slice(0, 5).map((item) => (
                <button
                  type="button"
                  key={`${item.platform || "all"}-${item.keyword}`}
                  className="ks-table__row ks-table__row--button"
                  onClick={() => openEvidence(item.keyword, [{ type: "keyword", title: item.keyword, platform: item.platform, reason: `${platformLabel(item.platform)} 机会值 ${item.score}`, payload: item }], item)}
                >
                  <strong className="ks-rank">{item.rank}</strong>
                  <span className="ks-row-title">{item.keyword}</span>
                  <span>{item.heat}</span>
                  <span className="ks-trend-cell">
                    <Sparkline points={item.points} color={trendColor(item.direction)} />
                  </span>
                  <em className={item.direction === "up" ? "is-up" : "is-down"}>
                    {item.score}
                    {item.direction === "up" ? <TrendingUp size={13} /> : <TrendingDown size={13} />}
                  </em>
                </button>
              ))}
            </div>
          ) : <EmptyState label={loading ? "正在计算趋势" : "暂无关键词趋势"} />}
        </Card>
      </div>}

      {!noProjectSelected && <div className="ks-grid ks-grid--middle">
        <Card className="ks-panel">
          <div className="ks-panel__head">
            <div>
              <h2>内容框架库</h2>
              <p>从样本标题和高互动证据聚类</p>
              <span className={`ks-badge ${sourceBadgeClass(sectionSource(summary, "frameworks"))}`}>
                {sourceBadgeLabel(sectionSource(summary, "frameworks"))}
              </span>
            </div>
            <button type="button" className="ks-link-btn" onClick={() => openEvidence("框架样本", evidenceItems.filter((item) => item.type === "post_sample"))}>
              查看更多 <ChevronRight size={14} />
            </button>
          </div>
          {summary?.frameworks.length ? (
            <div className="ks-framework-list">
              {summary.frameworks.slice(0, 5).map((item) => (
                <article key={item.title} className="ks-framework-card">
                  <div className="ks-framework-card__main">
                    <strong>{item.title}</strong>
                    <div className="ks-chip-row">
                      {item.tags.map((tag) => <span key={tag}>{tag}</span>)}
                    </div>
                  </div>
                  <div className="ks-framework-card__stats">
                    <div><span>参考内容</span><strong>{item.posts}</strong></div>
                    <div><span>互动中位数</span><strong>{item.interactions}</strong></div>
                    <div><span>线索估算</span><strong>{item.leads}</strong></div>
                  </div>
                  <Button variant="ghost" onClick={() => generateDraft("framework", { ...item, title: item.title })}>
                    使用框架
                  </Button>
                </article>
              ))}
            </div>
          ) : <EmptyState label={loading ? "正在聚类框架" : "暂无可复用框架"} />}
        </Card>

        <Card className="ks-panel">
          <div className="ks-panel__head">
            <div>
              <h2>选题建议</h2>
              <p>综合 AI 选题、机会评分和关键词趋势</p>
              <span className={`ks-badge ${sourceBadgeClass(sectionSource(summary, "suggestions"))}`}>
                {sourceBadgeLabel(sectionSource(summary, "suggestions"))}
              </span>
            </div>
            <button type="button" className="ks-link-btn" onClick={() => openEvidence("选题证据", evidenceItems.filter((item) => item.type === "suggestion"))}>
              查看更多 <ChevronRight size={14} />
            </button>
          </div>
          {summary?.suggestions.length ? (
            <div className="ks-table">
              <div className="ks-table__head ks-table__head--suggestions">
                <span>标题建议</span>
                <span>目标人群</span>
                <span>机会值</span>
                <span>风险等级</span>
                <span>操作</span>
              </div>
              {summary.suggestions.slice(0, 7).map((item) => (
                <div key={item.id} className="ks-table__row ks-table__row--suggestion">
                  <button
                    type="button"
                    className="ks-suggestion-main"
                    onClick={() => openEvidence(item.title, [{ type: "suggestion", title: item.title, platform: item.platform, reason: item.reason || item.direction, payload: item }], item)}
                  >
                    <strong>{item.title}</strong>
                    <small>{item.source === "ai" ? "AI 增强" : item.direction}</small>
                  </button>
                  <span>{item.audience}</span>
                  <b className="ks-score">{item.chance}</b>
                  <span className={`ks-badge ${riskClass(item.risk)}`}>{item.risk}</span>
                  <div className="ks-action-row">
                    <Button variant="ghost" size="sm" onClick={() => addSuggestionDraft(item)}>
                      <Plus size={14} />
                      加入草稿
                    </Button>
                    <Button variant="ghost" size="sm" onClick={() => generateDraft("copy", item as unknown as Record<string, unknown>)}>
                      <FileText size={14} />
                      生成文案
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          ) : <EmptyState label={loading ? "正在生成选题" : "暂无选题建议"} />}
        </Card>

        <Card className="ks-panel">
          <div className="ks-panel__head">
            <div>
              <h2>高表现同行内容样本</h2>
              <p>用于拆解标题、结构和互动入口</p>
            </div>
            <button type="button" className="ks-link-btn" onClick={() => openEvidence("同行样本证据", evidenceItems.filter((item) => item.type === "competitor_sample"))}>
              查看全部 <ChevronRight size={14} />
            </button>
          </div>
          {summary?.competitor_samples.length ? (
            <div className="ks-competitor-list">
              {summary.competitor_samples.slice(0, 6).map((item) => (
                <button
                  type="button"
                  key={`${item.platform}-${item.title}`}
                  className="ks-competitor-card ks-competitor-card--button"
                  onClick={() => openEvidence(item.title, [{ type: "competitor_sample", title: item.title, platform: item.platform_key, reason: `互动 ${item.interaction}`, payload: item }], item)}
                >
                  <span className={`ks-platform-badge ${item.badge}`}>{item.platform}</span>
                  <div className="ks-sample-thumb"><FileText size={18} /></div>
                  <div className="ks-competitor-card__main">
                    <strong>{item.title}</strong>
                    <small>互动 {item.interaction}</small>
                  </div>
                  <div className="ks-competitor-card__stats">
                    <span>点赞 {item.likes}</span>
                    <span>评论 {item.comments}</span>
                    <span>收藏 {item.favorites}</span>
                  </div>
                </button>
              ))}
            </div>
          ) : <EmptyState label={loading ? "正在整理同行样本" : "暂无同行样本"} />}
        </Card>
      </div>}

      {!noProjectSelected && <div className="ks-grid ks-grid--bottom">
        <Card className="ks-panel">
          <div className="ks-panel__head">
            <div>
              <h2>风险提醒</h2>
              <p>由机会风险、诊断和 AI 风险合并</p>
              <span className={`ks-badge ${sourceBadgeClass(sectionSource(summary, "risks"))}`}>
                {sourceBadgeLabel(sectionSource(summary, "risks"))}
              </span>
            </div>
            <button type="button" className="ks-link-btn" onClick={() => openEvidence("风险证据", [], summary?.risks)}>
              查看全部 <ChevronRight size={14} />
            </button>
          </div>
          {summary?.risks.length ? (
            <div className="ks-risk-list">
              {summary.risks.slice(0, 5).map((item) => (
                <article key={item.title} className="ks-risk-card">
                  <div className="ks-risk-card__top">
                    <span className={`ks-badge ${riskClass(item.level)}`}>{item.level}</span>
                    <strong>{item.count}</strong>
                  </div>
                  <h3>{item.title}</h3>
                  <p>{item.detail}</p>
                </article>
              ))}
            </div>
          ) : <EmptyState label={loading ? "正在检查风险" : "暂无风险提示"} />}
        </Card>

        <Card className="ks-panel">
          <div className="ks-panel__head">
            <div>
              <h2>本周内容组合建议</h2>
              <p>按目标和可用选题估算发布结构</p>
              <span className={`ks-badge ${sourceBadgeClass(sectionSource(summary, "weekly_mix"))}`}>
                {sourceBadgeLabel(sectionSource(summary, "weekly_mix"))}
              </span>
            </div>
          </div>
          {summary?.weekly_mix.length ? (
            <>
              <div className="ks-weekly-layout">
                <Donut value={`${summary.weekly_mix.reduce((sum, item) => sum + item.pieces, 0)}篇`} label="建议发布" segments={summary.weekly_mix.map((item) => ({ label: item.label, value: item.percent, color: item.color }))} />
                <div className="ks-weekly-table">
                  {summary.weekly_mix.map((item) => (
                    <div key={item.label} className="ks-weekly-row">
                      <div className="ks-weekly-row__main">
                        <span><i style={{ background: item.color }} />{item.label}</span>
                        <strong>{item.percent}%</strong>
                      </div>
                      <div className="ks-weekly-row__bar">
                        <i style={{ width: `${item.percent}%`, background: item.color }} />
                      </div>
                      <div className="ks-weekly-row__meta">
                        <span>{item.pieces} 篇</span>
                        <span>{item.exposure}</span>
                        <span>{item.leads}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
              <button type="button" className="ks-link-btn ks-link-btn--bottom" onClick={() => generateDraft("weekly_plan", { title: "本周内容计划", weekly_mix: summary.weekly_mix, drafts })}>
                调整方案 <ArrowRight size={14} />
              </button>
            </>
          ) : <EmptyState label={loading ? "正在生成组合" : "暂无组合建议"} />}
        </Card>

        <Card className="ks-panel">
          <div className="ks-panel__head">
            <div>
              <h2>预期流量分布</h2>
              <p>按平台样本和互动估算</p>
            </div>
            <button type="button" className="ks-link-btn" onClick={() => openEvidence("流量证据", evidenceItems)}>
              查看详情 <ChevronRight size={14} />
            </button>
          </div>
          {summary?.traffic_share.rows.length ? (
            <>
              <div className="ks-traffic-layout">
                <Donut value={summary.traffic_share.estimated_exposure} label="预估曝光" segments={summary.traffic_share.rows.map((item) => ({ label: item.platform, value: item.percent, color: item.color }))} />
                <div className="ks-legend">
                  {summary.traffic_share.rows.map((item) => (
                    <div key={item.platform} className="ks-legend__row">
                      <span><i style={{ background: item.color }} />{item.platform}</span>
                      <strong>{item.percent}%</strong>
                      <em>{item.traffic}</em>
                    </div>
                  ))}
                </div>
              </div>
              <div className="ks-summary-strip">
                <div>
                  <span>预估线索量</span>
                  <strong>{summary.traffic_share.estimated_leads}</strong>
                </div>
                <div>
                  <span>预估转化订单</span>
                  <strong>{summary.traffic_share.estimated_orders}</strong>
                </div>
              </div>
            </>
          ) : <EmptyState label={loading ? "正在估算流量" : "暂无流量样本"} />}
        </Card>
      </div>}

      {!noProjectSelected && <div className="ks-footer-cta">
        <div>
          <span className="ks-kicker">Action Board</span>
          <strong>把策略结果直接转成生产动作</strong>
          {drafts.length > 0 && <span className="ks-footer-hint">草稿池 {drafts.length} 个选题</span>}
        </div>
        <div className="ks-footer-cta__actions">
          <Button variant="ghost" onClick={() => generateDraft("topic_pack", { title: "选题包", suggestions: drafts.length ? drafts : summary?.suggestions.slice(0, 6) })} disabled={!summary}>
            <LayoutTemplate size={15} />
            创建选题包
          </Button>
          <Button variant="ghost" onClick={() => openEvidence("完整证据集", evidenceItems, summary?.evidence_pack)} disabled={!summary}>
            <Eye size={15} />
            查看证据集
          </Button>
          <Button variant="primary" onClick={() => generateDraft("weekly_plan", { title: "本周内容计划", suggestions: drafts.length ? drafts : summary?.suggestions.slice(0, 8), weekly_mix: summary?.weekly_mix })} disabled={!summary}>
            <Sparkles size={15} />
            生成本周内容计划
          </Button>
        </div>
      </div>}

      <Drawer
        open={!!evidenceDrawer}
        onOpenChange={(open) => {
          if (!open) setEvidenceDrawer(null);
        }}
        title={evidenceDrawer?.title || "证据集"}
        description="查看当前策略判断使用的关键词、选题、同行样本和原始证据。"
      >
        <div className="ks-drawer-body">
          {evidenceDrawer?.items.length ? (
            <div className="ks-evidence-list">
              {evidenceDrawer.items.map((item, index) => (
                <article key={`${item.type}-${item.title}-${index}`} className="ks-evidence-card">
                  <span>{item.type}</span>
                  <strong>{item.title}</strong>
                  <p>{item.reason || "已纳入策略判断。"}</p>
                  {item.platform && <em>{platformLabel(item.platform)}</em>}
                </article>
              ))}
            </div>
          ) : (
            <EmptyState label="暂无可展开证据" />
          )}
          {evidenceDrawer?.raw ? (
            <pre className="ks-json-detail">{JSON.stringify(evidenceDrawer.raw, null, 2)}</pre>
          ) : null}
        </div>
      </Drawer>

      <Drawer
        open={!!topicDrawer}
        onOpenChange={(open) => {
          if (!open) setTopicDrawer(null);
        }}
        title={topicDrawer?.title || "选题清单"}
        description={topicDrawer?.description || "查看当前指标下可优先执行的选题候选。"}
      >
        <div className="ks-drawer-body">
          {topicDrawer ? (
            <div className="ks-topic-drawer">
              <div className="ks-topic-drawer__summary">
                <strong>{topicDrawer.items.length} 个候选选题</strong>
                <p>{topicDrawer.description}</p>
              </div>
              {topicDrawer.items.length ? (
                <div className="ks-topic-list">
                  {topicDrawer.items.map((item) => (
                    <article key={item.id} className="ks-topic-card">
                      <div className="ks-topic-card__head">
                        <div>
                          <strong>{item.title}</strong>
                          <p>{item.reason || item.direction}</p>
                        </div>
                        <b className="ks-score">{item.chance}</b>
                      </div>
                      <div className="ks-topic-card__meta">
                        <span>{item.audience}</span>
                        <span className={`ks-badge ${riskClass(item.risk)}`}>{item.risk}</span>
                        <span>{item.source === "ai" ? "AI 增强" : item.direction}</span>
                      </div>
                      {item.keywords?.length ? (
                        <div className="ks-chip-row">
                          {item.keywords.slice(0, 4).map((keyword) => <span key={`${item.id}-${keyword}`}>{keyword}</span>)}
                        </div>
                      ) : null}
                      <div className="ks-topic-card__actions">
                        <Button variant="ghost" size="sm" onClick={() => openTopicEvidence(item)}>
                          <Eye size={14} />
                          查看证据
                        </Button>
                        <Button variant="ghost" size="sm" onClick={() => addSuggestionDraft(item)}>
                          <Plus size={14} />
                          加入草稿
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => {
                            setTopicDrawer(null);
                            void generateDraft("copy", item as unknown as Record<string, unknown>);
                          }}
                        >
                          <FileText size={14} />
                          生成文案
                        </Button>
                      </div>
                    </article>
                  ))}
                </div>
              ) : (
                <EmptyState label={topicDrawer.emptyLabel} />
              )}
            </div>
          ) : null}
        </div>
      </Drawer>

      <Drawer
        open={draftOpen}
        onOpenChange={(open) => {
          setDraftOpen(open);
          if (!open) {
            setDraftResponse(null);
            setDraftError(null);
          }
        }}
        title="策略草稿"
        description="查看 AI 或规则引擎生成的内容策略草稿，并复制到内容生产流程。"
      >
        <div className="ks-drawer-body">
          {draftLoading && (
            <div className="ks-draft-loading">
              <Loader2 size={18} className="spin" />
              <span>正在生成策略草稿...</span>
            </div>
          )}
          {draftError && (
            <div className="ks-notice is-error">
              <AlertTriangle size={16} />
              <span>{draftError}</span>
            </div>
          )}
          {draftResponse?.draft && (
            <div className="ks-draft">
              <div className="ks-draft__head">
                <div>
                  <span className={`ks-badge ${draftResponse.mode === "ai" ? "is-safe" : "is-warn"}`}>
                    {draftResponse.mode === "ai" ? "AI 生成" : "规则草稿"}
                  </span>
                  <h3>{draftResponse.draft.title}</h3>
                  <p>{draftResponse.draft.summary}</p>
                </div>
                <Button variant="ghost" size="sm" onClick={copyDraft}>
                  <Copy size={14} />
                  复制草稿
                </Button>
              </div>
              {draftResponse.draft.body && <pre className="ks-draft__body">{draftResponse.draft.body}</pre>}
              <div className="ks-draft-list">
                {draftResponse.draft.sections.map((section) => (
                  <article key={section.heading}>
                    <strong>{section.heading}</strong>
                    <ul>
                      {section.items.map((item) => <li key={item}>{item}</li>)}
                    </ul>
                  </article>
                ))}
                {draftResponse.draft.checklist.length > 0 && (
                  <article>
                    <strong>执行清单</strong>
                    <ul>
                      {draftResponse.draft.checklist.map((item) => <li key={item}>{item}</li>)}
                    </ul>
                  </article>
                )}
                {draftResponse.draft.risk_notes.length > 0 && (
                  <article>
                    <strong>风险提醒</strong>
                    <ul>
                      {draftResponse.draft.risk_notes.map((item) => <li key={item}>{item}</li>)}
                    </ul>
                  </article>
                )}
              </div>
            </div>
          )}
        </div>
      </Drawer>
    </section>
  );
}

type ContentStrategyDraftRequestKind = "copy" | "weekly_plan" | "topic_pack" | "framework" | "evidence_summary";

function EmptyState({ label }: { label: string }) {
  return (
    <div className="ks-empty">
      <ClipboardList size={18} />
      <span>{label}</span>
    </div>
  );
}
