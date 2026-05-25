export type UnknownRecord = Record<string, unknown>;

export type CreatorSearchProgress = {
  stage: string;
  label: string;
  percent: number;
};

export type CreatorSearchLog = {
  created_at?: string | null;
  stage?: string;
  level?: string;
  message?: string;
};

export type CreatorSearchRealtimeDiagnostics = {
  status?: string;
  error?: string;
} & UnknownRecord;

export type CreatorSearchResponse = {
  intent?: UnknownRecord | null;
  diagnostics?: UnknownRecord;
  realtime?: CreatorSearchRealtimeDiagnostics;
  progress?: CreatorSearchProgress;
  results: UnknownRecord[];
};

export type CreatorSearchTask = {
  task_id: string;
  status: string;
  request?: UnknownRecord;
  progress?: CreatorSearchProgress;
  logs?: CreatorSearchLog[];
  result?: CreatorSearchResponse | null;
  error?: string | null;
};

export type Tier = "A" | "B" | "C";
export type MatchBand = "high" | "mid" | "low";

export type DiscoveryStageKey = "understand" | "expand" | "find" | "rank";

export const DISCOVERY_STAGES: { key: DiscoveryStageKey; label: string }[] = [
  { key: "understand", label: "理解需求" },
  { key: "expand", label: "扩展关键词" },
  { key: "find", label: "寻找达人" },
  { key: "rank", label: "结果排序" },
];

export const PLATFORM_OPTIONS = [
  { value: "dy", label: "抖音" },
  { value: "xhs", label: "小红书" },
  { value: "bili", label: "B站" },
  { value: "wxchannels", label: "视频号" },
];

export function asRecord(value: unknown): UnknownRecord {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as UnknownRecord) : {};
}

export function text(value: unknown, fallback = "-") {
  return value === null || value === undefined || value === "" ? fallback : String(value);
}

export function num(value: unknown): number {
  const next = Number(value);
  return Number.isFinite(next) ? next : 0;
}

export function array(value: unknown): UnknownRecord[] {
  return Array.isArray(value) ? value.map(asRecord) : [];
}

export function textArray(value: unknown): string[] {
  return Array.isArray(value) ? value.map((item) => String(item)).filter(Boolean) : [];
}

export function optionalNumber(value: string): number | undefined {
  const trimmed = value.trim();
  if (!trimmed) return undefined;
  const next = Number(trimmed);
  return Number.isFinite(next) ? next : undefined;
}

export function sleepMs(ms: number) {
  return new Promise<void>((resolve) => setTimeout(resolve, ms));
}

export function toggleSelected(current: Set<string>, key: string, checked: boolean) {
  const next = new Set(current);
  if (checked) next.add(key);
  else next.delete(key);
  return next;
}

export function toggleValue<T>(values: T[], value: T, checked: boolean) {
  if (checked) return values.includes(value) ? values : [...values, value];
  return values.filter((item) => item !== value);
}

export function creatorRowKey(row: UnknownRecord) {
  return `${text(row.platform, "unknown")}:${text(row.creator_id || row.account_id, "unknown")}`;
}

export function candidateMetric(row: UnknownRecord, key: string) {
  const metrics = asRecord(asRecord(row.tag_summary_json).profile_metrics);
  return row[key] ?? metrics[key];
}

export function candidateTagLabel(tag: UnknownRecord) {
  const evidence = asRecord(tag.evidence_json);
  return text(tag.tag_name || evidence.tag_name || tag.name || tag.term || tag.keyword, "命中标签");
}

export function formatCount(value: unknown): string {
  const n = num(value);
  if (!Number.isFinite(n) || n <= 0) return "-";
  if (n >= 100_000_000) return `${(n / 100_000_000).toFixed(1)}亿`;
  if (n >= 10_000) return `${(n / 10_000).toFixed(1)}万`;
  return String(Math.round(n));
}

export function formatPercent(value: unknown): string {
  const n = Number(value);
  if (!Number.isFinite(n)) return "-";
  const pct = Math.abs(n) <= 1 ? n * 100 : n;
  return `${pct.toFixed(2)}%`;
}

export function formatScore(value: unknown): number {
  const n = num(value);
  return Math.min(100, Math.max(0, Math.round(n)));
}

export function tierOf(row: UnknownRecord): Tier {
  const direct = String(row.tier || "").toUpperCase();
  if (direct === "A" || direct === "B" || direct === "C") return direct as Tier;
  const score = num(row.match_score);
  if (score >= 85) return "A";
  if (score >= 70) return "B";
  return "C";
}

export function matchBandOf(row: UnknownRecord): MatchBand {
  const direct = String(row.match_band || "").toLowerCase();
  if (direct === "high" || direct === "mid" || direct === "low") return direct as MatchBand;
  const score = num(row.match_score);
  if (score >= 85) return "high";
  if (score >= 70) return "mid";
  return "low";
}

export function matchBandLabel(band: MatchBand) {
  if (band === "high") return "高度匹配";
  if (band === "mid") return "较高匹配";
  return "较高匹配";
}

export function tierLabel(tier: Tier) {
  if (tier === "A") return "A类 精准匹配";
  if (tier === "B") return "B类 高潜达人";
  return "C类 拓展达人";
}

export function labelPlatform(value: unknown): string {
  const v = String(value || "");
  if (v === "xhs") return "小红书";
  if (v === "dy") return "抖音";
  if (v === "bili") return "B站";
  if (v === "wxchannels") return "视频号";
  if (v === "ks") return "快手";
  return v || "未知";
}

