import React from "react";
import {
  Radar,
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  ResponsiveContainer,
} from "recharts";
import {
  Bookmark,
  Bot,
  Check,
  ChevronsUpDown,
  CircleDollarSign,
  Download,
  Eye,
  Loader2,
  Plus,
  RefreshCw,
  Search,
  Sparkles,
  Star,
  Target,
  TrendingUp,
  Users,
} from "lucide-react";
import { api } from "../../utils/api";
import "./styles.css";

type PlatformKey = "all" | "douyin" | "xiaohongshu" | "bilibili" | "weibo";
type TierKey = "recommended" | "A" | "B" | "C";

type Dimension = {
  label: string;
  value: number;
  max: number;
};

type EvidenceCard = {
  title: string;
  stats: string;
  date: string;
  tone: string;
};

type CreatorRecord = {
  id: number;
  name: string;
  subtitle: string;
  tags: string[];
  platform: Exclude<PlatformKey, "all">;
  creatorId?: string;
  backendPlatform?: string;
  matchScore: number;
  tier: Exclude<TierKey, "recommended">;
  followersWan: number;
  followerCount?: number | null;
  posts30d: number;
  engagementRate: number | null;
  viralRate: number | null;
  commercialSignals: string[];
  hasRealtimeSource?: boolean;
  favorited: boolean;
  avatarTone: string;
  platformHandle: string;
  profileUrl?: string;
  updatedAt: string;
  dimensions: Dimension[];
  keywords: string[];
  commerceFacts: Array<{ label: string; value: string }>;
  hotTopics: Array<{ label: string; heat: string }>;
  evidences: EvidenceCard[];
};

type UnknownRecord = Record<string, unknown>;

type VerticalOption = {
  id: number;
  code: string;
  name: string;
  enabled?: boolean;
};

type CreatorSearchResponse = {
  diagnostics?: UnknownRecord;
  realtime?: UnknownRecord;
  progress?: UnknownRecord;
  results?: UnknownRecord[];
};

type CreatorCandidatePoolResponse = {
  candidates?: UnknownRecord[];
};

type CreatorSearchSessionResponse = {
  session?: UnknownRecord | null;
};

type AnalysisStatus = "idle" | "loading" | "done" | "error";
type ProcessStepState = "pending" | "active" | "done" | "error";
const DEFAULT_REALTIME_RATIO = "50";
const DEFAULT_PAGE_SIZE = "10";

type DiscoveryFilters = {
  followerMinCount: string;
  followerMaxCount: string;
  recentPostsMin: string;
  activityLevel: "any" | "active" | "highly" | "dormant";
  engagementMinPercent: string;
  viralMinPercent: string;
};

const DEFAULT_FILTERS: DiscoveryFilters = {
  followerMinCount: "100",
  followerMaxCount: "",
  recentPostsMin: "1",
  activityLevel: "any",
  engagementMinPercent: "",
  viralMinPercent: "",
};

const TAB_LABELS: Record<TierKey, string> = {
  recommended: "推荐",
  A: "A 类 精准匹配",
  B: "B 类 高潜达人",
  C: "C 类 拓展达人",
};

const PLATFORM_LABELS: Record<PlatformKey, string> = {
  all: "全平台",
  douyin: "抖音",
  xiaohongshu: "小红书",
  bilibili: "哔哩哔哩",
  weibo: "微博",
};

const RECORDS: CreatorRecord[] = [
  {
    id: 1,
    name: "猫宁日记",
    subtitle: "专注宠物主粮测评与科学喂养",
    tags: ["测评", "科普"],
    platform: "douyin",
    matchScore: 93,
    tier: "A",
    followersWan: 168.7,
    posts30d: 8,
    engagementRate: 6.38,
    viralRate: 18.2,
    commercialSignals: ["¥", "品牌合作"],
    favorited: false,
    avatarTone: "linear-gradient(135deg, #f1d1b5, #b87a4e)",
    platformHandle: "抖音 ID: maoningriji",
    updatedAt: "2026-05-22",
    dimensions: [
      { label: "内容相关性", value: 24, max: 25 },
      { label: "受众匹配度", value: 23, max: 25 },
      { label: "互动表现", value: 22, max: 25 },
      { label: "商业化能力", value: 18, max: 20 },
      { label: "安全合规", value: 12, max: 15 },
    ],
    keywords: ["新手养猫", "主粮测评", "猫粮推荐", "宠物营养", "科学喂养"],
    commerceFacts: [
      { label: "报价区间", value: "¥8,000 - ¥20,000" },
      { label: "预估品牌率", value: "96%" },
      { label: "合作品牌数", value: "12" },
      { label: "近30天合作", value: "3" },
    ],
    hotTopics: [
      { label: "#新手养猫", heat: "1,285万" },
      { label: "#猫粮推荐", heat: "862万" },
      { label: "#宠物主粮", heat: "734万" },
    ],
    evidences: [
      { title: "新手猫粮怎么选？主粮怎么吃？", stats: "12万 / 346", date: "05-18", tone: "tone-one" },
      { title: "红黑榜测评主粮思路", stats: "8.7万 / 221", date: "05-12", tone: "tone-two" },
      { title: "新手养猫常见误区盘点", stats: "6.2万 / 198", date: "05-06", tone: "tone-three" },
      { title: "性价比高的冻干拌粮", stats: "5.8万 / 173", date: "04-29", tone: "tone-four" },
    ],
  },
  {
    id: 2,
    name: "奶糖是只猫呀",
    subtitle: "科学养猫干货｜主粮测评",
    tags: ["测评", "分享"],
    platform: "xiaohongshu",
    matchScore: 91,
    tier: "A",
    followersWan: 112.3,
    posts30d: 6,
    engagementRate: 5.21,
    viralRate: 16.7,
    commercialSignals: ["¥", "店播"],
    favorited: false,
    avatarTone: "linear-gradient(135deg, #f3c5cc, #cf7d8b)",
    platformHandle: "小红书 ID: naitangmiaoya",
    updatedAt: "2026-05-22",
    dimensions: [
      { label: "内容相关性", value: 23, max: 25 },
      { label: "受众匹配度", value: 22, max: 25 },
      { label: "互动表现", value: 21, max: 25 },
      { label: "商业化能力", value: 17, max: 20 },
      { label: "安全合规", value: 13, max: 15 },
    ],
    keywords: ["幼猫主粮", "主粮测评", "养猫分享", "主粮避雷"],
    commerceFacts: [
      { label: "报价区间", value: "¥6,000 - ¥16,000" },
      { label: "预估品牌率", value: "91%" },
      { label: "合作品牌数", value: "9" },
      { label: "近30天合作", value: "2" },
    ],
    hotTopics: [
      { label: "#幼猫主粮", heat: "523万" },
      { label: "#养猫避雷", heat: "401万" },
      { label: "#主粮推荐", heat: "298万" },
    ],
    evidences: [
      { title: "科学养猫主粮清单", stats: "9.8万 / 188", date: "05-20", tone: "tone-two" },
      { title: "预算档猫粮怎么选", stats: "7.1万 / 130", date: "05-10", tone: "tone-one" },
      { title: "高蛋白主粮实测", stats: "5.6万 / 95", date: "05-08", tone: "tone-four" },
      { title: "冻干拌粮思路", stats: "4.9万 / 87", date: "04-28", tone: "tone-three" },
    ],
  },
  {
    id: 3,
    name: "宠物研究所所长",
    subtitle: "宠物营养师｜科学喂养",
    tags: ["科普", "测评"],
    platform: "douyin",
    matchScore: 89,
    tier: "B",
    followersWan: 156.8,
    posts30d: 10,
    engagementRate: 4.12,
    viralRate: 12.3,
    commercialSignals: ["¥", "测评"],
    favorited: false,
    avatarTone: "linear-gradient(135deg, #a8c7dd, #5f88a5)",
    platformHandle: "抖音 ID: petresearchlab",
    updatedAt: "2026-05-22",
    dimensions: [
      { label: "内容相关性", value: 22, max: 25 },
      { label: "受众匹配度", value: 21, max: 25 },
      { label: "互动表现", value: 19, max: 25 },
      { label: "商业化能力", value: 16, max: 20 },
      { label: "安全合规", value: 14, max: 15 },
    ],
    keywords: ["宠物营养", "科学喂养", "猫粮成分", "主粮评测"],
    commerceFacts: [
      { label: "报价区间", value: "¥7,500 - ¥18,000" },
      { label: "预估品牌率", value: "88%" },
      { label: "合作品牌数", value: "7" },
      { label: "近30天合作", value: "2" },
    ],
    hotTopics: [
      { label: "#宠物营养", heat: "488万" },
      { label: "#科学喂养", heat: "376万" },
      { label: "#猫粮成分", heat: "240万" },
    ],
    evidences: [
      { title: "猫粮成分表怎么看", stats: "6.1万 / 171", date: "05-21", tone: "tone-three" },
      { title: "成长期主粮建议", stats: "5.4万 / 128", date: "05-13", tone: "tone-two" },
      { title: "科学喂养误区", stats: "4.2万 / 90", date: "05-04", tone: "tone-one" },
      { title: "挑主粮的三个指标", stats: "3.5万 / 66", date: "04-25", tone: "tone-four" },
    ],
  },
  {
    id: 4,
    name: "一只小团子",
    subtitle: "萌宠日常｜主粮测评｜避坑指南",
    tags: ["分享", "日常"],
    platform: "xiaohongshu",
    matchScore: 86,
    tier: "B",
    followersWan: 98.5,
    posts30d: 5,
    engagementRate: 3.85,
    viralRate: 9.8,
    commercialSignals: ["¥", "笔记"],
    favorited: true,
    avatarTone: "linear-gradient(135deg, #d4d8de, #8a949e)",
    platformHandle: "小红书 ID: tuanzi_cat",
    updatedAt: "2026-05-22",
    dimensions: [
      { label: "内容相关性", value: 21, max: 25 },
      { label: "受众匹配度", value: 20, max: 25 },
      { label: "互动表现", value: 18, max: 25 },
      { label: "商业化能力", value: 15, max: 20 },
      { label: "安全合规", value: 14, max: 15 },
    ],
    keywords: ["萌宠日常", "主粮开箱", "养猫避坑"],
    commerceFacts: [
      { label: "报价区间", value: "¥4,000 - ¥10,000" },
      { label: "预估品牌率", value: "79%" },
      { label: "合作品牌数", value: "5" },
      { label: "近30天合作", value: "1" },
    ],
    hotTopics: [
      { label: "#萌宠日常", heat: "733万" },
      { label: "#养猫避坑", heat: "310万" },
    ],
    evidences: [
      { title: "主粮开箱实拍", stats: "4.8万 / 120", date: "05-18", tone: "tone-four" },
      { title: "养猫避坑 5 条", stats: "3.7万 / 85", date: "05-11", tone: "tone-one" },
      { title: "新手养猫设备清单", stats: "3.0万 / 62", date: "05-06", tone: "tone-two" },
      { title: "主粮囤货建议", stats: "2.6万 / 51", date: "04-26", tone: "tone-three" },
    ],
  },
  {
    id: 5,
    name: "养猫少女小凛",
    subtitle: "新手养猫｜主粮分享｜追评",
    tags: ["分享", "种草"],
    platform: "bilibili",
    matchScore: 84,
    tier: "C",
    followersWan: 132.2,
    posts30d: 7,
    engagementRate: 4.01,
    viralRate: 10.1,
    commercialSignals: ["¥", "视频"],
    favorited: false,
    avatarTone: "linear-gradient(135deg, #f4c7ab, #c27045)",
    platformHandle: "B站 UID: xiaolin-cat",
    updatedAt: "2026-05-22",
    dimensions: [
      { label: "内容相关性", value: 20, max: 25 },
      { label: "受众匹配度", value: 19, max: 25 },
      { label: "互动表现", value: 18, max: 25 },
      { label: "商业化能力", value: 15, max: 20 },
      { label: "安全合规", value: 12, max: 15 },
    ],
    keywords: ["猫粮分享", "新手养猫", "主粮追评"],
    commerceFacts: [
      { label: "报价区间", value: "¥5,000 - ¥12,000" },
      { label: "预估品牌率", value: "76%" },
      { label: "合作品牌数", value: "6" },
      { label: "近30天合作", value: "1" },
    ],
    hotTopics: [
      { label: "#养猫vlog", heat: "280万" },
      { label: "#主粮分享", heat: "198万" },
    ],
    evidences: [
      { title: "一周主粮追评", stats: "3.9万 / 73", date: "05-16", tone: "tone-two" },
      { title: "猫粮真实反馈", stats: "3.1万 / 55", date: "05-12", tone: "tone-four" },
      { title: "预算养猫怎么选", stats: "2.8万 / 44", date: "05-05", tone: "tone-one" },
      { title: "囤粮建议", stats: "2.2万 / 38", date: "04-30", tone: "tone-three" },
    ],
  },
  {
    id: 6,
    name: "朵朵麻麻",
    subtitle: "养宠经验分享｜主粮推荐",
    tags: ["测评", "记录"],
    platform: "xiaohongshu",
    matchScore: 82,
    tier: "C",
    followersWan: 86.4,
    posts30d: 6,
    engagementRate: 3.32,
    viralRate: 7.9,
    commercialSignals: ["¥", "专栏"],
    favorited: false,
    avatarTone: "linear-gradient(135deg, #ead4d8, #a86f7a)",
    platformHandle: "小红书 ID: duoduomama",
    updatedAt: "2026-05-22",
    dimensions: [
      { label: "内容相关性", value: 19, max: 25 },
      { label: "受众匹配度", value: 18, max: 25 },
      { label: "互动表现", value: 17, max: 25 },
      { label: "商业化能力", value: 14, max: 20 },
      { label: "安全合规", value: 13, max: 15 },
    ],
    keywords: ["猫粮记录", "养宠分享", "主粮推荐"],
    commerceFacts: [
      { label: "报价区间", value: "¥3,500 - ¥8,000" },
      { label: "预估品牌率", value: "72%" },
      { label: "合作品牌数", value: "4" },
      { label: "近30天合作", value: "1" },
    ],
    hotTopics: [
      { label: "#主粮推荐", heat: "188万" },
      { label: "#养宠记录", heat: "126万" },
    ],
    evidences: [
      { title: "低敏主粮记录", stats: "2.8万 / 41", date: "05-14", tone: "tone-three" },
      { title: "新手养猫注意项", stats: "2.4万 / 37", date: "05-07", tone: "tone-one" },
      { title: "冻干主粮搭配", stats: "2.2万 / 31", date: "05-02", tone: "tone-four" },
      { title: "一周投喂记录", stats: "1.9万 / 26", date: "04-24", tone: "tone-two" },
    ],
  },
];

