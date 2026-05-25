import React from "react";
import {
  BadgeCheck,
  CalendarRange,
  CheckCircle2,
  ChevronRight,
  CircleDollarSign,
  Download,
  Eye,
  Filter,
  Flame,
  MessageCircleMore,
  MousePointerClick,
  Orbit,
  RefreshCw,
  Search,
  ShoppingCart,
  Sparkles,
  Target,
  TrendingUp,
  UserRoundPlus,
  Users,
} from "lucide-react";
import { Button, Card, Drawer, Select, Skeleton } from "../components/ui";
import type {
  AttributionModel,
  GrowthProjectSummary,
  LeadAttributionConfig,
  LeadAttributionFunnelStep,
  LeadAttributionRow,
  LeadAttributionSummaryPayload,
  LeadDetailResponse,
  LeadListItem,
  LeadTimelineEntry,
  LeadTimelineResponse,
} from "../types";
import { api, ApiError } from "../utils/api";

type MetricCard = {
  label: string;
  value: string;
  delta: string;
  accent: "teal" | "cyan" | "orange";
  icon: React.ReactNode;
  points: number[];
};

type LeadRowView = {
  id: number;
  name: string;
  platform: string;
  source: string;
  tag: string;
  score: number;
  stage: string;
  nextAction: string;
  updatedAt: string;
  owner: string;
};

type SampleCandidateRow = {
  id: string;
  name: string;
  platform: string;
  source: string;
  tag: string;
  score: number;
  stage: string;
  nextAction: string;
  latest: string;
  owner: string;
};

type Recommendation = {
  leadId: number;
  name: string;
  labels: string[];
  reason: string;
  score: number;
  action: string;
};

type ActionRecommendation = {
  title: string;
  description: string;
  cta: string;
};

type SampleAnalysis = NonNullable<LeadAttributionSummaryPayload["sample_analysis"]>;

type AttributionWorkspace = "overview" | "sample" | "attribution";
type ReadinessStatus = "done" | "active" | "blocked";

type ReadinessStep = {
  key: string;
  title: string;
  description: string;
  metric: string;
  status: ReadinessStatus;
  workspace: AttributionWorkspace;
};

type ModeInsight = {
  title: string;
  body: string;
  primaryMetric: string;
  secondaryMetric: string;
};

const PLATFORM_LABELS: Record<string, string> = {
  xhs: "小红书",
  dy: "抖音",
  douyin: "抖音",
  wx: "微信",
  wechat: "微信",
  video: "视频号",
  shipinhao: "视频号",
  bilibili: "B站",
  wb: "微博",
  weibo: "微博",
};

const PLATFORM_COLORS = ["#0f8f85", "#ff7d66", "#ffb23f", "#5b8def", "#6fc7bf", "#c5d7d3"];
const ALL_SOURCE_LABEL = "全部来源";
const ALL_PLATFORM_LABEL = "全部平台";
const GLOBAL_PROJECT_ID = "__global__";
const GLOBAL_PROJECT_OPTION = {
  value: GLOBAL_PROJECT_ID,
  label: "全部数据",
};
const GLOBAL_ATTRIBUTION_CONFIG: LeadAttributionConfig = {
  default_model: "last_touch",
  window_days: 7,
  enabled_dimensions: ["platform", "keyword", "content", "creator"],
  dedupe_by: "external_lead_id",
};

const MODEL_LABELS: Record<AttributionModel, string> = {
  first_touch: "首次触点",
  last_touch: "末次触点",
  linear: "线性归因",
};

function uniqueValues(values: string[]) {
  return Array.from(new Set(values.filter(Boolean)));
}

function formatNumber(value: number | null | undefined) {
  const numeric = Number(value || 0);
  if (numeric >= 100000000) return `${(numeric / 100000000).toFixed(1)}亿`;
  if (numeric >= 10000) return `${(numeric / 10000).toFixed(1)}万`;
  return new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 0 }).format(numeric);
}

function formatMoney(value: number | null | undefined) {
  const numeric = Number(value || 0);
  return `¥${new Intl.NumberFormat("zh-CN", {
    maximumFractionDigits: numeric >= 1000 ? 0 : 2,
  }).format(numeric)}`;
}

function formatRatio(value: number | null | undefined) {
  if (value == null || Number.isNaN(Number(value))) return "--";
  return `${(Number(value) * 100).toFixed(1)}%`;
}