export function platformShort(value: unknown): string {
  const v = String(value || "");
  if (v === "xhs") return "小红书";
  if (v === "dy") return "抖音";
  if (v === "bili") return "bili";
  if (v === "wxchannels") return "视频号";
  return v || "-";
}

export function creatorAvatarUrl(row: UnknownRecord): string | undefined {
  const metrics = asRecord(asRecord(row.tag_summary_json).profile_metrics);
  const v = row.avatar_url || row.avatar || metrics.avatar_url || metrics.avatar;
  return v ? String(v) : undefined;
}

export function creatorDisplayName(row: UnknownRecord): string {
  return text(row.display_name || row.nickname || row.creator_id, "-");
}

export function creatorProfileId(row: UnknownRecord): string {
  return text(row.creator_id || row.account_id, "");
}

export function matchedKeywords(row: UnknownRecord): string[] {
  const tagged = array(row.matched_tags).map(candidateTagLabel);
  if (tagged.length) return Array.from(new Set(tagged)).slice(0, 10);
  const fallback = textArray(row.matched_keywords);
  return fallback.slice(0, 10);
}

export type ScoreDimension = {
  key: string;
  label: string;
  value: number;
  max: number;
};

export const DEFAULT_DIMENSIONS: { key: string; label: string; max: number }[] = [
  { key: "content_relevance", label: "内容相关性", max: 25 },
  { key: "audience_match", label: "受众匹配度", max: 25 },
  { key: "engagement", label: "互动表现", max: 25 },
  { key: "commerce", label: "商业化潜力", max: 15 },
  { key: "safety", label: "安全合规", max: 15 },
];

export function scoreDimensions(row: UnknownRecord): ScoreDimension[] {
  const provided = asRecord(row.score_dimensions);
  return DEFAULT_DIMENSIONS.map((spec) => {
    const raw = provided[spec.key];
    if (typeof raw === "number" && Number.isFinite(raw)) {
      return { ...spec, value: Math.min(spec.max, Math.max(0, raw)) };
    }
    return { ...spec, value: estimateDimension(row, spec.key, spec.max) };
  });
}

function estimateDimension(row: UnknownRecord, key: string, max: number): number {
  const score = num(row.match_score);
  const base = score >= 85 ? 0.94 : score >= 70 ? 0.86 : 0.7;
  const jitter: Record<string, number> = {
    content_relevance: 0.02,
    audience_match: -0.04,
    engagement: -0.08,
    commerce: -0.18,
    safety: -0.18,
  };
  const ratio = Math.min(1, Math.max(0, base + (jitter[key] || 0)));
  return Math.round(max * ratio);
}

export type CommerceSignal = {
  key: string;
  label: string;
  value: string;
  note?: string;
};

export function commerceSignals(row: UnknownRecord): CommerceSignal[] {
  const sig = asRecord(row.commerce_signals);
  const priceMin = num(sig.price_min);
  const priceMax = num(sig.price_max);
  const priceLabel = priceMin || priceMax ? `¥${formatCount(priceMin || priceMax)}${priceMin && priceMax && priceMin !== priceMax ? ` ~ ${formatCount(priceMax)}` : ""}` : "-";
  return [
    { key: "price", label: "报价区间", value: priceLabel },
    { key: "gmv_items", label: "带货商品数", value: text(sig.gmv_items, "-") },
    { key: "live_count", label: "直播带货", value: sig.live_count_30d ? `近30天 ${sig.live_count_30d} 场` : "-" },
    { key: "brand_count", label: "合作品牌数", value: text(sig.brand_count, "-") },
  ];
}

export type RelatedTopic = {
  topic: string;
  heat: number;
};

export function relatedTopics(row: UnknownRecord): RelatedTopic[] {
  const items = array(row.related_topics);
  if (!items.length) return [];
  return items
    .map((item) => ({
      topic: text(item.topic || item.tag || item.name, ""),
      heat: num(item.heat || item.count || item.value),
    }))
    .filter((item) => item.topic);
}

export type EvidencePost = {
  title: string;
  cover?: string;
  likes?: number;
  comments?: number;
  collects?: number;
  publishedAt?: string;
};

export function evidencePosts(row: UnknownRecord): EvidencePost[] {
  const reps = array(row.representative_posts);
  return reps.slice(0, 4).map((post) => ({
    title: text(post.title || post.desc || post.content || post.note_id || post.aweme_id, "代表内容"),
    cover: post.cover_url ? String(post.cover_url) : post.image_url ? String(post.image_url) : undefined,
    likes: num(post.like_count || post.likes),
    comments: num(post.comment_count || post.comments),
    collects: num(post.collect_count || post.collects),
    publishedAt: text(post.published_at || post.publish_time || post.create_time, ""),
  }));
}

export function shortTime(value: string | undefined): string {
  if (!value) return "";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value.slice(0, 10);
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${m}-${day}`;
}

export function progressStageKey(stage: string | undefined): DiscoveryStageKey {
  const s = (stage || "").toLowerCase();
  if (s === "intent" || s === "understand" || s === "parse_intent") return "understand";
  if (s === "expand" || s === "expand_keywords" || s === "keywords") return "expand";
  if (s === "find" || s === "find_creators" || s === "database" || s === "realtime") return "find";
  if (s === "rank" || s === "rank_results" || s === "merging" || s === "persistence" || s === "complete") return "rank";
  return "understand";
}