function formatWan(value: number) {
  return `${value.toFixed(1)}万`;
}

function formatCount(value: number) {
  if (value >= 10000) return `${(value / 10000).toFixed(1)}万`;
  return String(Math.round(value));
}

function formatFollowerMetric(value: number | null | undefined) {
  if (value === null || value === undefined) return "未采集";
  if (value >= 10000) return `${(value / 10000).toFixed(1).replace(/\.0$/, "")}万`;
  if (value >= 1000) return `${(value / 1000).toFixed(1).replace(/\.0$/, "")}千`;
  return String(Math.round(value));
}

function formatPercent(value: number) {
  return `${value.toFixed(2)}%`;
}

function formatPercentMetric(value: number | null | undefined) {
  if (value === null || value === undefined) return "未采集";
  return formatPercent(value);
}

function creatorFollowerCount(record: CreatorRecord) {
  if (record.followerCount === undefined) {
    return Math.round(record.followersWan * 10000);
  }
  return record.followerCount;
}

function normalizeSourceLabel(label: string) {
  if (label === "Realtime") return "实时";
  if (label === "Database") return "本地";
  return label;
}

function platformClassName(platform: CreatorRecord["platform"]) {
  return `is-${platform}`;
}

function asRecord(value: unknown): UnknownRecord {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as UnknownRecord) : {};
}

function asArray(value: unknown): UnknownRecord[] {
  return Array.isArray(value) ? value.map(asRecord) : [];
}

function asNumber(value: unknown, fallback = 0) {
  const next = Number(value);
  return Number.isFinite(next) ? next : fallback;
}

function asOptionalNumber(value: unknown) {
  if (value === null || value === undefined || value === "") return null;
  const next = Number(value);
  return Number.isFinite(next) ? next : null;
}

function firstText(...values: unknown[]) {
  for (const value of values) {
    if (value !== null && value !== undefined && String(value).trim()) {
      return String(value);
    }
  }
  return "";
}

function safeExternalUrl(value: string) {
  const trimmed = value.trim();
  return /^https?:\/\//i.test(trimmed) ? trimmed : "";
}

function hasRealtimeSource(row: UnknownRecord) {
  const sourceType = firstText(row.source_type).toLowerCase();
  if (sourceType === "realtime" || sourceType === "mixed") return true;
  return Array.isArray(row.source_labels) && row.source_labels.some((label) => String(label) === "Realtime");
}

function frontendPlatform(platform: unknown): CreatorRecord["platform"] | null {
  const value = String(platform || "");
  if (value === "dy" || value === "douyin") return "douyin";
  if (value === "xhs" || value === "xiaohongshu") return "xiaohongshu";
  if (value === "bili" || value === "bilibili") return "bilibili";
  if (value === "wb" || value === "weibo") return "weibo";
  return null;
}

function backendPlatforms(platform: PlatformKey): string[] {
  if (platform === "all") return ["xhs", "dy", "bili", "wb"];
  if (platform === "douyin") return ["dy"];
  if (platform === "xiaohongshu") return ["xhs"];
  if (platform === "bilibili") return ["bili"];
  return ["wb"];
}

function backendPlatformForRecord(platform: CreatorRecord["platform"]): string {
  if (platform === "douyin") return "dy";
  if (platform === "xiaohongshu") return "xhs";
  if (platform === "bilibili") return "bili";
  return "wb";
}

function creatorMonitorKey(record: CreatorRecord): string {
  return `${record.backendPlatform || backendPlatformForRecord(record.platform)}:${record.creatorId || record.id}`;
}

function tierFromScore(score: number): CreatorRecord["tier"] {
  if (score >= 85) return "A";
  if (score >= 70) return "B";
  return "C";
}

function metricPercent(value: unknown) {
  const next = asNumber(value);
  return Math.abs(next) <= 1 ? next * 100 : next;
}

function metricPercentOrNull(value: unknown) {
  if (value === null || value === undefined || value === "") return null;
  const next = Number(value);
  if (!Number.isFinite(next)) return null;
  return Math.abs(next) <= 1 ? next * 100 : next;
}