function formatTimestamp(value: string | null | undefined) {
  if (!value) return "--";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function formatDateRange(summary?: LeadAttributionSummaryPayload["summary"]) {
  if (!summary) return "最近归因窗口";
  if (summary.date_from && summary.date_to) {
    return `${summary.date_from.slice(0, 10)} 至 ${summary.date_to.slice(0, 10)}`;
  }
  return "项目累计数据";
}

function funnelStageLabel(stage: string) {
  switch (stage) {
    case "lead":
      return "线索";
    case "qualified":
      return "有效线索";
    case "wechat_added":
      return "加微";
    case "first_reply":
      return "首聊";
    case "deal_closed":
      return "成交";
    default:
      return stage || "未知节点";
  }
}

function platformLabel(value: string | null | undefined) {
  if (!value) return "未知平台";
  return PLATFORM_LABELS[value.toLowerCase()] || value.toUpperCase();
}

function stageLabel(status: string) {
  switch (status) {
    case "dealt":
      return "已成交";
    case "contacted":
      return "已联系";
    case "qualified":
      return "有效线索";
    case "lost":
      return "已流失";
    case "new":
    default:
      return "新线索";
  }
}

function stageTone(score: number) {
  if (score >= 85) return "high";
  if (score >= 70) return "mid";
  return "warm";
}

function metricTrendPoints(value: number, seed: number) {
  const base = Math.max(value, 1);
  return Array.from({ length: 10 }, (_, index) => {
    const ratio = 0.74 + index * 0.035;
    const wobble = ((seed + index * 7) % 5) - 2;
    return Math.max(1, Math.round(base * ratio + wobble));
  });
}

function buildMetricCards(summary?: LeadAttributionSummaryPayload["summary"]): MetricCard[] {
  const fallbackSummary: LeadAttributionSummaryPayload["summary"] = {
    lead_count: 0,
    qualified_lead_count: 0,
    wechat_added_count: 0,
    first_reply_count: 0,
    deal_lead_count: 0,
    deal_count: 0,
    deal_amount: 0,
    qualified_lead_rate: 0,
    lead_to_wechat_rate: 0,
    wechat_to_reply_rate: 0,
    reply_to_deal_rate: 0,
    cost: 0,
    cpl: 0,
    cost_per_qualified_lead: 0,
    roi: 0,
    model: "last_touch",
    date_from: null,
    date_to: null,
  };
  const data = summary || fallbackSummary;
  return [
    {
      label: "线索数",
      value: formatNumber(data.lead_count),
      delta: `有效率 ${formatRatio(data.qualified_lead_rate)}`,
      accent: "cyan",
      icon: <Eye size={18} />,
      points: metricTrendPoints(data.lead_count, 1),
    },
    {
      label: "有效线索",
      value: formatNumber(data.qualified_lead_count),
      delta: `占比 ${formatRatio(data.qualified_lead_rate)}`,
      accent: "teal",
      icon: <MousePointerClick size={18} />,
      points: metricTrendPoints(data.qualified_lead_count, 2),
    },
    {
      label: "加微",
      value: formatNumber(data.wechat_added_count),
      delta: `转化 ${formatRatio(data.lead_to_wechat_rate)}`,
      accent: "teal",
      icon: <UserRoundPlus size={18} />,
      points: metricTrendPoints(data.wechat_added_count, 3),
    },
    {
      label: "首聊",
      value: formatNumber(data.first_reply_count),
      delta: `转化 ${formatRatio(data.wechat_to_reply_rate)}`,
      accent: "cyan",
      icon: <MessageCircleMore size={18} />,
      points: metricTrendPoints(data.first_reply_count, 4),
    },
    {
      label: "成交线索",
      value: formatNumber(data.deal_count),
      delta: `转化 ${formatRatio(data.reply_to_deal_rate)}`,
      accent: "orange",
      icon: <BadgeCheck size={18} />,
      points: metricTrendPoints(data.deal_count, 5),
    },
    {
      label: "成交金额",
      value: formatMoney(data.deal_amount),
      delta: `CPL ${data.cpl != null ? formatMoney(data.cpl) : "--"}`,
      accent: "orange",
      icon: <ShoppingCart size={18} />,
      points: metricTrendPoints(data.deal_amount, 6),
    },
    {
      label: "ROI",
      value: data.roi != null ? Number(data.roi).toFixed(2) : "--",
      delta: `成本 ${data.cost != null ? formatMoney(data.cost) : "--"}`,
      accent: "teal",
      icon: <CircleDollarSign size={18} />,
      points: metricTrendPoints(Number(data.roi || 0) * 100, 7),
    },
  ];
}

function buildSampleMetricCards(sample: SampleAnalysis): MetricCard[] {
  const data = sample.summary;
  return [
    {
      label: "原始记录",
      value: formatNumber(data.raw_record_count),
      delta: `任务 ${formatNumber(data.job_count)} 个`,
      accent: "cyan",
      icon: <Eye size={18} />,
      points: metricTrendPoints(data.raw_record_count, 1),
    },
    {
      label: "内容样本",
      value: formatNumber(data.post_count),
      delta: "来自采集帖子",
      accent: "teal",
      icon: <MousePointerClick size={18} />,
      points: metricTrendPoints(data.post_count, 2),
    },
    {
      label: "评论样本",
      value: formatNumber(data.comment_count),
      delta: "用于需求识别",
      accent: "teal",
      icon: <MessageCircleMore size={18} />,
      points: metricTrendPoints(data.comment_count, 3),
    },
    {
      label: "意向评论",
      value: formatNumber(data.intent_comment_count),
      delta: `占比 ${formatRatio(data.intent_comment_rate)}`,
      accent: "orange",
      icon: <UserRoundPlus size={18} />,
      points: metricTrendPoints(data.intent_comment_count, 4),
    },
    {
      label: "创作者样本",
      value: formatNumber(data.creator_count),
      delta: "按作者去重",
      accent: "cyan",
      icon: <Users size={18} />,
      points: metricTrendPoints(data.creator_count, 5),
    },
    {
      label: "平台覆盖",
      value: formatNumber(sample.platform_rows.length),
      delta: "样本分布",
      accent: "teal",
      icon: <Orbit size={18} />,
      points: metricTrendPoints(sample.platform_rows.length, 6),
    },
    {
      label: "关键词",
      value: formatNumber(sample.top_keywords.length),
      delta: "命中样本",
      accent: "orange",
      icon: <Target size={18} />,
      points: metricTrendPoints(sample.top_keywords.length, 7),
    },
  ];
}

function buildFunnel(summary?: LeadAttributionSummaryPayload) {
  const rawSteps = summary?.funnel || [];
  const steps = rawSteps.map((rawStep, index) => {
    const row = rawStep as LeadAttributionFunnelStep & { stage?: string; count?: number };
    const stage = row.stage || row.key || String(index);
    const value = Number(row.value ?? row.count ?? 0);
    const previous = rawSteps[index - 1] as (LeadAttributionFunnelStep & { count?: number }) | undefined;
    const previousValue = Number(previous?.value ?? previous?.count ?? 0);
    return {
      key: row.key || stage,
      label: row.label || funnelStageLabel(stage),
      value,
      rate: row.rate ?? (index === 0 ? (value > 0 ? 1 : 0) : previousValue > 0 ? value / previousValue : 0),
    };
  });
  const maxValue = Math.max(...steps.map((step) => step.value), 1);
  return steps.map((step, index) => ({
    ...step,
    width: Math.max(44, Math.round((step.value / Math.max(maxValue, 1)) * (100 - index * 6))),
  }));
}

function buildSampleFunnel(sample: SampleAnalysis) {
  const stages = [
    { key: "raw_records", label: "原始记录", value: sample.summary.raw_record_count },
    { key: "posts", label: "内容样本", value: sample.summary.post_count },
    { key: "comments", label: "评论样本", value: sample.summary.comment_count },
    { key: "intent_comments", label: "意向评论", value: sample.summary.intent_comment_count },
  ];
  const maxValue = Math.max(...stages.map((step) => step.value), 1);
  return stages.map((step, index) => {
    const previous = stages[index - 1];
    return {
      ...step,
      rate: index === 0 ? (step.value > 0 ? 1 : 0) : previous.value > 0 ? step.value / previous.value : 0,
      width: Math.max(44, Math.round((step.value / Math.max(maxValue, 1)) * (100 - index * 6))),
    };
  });
}

function deriveLeadRows(leads: LeadListItem[]): LeadRowView[] {
  return leads.map((lead) => {
    const score = Number(lead.lead_score || 0);
    const name = lead.name_masked || lead.external_lead_id || `线索 #${lead.id}`;
    return {
      id: lead.id,
      name,
      platform: platformLabel(lead.source_platform),
      source: lead.source_keyword || lead.external_lead_id || "待补来源",
      tag: lead.source_keyword || "未打标签",
      score,
      stage: stageLabel(lead.lead_status),
      nextAction: score >= 85 ? "优先跟进" : score >= 70 ? "今日回访" : "继续观察",
      updatedAt: formatTimestamp(lead.updated_at || lead.last_touch_at || lead.created_at),
      owner: lead.owner || "未分配",
    };
  });
}

function sampleCandidateScore(value: number) {
  const numeric = Math.max(0, Number(value || 0));
  return Math.min(99, Math.max(58, Math.round(58 + Math.log10(numeric + 1) * 13)));
}

function deriveSampleCandidateRows(sample?: SampleAnalysis): SampleCandidateRow[] {
  if (!sample) return [];
  const contentRows = sample.top_contents.slice(0, 8).map((item, index) => ({
    id: `content-${item.post_id || index}`,
    name: item.title || `内容样本 #${index + 1}`,
    platform: platformLabel(item.platform),
    source: item.publish_time ? formatTimestamp(item.publish_time) : "内容互动",
    tag: "内容样本",
    score: sampleCandidateScore(item.engagement_score),
    stage: "待转线索",
    nextAction: item.url ? "打开内容核验" : "沉淀线索入口",
    latest: `互动 ${formatNumber(item.engagement_score)}`,
    owner: "采集样本",
  }));
  const keywordRows = sample.top_keywords.slice(0, 6).map((item, index) => ({
    id: `keyword-${item.keyword || index}`,
    name: `关键词：${item.keyword}`,
    platform: "全部平台",
    source: item.keyword,
    tag: "关键词命中",
    score: sampleCandidateScore(item.score),
    stage: "需求识别",
    nextAction: "扩展线索规则",
    latest: `命中 ${formatNumber(item.hit_count)} 次`,
    owner: `样本 ${formatNumber(item.sample_count)}`,
  }));
  const intentRows = sample.intent_terms.slice(0, 6).map((item, index) => ({
    id: `intent-${item.term || index}`,
    name: `意向词：${item.term}`,
    platform: "评论样本",
    source: item.term,
    tag: "意向评论",
    score: sampleCandidateScore(item.count * 8),
    stage: "高意向",
    nextAction: "转入线索规则",
    latest: `出现 ${formatNumber(item.count)} 次`,
    owner: "规则候选",
  }));
  return [...contentRows, ...keywordRows, ...intentRows]
    .sort((a, b) => b.score - a.score)
    .slice(0, 12);
}

function deriveRecommendations(leads: LeadListItem[]): Recommendation[] {
  return leads
    .slice()
    .sort((a, b) => Number(b.lead_score || 0) - Number(a.lead_score || 0))
    .slice(0, 3)
    .map((lead) => ({
      leadId: lead.id,
      name: lead.name_masked || lead.external_lead_id || `线索 #${lead.id}`,
      labels: [platformLabel(lead.source_platform), lead.source_keyword || "未标记", stageLabel(lead.lead_status)],
      reason:
        Number(lead.lead_score || 0) >= 85
          ? "高分线索且最近触点活跃，建议立即跟进。"
          : "近期有归因触点且质量分较高，适合优先承接。",
      score: Number(lead.lead_score || 0),
      action: Number(lead.lead_score || 0) >= 85 ? "立即跟进" : "查看详情",
    }));
}

function deriveSampleRecommendations(sample?: SampleAnalysis): Recommendation[] {
  if (!sample) return [];
  return sample.top_contents.slice(0, 3).map((item, index) => ({
    leadId: 0 - index,
    name: item.title || `内容样本 #${index + 1}`,
    labels: [platformLabel(item.platform), `互动 ${formatNumber(item.engagement_score)}`, "潜在线索入口"],
    reason: "当前无线索闭环数据，先按内容互动和评论样本识别潜在线索入口。",
    score: Math.min(99, Math.max(60, Math.round(Number(item.engagement_score || 0) / 10))),
    action: "查看内容",
  }));
}

function deriveActionRecommendations(
  summary?: LeadAttributionSummaryPayload,
  leads: LeadListItem[] = [],
): ActionRecommendation[] {
  const actions: ActionRecommendation[] = [];
  const data = summary?.summary;
  if (data) {
    if ((data.lead_to_wechat_rate || 0) < 0.35) {
      actions.push({
        title: "优化加微承接",
        description: "线索到加微转化偏低，优先检查落地页、私信入口和销售承接话术。",
        cta: "查看漏斗",
      });
    }
    if ((data.wechat_to_reply_rate || 0) < 0.5) {
      actions.push({
        title: "提升首聊效率",
        description: "加微后首聊转化偏弱，建议补标准首聊话术和 24 小时跟进机制。",
        cta: "查看详情",
      });
    }
    if (data.cost && data.deal_amount < data.cost) {
      actions.push({
        title: "收紧低 ROI 来源",
        description: "当前成交金额未覆盖成本，建议优先复盘低 ROI 平台和内容。",
        cta: "查看 ROI",
      });
    }
  }
  const highScoreCount = leads.filter((lead) => Number(lead.lead_score || 0) >= 80).length;
  if (highScoreCount > 0) {
    actions.push({
      title: "高潜线索待承接",
      description: `当前有 ${highScoreCount} 条高分线索，建议销售优先处理。`,
      cta: "打开线索",
    });
  }
  return actions.slice(0, 4);
}

function deriveSampleActionRecommendations(sample?: SampleAnalysis): ActionRecommendation[] {
  if (!sample) return [];
  const actions: ActionRecommendation[] = [
    {
      title: "导入线索闭环",
      description: "当前已有采集样本，但线索、触点和转化事件为空，建议先导入业务线索表。",
      cta: "导入线索",
    },
    {
      title: "补齐触点映射",
      description: "把高互动内容映射到触点，才能判断哪些内容真正贡献加微和成交。",
      cta: "补触点",
    },
  ];
  if (sample.summary.intent_comment_count > 0) {
    actions.push({
      title: "优先跟进意向评论",
      description: `样本中识别到 ${sample.summary.intent_comment_count} 条意向评论，可作为第一批线索候选。`,
      cta: "查看样本",
    });
  }
  if (sample.diagnostics.length > 0) {
    actions.push({
      title: "补齐样本缺口",
      description: sample.diagnostics[0].body,
      cta: "继续采集",
    });
  }
  return actions.slice(0, 4);
}

function buildReadinessSteps({
  isSampleMode,
  sample,
  summary,
  leads,
}: {
  isSampleMode: boolean;
  sample?: SampleAnalysis;
  summary?: LeadAttributionSummaryPayload | null;
  leads: LeadListItem[];
}): ReadinessStep[] {
  const summaryData = summary?.summary;
  const sampleCount = Number(sample?.summary.raw_record_count || 0);
  const leadCount = Math.max(Number(summaryData?.lead_count || 0), leads.length);
  const hasAttributionRows = Boolean(
    (summary?.top_platforms || []).length ||
      (summary?.top_keywords || []).length ||
      (summary?.top_contents || []).length ||
      (summary?.top_creators || []).length,
  );
  const conversionCount =
    Number(summaryData?.wechat_added_count || 0) +
    Number(summaryData?.first_reply_count || 0) +
    Number(summaryData?.deal_count || 0);
  const cost = Number(summaryData?.cost || 0);

  return [
    {
      key: "samples",
      title: "采集样本",
      description: "帖子、评论和关键词样本，用于识别潜在线索入口。",
      metric: sampleCount ? formatNumber(sampleCount) : "未就绪",
      status: sampleCount > 0 ? "done" : "active",
      workspace: "sample",
    },
    {
      key: "leads",
      title: "线索主表",
      description: "业务线索、来源平台、来源关键词和承接人。",
      metric: leadCount ? formatNumber(leadCount) : "待导入",
      status: leadCount > 0 ? "done" : isSampleMode ? "active" : "blocked",
      workspace: "attribution",
    },
    {
      key: "touchpoints",
      title: "触点路径",
      description: "线索接触过的内容、达人、关键词和平台。",
      metric: hasAttributionRows ? "已映射" : "待补齐",
      status: hasAttributionRows ? "done" : leadCount > 0 ? "active" : "blocked",
      workspace: "attribution",
    },
    {
      key: "conversions",
      title: "转化事件",
      description: "加微、首聊、有效线索、成交等业务事件。",
      metric: conversionCount ? formatNumber(conversionCount) : "待导入",
      status: conversionCount > 0 ? "done" : leadCount > 0 ? "active" : "blocked",
      workspace: "attribution",
    },
    {
      key: "cost",
      title: "成本数据",
      description: "平台、内容、关键词、达人维度的投放或人工成本。",
      metric: cost > 0 ? formatMoney(cost) : "可选",
      status: cost > 0 ? "done" : conversionCount > 0 ? "active" : "blocked",
      workspace: "attribution",
    },
  ];
}

function buildModeInsight({
  isSampleMode,
  sample,
  summary,
  readinessSteps,
}: {
  isSampleMode: boolean;
  sample?: SampleAnalysis;
  summary?: LeadAttributionSummaryPayload | null;
  readinessSteps: ReadinessStep[];
}): ModeInsight {
  const doneCount = readinessSteps.filter((step) => step.status === "done").length;
  const totalCount = readinessSteps.length || 1;
  if (isSampleMode) {
    const intentCount = Number(sample?.summary.intent_comment_count || 0);
    const rawCount = Number(sample?.summary.raw_record_count || 0);
    return {
      title: "当前为样本分析模式",
      body: "系统已用采集到的帖子、评论和关键词识别潜在线索入口；正式归因还需要导入线索、触点、转化和成本数据。",
      primaryMetric: `${doneCount}/${totalCount} 数据层就绪`,
      secondaryMetric: intentCount
        ? `${formatNumber(intentCount)} 条意向评论`
        : `${formatNumber(rawCount)} 条样本待转线索`,
    };
  }
  const leadCount = Number(summary?.summary.lead_count || 0);
  return {
    title: "当前为正式归因模式",
    body: "系统正在基于真实线索、触点、转化事件和成本数据，计算平台、内容、关键词和达人对业务结果的贡献。",
    primaryMetric: `${doneCount}/${totalCount} 数据层就绪`,
    secondaryMetric: `${formatNumber(leadCount)} 条线索参与归因`,
  };
}

function readinessStatusLabel(status: ReadinessStatus) {
  if (status === "done") return "已就绪";
  if (status === "active") return "待处理";
  return "缺数据";
}

function buildPlatformShare(rows: LeadAttributionRow[]) {
  const total = rows.reduce((sum, row) => sum + Number(row.lead_count || 0), 0);
  return rows.slice(0, 6).map((row, index) => {
    const count = Number(row.lead_count || 0);
    const percent = total > 0 ? (count / total) * 100 : 0;
    return {
      label: platformLabel(row.dimension_key),
      percent: `${percent.toFixed(1)}%`,
      count: formatNumber(count),
      color: PLATFORM_COLORS[index % PLATFORM_COLORS.length],
    };
  });
}

function buildSamplePlatformShare(rows: SampleAnalysis["platform_rows"]) {
  const total = rows.reduce((sum, row) => sum + Number(row.sample_count || 0), 0);
  return rows.slice(0, 6).map((row, index) => {
    const count = Number(row.sample_count || 0);
    const percent = total > 0 ? (count / total) * 100 : 0;
    return {
      label: platformLabel(row.dimension_key),
      percent: `${percent.toFixed(1)}%`,
      count: formatNumber(count),
      color: PLATFORM_COLORS[index % PLATFORM_COLORS.length],
    };
  });
}

function buildLossReasons(summary?: LeadAttributionSummaryPayload) {
  const funnel = summary?.funnel || [];
  return funnel
    .slice(1)
    .map((step, index) => {
      const previous = funnel[index];
      const loss = Math.max(Number(previous.value || 0) - Number(step.value || 0), 0);
      return {
        label: `${previous.label} -> ${step.label}`,
        value: loss,
        percent: previous.value > 0 ? `${((loss / previous.value) * 100).toFixed(1)}%` : "--",
      };
    })
    .sort((a, b) => b.value - a.value)
    .slice(0, 5);
}

function buildLossReasonsFromSteps(funnel: Array<{ label: string; value: number }>) {
  return funnel
    .slice(1)
    .map((step, index) => {
      const previous = funnel[index];
      const loss = Math.max(Number(previous.value || 0) - Number(step.value || 0), 0);
      return {
        label: `${previous.label} -> ${step.label}`,
        value: loss,
        percent: previous.value > 0 ? `${((loss / previous.value) * 100).toFixed(1)}%` : "--",
      };
    })
    .sort((a, b) => b.value - a.value)
    .slice(0, 5);
}

function timelineTitle(entry: LeadTimelineEntry) {
  if (entry.kind === "conversion_event") {
    return String((entry.payload as { event_type?: string }).event_type || "转化事件");
  }
  return String((entry.payload as { touch_type?: string }).touch_type || "触点");
}

function roleLabel(role?: LeadTimelineEntry["role"]) {
  switch (role) {
    case "winning":
      return "胜出触点";
    case "assist":
      return "辅助触点";
    case "out_of_window":
      return "窗口外";
    case "after_conversion":
      return "转化后触点";
    default:
      return "未归因";
  }
}

function roleColor(role?: LeadTimelineEntry["role"]) {
  switch (role) {
    case "winning":
      return "#0f8f85";
    case "assist":
      return "#5b8def";
    case "out_of_window":
      return "#ffb23f";
    case "after_conversion":
      return "#ff7d66";
    default:
      return "#6d837d";
  }
}

function Sparkline({ points, accent }: { points: number[]; accent: MetricCard["accent"] }) {
  const palette = {
    teal: { stroke: "#089981", fill: "rgba(8, 153, 129, 0.16)" },
    cyan: { stroke: "#27a8b8", fill: "rgba(39, 168, 184, 0.14)" },
    orange: { stroke: "#ff7c44", fill: "rgba(255, 124, 68, 0.14)" },
  }[accent];
  const max = Math.max(...points, 1);
  const min = Math.min(...points, 0);
  const span = Math.max(max - min, 1);
  const line = points
    .map((point, index) => {
      const x = (index / Math.max(points.length - 1, 1)) * 100;
      const y = 26 - ((point - min) / span) * 22;
      return `${index === 0 ? "M" : "L"} ${x} ${y}`;
    })
    .join(" ");

  return (
    <svg viewBox="0 0 100 30" className="la-sparkline" aria-hidden="true">
      <path d={`${line} L 100 30 L 0 30 Z`} fill={palette.fill} />
      <path d={line} fill="none" stroke={palette.stroke} strokeWidth="2.1" strokeLinecap="round" />
    </svg>
  );
}

function DonutRingRefined({
  items,
  total,
}: {
  items: Array<{ label: string; percent: string; count: string; color: string }>;
  total: number;
}) {
  const radius = 54;
  const stroke = 9;
  const circumference = 2 * Math.PI * radius;
  const gap = 6.5;
  let offset = -circumference * 0.25;

  return (
    <div className="la-donut la-donut--refined">
      <svg viewBox="0 0 140 140" className="la-donut__svg" aria-hidden="true">
        <defs>
          <filter id="la-donut-shadow" x="-20%" y="-20%" width="140%" height="140%">
            <feDropShadow dx="0" dy="5" stdDeviation="6" floodColor="rgba(15, 45, 38, 0.08)" />
          </filter>
        </defs>
        <circle className="la-donut__halo" cx="70" cy="70" r="65" />
        <circle className="la-donut__track" cx="70" cy="70" r={radius} />
        {items.map((item, index) => {
          const percent = Number.parseFloat(item.percent);
          const length = Math.max((percent / 100) * circumference - gap, 0);
          const dasharray = `${length} ${circumference - length}`;
          const currentOffset = offset;
          offset -= (percent / 100) * circumference;
          return (
            <circle
              key={`donut-segment-${item.label}-${index}`}
              className="la-donut__segment"
              cx="70"
              cy="70"
              r={radius}
              stroke={item.color}
              strokeWidth={stroke}
              strokeDasharray={dasharray}
              strokeDashoffset={currentOffset}
            />
          );
        })}
        <circle className="la-donut__inner-ring" cx="70" cy="70" r="40.5" />
      </svg>
      <div className="la-donut__center">
        <span>线索数</span>
        <strong>{formatNumber(total)}</strong>
      </div>
    </div>
  );
}

export function LeadAttributionPage() {
  const [projects, setProjects] = React.useState<GrowthProjectSummary[]>([]);
  const [projectId, setProjectId] = React.useState<string>("");
  const [config, setConfig] = React.useState<LeadAttributionConfig | null>(null);
  const [summary, setSummary] = React.useState<LeadAttributionSummaryPayload | null>(null);
  const [leads, setLeads] = React.useState<LeadListItem[]>([]);
  const [selectedLeadId, setSelectedLeadId] = React.useState<number | null>(null);
  const [leadDetail, setLeadDetail] = React.useState<LeadDetailResponse | null>(null);
  const [leadTimeline, setLeadTimeline] = React.useState<LeadTimelineResponse | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [refreshing, setRefreshing] = React.useState(false);
  const [detailLoading, setDetailLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [detailError, setDetailError] = React.useState<string | null>(null);
  const [activeWorkspace, setActiveWorkspace] = React.useState<AttributionWorkspace>("overview");
  const [templateOpen, setTemplateOpen] = React.useState(false);
  const [activeSource, setActiveSource] = React.useState(ALL_SOURCE_LABEL);
  const [activePlatform, setActivePlatform] = React.useState(ALL_PLATFORM_LABEL);
  const projectIdRef = React.useRef("");
  const pageRequestIdRef = React.useRef(0);
  const isGlobalScope = projectId === GLOBAL_PROJECT_ID;

  const currentProject = React.useMemo(
    () => projects.find((project) => String(project.id) === projectId) || null,
    [projectId, projects],
  );
  const projectOptions = React.useMemo(
    () =>
      [
        GLOBAL_PROJECT_OPTION,
        ...projects.map((project) => ({
          value: String(project.id),
          label: project.name || `项目 ${project.id}`,
        })),
      ],
    [projects],
  );
  const model = config?.default_model || "last_touch";
  const sampleAnalysis = summary?.sample_analysis;
  const isSampleMode = Boolean(sampleAnalysis && Number(summary?.summary.lead_count || 0) === 0);

  const sourceOptions = React.useMemo(() => {
    const keywords = isSampleMode
      ? (sampleAnalysis?.top_keywords || []).map((row) => row.keyword).slice(0, 3)
      : (summary?.top_keywords || []).map((row) => row.dimension_key).filter(Boolean).slice(0, 3);
    return uniqueValues([ALL_SOURCE_LABEL, ...keywords]);
  }, [isSampleMode, sampleAnalysis, summary]);

  const platformOptions = React.useMemo(() => {
    const platforms = isSampleMode
      ? (sampleAnalysis?.platform_rows || []).map((row) => platformLabel(row.dimension_key)).slice(0, 4)
      : (summary?.top_platforms || []).map((row) => platformLabel(row.dimension_key)).filter(Boolean).slice(0, 4);
    return uniqueValues([ALL_PLATFORM_LABEL, ...platforms]);
  }, [isSampleMode, sampleAnalysis, summary]);

  const filteredLeads = React.useMemo(() => {
    return leads.filter((lead) => {
      const sourceMatched = activeSource === ALL_SOURCE_LABEL || (lead.source_keyword || "未标记") === activeSource;
      const platformMatched =
        activePlatform === ALL_PLATFORM_LABEL || platformLabel(lead.source_platform) === activePlatform;
      return sourceMatched && platformMatched;
    });
  }, [activePlatform, activeSource, leads]);

  const metricCards = React.useMemo(
    () => (isSampleMode && sampleAnalysis ? buildSampleMetricCards(sampleAnalysis) : buildMetricCards(summary?.summary)),
    [isSampleMode, sampleAnalysis, summary],
  );
  const funnelSteps = React.useMemo(
    () => (isSampleMode && sampleAnalysis ? buildSampleFunnel(sampleAnalysis) : buildFunnel(summary || undefined)),
    [isSampleMode, sampleAnalysis, summary],
  );
  const leadRows = React.useMemo(() => deriveLeadRows(filteredLeads), [filteredLeads]);
  const sampleCandidateRows = React.useMemo(
    () =>
      deriveSampleCandidateRows(sampleAnalysis).filter((row) => {
        const platformMatched = activePlatform === ALL_PLATFORM_LABEL || row.platform === activePlatform;
        const sourceMatched =
          activeSource === ALL_SOURCE_LABEL ||
          row.source.toLowerCase().includes(activeSource.toLowerCase()) ||
          row.name.toLowerCase().includes(activeSource.toLowerCase()) ||
          row.tag.toLowerCase().includes(activeSource.toLowerCase());
        return platformMatched && sourceMatched;
      }),
    [activePlatform, activeSource, sampleAnalysis],
  );
  const recommendations = React.useMemo(
    () => (isSampleMode ? deriveSampleRecommendations(sampleAnalysis) : deriveRecommendations(filteredLeads)),
    [filteredLeads, isSampleMode, sampleAnalysis],
  );
  const actionRecommendations = React.useMemo(
    () =>
      isSampleMode
        ? deriveSampleActionRecommendations(sampleAnalysis)
        : deriveActionRecommendations(summary || undefined, filteredLeads),
    [filteredLeads, isSampleMode, sampleAnalysis, summary],
  );
  const platformShare = React.useMemo(
    () =>
      isSampleMode && sampleAnalysis
        ? buildSamplePlatformShare(sampleAnalysis.platform_rows)
        : buildPlatformShare(summary?.top_platforms || []),
    [isSampleMode, sampleAnalysis, summary],
  );
  const lossReasons = React.useMemo(
    () => (isSampleMode ? buildLossReasonsFromSteps(funnelSteps) : buildLossReasons(summary || undefined)),
    [funnelSteps, isSampleMode, summary],
  );
  const displayContentRows = React.useMemo(() => {
    const rows =
      isSampleMode && sampleAnalysis
        ? sampleAnalysis.top_contents.map((row) => ({
            key: `sample-content-${row.post_id || row.title}`,
            title: row.title,
            platform: row.platform,
            primary: row.engagement_score,
            secondary: 0,
          }))
        : (summary?.top_contents || []).map((row) => ({
            key: row.dimension_key,
            title: row.title || row.dimension_key,
            platform: row.platform,
            primary: row.lead_count,
            secondary: row.deal_amount,
          }));
    return rows.filter((row) => {
      const platformMatched = activePlatform === ALL_PLATFORM_LABEL || platformLabel(row.platform) === activePlatform;
      const sourceMatched =
        activeSource === ALL_SOURCE_LABEL || String(row.title || "").toLowerCase().includes(activeSource.toLowerCase());
      return platformMatched && sourceMatched;
    });
  }, [activePlatform, activeSource, isSampleMode, sampleAnalysis, summary]);
  const displayKeywordRows = React.useMemo(
    () =>
      isSampleMode && sampleAnalysis
        ? sampleAnalysis.top_keywords.map((row) => ({
            key: row.keyword,
            label: row.keyword,
            value: row.hit_count,
          }))
        : (summary?.top_keywords || []).map((row) => ({
            key: row.dimension_key,
            label: row.dimension_key,
            value: row.qualified_lead_count,
          })),
    [isSampleMode, sampleAnalysis, summary],
  );
  const displayCoverageRows = React.useMemo(
    () =>
      isSampleMode && sampleAnalysis
        ? sampleAnalysis.platform_rows.map((row) => ({
            key: row.dimension_key,
            label: platformLabel(row.dimension_key),
            platform: row.dimension_key,
            cost: row.post_count,
            leads: row.sample_count,
            rate: row.sample_count ? row.comment_count / row.sample_count : 0,
            roi: row.comment_count,
          }))
        : (summary?.top_creators || []).map((row) => ({
            key: row.dimension_key,
            label: row.dimension_key,
            platform: row.platform,
            cost: row.cost || 0,
            leads: row.lead_count,
            rate: row.lead_count ? row.qualified_lead_count / row.lead_count : 0,
            roi: row.roi,
          })),
    [isSampleMode, sampleAnalysis, summary],
  );
  const platformTotal = isSampleMode
    ? Number(sampleAnalysis?.summary.raw_record_count || 0)
    : Number(summary?.summary.lead_count || 0);
  const readinessSteps = React.useMemo(
    () =>
      buildReadinessSteps({
        isSampleMode,
        sample: sampleAnalysis,
        summary,
        leads,
      }),
    [isSampleMode, leads, sampleAnalysis, summary],
  );
  const modeInsight = React.useMemo(
    () =>
      buildModeInsight({
        isSampleMode,
        sample: sampleAnalysis,
        summary,
        readinessSteps,
      }),
    [isSampleMode, readinessSteps, sampleAnalysis, summary],
  );

  const handleExportReport = React.useCallback(() => {
    if (!summary) return;
    const payload = {
      exported_at: new Date().toISOString(),
      mode: isSampleMode ? "sample_analysis" : "lead_attribution",
      scope: isGlobalScope ? "global" : "project",
      active_workspace: activeWorkspace,
      project_id: summary.project_id,
      project_name: summary.project_name,
      summary,
      leads,
      readiness_steps: readinessSteps,
    };
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `lead-attribution-${String(summary.project_id)}-${new Date().toISOString().slice(0, 10)}.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  }, [activeWorkspace, isGlobalScope, isSampleMode, leads, readinessSteps, summary]);

  const handleActionClick = React.useCallback((item: ActionRecommendation) => {
    const text = `${item.title} ${item.cta}`;
    if (text.includes("导入") || text.includes("触点") || text.includes("模板")) {
      setTemplateOpen(true);
      setActiveWorkspace("attribution");
      return;
    }
    if (text.includes("样本") || text.includes("采集")) {
      setActiveWorkspace("sample");
      return;
    }
    setActiveWorkspace("overview");
  }, []);

  const loadLeadDetail = React.useCallback(
    async (leadId: number, currentModel: AttributionModel) => {
      setDetailLoading(true);
      setDetailError(null);
      try {
        const [detail, timeline] = await Promise.all([
          api<LeadDetailResponse>(`/api/research/leads/${leadId}?model=${encodeURIComponent(currentModel)}`),
          api<LeadTimelineResponse>(`/api/research/leads/${leadId}/timeline?model=${encodeURIComponent(currentModel)}`),
        ]);
        setLeadDetail(detail);
        setLeadTimeline(timeline);
      } catch (requestError) {
        const message = requestError instanceof ApiError ? requestError.message : "线索详情加载失败，请稍后重试。";
        setDetailError(message);
      } finally {
        setDetailLoading(false);
      }
    },
    [],
  );

  const loadPageData = React.useCallback(
    async (mode: "initial" | "refresh" = "initial", requestedProjectId?: string) => {
      const requestId = pageRequestIdRef.current + 1;
      pageRequestIdRef.current = requestId;
      if (mode === "initial") setLoading(true);
      if (mode === "refresh") setRefreshing(true);
      setError(null);
      try {
        const projectResponse = await api<{ projects: GrowthProjectSummary[] }>("/api/research/growth-projects");
        if (requestId !== pageRequestIdRef.current) return;
        const nextProjects = projectResponse.projects || [];
        setProjects(nextProjects);
        const preferredProjectId = requestedProjectId || projectIdRef.current;
        const wantsGlobalScope = preferredProjectId === GLOBAL_PROJECT_ID;
        if (!nextProjects.length && !wantsGlobalScope) {
          projectIdRef.current = "";
          setProjectId("");
          setConfig(null);
          setSummary(null);
          setLeads([]);
          return;
        }
        const resolvedProjectId = wantsGlobalScope
          ? GLOBAL_PROJECT_ID
          : preferredProjectId && nextProjects.some((project) => String(project.id) === preferredProjectId)
            ? preferredProjectId
            : String(nextProjects[0].id);
        projectIdRef.current = resolvedProjectId;
        setProjectId(resolvedProjectId);
        if (resolvedProjectId === GLOBAL_PROJECT_ID) {
          setConfig(GLOBAL_ATTRIBUTION_CONFIG);
          const [summaryResponse, leadsResponse] = await Promise.all([
            api<LeadAttributionSummaryPayload>("/api/reports/lead-attribution/summary?scope=global"),
            api<{ leads: LeadListItem[] }>("/api/research/leads?scope=global"),
          ]);
          if (requestId !== pageRequestIdRef.current) return;
          setSummary(summaryResponse);
          setLeads(leadsResponse.leads || []);
          return;
        }
        const configResponse = await api<{ config: LeadAttributionConfig }>(
          `/api/research/growth-projects/${encodeURIComponent(resolvedProjectId)}/attribution-config`,
        );
        if (requestId !== pageRequestIdRef.current) return;
        setConfig(configResponse.config);
        const resolvedModel = configResponse.config.default_model;
        const [summaryResponse, leadsResponse] = await Promise.all([
          api<LeadAttributionSummaryPayload>(
            `/api/reports/lead-attribution/summary?project_id=${encodeURIComponent(resolvedProjectId)}&model=${encodeURIComponent(resolvedModel)}`,
          ),
          api<{ leads: LeadListItem[] }>(
            `/api/research/growth-projects/${encodeURIComponent(resolvedProjectId)}/leads`,
          ),
        ]);
        if (requestId !== pageRequestIdRef.current) return;
        setSummary(summaryResponse);
        setLeads(leadsResponse.leads || []);
      } catch (requestError) {
        if (requestId !== pageRequestIdRef.current) return;
        const message = requestError instanceof ApiError ? requestError.message : "归因页加载失败，请检查后端服务。";
        setError(message);
      } finally {
        if (requestId === pageRequestIdRef.current) {
          setLoading(false);
          setRefreshing(false);
        }
      }
    },
    [],
  );

  const handleProjectChange = React.useCallback(
    (nextProjectId: string) => {
      if (!nextProjectId || nextProjectId === projectIdRef.current) return;
      projectIdRef.current = nextProjectId;
      setProjectId(nextProjectId);
      setSelectedLeadId(null);
      setLeadDetail(null);
      setLeadTimeline(null);
      setDetailError(null);
      setError(null);
      setActiveSource(ALL_SOURCE_LABEL);
      setActivePlatform(ALL_PLATFORM_LABEL);
      setActiveWorkspace("overview");
      setConfig(null);
      setSummary(null);
      setLeads([]);
      void loadPageData("initial", nextProjectId);
    },
    [loadPageData],
  );

  React.useEffect(() => {
    void loadPageData("initial");
  }, [loadPageData]);

  React.useEffect(() => {
    if (selectedLeadId == null || !config) {
      setLeadDetail(null);
      setLeadTimeline(null);
      return;
    }
    void loadLeadDetail(selectedLeadId, model);
  }, [config, loadLeadDetail, model, selectedLeadId]);

  return (
    <section className="la-page">
      <div className="la-hero">
        <div className="la-hero__nav">
          <div className="la-project-select" aria-label="当前归因项目">
            <span className="la-project-pill__mark">归</span>
            {projectOptions.length ? (
              <Select
                label="切换归因项目"
                value={projectId || projectOptions[0]?.value || ""}
                onValueChange={handleProjectChange}
                options={projectOptions}
              />
            ) : (
              <span className="la-project-select__empty">
                {currentProject?.name || summary?.project_name || "线索归因项目"}
              </span>
            )}
          </div>

          <label className="la-hero__search">
            <Search size={16} />
            <input readOnly type="text" value={activeSource === ALL_SOURCE_LABEL ? "搜索内容 / 账号 / 话题 / 关键词" : activeSource} />
          </label>

          <div className="la-hero__actions">
            <button
              type="button"
              className={`la-hero__ghost ${activeWorkspace === "sample" ? "is-active" : ""}`}
              onClick={() => setActiveWorkspace("sample")}
            >
              <Sparkles size={15} />
              {isSampleMode ? "样本分析" : MODEL_LABELS[model]}
            </button>
            <button
              type="button"
              className={`la-hero__ghost ${activeWorkspace === "overview" ? "is-active" : ""}`}
              onClick={() => setActiveWorkspace("overview")}
            >
              <CalendarRange size={15} />
              {formatDateRange(summary?.summary)}
            </button>
            <button type="button" className="la-hero__ghost" onClick={() => void loadPageData("refresh")}>
              <RefreshCw size={15} />
              {refreshing ? "刷新中" : "刷新"}
            </button>
            <Button variant="ghost" onClick={handleExportReport} disabled={!summary}>
              <Download size={15} />
              导出报告
            </Button>
          </div>
        </div>

        <div className="la-hero__title">
          <div>
            <span className="la-kicker">Lead Attribution</span>
            <h1>线索转化与归因</h1>
            <p>
              {isGlobalScope
                ? "基于当前数据库全部爬虫任务、帖子、评论和线索数据，统一查看全局潜在线索入口与转化归因。"
                : "基于项目真实线索、触点、转化和成本数据，统一查看转化效率、归因结果与高优先级动作。"}
            </p>
          </div>
          <div className="la-hero__badge">
            <Orbit size={18} />
            <span>{isGlobalScope ? "全局数据" : isSampleMode ? "采集样本" : config ? `窗口 ${config.window_days} 天` : "增长驾驶舱"}</span>
          </div>
        </div>
      </div>

      {error ? (
        <Card className="la-panel">
          <div className="la-panel__head">
            <div>
              <h2>数据加载失败</h2>
              <p>{error}</p>
            </div>
            <Button variant="ghost" onClick={() => void loadPageData("initial")}>
              <RefreshCw size={15} />
              重试
            </Button>
          </div>
        </Card>
      ) : null}

      <Card className="la-panel la-mode-panel">
        <div className="la-mode-panel__summary">
          <span className="la-kicker">Attribution State</span>
          <h2>{modeInsight.title}</h2>
          <p>{modeInsight.body}</p>
          <div className="la-mode-panel__metrics">
            <strong>{modeInsight.primaryMetric}</strong>
            <span>{modeInsight.secondaryMetric}</span>
          </div>
          <div className="la-workspace-tabs" role="tablist" aria-label="归因分析视角">
            {[
              ["overview", "闭环状态"],
              ["sample", "潜在线索入口"],
              ["attribution", "正式归因数据"],
            ].map(([key, label]) => (
              <button
                key={key}
                type="button"
                className={activeWorkspace === key ? "is-active" : ""}
                onClick={() => setActiveWorkspace(key as AttributionWorkspace)}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
        <div className="la-readiness-grid">
          {readinessSteps.map((step, index) => (
            <button
              key={step.key}
              type="button"
              className={`la-readiness-card status-${step.status} ${activeWorkspace === step.workspace ? "is-focused" : ""}`}
              onClick={() => setActiveWorkspace(step.workspace)}
            >
              <div className="la-readiness-card__top">
                <span className="la-readiness-card__index">{String(index + 1).padStart(2, "0")}</span>
                <b>{readinessStatusLabel(step.status)}</b>
              </div>
              <div className="la-readiness-card__body">
                <strong>{step.title}</strong>
                <p>{step.description}</p>
              </div>
              <em>{step.metric}</em>
            </button>
          ))}
        </div>
        <div className="la-mode-panel__actions">
          <Button variant="ghost" onClick={() => setActiveWorkspace("sample")}>
            查看候选样本
          </Button>
          <Button variant="ghost" onClick={() => setTemplateOpen(true)}>
            归因字段模板
          </Button>
          <Button variant="ghost" onClick={handleExportReport} disabled={!summary}>
            <Download size={15} />
            导出当前分析
          </Button>
        </div>
      </Card>

      {loading ? (
        <div className="la-metric-grid">
          {Array.from({ length: 7 }).map((_, index) => (
            <Card key={index} className="la-metric-card">
              <Skeleton />
              <Skeleton />
              <Skeleton />
            </Card>
          ))}
        </div>
      ) : (
        <div className="la-metric-grid">
          {metricCards.map((card, index) => (
            <article
              key={card.label}
              className={`la-metric-card accent-${card.accent}`}
              style={{ animationDelay: `${index * 60}ms` }}
            >
              <div className="la-metric-card__head">
                <span>{card.label}</span>
                <i>{card.icon}</i>
              </div>
              <strong>{card.value}</strong>
              <small>{card.delta}</small>
              <Sparkline points={card.points} accent={card.accent} />
            </article>
          ))}
        </div>
      )}

      <div className="la-main-grid">
        <Card className="la-panel la-funnel-panel">
          <div className="la-panel__head">
            <div>
              <h2>{isSampleMode ? "样本分析漏斗" : "线索转化漏斗"}</h2>
              <p>{isSampleMode ? "基于现有采集样本识别潜在线索入口。" : "当前归因模型下的关键转化节点。"}</p>
            </div>
            <button type="button" className="la-soft-chip">
              {isSampleMode ? "样本模式" : MODEL_LABELS[model]}
            </button>
          </div>
          <div className="la-funnel">
            <div className="la-funnel__axis" aria-hidden="true" />
            {funnelSteps.map((step: LeadAttributionFunnelStep & { width: number }, index) => (
              <div
                key={`funnel-${step.key || step.label || index}`}
                className="la-funnel__row"
                style={{ "--funnel-width": `${step.width}%` } as React.CSSProperties}
              >
                <span className="la-funnel__ordinal">{String(index + 1).padStart(2, "0")}</span>
                <div className={`la-funnel__shape la-funnel__shape--${index}`}>
                  <i className="la-funnel__shine" aria-hidden="true" />
                  <span className="la-funnel__label">{step.label}</span>
                  <strong>{formatNumber(step.value)}</strong>
                </div>
                <em className="la-funnel__rate">{formatRatio(step.rate)}</em>
              </div>
            ))}
          </div>
        </Card>

        <Card className="la-panel la-table-panel">
          <div className="la-panel__head">
            <div>
              <h2>{isSampleMode ? "线索候选样本" : "线索列表"}</h2>
              <p>
                {isSampleMode
                  ? `当前无线索闭环，从 ${formatNumber(sampleAnalysis?.summary.raw_record_count || 0)} 条采集样本中筛出 ${formatNumber(sampleCandidateRows.length)} 个候选入口。`
                  : `共 ${formatNumber(filteredLeads.length)} 条，按来源和平台筛选。`}
              </p>
            </div>
            <div className="la-filter-row">
              {sourceOptions.map((option, index) => (
                <button
                  key={`source-${option || index}`}
                  type="button"
                  className={`la-filter-chip ${activeSource === option ? "is-active" : ""}`}
                  onClick={() => setActiveSource(option)}
                >
                  {option}
                </button>
              ))}
              {platformOptions.map((option, index) => (
                <button
                  key={`platform-filter-${option || index}`}
                  type="button"
                  className={`la-filter-chip ${activePlatform === option ? "is-active" : ""}`}
                  onClick={() => setActivePlatform(option)}
                >
                  {option}
                </button>
              ))}
              <button type="button" className="la-filter-chip">
                <Filter size={14} />
                实时筛选
              </button>
            </div>
          </div>

          <div className="la-table-wrap">
            <table className="la-table">
              <thead>
                <tr>
                  <th>{isSampleMode ? "候选样本" : "线索"}</th>
                  <th>来源平台</th>
                  <th>来源关键词</th>
                  <th>标签</th>
                  <th>意向分</th>
                  <th>{isSampleMode ? "识别阶段" : "跟进阶段"}</th>
                  <th>{isSampleMode ? "建议动作" : "最新动作"}</th>
                  <th>{isSampleMode ? "样本来源" : "负责人"}</th>
                </tr>
              </thead>
              <tbody>
                {isSampleMode && sampleCandidateRows.length ? (
                  sampleCandidateRows.map((row) => (
                    <tr key={row.id}>
                      <td>
                        <div className="la-name-cell">
                          <span className="la-avatar-dot">{row.name.slice(0, 1)}</span>
                          <strong>{row.name}</strong>
                        </div>
                      </td>
                      <td>{row.platform}</td>
                      <td className="is-dense">{row.source}</td>
                      <td>
                        <span className="la-inline-tag">{row.tag}</span>
                      </td>
                      <td className="is-score">{row.score}</td>
                      <td>
                        <span className={`la-stage-pill stage-${stageTone(row.score)}`}>{row.stage}</span>
                      </td>
                      <td className="is-dense">
                        <strong>{row.nextAction}</strong>
                        <span>{row.latest}</span>
                      </td>
                      <td>{row.owner}</td>
                    </tr>
                  ))
                ) : !isSampleMode && leadRows.length ? (
                  leadRows.map((row) => (
                    <tr key={row.id} onClick={() => setSelectedLeadId(row.id)} style={{ cursor: "pointer" }}>
                      <td>
                        <div className="la-name-cell">
                          <span className="la-avatar-dot">{row.name.slice(0, 1)}</span>
                          <strong>{row.name}</strong>
                        </div>
                      </td>
                      <td>{row.platform}</td>
                      <td className="is-dense">{row.source}</td>
                      <td>
                        <span className="la-inline-tag">{row.tag}</span>
                      </td>
                      <td className="is-score">{row.score}</td>
                      <td>
                        <span className={`la-stage-pill stage-${stageTone(row.score)}`}>{row.stage}</span>
                      </td>
                      <td className="is-dense">
                        <strong>{row.nextAction}</strong>
                        <span>{row.updatedAt}</span>
                      </td>
                      <td>{row.owner}</td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={8}>
                      {isSampleMode ? "当前采集样本还没有形成可展示的内容、关键词或意向词候选。" : "当前筛选条件下暂无线索。"}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </Card>

        <div className="la-side-stack">
          <Card className="la-panel">
            <div className="la-panel__head">
              <div>
                <h2>{isSampleMode ? "潜在线索入口" : "高潜线索推荐"}</h2>
                <p>{isSampleMode ? "按内容互动和意向评论识别可转线索入口。" : "按线索质量分和最近触点优先排序。"}</p>
              </div>
              <button type="button" className="la-link-btn">
                查看全部 <ChevronRight size={14} />
              </button>
            </div>
            <div className="la-recommend-list">
              {recommendations.map((item) => (
                <article key={item.leadId} className="la-recommend-card">
                  <span className="la-avatar-dot">{item.name.slice(0, 1)}</span>
                  <div>
                    <div className="la-recommend-card__top">
                      <strong>{item.name}</strong>
                      <b>{item.score}</b>
                    </div>
                    <div className="la-chip-row">
                      {item.labels.map((label, index) => (
                        <span key={`${item.leadId}-${label || index}`}>{label}</span>
                      ))}
                    </div>
                    <p>{item.reason}</p>
                  </div>
                  <Button variant="ghost" onClick={() => (item.leadId > 0 ? setSelectedLeadId(item.leadId) : undefined)}>
                    {item.action}
                  </Button>
                </article>
              ))}
            </div>
          </Card>

          <Card className="la-panel">
            <div className="la-panel__head">
              <div>
                <h2>{isSampleMode ? "样本缺口分析" : "流失分析"}</h2>
                <p>{isSampleMode ? "识别采集样本到意向信号之间的断层。" : "自动识别当前漏斗中的主要断层。"}</p>
              </div>
              <button type="button" className="la-link-btn">
                查看详情 <ChevronRight size={14} />
              </button>
            </div>
            <div className="la-loss-grid">
              <div className="la-loss-bars">
                {funnelSteps.slice(0, 5).map((step, index) => (
                  <div key={`loss-step-${step.key || step.label || index}`} className="la-loss-row">
                    <span>{step.label}</span>
                    <div>
                      <i style={{ width: `${Math.max(step.width * 0.8, 18)}%` }} />
                    </div>
                    <strong>{formatNumber(step.value)}</strong>
                  </div>
                ))}
              </div>
              <div className="la-loss-reasons">
                {lossReasons.map((item) => (
                  <div key={item.label}>
                    <span>{item.label}</span>
                    <strong>{item.percent}</strong>
                  </div>
                ))}
              </div>
            </div>
          </Card>
        </div>
      </div>

      <div className="la-analytics-grid">
        <Card className="la-panel la-wide-panel">
          <div className="la-panel__head">
            <div>
              <h2>{isSampleMode ? "内容样本分析" : "内容归因分析"}</h2>
              <p>{isSampleMode ? "用现有帖子样本识别高互动和高潜内容入口。" : "识别带来线索、成交和 ROI 的内容来源。"}</p>
            </div>
            <button type="button" className="la-link-btn">
              查看明细 <ChevronRight size={14} />
            </button>
          </div>
          <div className="la-triple-grid">
            <div className="la-mini-table">
              <div className="la-mini-table__head">
                <span>内容</span>
                <span>平台</span>
                <span>{isSampleMode ? "互动" : "线索"}</span>
                <span>{isSampleMode ? "状态" : "成交金额"}</span>
              </div>
              {displayContentRows.slice(0, 3).map((row, index) => (
                <div key={`content-row-${row.key || index}`} className="la-mini-table__row">
                  <strong>{row.title}</strong>
                  <span>{platformLabel(row.platform)}</span>
                  <span>{formatNumber(row.primary)}</span>
                  <span className="is-accent">{isSampleMode ? "样本" : formatMoney(row.secondary)}</span>
                </div>
              ))}
            </div>
            <div className="la-ranked-list">
              <h3>内容标题 TOP5</h3>
              {displayContentRows.slice(0, 5).map((row, index) => (
                <div key={`content-rank-${row.key || index}`}>
                  <span>{index + 1}</span>
                  <strong>{row.title}</strong>
                  <em>{isSampleMode ? "互动" : "线索"} {formatNumber(row.primary)}</em>
                </div>
              ))}
            </div>
            <div className="la-ranked-list">
              <h3>关键词 TOP5</h3>
              {displayKeywordRows.slice(0, 5).map((row, index) => (
                <div key={`keyword-rank-${row.key || index}`}>
                  <span>{index + 1}</span>
                  <strong>{row.label}</strong>
                  <em>{isSampleMode ? "命中" : "有效线索"} {formatNumber(row.value)}</em>
                </div>
              ))}
            </div>
          </div>
        </Card>

        <Card className="la-panel">
          <div className="la-panel__head">
            <div>
              <h2>{isSampleMode ? "平台样本覆盖" : "达人归因"}</h2>
              <p>{isSampleMode ? "按平台展示帖子、评论和样本覆盖。" : "最近窗口内达人带来的线索、成本和 ROI。"}</p>
            </div>
          </div>
          <div className="la-mini-table la-mini-table--compact">
            <div className="la-mini-table__head">
              <span>{isSampleMode ? "平台" : "达人"}</span>
              <span>平台</span>
              <span>{isSampleMode ? "帖子" : "成本"}</span>
              <span>{isSampleMode ? "样本" : "线索"}</span>
              <span>{isSampleMode ? "评论占比" : "有效率"}</span>
              <span>{isSampleMode ? "评论" : "ROI"}</span>
            </div>
            {displayCoverageRows.slice(0, 5).map((row, index) => (
              <div key={`creator-row-${row.key || index}`} className="la-mini-table__row">
                <strong>{row.label}</strong>
                <span>{platformLabel(row.platform)}</span>
                <span>{isSampleMode ? formatNumber(row.cost) : formatMoney(row.cost)}</span>
                <span>{formatNumber(row.leads)}</span>
                <span>{formatRatio(row.rate)}</span>
                <span className="is-accent">{isSampleMode ? formatNumber(row.roi || 0) : row.roi != null ? Number(row.roi).toFixed(2) : "--"}</span>
              </div>
            ))}
          </div>
          <button type="button" className="la-link-btn is-inline">
            {isSampleMode ? "查看样本覆盖详情" : "查看达人归因详情"} <ChevronRight size={14} />
          </button>
        </Card>

        <Card className="la-panel">
          <div className="la-panel__head">
            <div>
              <h2>{isSampleMode ? "平台样本分布" : "平台归因"}</h2>
              <p>{isSampleMode ? "当前项目采集样本的平台占比和量级分布。" : "最近窗口内的平台线索占比和量级分布。"}</p>
            </div>
          </div>
          <div className="la-platform-card">
            <DonutRingRefined items={platformShare} total={platformTotal} />
            <div className="la-platform-legend">
              {platformShare.map((item, index) => (
                <div key={`platform-share-${item.label}-${index}`}>
                  <span>
                    <i style={{ background: item.color }} />
                    {item.label}
                  </span>
                  <strong>{item.percent}</strong>
                  <em>{item.count}</em>
                </div>
              ))}
            </div>
          </div>
          <button type="button" className="la-link-btn is-inline">
            查看平台归因详情 <ChevronRight size={14} />
          </button>
        </Card>

        <Card className="la-panel">
          <div className="la-panel__head">
            <div>
              <h2>推荐动作</h2>
              <p>基于当前归因表现自动生成优先动作。</p>
            </div>
          </div>
          <div className="la-action-list">
            {actionRecommendations.map((item) => (
              <article key={item.title}>
                <div className="la-action-icon">
                  <Target size={16} />
                </div>
                <div>
                  <strong>{item.title}</strong>
                  <p>{item.description}</p>
                </div>
                <Button variant="ghost" onClick={() => handleActionClick(item)}>{item.cta}</Button>
              </article>
            ))}
          </div>
        </Card>
      </div>

      <div className="la-footer-bar">
        <strong>快捷操作</strong>
        <div className="la-footer-bar__actions">
          <button type="button" onClick={() => setTemplateOpen(true)}>
            <Users size={15} />
            线索承接中心
          </button>
          <button type="button" onClick={() => setActiveWorkspace("attribution")}>
            <Flame size={15} />
            跟进任务
          </button>
          <button type="button" onClick={() => setActiveWorkspace("sample")}>
            <TrendingUp size={15} />
            内容归因报表
          </button>
          <button type="button" onClick={() => setActiveWorkspace("sample")}>
            <CheckCircle2 size={15} />
            达人归因报表
          </button>
          <button type="button" onClick={handleExportReport}>
            <Download size={15} />
            导出数据
          </button>
        </div>
      </div>

      <Drawer
        open={templateOpen}
        onOpenChange={setTemplateOpen}
        title="归因数据字段模板"
      >
        <div className="la-template-drawer">
          <p className="la-template-drawer__intro">
            要从样本分析进入正式归因，需要把业务线索、触点、转化事件和成本数据导入到同一个项目下。
          </p>
          {[
            {
              title: "1. 线索主表",
              body: "用于确认谁是线索，以及这条线索最初来自哪里。",
              fields: ["external_lead_id", "lead_status", "source_platform", "source_keyword", "owner", "lead_score"],
            },
            {
              title: "2. 触点路径",
              body: "用于记录线索接触过哪些内容、达人、关键词或平台。",
              fields: ["external_lead_id", "touch_type", "platform", "source_keyword", "post_id", "creator_id", "touch_time"],
            },
            {
              title: "3. 转化事件",
              body: "用于标记加微、首聊、有效线索、成交等业务结果。",
              fields: ["external_lead_id", "event_type", "event_time", "event_value", "source_system", "operator"],
            },
            {
              title: "4. 成本数据",
              body: "用于计算 CPL、有效线索成本和 ROI。",
              fields: ["spend_date", "dimension", "dimension_key", "amount", "source_system"],
            },
          ].map((section) => (
            <Card key={section.title} className="la-template-card">
              <h3>{section.title}</h3>
              <p>{section.body}</p>
              <div className="la-template-card__fields">
                {section.fields.map((field) => (
                  <code key={field}>{field}</code>
                ))}
              </div>
            </Card>
          ))}
          <div className="la-template-drawer__footer">
            <Button variant="ghost" onClick={() => setActiveWorkspace("attribution")}>
              返回归因数据区
            </Button>
            <Button variant="ghost" onClick={handleExportReport} disabled={!summary}>
              <Download size={15} />
              导出当前分析 JSON
            </Button>
          </div>
        </div>
      </Drawer>

      <Drawer
        open={selectedLeadId != null}
        onOpenChange={(open) => {
          if (!open) {
            setSelectedLeadId(null);
            setLeadDetail(null);
            setLeadTimeline(null);
            setDetailError(null);
          }
        }}
        title={leadDetail?.lead.name_masked || leadDetail?.lead.external_lead_id || "线索详情"}
      >
        <div style={{ display: "grid", gap: 16 }}>
          {detailLoading ? (
            <>
              <Skeleton />
              <Skeleton />
              <Skeleton />
            </>
          ) : detailError ? (
            <p>{detailError}</p>
          ) : leadDetail ? (
            <>
              <Card className="la-panel">
                <div className="la-panel__head">
                  <div>
                    <h2>归因解释</h2>
                    <p>{leadDetail.attribution_explanation.narrative}</p>
                  </div>
                  <button type="button" className="la-soft-chip">
                    {MODEL_LABELS[(leadDetail.attribution_explanation.model as AttributionModel) || model] || model}
                  </button>
                </div>
                <div className="la-loss-reasons">
                  <div>
                    <span>转化事件</span>
                    <strong>{leadDetail.attribution_explanation.conversion_summary.event_types.join(" / ") || "--"}</strong>
                  </div>
                  <div>
                    <span>成交金额</span>
                    <strong>{formatMoney(leadDetail.attribution_explanation.conversion_summary.deal_amount)}</strong>
                  </div>
                  <div>
                    <span>触点数</span>
                    <strong>{formatNumber(leadDetail.attribution_explanation.touchpoint_summary.touch_count)}</strong>
                  </div>
                  <div>
                    <span>胜出触点</span>
                    <strong>{leadDetail.attribution_explanation.touchpoint_summary.winning_touch_type || "--"}</strong>
                  </div>
                </div>
              </Card>

              <Card className="la-panel">
                <div className="la-panel__head">
                  <div>
                    <h2>触点时间线</h2>
                    <p>按当前模型标记胜出、辅助和窗口外触点。</p>
                  </div>
                </div>
                <div className="la-action-list">
                  {(leadTimeline?.timeline || []).map((entry, index) => (
                    <article key={`${entry.kind}-${entry.time || index}`}>
                      <div className="la-action-icon" style={{ color: roleColor(entry.role) }}>
                        {entry.kind === "conversion_event" ? <BadgeCheck size={16} /> : <Target size={16} />}
                      </div>
                      <div>
                        <strong>
                          {timelineTitle(entry)}
                          {entry.kind === "touchpoint" ? ` · ${roleLabel(entry.role)}` : ""}
                        </strong>
                        <p>
                          {formatTimestamp(entry.time)} ·{" "}
                          {"platform" in entry.payload ? platformLabel(entry.payload.platform) : "转化"} ·{" "}
                          {"source_keyword" in entry.payload
                            ? entry.payload.source_keyword || "未标记"
                            : "event_value" in entry.payload
                              ? formatMoney(entry.payload.event_value)
                              : "--"}
                        </p>
                      </div>
                    </article>
                  ))}
                </div>
              </Card>
            </>
          ) : (
            <p>请选择线索查看详情。</p>
          )}
        </div>
      </Drawer>
    </section>
  );
}
