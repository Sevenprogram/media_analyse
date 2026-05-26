// 友商监控工作台用到的数据类型（与后端 4 个 GET 接口对齐）
export type MonitorType = "competitor" | "partner_creator";

export interface WorkbenchAccount {
  id: number;
  platform: string;
  creator_id: string;
  monitor_type?: MonitorType;
  project_ids?: number[];
  display_name?: string | null;
  enabled?: boolean;
  notes?: string | null;
  updated_at?: string | null;
  profile_url?: string | null;
}

export interface TodaySummary {
  account_id: number;
  date: string;
  stale: boolean;
  snapshot_date?: string | null;
  unmatched_post_count: number;
  metrics: {
    new_post_count: number;
    interaction_delta: number;
    new_hot_post_count: number;
    anomaly_count: number;
    new_content_contribution: number;
    old_content_contribution: number;
    new_content_contribution_pct: number;
    old_content_contribution_pct: number;
    breakdown: {
      like: { value: number; delta_pct: number };
      comment: { value: number; delta_pct: number };
      collect: { value: number; delta_pct: number };
      share: { value: number; delta_pct: number };
    };
    yesterday_diff_pct: { new_posts: number; interaction: number };
    deduped_post_count: number;
  };
}

export type ContributionScope = "all" | "new" | "old";

export interface ContributionRow {
  rank: number;
  post_id: string;
  title: string;
  thumbnail_url: string | null;
  duration_sec: number | null;
  publish_time: string | null;
  is_new: boolean;
  interaction_total?: number;
  interaction_delta: number;
  delta_pct: number;
  contribution_share: number;
  tags: string[];
  platform_url: string;
  source_url?: string | null;
  content_type?: string;
  author_verified?: boolean;
  has_valid_url?: boolean;
  link_available?: boolean;
  link_status?: string;
}

export interface ContributionRanking {
  account_id: number;
  date: string;
  stale: boolean;
  scope: ContributionScope;
  rows: ContributionRow[];
  total: number;
}

export interface RefreshDiagnosticEntry {
  id: string;
  timestamp: string | null;
  level: "info" | "warn" | "error" | "success" | string;
  message: string;
}

export interface RefreshDiagnostics {
  account_id: number;
  date: string;
  stale: boolean;
  timezone: string;
  last_refresh_at: string | null;
  last_refresh_status: string | null;
  stats: {
    raw_matched_posts: number;
    author_verified_posts: number;
    displayable_posts?: number;
    eligible_posts: number;
    degraded_link_posts?: number;
    invalid_url_posts: number;
    missing_token_posts: number;
    author_mismatch_posts: number;
  };
  entries: RefreshDiagnosticEntry[];
}

export interface SampledPostRow {
  post_id: string;
  title: string;
  publish_time: string | null;
  platform_url: string;
  source_url?: string | null;
  content_type: string;
  author_verified: boolean;
  has_valid_url: boolean;
  link_status: string;
  interaction_total: number;
  interaction_delta: number;
  like_count: number;
  comment_count: number;
  collect_count: number;
  share_count: number;
}

export interface SampledPostsResponse {
  account_id: number;
  date: string;
  stale: boolean;
  timezone: string;
  total: number;
  rows: SampledPostRow[];
}

export interface CompositionData {
  account_id: number;
  date: string;
  stale: boolean;
  keywords: Array<{ word: string; weight: number }>;
  content_types: Array<{ name: string; value: number }>;
  publish_heatmap: {
    buckets: string[];
    days: string[];
    values: number[][];
  };
}

export function isCompositionData(value: unknown): value is CompositionData {
  const data = value as Partial<CompositionData> | null | undefined;
  const heatmap = data?.publish_heatmap;
  return Boolean(
    data &&
      Array.isArray(data.keywords) &&
      Array.isArray(data.content_types) &&
      heatmap &&
      Array.isArray(heatmap.buckets) &&
      Array.isArray(heatmap.days) &&
      Array.isArray(heatmap.values),
  );
}

export interface AnomalyItem {
  id: string;
  type: string;
  severity: "high" | "medium" | string;
  title: string;
  reason: string;
  timestamp: string | null;
  post_ref: { id: string; title: string } | null;
}

export interface AnomalyFeed {
  account_id: number;
  date: string;
  stale: boolean;
  items: AnomalyItem[];
}