function parseNumericInput(value: string): number | undefined {
  const normalized = value.trim().replace(/[,，]/g, "").replace(/[％%]/g, "");
  if (!normalized) return undefined;
  const next = Number(normalized);
  return Number.isFinite(next) ? next : undefined;
}

function parseFollowerInput(value: string): number | undefined {
  const next = parseNumericInput(value.replace(/[个人]/g, ""));
  return next === undefined ? undefined : Math.round(next);
}

function parsePercentInput(value: string): number | undefined {
  const next = parseNumericInput(value);
  return next === undefined ? undefined : next;
}

function normalizeActivityLevel(value: unknown): DiscoveryFilters["activityLevel"] {
  return value === "active" || value === "highly" || value === "dormant" ? value : "any";
}

function normalizePlatformFilter(value: unknown): PlatformKey {
  return value === "douyin" || value === "xiaohongshu" || value === "bilibili" || value === "weibo" ? value : "all";
}

function normalizeTierKey(value: unknown): TierKey {
  return value === "A" || value === "B" || value === "C" ? value : "recommended";
}

function normalizeAnalysisStatus(value: unknown): AnalysisStatus {
  return value === "loading" || value === "done" || value === "error" ? value : "idle";
}

function restoreDiscoveryFilters(value: unknown): DiscoveryFilters {
  const record = asRecord(value);
  return {
    followerMinCount: firstText(record.followerMinCount, DEFAULT_FILTERS.followerMinCount),
    followerMaxCount: firstText(record.followerMaxCount, DEFAULT_FILTERS.followerMaxCount),
    recentPostsMin: firstText(record.recentPostsMin, DEFAULT_FILTERS.recentPostsMin),
    activityLevel: normalizeActivityLevel(record.activityLevel),
    engagementMinPercent: firstText(record.engagementMinPercent, DEFAULT_FILTERS.engagementMinPercent),
    viralMinPercent: firstText(record.viralMinPercent, DEFAULT_FILTERS.viralMinPercent),
  };
}

function clampInteger(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, Math.round(value)));
}

function effectiveRecentPostsMin(filters: DiscoveryFilters): number | undefined {
  const explicit = parseNumericInput(filters.recentPostsMin);
  if (filters.activityLevel === "highly") return Math.max(explicit ?? 0, 5);
  if (filters.activityLevel === "active") return Math.max(explicit ?? 0, 1);
  if (filters.activityLevel === "dormant") return explicit;
  return explicit;
}

function applyDiscoveryFilters(records: CreatorRecord[], filters: DiscoveryFilters): CreatorRecord[] {
  const followerMin = parseFollowerInput(filters.followerMinCount);
  const followerMax = parseFollowerInput(filters.followerMaxCount);
  const recentMin = effectiveRecentPostsMin(filters);
  const engagementMin = parsePercentInput(filters.engagementMinPercent);
  const viralMin = parsePercentInput(filters.viralMinPercent);

  return records.filter((record) => {
    const followers = creatorFollowerCount(record);
    if (followerMin !== undefined && followers !== null && followers < followerMin) return false;
    if (followerMax !== undefined && followers !== null && followers > followerMax) return false;
    if (recentMin !== undefined && record.posts30d < recentMin) return false;
    if (filters.activityLevel === "dormant" && record.posts30d > 0) return false;
    if (engagementMin !== undefined && (record.engagementRate === null || record.engagementRate < engagementMin)) return false;
    if (viralMin !== undefined && (record.viralRate === null || record.viralRate < viralMin)) return false;
    return true;
  });
}

function tagLabels(row: UnknownRecord): string[] {
  const labels = new Set<string>();
  const matchedTags = asArray(row.matched_tags);
  for (const tag of matchedTags) {
    const evidence = asRecord(tag.evidence_json);
    const label = firstText(tag.tag_name, evidence.tag_name, tag.name, tag.term, tag.keyword);
    if (label) labels.add(label);
  }
  for (const keyword of Array.isArray(row.matched_keywords) ? row.matched_keywords : []) {
    if (keyword) labels.add(String(keyword));
  }
  return [...labels].slice(0, 4);
}

function representativePosts(row: UnknownRecord): UnknownRecord[] {
  const direct = asArray(row.representative_posts);
  if (direct.length) return direct;
  const evidence = row.evidence;
  if (Array.isArray(evidence)) return evidence.map(asRecord);
  return asArray(asRecord(evidence).representative_posts);
}

function evidenceStats(post: UnknownRecord) {
  const engagement = asRecord(post.engagement);
  const likes = asNumber(post.like_count ?? post.likes ?? engagement.liked_count ?? engagement.like_count);
  const comments = asNumber(post.comment_count ?? post.comments ?? engagement.comment_count ?? engagement.comments_count);
  if (!likes && !comments) return "-";
  return `${formatWan(likes / 10000)} / ${Math.round(comments)}`;
}

function buildDimensions(score: number): Dimension[] {
  const ratio = Math.max(0.45, Math.min(1, score / 100));
  return [
    { label: "内容相关性", value: Math.round(25 * ratio), max: 25 },
    { label: "受众匹配度", value: Math.round(25 * Math.max(0.4, ratio - 0.04)), max: 25 },
    { label: "互动表现", value: Math.round(25 * Math.max(0.35, ratio - 0.08)), max: 25 },
    { label: "商业化能力", value: Math.round(20 * Math.max(0.3, ratio - 0.16)), max: 20 },
    { label: "安全合规", value: Math.round(15 * Math.max(0.55, ratio - 0.1)), max: 15 },
  ];
}

function mapCreatorRows(rows: UnknownRecord[]): CreatorRecord[] {
  return rows
    .map((row, index): CreatorRecord | null => {
      const platform = frontendPlatform(row.platform);
      if (!platform) return null;
      const matchScore = Math.round(asNumber(row.match_score));
      const tags = tagLabels(row);
      const posts = representativePosts(row);
      const name = firstText(row.display_name, row.nickname, row.creator_id, `达人 ${index + 1}`);
      const creatorId = firstText(row.creator_id, row.account_id);
      const followerCount = asOptionalNumber(row.follower_count);
      const postCount = asNumber(row.recent_post_count_30d ?? row.post_count);
      const profileUrl = safeExternalUrl(firstText(row.profile_url, row.profileUrl, row.url, row.homepage));
      const sourceLabels = Array.isArray(row.source_labels)
        ? row.source_labels.map((label) => normalizeSourceLabel(String(label)))
        : [];
      const realtimeSource = hasRealtimeSource(row);
      return {
        id: asNumber(row.id, index + 1),
        name,
        subtitle: firstText(row.bio, row.notes, "来自本地达人画像与内容证据"),
        tags: tags.length ? tags : ["画像匹配"],
        platform,
        creatorId,
        backendPlatform: backendPlatformForRecord(platform),
        matchScore,
        tier: tierFromScore(matchScore),
        followersWan: followerCount === null ? 0 : followerCount / 10000,
        followerCount,
        posts30d: Math.round(postCount),
        engagementRate: metricPercentOrNull(row.avg_engagement_rate ?? row.engagement_rate),
        viralRate: metricPercentOrNull(row.hot_post_rate ?? row.viral_post_rate ?? row.viral_rate),
        commercialSignals: sourceLabels.length
          ? [...new Set(sourceLabels)].slice(0, 3)
          : row.realtime_unverified || realtimeSource
            ? ["实时"]
            : ["本地"],
        hasRealtimeSource: realtimeSource,
        favorited: false,
        avatarTone: index % 4 === 0
          ? "linear-gradient(135deg, #d3a570, #8f6742)"
          : index % 4 === 1
            ? "linear-gradient(135deg, #8bb7bd, #387880)"
            : index % 4 === 2
              ? "linear-gradient(135deg, #e0b68a, #a05c35)"
              : "linear-gradient(135deg, #a7b8c7, #607789)",
        platformHandle: `${PLATFORM_LABELS[platform]} ID: ${firstText(row.creator_id, row.account_id, "-")}`,
        profileUrl,
        updatedAt: firstText(row.latest_snapshot_at, row.updated_at, row.created_at, new Date().toISOString()).slice(0, 10),
        dimensions: buildDimensions(matchScore),
        keywords: tags.length ? tags : ["本地画像"],
        commerceFacts: [
          { label: "粉丝数", value: formatFollowerMetric(followerCount) },
          { label: "近30天样本发文", value: String(Math.round(postCount || 0)) },
          { label: "互动率", value: formatPercentMetric(metricPercentOrNull(row.avg_engagement_rate ?? row.engagement_rate)) },
          { label: "爆款率", value: formatPercentMetric(metricPercentOrNull(row.hot_post_rate ?? row.viral_post_rate ?? row.viral_rate)) },
        ],
        hotTopics: (tags.length ? tags : ["画像匹配"]).map((tag) => ({ label: `#${tag}`, heat: "命中" })),
        evidences: posts.slice(0, 4).map((post, postIndex) => ({
          title: firstText(post.title, post.content, post.desc, "代表性内容"),
          stats: evidenceStats(post),
          date: firstText(post.publish_time, post.published_at, post.create_time, "").slice(5, 10) || "-",
          tone: ["tone-one", "tone-two", "tone-three", "tone-four"][postIndex % 4],
        })),
      };
    })
    .filter((item): item is CreatorRecord => item !== null);
}

export function CreatorDiscoveryPage() {
  const [query, setQuery] = React.useState("K12 家长");
  const [activeTab, setActiveTab] = React.useState<TierKey>("recommended");
  const [platformFilter, setPlatformFilter] = React.useState<PlatformKey>("all");
  const [verticals, setVerticals] = React.useState<VerticalOption[]>([]);
  const [selectedVerticalId, setSelectedVerticalId] = React.useState<string>("all");
  const [filters, setFilters] = React.useState<DiscoveryFilters>(DEFAULT_FILTERS);
  const [records, setRecords] = React.useState<CreatorRecord[]>([]);
  const [selectedId, setSelectedId] = React.useState<number | null>(null);
  const [isLoading, setIsLoading] = React.useState(false);
  const [message, setMessage] = React.useState("请选择赛道并输入业务描述，系统会基于本地达人画像和标签证据返回真实结果。");
  const [resultSummary, setResultSummary] = React.useState("等待搜索");
  const [analysisStatus, setAnalysisStatus] = React.useState<AnalysisStatus>("idle");
  const [analysisDiagnostics, setAnalysisDiagnostics] = React.useState<UnknownRecord>({});
  const [analysisRealtime, setAnalysisRealtime] = React.useState<UnknownRecord>({});
  const [monitoringKeys, setMonitoringKeys] = React.useState<Set<string>>(() => new Set());
  const [addingMonitorKey, setAddingMonitorKey] = React.useState<string | null>(null);
  const [includeRealtime, setIncludeRealtime] = React.useState(true);
  const [realtimeRatioPercent, setRealtimeRatioPercent] = React.useState(DEFAULT_REALTIME_RATIO);
  const [pageSizeInput, setPageSizeInput] = React.useState(DEFAULT_PAGE_SIZE);
  const [currentSessionId, setCurrentSessionId] = React.useState<number | null>(null);
  const [latestSessionResolved, setLatestSessionResolved] = React.useState(false);
  const [skipCandidatePoolBootstrap, setSkipCandidatePoolBootstrap] = React.useState(false);

  const displayLimit = React.useMemo(() => {
    const parsed = parseNumericInput(pageSizeInput);
    return clampInteger(parsed ?? Number(DEFAULT_PAGE_SIZE), 1, 50);
  }, [pageSizeInput]);

  const filteredByControls = React.useMemo(() => {
    return applyDiscoveryFilters(records, filters);
  }, [filters, records]);

  const filteredBaseRecords = React.useMemo(() => {
    const byPlatform =
      platformFilter === "all" ? filteredByControls : filteredByControls.filter((item) => item.platform === platformFilter);
    return byPlatform;
  }, [filteredByControls, platformFilter]);

  const filteredRecords = React.useMemo(() => {
    if (activeTab === "recommended") {
      return filteredBaseRecords;
    }
    return filteredBaseRecords.filter((item) => item.tier === activeTab);
  }, [activeTab, filteredBaseRecords]);

  const displayedRecords = React.useMemo(() => {
    return filteredRecords.slice(0, displayLimit);
  }, [displayLimit, filteredRecords]);

  const selectedRecord = React.useMemo(() => {
    return displayedRecords.find((item) => item.id === selectedId) || displayedRecords[0] || null;
  }, [displayedRecords, selectedId]);

  const tabCounts = React.useMemo(() => {
    return {
      recommended: filteredBaseRecords.length,
      A: filteredBaseRecords.filter((item) => item.tier === "A").length,
      B: filteredBaseRecords.filter((item) => item.tier === "B").length,
      C: filteredBaseRecords.filter((item) => item.tier === "C").length,
    } satisfies Record<TierKey, number>;
  }, [filteredBaseRecords]);

  const filteredPoolSize = filteredBaseRecords.length;

  const selectedVertical = React.useMemo(() => {
    return verticals.find((item) => String(item.id) === selectedVerticalId) || null;
  }, [selectedVerticalId, verticals]);

  const averageEngagement = React.useMemo(() => {
    const values = filteredBaseRecords
      .map((item) => item.engagementRate)
      .filter((value): value is number => value !== null);
    if (!values.length) return "未采集";
    return formatPercent(values.reduce((sum, item) => sum + item, 0) / values.length);
  }, [filteredBaseRecords, filteredPoolSize]);

  const averageViral = React.useMemo(() => {
    const values = filteredBaseRecords
      .map((item) => item.viralRate)
      .filter((value): value is number => value !== null);
    if (!values.length) return "未采集";
    return formatPercent(values.reduce((sum, item) => sum + item, 0) / values.length);
  }, [filteredBaseRecords, filteredPoolSize]);

  const visibleResultSummary = React.useMemo(() => {
    if (!records.length || resultSummary.includes("失败")) {
      return resultSummary;
    }
    const realtimeStatus = firstText(analysisRealtime.status).toLowerCase();
    const realtimeSelectedCount = Math.round(asNumber(analysisRealtime.selected_count));
    if (includeRealtime && realtimeStatus === "failed") {
      return `原始返回 ${formatCount(records.length)} 位，实时补充失败，筛选后 ${formatCount(filteredRecords.length)} 位，当前展示 ${formatCount(displayedRecords.length)} 位`;
    }
    if (includeRealtime && realtimeSelectedCount > 0) {
      if (filteredRecords.length === records.length) {
        return `原始返回 ${formatCount(records.length)} 位，其中实时 ${formatCount(realtimeSelectedCount)} 位，当前展示 ${formatCount(displayedRecords.length)} 位`;
      }
      return `原始返回 ${formatCount(records.length)} 位，其中实时 ${formatCount(realtimeSelectedCount)} 位，符合当前筛选 ${formatCount(filteredRecords.length)} 位，当前展示 ${formatCount(displayedRecords.length)} 位`;
    }
    if (filteredRecords.length === records.length) {
      return `原始返回 ${formatCount(records.length)} 位，当前展示 ${formatCount(displayedRecords.length)} 位`;
    }
    return `原始返回 ${formatCount(records.length)} 位，符合当前筛选 ${formatCount(filteredRecords.length)} 位，当前展示 ${formatCount(displayedRecords.length)} 位`;
  }, [analysisRealtime, displayedRecords.length, filteredRecords.length, includeRealtime, records.length, resultSummary]);

  const processSteps = React.useMemo(() => {
    const verticalLabel = selectedVertical?.name || (selectedVerticalId === "all" ? "全部赛道" : "当前赛道");
    const queryLabel = query.trim() || "未输入关键词";
    const matchedTagCount = Math.round(asNumber(analysisDiagnostics.matched_tag_count));
    const tagDefinitionCount = Math.round(asNumber(analysisDiagnostics.tag_definition_count));
    const profileCount = Math.round(asNumber(analysisDiagnostics.profile_count, records.length));
    const realtimeStatus = firstText(analysisRealtime.status).toLowerCase();
    const realtimeSelectedCount = Math.round(asNumber(analysisRealtime.selected_count));
    const realtimeRequestedRatio = Math.round(asNumber(analysisRealtime.requested_ratio, includeRealtime ? 50 : 0));
    const hasResultContext = analysisStatus === "done" || records.length > 0;
    const states: ProcessStepState[] =
      analysisStatus === "loading"
        ? ["done", "active", "pending", "pending"]
        : analysisStatus === "error"
          ? ["done", "done", "done", "error"]
          : hasResultContext
            ? ["done", "done", "done", "done"]
            : ["active", "pending", "pending", "pending"];

    return [
      {
        index: 1,
        title: "理解需求",
        detail: `${verticalLabel} · ${queryLabel}`,
        state: states[0],
      },
      {
        index: 2,
        title: "匹配标签",
        detail: analysisStatus === "loading"
          ? "正在匹配标签与关键词"
          : matchedTagCount > 0
            ? `命中 ${matchedTagCount} 个标签`
            : tagDefinitionCount > 0
              ? `可用 ${tagDefinitionCount} 个标签`
              : "等待分析条件",
        state: states[1],
      },
      {
        index: 3,
        title: "寻找达人",
        detail: analysisStatus === "loading"
          ? includeRealtime
            ? "正在扫描本地库并补充小红书 / 抖音实时达人"
            : "正在读取本地达人画像"
          : includeRealtime && realtimeStatus === "failed"
            ? "实时补充失败，已回退本地结果"
          : profileCount > 0
            ? includeRealtime && realtimeSelectedCount > 0
              ? `扫描 ${formatCount(profileCount)} 个账号，实时补充 ${formatCount(realtimeSelectedCount)} 位`
              : `扫描 ${formatCount(profileCount)} 个账号`
            : "等待检索",
        state: states[2],
      },
      {
        index: 4,
        title: "结果筛选",
        detail: analysisStatus === "loading"
          ? "等待结果排序"
          : analysisStatus === "error"
            ? "请调整条件后重试"
            : records.length
              ? includeRealtime && realtimeStatus === "failed"
                ? `原始返回 ${formatCount(records.length)} 位，实时补充失败，筛选后 ${formatCount(filteredRecords.length)} 位，当前展示 ${formatCount(displayedRecords.length)} 位`
                : includeRealtime && realtimeSelectedCount > 0
                ? `原始返回 ${formatCount(records.length)} 位，其中实时 ${formatCount(realtimeSelectedCount)} 位（目标 ${realtimeRequestedRatio}%），筛选后 ${formatCount(filteredRecords.length)} 位，当前展示 ${formatCount(displayedRecords.length)} 位`
                : `原始返回 ${formatCount(records.length)} 位，筛选后 ${formatCount(filteredRecords.length)} 位，当前展示 ${formatCount(displayedRecords.length)} 位`
              : "暂无匹配结果",
        state: states[3],
      },
    ];
  }, [analysisDiagnostics, analysisRealtime, analysisStatus, displayedRecords.length, filteredRecords, includeRealtime, query, records.length, selectedVertical?.name, selectedVerticalId]);

  const restoreLatestSearchSession = React.useCallback((sessionRow: UnknownRecord) => {
    const sessionId = asOptionalNumber(sessionRow.id);
    const viewState = asRecord(sessionRow.view_state);
    const restoredQuery = firstText(sessionRow.raw_query, viewState.query);
    const restoredVerticalId = firstText(
      viewState.selectedVerticalId,
      sessionRow.selected_vertical_id !== null && sessionRow.selected_vertical_id !== undefined
        ? String(sessionRow.selected_vertical_id)
        : "",
      "all",
    );
    const restoredResults = mapCreatorRows(asArray(sessionRow.results));

    setCurrentSessionId(sessionId);
    setQuery(restoredQuery);
    setSelectedVerticalId(restoredVerticalId || "all");
    setPlatformFilter(normalizePlatformFilter(viewState.platformFilter));
    setActiveTab(normalizeTierKey(viewState.activeTab));
    setFilters(restoreDiscoveryFilters(viewState.filters));
    setIncludeRealtime(Boolean(viewState.includeRealtime ?? false));
    setRealtimeRatioPercent(
      firstText(
        viewState.realtimeRatioPercent,
        viewState.realtimeRatio,
        DEFAULT_REALTIME_RATIO,
      ),
    );
    setPageSizeInput(
      String(
        clampInteger(
          asNumber(viewState.displayLimit, Number(DEFAULT_PAGE_SIZE)),
          1,
          50,
        ),
      ),
    );
    setRecords(restoredResults);
    setSelectedId(restoredResults[0]?.id ?? null);
    setAnalysisDiagnostics(asRecord(sessionRow.diagnostics));
    setAnalysisRealtime(asRecord(sessionRow.realtime));
    setAnalysisStatus(
      normalizeAnalysisStatus(firstText(viewState.analysisStatus, sessionRow.status)),
    );
    setResultSummary(
      firstText(
        sessionRow.result_summary,
        restoredResults.length ? `返回 ${restoredResults.length} 位达人` : "",
        "等待搜索",
      ),
    );
    setMessage(
      firstText(
        sessionRow.message,
        "已恢复上一次搜索结果。",
      ),
    );
    setSkipCandidatePoolBootstrap(true);
  }, []);

  const persistSearchSession = React.useCallback(
    async ({
      searchPayload,
      rawResults,
      diagnostics,
      realtime,
      progress,
      status,
      messageText,
      resultSummaryText,
      saved = false,
    }: {
      searchPayload: Record<string, unknown>;
      rawResults: UnknownRecord[];
      diagnostics: UnknownRecord;
      realtime: UnknownRecord;
      progress: UnknownRecord;
      status: AnalysisStatus;
      messageText: string;
      resultSummaryText: string;
      saved?: boolean;
    }) => {
      const response = await api<CreatorSearchSessionResponse>("/api/creator-search/search-sessions", {
        method: "POST",
        body: JSON.stringify({
          raw_query: query.trim(),
          selected_vertical_id: selectedVerticalId === "all" ? null : Number(selectedVerticalId),
          search_payload: searchPayload,
          view_state: {
            query: query.trim(),
            selectedVerticalId,
            platformFilter,
            activeTab,
            filters,
            includeRealtime,
            realtimeRatioPercent,
            displayLimit,
            analysisStatus: status,
          },
          diagnostics,
          realtime,
          progress,
          message: messageText,
          result_summary: resultSummaryText,
          results: rawResults,
          saved,
          saved_name: saved ? query.trim().slice(0, 255) || undefined : undefined,
          status,
        }),
      });
      const sessionId = asOptionalNumber(asRecord(response.session).id);
      setCurrentSessionId(sessionId);
      return sessionId;
    },
    [
      activeTab,
      displayLimit,
      filters,
      includeRealtime,
      platformFilter,
      query,
      realtimeRatioPercent,
      selectedVerticalId,
    ],
  );

  const loadCandidatePool = React.useCallback(async (verticalId: string) => {
    setIsLoading(true);
    setAnalysisStatus("loading");
    setAnalysisDiagnostics({});
    setAnalysisRealtime({});
    setCurrentSessionId(null);
    try {
      const params = new URLSearchParams();
      params.set("include_profile_candidates", "false");
      if (verticalId !== "all") params.set("vertical_id", verticalId);
      const data = await api<CreatorCandidatePoolResponse>(`/api/creator-search/candidate-pool?${params.toString()}`);
      const mapped = mapCreatorRows(data.candidates || []);
      setRecords(mapped);
      setSelectedId(mapped[0]?.id ?? null);
      setAnalysisDiagnostics({ profile_count: mapped.length, matched_tag_count: 0, tag_definition_count: 0 });
      setAnalysisStatus("done");
      setResultSummary(mapped.length ? `已加载 ${mapped.length} 位候选达人` : "当前赛道暂无候选池结果");
      setMessage(mapped.length ? `已切换到${verticalId === "all" ? "全部赛道" : selectedVertical?.name || "当前赛道"}，候选池结果已刷新。` : "当前赛道候选池为空，可以输入关键词发起真实搜索。");
    } catch (error) {
      setAnalysisStatus("error");
      setResultSummary("候选池加载失败");
      setMessage(error instanceof Error ? error.message : "候选池加载失败，请稍后重试。");
    } finally {
      setIsLoading(false);
    }
  }, [selectedVertical?.name]);

  const handleSearch = React.useCallback(async () => {
    const trimmedQuery = query.trim();
    if (!trimmedQuery && selectedVerticalId === "all") {
      setMessage("请先选择赛道，或输入一段达人发现需求。");
      return;
    }
    setIsLoading(true);
    setAnalysisStatus("loading");
    setAnalysisDiagnostics({});
    setAnalysisRealtime({});
    setMessage("正在检索本地达人画像、标签和近期内容证据。");
    try {
      const parsedRealtimeRatio = parseNumericInput(realtimeRatioPercent);
      const realtimeRatio = Math.max(0, Math.min(100, Math.round(parsedRealtimeRatio ?? 50)));
      const payload: Record<string, unknown> = {
        raw_query: trimmedQuery,
        platforms: backendPlatforms(platformFilter),
        limit: 50,
        include_realtime: includeRealtime,
        realtime_ratio: realtimeRatio,
      };
      const followerMin = parseFollowerInput(filters.followerMinCount);
      const followerMax = parseFollowerInput(filters.followerMaxCount);
      const recentMin = effectiveRecentPostsMin(filters);
      const engagementMin = parsePercentInput(filters.engagementMinPercent);
      if (followerMin !== undefined && followerMax !== undefined && followerMax < followerMin) {
        setAnalysisStatus("error");
        setResultSummary("筛选条件有误");
        setMessage("粉丝数上限不能小于下限，请调整后再搜索。");
        return;
      }
      if (followerMin !== undefined) payload.follower_min = followerMin;
      if (followerMax !== undefined) payload.follower_max = followerMax;
      if (recentMin !== undefined && filters.activityLevel !== "dormant") {
        payload.recent_activity_min = recentMin;
      }
      if (engagementMin !== undefined) payload.engagement_rate_min = engagementMin / 100;
      if (selectedVerticalId !== "all") {
        payload.selected_vertical_id = Number(selectedVerticalId);
      }
      const data = await api<CreatorSearchResponse>("/api/creator-search/search", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      const rawResults = asArray(data.results);
      const mapped = mapCreatorRows(rawResults);
      const realtimeInfo = asRecord(data.realtime);
      const realtimeFailed = firstText(realtimeInfo.status).toLowerCase() === "failed";
      const diagnostics = asRecord(data.diagnostics);
      const progress = asRecord(data.progress);
      setRecords(mapped);
      setSelectedId(mapped[0]?.id ?? null);
      setAnalysisDiagnostics(diagnostics);
      setAnalysisRealtime(realtimeInfo);
      setAnalysisStatus("done");
      const guidance = firstText(diagnostics.guidance);
      const nextResultSummary = mapped.length ? `返回 ${mapped.length} 位达人` : "没有匹配结果";
      const nextMessage = realtimeFailed
        ? "实时补充失败，当前已回退为本地库结果。"
        : guidance || (mapped.length ? "搜索完成，结果已按本地库与实时补充的综合匹配分排序。" : "没有找到匹配达人，请放宽关键词、赛道或平台条件。");
      setResultSummary(nextResultSummary);
      setMessage(nextMessage);
      try {
        await persistSearchSession({
          searchPayload: payload,
          rawResults,
          diagnostics,
          realtime: realtimeInfo,
          progress,
          status: "done",
          messageText: nextMessage,
          resultSummaryText: nextResultSummary,
        });
      } catch {
        setMessage(`${nextMessage} 最近一次搜索未能保存，刷新后可能需要重新搜索。`);
      }
    } catch (error) {
      setAnalysisStatus("error");
      setResultSummary("搜索失败");
      setMessage(error instanceof Error ? error.message : "搜索失败，请检查后端服务状态。");
    } finally {
      setIsLoading(false);
    }
  }, [filters, includeRealtime, persistSearchSession, platformFilter, query, realtimeRatioPercent, selectedVerticalId]);

  const handleSaveSearch = React.useCallback(async () => {
    if (!currentSessionId) {
      setMessage("请先执行一次真实搜索后再保存。");
      return;
    }
    try {
      const response = await api<CreatorSearchSessionResponse>(`/api/creator-search/search-sessions/${currentSessionId}/save`, {
        method: "POST",
        body: JSON.stringify({
          saved: true,
          saved_name: query.trim().slice(0, 255) || undefined,
        }),
      });
      setCurrentSessionId(asOptionalNumber(asRecord(response.session).id));
      setMessage("当前搜索已保存到工作台，刷新后可直接恢复。");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "保存搜索失败，请稍后重试。");
    }
  }, [currentSessionId, query]);

  async function handleAddMonitor(record: CreatorRecord) {
    const creatorId = (record.creatorId || "").trim();
    const backendPlatform = record.backendPlatform || backendPlatformForRecord(record.platform);
    if (!creatorId) {
      setMessage(`无法添加 ${record.name}：缺少达人账号 ID。`);
      return;
    }
    const key = creatorMonitorKey(record);
    setAddingMonitorKey(key);
    try {
      await api("/api/competitors/from-candidate", {
        method: "POST",
        body: JSON.stringify({
          platform: backendPlatform,
          creator_id: creatorId,
          monitor_type: "partner_creator",
          display_name: record.name,
          profile_url: record.profileUrl || undefined,
          notes: selectedVertical?.name ? `来自达人发现：${selectedVertical.name}` : "来自达人发现",
        }),
      });
      setMonitoringKeys((current) => new Set(current).add(key));
      setMessage(`已将 ${record.name} 添加到达人监控。`);
      setSelectedId(record.id);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : `添加 ${record.name} 到达人监控失败。`);
    } finally {
      setAddingMonitorKey(null);
    }
  }

  React.useEffect(() => {
    if (!displayedRecords.length) {
      if (!filteredRecords.length && selectedId !== null) {
        setSelectedId(null);
      }
      return;
    }
    if (!displayedRecords.some((item) => item.id === selectedId)) {
      setSelectedId(displayedRecords[0].id);
    }
  }, [displayedRecords, filteredRecords.length, selectedId]);

  React.useEffect(() => {
    let cancelled = false;
    api<{ verticals: VerticalOption[] }>("/api/admin/verticals?enabled_only=true")
      .then((data) => {
        if (cancelled) return;
        const nextVerticals = data.verticals || [];
        setVerticals(nextVerticals);
        const education = nextVerticals.find((item) => item.code === "education") || nextVerticals[0];
        if (education && selectedVerticalId === "all") {
          setSelectedVerticalId(String(education.id));
        }
      })
      .catch((error) => {
        if (!cancelled) {
          setMessage(error instanceof Error ? error.message : "赛道列表加载失败。");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [selectedVerticalId]);

  React.useEffect(() => {
    if (!verticals.length || latestSessionResolved) return;
    let cancelled = false;
    api<CreatorSearchSessionResponse>("/api/creator-search/search-sessions/latest")
      .then((data) => {
        if (cancelled) return;
        const sessionRow = asRecord(data.session);
        if (Object.keys(sessionRow).length) {
          restoreLatestSearchSession(sessionRow);
        }
        setLatestSessionResolved(true);
      })
      .catch(() => {
        if (!cancelled) {
          setLatestSessionResolved(true);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [latestSessionResolved, restoreLatestSearchSession, verticals.length]);

  React.useEffect(() => {
    if (!verticals.length || !latestSessionResolved) return;
    if (skipCandidatePoolBootstrap) {
      setSkipCandidatePoolBootstrap(false);
      return;
    }
    void loadCandidatePool(selectedVerticalId);
  }, [latestSessionResolved, loadCandidatePool, selectedVerticalId, skipCandidatePoolBootstrap, verticals.length]);

  return (
    <section className="creator-discovery-v2">
      <div className="cdv2-layout">
        <div className="cdv2-main">
          <section className="cdv2-panel cdv2-search-panel">
            <div className="cdv2-section-head">
              <div>
                <h1>达人发现</h1>
                <p>选择赛道后输入自然语言需求，基于本地画像、标签和内容证据发现可跟进达人</p>
              </div>
            </div>

            <div className="cdv2-search-row">
              <label className="cdv2-search-box" aria-label="达人发现搜索">
                <Search size={18} />
                <input
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") {
                      event.preventDefault();
                      void handleSearch();
                    }
                  }}
                  placeholder="请输入要搜索的内容，例如：帮我找近期活跃的宠物主粮领域，擅长测评与科普的抖音/小红书达人"
                />
              </label>
              <button
                type="button"
                className="cdv2-button primary"
                disabled={isLoading}
                onClick={() => void handleSearch()}
              >
                <Sparkles size={16} />
                {isLoading ? "分析中" : "智能发现"}
              </button>
              <button
                type="button"
                className="cdv2-button ghost"
                onClick={() => void handleSaveSearch()}
              >
                <Bookmark size={16} />
                保存搜索
              </button>
            </div>

            <div className="cdv2-steps">
              {processSteps.map((step, index) => (
                <React.Fragment key={step.index}>
                  <div className={`cdv2-step is-${step.state}`}>
                    <span className="cdv2-step-index">{step.index}</span>
                    <div>
                      <strong>{step.title}</strong>
                      <small>{step.detail}</small>
                    </div>
                  </div>
                  {index < processSteps.length - 1 && <span className={`cdv2-step-line ${step.state === "done" ? "is-done" : ""}`} aria-hidden />}
                </React.Fragment>
              ))}
            </div>

            <div className="cdv2-filter-row">
              <VerticalSelect
                value={selectedVerticalId}
                verticals={verticals}
                onChange={(value) => {
                  setSelectedVerticalId(value);
                  setActiveTab("recommended");
                }}
              />
              <FilterSelectControl
                label="平台"
                value={platformFilter}
                onChange={(value) => setPlatformFilter(value as PlatformKey)}
                options={[
                  { value: "all", label: "全平台" },
                  { value: "douyin", label: "抖音" },
                  { value: "xiaohongshu", label: "小红书" },
                  { value: "bilibili", label: "B站" },
                  { value: "weibo", label: "微博" },
                ]}
              />
              <RealtimeConfigControl
                enabled={includeRealtime}
                ratio={realtimeRatioPercent}
                onToggle={setIncludeRealtime}
                onRatioChange={setRealtimeRatioPercent}
              />
              <FilterInputControl
                label="展示数量"
                value={pageSizeInput}
                placeholder="10"
                suffix="位"
                inputMode="numeric"
                onChange={setPageSizeInput}
                onBlur={() => setPageSizeInput(String(displayLimit))}
              />
              <FilterRangeControl
                label="粉丝数"
                minValue={filters.followerMinCount}
                maxValue={filters.followerMaxCount}
                minPlaceholder="最小"
                maxPlaceholder="最大"
                suffix="个"
                onMinChange={(value) => setFilters((current) => ({ ...current, followerMinCount: value }))}
                onMaxChange={(value) => setFilters((current) => ({ ...current, followerMaxCount: value }))}
              />
              <FilterInputControl
                label="近30天样本发文"
                value={filters.recentPostsMin}
                placeholder="不限"
                suffix="篇"
                onChange={(value) => setFilters((current) => ({ ...current, recentPostsMin: value }))}
              />
              <FilterSelectControl
                label="活跃度"
                value={filters.activityLevel}
                onChange={(value) => setFilters((current) => ({ ...current, activityLevel: value as DiscoveryFilters["activityLevel"] }))}
                options={[
                  { value: "any", label: "不限" },
                  { value: "active", label: "活跃" },
                  { value: "highly", label: "高活跃" },
                  { value: "dormant", label: "沉寂" },
                ]}
              />
              <FilterInputControl
                label="互动率"
                value={filters.engagementMinPercent}
                placeholder="不限"
                suffix="%"
                onChange={(value) => setFilters((current) => ({ ...current, engagementMinPercent: value }))}
              />
              <FilterInputControl
                label="爆款率"
                value={filters.viralMinPercent}
                placeholder="不限"
                suffix="%"
                onChange={(value) => setFilters((current) => ({ ...current, viralMinPercent: value }))}
              />
              <button
                type="button"
                className="cdv2-reset"
                onClick={() => {
                  setQuery("");
                  setSelectedVerticalId(verticals[0] ? String(verticals[0].id) : "all");
                  setFilters(DEFAULT_FILTERS);
                  setIncludeRealtime(true);
                  setRealtimeRatioPercent(DEFAULT_REALTIME_RATIO);
                  setPageSizeInput(DEFAULT_PAGE_SIZE);
                  setPlatformFilter("all");
                  setActiveTab("recommended");
                  setMessage("筛选器已恢复为默认推荐组合。");
                }}
              >
                重置
              </button>
            </div>
          </section>

          <section className="cdv2-panel cdv2-results-panel">
            <div className="cdv2-results-head">
              <div className="cdv2-tabs" role="tablist" aria-label="达人分层">
                {(Object.keys(TAB_LABELS) as TierKey[]).map((tab) => (
                  <button
                    key={tab}
                    type="button"
                    role="tab"
                    aria-selected={activeTab === tab}
                    className={`cdv2-tab ${activeTab === tab ? "is-active" : ""}`}
                    onClick={() => setActiveTab(tab)}
                  >
                    {TAB_LABELS[tab]}
                    <span>({tabCounts[tab]})</span>
                  </button>
                ))}
              </div>
              <div className="cdv2-results-tools">
                <button
                  type="button"
                  className={`cdv2-platform-switch ${platformFilter === "all" ? "is-active" : ""}`}
                  onClick={() => setPlatformFilter("all")}
                >
                  全平台
                </button>
                <button
                  type="button"
                  className={`cdv2-platform-switch ${platformFilter === "douyin" ? "is-active" : ""}`}
                  onClick={() => setPlatformFilter("douyin")}
                >
                  抖音
                </button>
                <button
                  type="button"
                  className={`cdv2-platform-switch ${platformFilter === "xiaohongshu" ? "is-active" : ""}`}
                  onClick={() => setPlatformFilter("xiaohongshu")}
                >
                  小红书
                </button>
                <button
                  type="button"
                  className={`cdv2-platform-switch ${platformFilter === "bilibili" ? "is-active" : ""}`}
                  onClick={() => setPlatformFilter("bilibili")}
                >
                  B站
                </button>
                <button
                  type="button"
                  className={`cdv2-platform-switch ${platformFilter === "weibo" ? "is-active" : ""}`}
                  onClick={() => setPlatformFilter("weibo")}
                >
                  微博
                </button>
              </div>
            </div>

            <div className="cdv2-table-wrap">
              <table className="cdv2-table">
                <thead>
                  <tr>
                    <th>达人</th>
                    <th>平台</th>
                    <th>匹配分</th>
                    <th>粉丝数</th>
                    <th>近30天样本发文</th>
                    <th>互动率</th>
                    <th>爆款率</th>
                    <th>商业化信号</th>
                    <th>操作</th>
                  </tr>
                </thead>
                <tbody>
                  {displayedRecords.map((record, index) => (
                    <tr
                      key={record.id}
                      className={record.id === selectedRecord?.id ? "is-selected" : ""}
                      onClick={() => setSelectedId(record.id)}
                    >
                      <td>
                        <div className="cdv2-creator-cell">
                          <span className={`cdv2-rank rank-${index + 1}`}>{index + 1}</span>
                          <span className="cdv2-avatar" style={{ background: record.avatarTone }}>
                            {record.name.slice(0, 1)}
                          </span>
                          <div>
                            <CreatorNameLink record={record} />
                            <p>
                              {record.subtitle}
                              <span className="cdv2-inline-tags">
                                {record.tags.map((tag) => (
                                  <em key={tag}>{tag}</em>
                                ))}
                              </span>
                            </p>
                          </div>
                        </div>
                      </td>
                      <td>
                        <span className={`cdv2-platform-badge ${platformClassName(record.platform)}`}>
                          {PLATFORM_LABELS[record.platform]}
                        </span>
                      </td>
                      <td>
                        <div className="cdv2-score-cell">
                          <strong>{record.matchScore}</strong>
                          <span>{record.tier === "A" ? "精准匹配" : record.tier === "B" ? "高潜匹配" : "拓展匹配"}</span>
                        </div>
                      </td>
                      <td>{formatFollowerMetric(creatorFollowerCount(record))}</td>
                      <td>{record.posts30d}</td>
                      <td>{formatPercentMetric(record.engagementRate)}</td>
                      <td>{formatPercentMetric(record.viralRate)}</td>
                      <td>
                        <div className="cdv2-signals">
                          {record.commercialSignals.map((signal) => (
                            <span key={signal}>{signal}</span>
                          ))}
                        </div>
                      </td>
                      <td>
                        <div className="cdv2-row-actions">
                          <button
                            type="button"
                            className={`cdv2-monitor-btn ${monitoringKeys.has(creatorMonitorKey(record)) ? "is-added" : ""}`}
                            disabled={addingMonitorKey === creatorMonitorKey(record) || monitoringKeys.has(creatorMonitorKey(record))}
                            onClick={(event) => {
                              event.stopPropagation();
                              void handleAddMonitor(record);
                            }}
                          >
                            {addingMonitorKey === creatorMonitorKey(record) ? (
                              <Loader2 size={14} className="spin" />
                            ) : monitoringKeys.has(creatorMonitorKey(record)) ? (
                              <Check size={14} />
                            ) : (
                              <Plus size={14} />
                            )}
                            {monitoringKeys.has(creatorMonitorKey(record)) ? "已监控" : "添加监控"}
                          </button>
                          <button
                            type="button"
                            className={`cdv2-fav ${record.favorited ? "is-active" : ""}`}
                            aria-label="收藏达人"
                            onClick={(event) => {
                              event.stopPropagation();
                              setMessage(`已将 ${record.name} 加入重点关注列表。`);
                              setSelectedId(record.id);
                            }}
                          >
                            <Star size={16} fill={record.favorited ? "currentColor" : "none"} />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                  {!filteredRecords.length && (
                    <tr>
                      <td colSpan={9}>
                        <div className="cdv2-empty-state">
                          <strong>{isLoading ? "正在分析达人线索" : records.length ? "当前筛选无匹配达人" : "暂无匹配达人"}</strong>
                          <p>{isLoading ? "请稍候，系统正在读取画像、标签和内容证据。" : records.length ? "请放宽粉丝数、近30天样本发文、互动率或爆款率条件。" : "可以切换赛道、放宽平台筛选，或输入更贴近已有样本的关键词。"}</p>
                        </div>
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>

            <div className="cdv2-pagination">
              <span>当前展示 {displayedRecords.length} / {filteredRecords.length} 条结果 · {visibleResultSummary}</span>
              <div className="cdv2-page-controls">
                <span className="cdv2-page-chip">展示数量 {displayLimit} 位</span>
              </div>
            </div>
          </section>

          <div className="cdv2-insights-grid">
            <section className="cdv2-panel cdv2-insight-card">
              <div className="cdv2-card-head">
                <div>
                  <span className="cdv2-kicker">
                    <Bot size={14} />
                    AI 洞察总结
                  </span>
                </div>
              </div>
              <ul className="cdv2-bullet-list">
                <li>当前赛道：{selectedVertical?.name || "全部赛道"}，原始候选 {records.length} 位，筛选后 {filteredRecords.length} 位，当前展示 {displayedRecords.length} 位。</li>
                <li>A 类精准匹配 {tabCounts.A} 位，B 类高潜达人 {tabCounts.B} 位。</li>
                <li>{message}</li>
              </ul>
              <button type="button" className="cdv2-link-button" onClick={() => void handleSearch()}>重新分析当前条件</button>
            </section>

            <section className="cdv2-panel cdv2-insight-card">
              <div className="cdv2-card-head">
                <h3>热门达人画像分布</h3>
              </div>
              <div className="cdv2-distribution">
                <div className="cdv2-bars">
                  <DistributionBar label="10万以下" value="18.6%" width={18.6} />
                  <DistributionBar label="10-50万" value="42.3%" width={42.3} />
                  <DistributionBar label="50-100万" value="23.7%" width={23.7} />
                  <DistributionBar label="100-200万" value="15.4%" width={15.4} />
                </div>
                <div className="cdv2-donut-card">
                  <div
                    className="cdv2-donut"
                    style={{
                      background:
                        "conic-gradient(#0e9488 0 46%, #9fb2c6 46% 74%, #f2b24f 74% 90%, #d7dde3 90% 100%)",
                    }}
                  >
                    <div />
                  </div>
                  <ul>
                    <li><span className="dot is-teal" />测评 46%</li>
                    <li><span className="dot is-slate" />科普 28%</li>
                    <li><span className="dot is-amber" />日常 16%</li>
                    <li><span className="dot is-gray" />其他 10%</li>
                  </ul>
                </div>
              </div>
            </section>

            <section className="cdv2-panel cdv2-insight-card">
              <div className="cdv2-card-head">
                <h3>内容表现趋势</h3>
                <span>按已采样本估算</span>
              </div>
              <div className="cdv2-trend-metrics">
                <TrendMetric label="平均互动率" value={averageEngagement} delta="样本估算" />
                <TrendMetric label="平均爆款率" value={averageViral} delta="样本估算" />
                <TrendMetric label="A类占比" value={filteredPoolSize ? formatPercent((tabCounts.A / filteredPoolSize) * 100) : "0.00%"} delta="按匹配分分层" />
              </div>
            </section>
          </div>
        </div>

        <aside className="cdv2-side">
          <section className="cdv2-panel cdv2-side-panel">
            <div className="cdv2-side-head">
              <h2>达人评分卡</h2>
              <button
                type="button"
                className="cdv2-icon-button"
                onClick={() => setMessage("评分卡已按最新模型重新评估。")}
              >
                <RefreshCw size={14} />
                重新评估
              </button>
            </div>

            {selectedRecord ? (
              <>
            <div className="cdv2-profile">
              <span className="cdv2-profile-avatar" style={{ background: selectedRecord.avatarTone }}>
                {selectedRecord.name.slice(0, 1)}
              </span>
              <div className="cdv2-profile-meta">
                <div className="cdv2-profile-title">
                  <CreatorNameLink record={selectedRecord} />
                  <span className="cdv2-grade">A 类 精准匹配</span>
                </div>
                <p>{selectedRecord.platformHandle}</p>
                <small>{selectedRecord.subtitle}</small>
              </div>
            </div>

            <div className="cdv2-score-summary">
              <div>
                <span>匹配分</span>
                <strong>
                  {selectedRecord.matchScore}
                  <em>/100</em>
                </strong>
              </div>
              <ul>
                <li>
                  <span>排名</span>
                  <strong>1</strong>
                </li>
                <li>
                  <span>数据更新</span>
                  <strong>{selectedRecord.updatedAt}</strong>
                </li>
              </ul>
            </div>

            <div className="cdv2-radar-section">
              <div className="cdv2-subtitle">维度得分</div>
              <ResponsiveContainer width="100%" height={230}>
                <RadarChart
                  data={selectedRecord.dimensions.map((item) => ({
                    subject: item.label,
                    value: item.value,
                    fullMark: item.max,
                  }))}
                  outerRadius={76}
                >
                  <PolarGrid stroke="#dce9e2" />
                  <PolarAngleAxis dataKey="subject" tick={{ fontSize: 11, fill: "#59706a" }} />
                  <PolarRadiusAxis axisLine={false} tick={false} domain={[0, 25]} />
                  <Radar dataKey="value" stroke="#0e9488" fill="#0e9488" fillOpacity={0.16} strokeWidth={2} />
                </RadarChart>
              </ResponsiveContainer>
              <div className="cdv2-dimension-row">
                {selectedRecord.dimensions.map((item) => (
                  <div key={item.label}>
                    <span>{item.label}</span>
                    <strong>
                      {item.value}/{item.max}
                    </strong>
                  </div>
                ))}
              </div>
            </div>

            <div className="cdv2-side-block">
              <div className="cdv2-block-head">
                <h3>代表性内容证据</h3>
                <button type="button" className="cdv2-link-button small">查看更多</button>
              </div>
              <div className="cdv2-evidence-grid">
                {selectedRecord.evidences.map((item, index) => (
                  <article key={`${item.title}-${index}`} className="cdv2-evidence-card">
                    <div className={`cdv2-evidence-cover ${item.tone}`}>
                      <span>{selectedRecord.name.slice(0, 1)}</span>
                    </div>
                    <strong>{item.title}</strong>
                    <p>{item.stats}</p>
                    <small>{item.date}</small>
                  </article>
                ))}
              </div>
            </div>

            <div className="cdv2-side-block">
              <h3>匹配关键词</h3>
              <div className="cdv2-chip-group">
                {selectedRecord.keywords.map((item) => (
                  <span key={item} className="cdv2-chip">
                    {item}
                  </span>
                ))}
              </div>
            </div>

            <div className="cdv2-side-block">
              <h3>商业化信号</h3>
              <div className="cdv2-fact-grid">
                {selectedRecord.commerceFacts.map((item) => (
                  <div key={item.label} className="cdv2-fact-card">
                    <span>{item.label}</span>
                    <strong>{item.value}</strong>
                  </div>
                ))}
              </div>
            </div>

            <div className="cdv2-side-block">
              <div className="cdv2-block-head">
                <h3>关联话题</h3>
                <button type="button" className="cdv2-link-button small">查看更多</button>
              </div>
              <div className="cdv2-topic-group">
                {selectedRecord.hotTopics.map((item) => (
                  <span key={item.label} className="cdv2-topic-pill">
                    {item.label}
                    <em>{item.heat}</em>
                  </span>
                ))}
              </div>
            </div>

            <div className="cdv2-side-actions">
              <button type="button" className="cdv2-button primary" onClick={() => setMessage(`已将 ${selectedRecord.name} 加入候选池。`)}>
                加入候选池
              </button>
              <button type="button" className="cdv2-button ghost" onClick={() => setMessage(`已将 ${selectedRecord.name} 加入友商池。`)}>
                加入友商池
              </button>
              <button type="button" className="cdv2-button ghost" onClick={() => setMessage(`已为 ${selectedRecord.name} 创建监控任务。`)}>
                创建监控
              </button>
              <button type="button" className="cdv2-button ghost" onClick={() => setMessage(`已导出 ${selectedRecord.name} 的评分卡。`)}>
                <Download size={15} />
                导出
              </button>
            </div>
              </>
            ) : (
              <div className="cdv2-empty-state is-side">
                <strong>{isLoading ? "正在生成评分卡" : "暂无评分卡"}</strong>
                <p>{isLoading ? "搜索完成后会自动展示排名最高的达人。" : "请选择赛道并发起搜索，或切换到已有候选池的赛道。"}</p>
              </div>
            )}
          </section>

          <section className="cdv2-panel cdv2-floating-tip">
            <div className="cdv2-tip-row">
              <Target size={16} />
              <span>{message}</span>
            </div>
            <div className="cdv2-tip-actions">
              <TipStat icon={<Users size={14} />} label="达人" value={String(records.length)} />
              <TipStat icon={<TrendingUp size={14} />} label="高潜" value={String(tabCounts.A + tabCounts.B)} />
              <TipStat icon={<CircleDollarSign size={14} />} label="A类" value={String(tabCounts.A)} />
              <TipStat icon={<Eye size={14} />} label="赛道" value={selectedVertical?.name || "全部"} />
            </div>
          </section>
        </aside>
      </div>
    </section>
  );
}

function VerticalSelect({
  value,
  verticals,
  onChange,
}: {
  value: string;
  verticals: VerticalOption[];
  onChange: (value: string) => void;
}) {
  return (
    <label className="cdv2-filter-select">
      <span>赛道</span>
      <select value={value} onChange={(event) => onChange(event.target.value)}>
        <option value="all">全部赛道</option>
        {verticals.map((vertical) => (
          <option key={vertical.id} value={String(vertical.id)}>
            {vertical.name}
          </option>
        ))}
      </select>
      <ChevronsUpDown size={14} />
    </label>
  );
}

function CreatorNameLink({ record }: { record: CreatorRecord }) {
  if (!record.profileUrl) {
    return <strong>{record.name}</strong>;
  }
  return (
    <a
      className="cdv2-creator-link"
      href={record.profileUrl}
      target="_blank"
      rel="noreferrer"
      onClick={(event) => event.stopPropagation()}
      aria-label={`打开 ${record.name} 的主页`}
    >
      <strong>{record.name}</strong>
    </a>
  );
}

function RealtimeConfigControl({
  enabled,
  ratio,
  onToggle,
  onRatioChange,
}: {
  enabled: boolean;
  ratio: string;
  onToggle: (value: boolean) => void;
  onRatioChange: (value: string) => void;
}) {
  return (
    <div className="cdv2-realtime-control">
      <span>实时获取</span>
      <div className="cdv2-realtime-main">
        <label className={`cdv2-switch ${enabled ? "is-active" : ""}`}>
          <input
            type="checkbox"
            checked={enabled}
            onChange={(event) => onToggle(event.target.checked)}
          />
          <i aria-hidden />
          <strong>{enabled ? "开启" : "关闭"}</strong>
        </label>
        <div className={`cdv2-realtime-ratio ${enabled ? "" : "is-disabled"}`}>
          <input
            value={ratio}
            inputMode="numeric"
            disabled={!enabled}
            onChange={(event) => onRatioChange(event.target.value)}
          />
          <em>%</em>
        </div>
      </div>
      <small>小红书 / 抖音，默认 50%</small>
    </div>
  );
}

function FilterSelectControl({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: Array<{ value: string; label: string }>;
  onChange: (value: string) => void;
}) {
  return (
    <label className="cdv2-filter-select">
      <span>{label}</span>
      <select value={value} onChange={(event) => onChange(event.target.value)}>
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
      <ChevronsUpDown size={14} />
    </label>
  );
}

function FilterInputControl({
  label,
  value,
  placeholder,
  suffix,
  inputMode = "decimal",
  onChange,
  onBlur,
}: {
  label: string;
  value: string;
  placeholder: string;
  suffix: string;
  inputMode?: React.HTMLAttributes<HTMLInputElement>["inputMode"];
  onChange: (value: string) => void;
  onBlur?: () => void;
}) {
  return (
    <label className="cdv2-filter-input">
      <span>{label}</span>
      <div>
        <input
          value={value}
          placeholder={placeholder}
          inputMode={inputMode}
          onChange={(event) => onChange(event.target.value)}
          onBlur={onBlur}
        />
        <em>{suffix}</em>
      </div>
    </label>
  );
}

function FilterRangeControl({
  label,
  minValue,
  maxValue,
  minPlaceholder,
  maxPlaceholder,
  suffix,
  onMinChange,
  onMaxChange,
}: {
  label: string;
  minValue: string;
  maxValue: string;
  minPlaceholder: string;
  maxPlaceholder: string;
  suffix: string;
  onMinChange: (value: string) => void;
  onMaxChange: (value: string) => void;
}) {
  return (
    <div className="cdv2-filter-range">
      <span>{label}</span>
      <div>
        <input
          value={minValue}
          placeholder={minPlaceholder}
          inputMode="decimal"
          onChange={(event) => onMinChange(event.target.value)}
        />
        <i>-</i>
        <input
          value={maxValue}
          placeholder={maxPlaceholder}
          inputMode="decimal"
          onChange={(event) => onMaxChange(event.target.value)}
        />
        <em>{suffix}</em>
      </div>
    </div>
  );
}

function DistributionBar({ label, value, width }: { label: string; value: string; width: number }) {
  return (
    <div className="cdv2-distribution-row">
      <span>{label}</span>
      <div className="cdv2-distribution-track">
        <i style={{ width: `${width}%` }} />
      </div>
      <strong>{value}</strong>
    </div>
  );
}

function TrendMetric({ label, value, delta }: { label: string; value: string; delta: string }) {
  return (
    <div className="cdv2-trend-card">
      <span>{label}</span>
      <strong>{value}</strong>
      <em>{delta}</em>
    </div>
  );
}

function TipStat({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) {
  return (
    <div className="cdv2-tip-stat">
      <span>{icon}</span>
      <div>
        <small>{label}</small>
        <strong>{value}</strong>
      </div>
    </div>
  );
}
