export type DashboardConfidence = "low" | "medium" | "high";
export type DashboardSampleStatus = "insufficient" | "limited" | "enough";

export type OpportunityRiskTag =
  | "small_sample_spike"
  | "single_platform_signal"
  | "stale_data"
  | "overheated_competition"
  | "missing_execution_parameters"
  | "high_cost";

export type OpportunityAction = {
  kind: string;
  label: string;
  risk: "low" | "high";
  payload: Record<string, unknown>;
};

export type OpportunitySample = {
  type: "post" | "comment" | "content" | "creator" | "competitor";
  title?: string;
  body?: string;
  platform?: string | null;
  url?: string | null;
  publish_time?: string | null;
  engagement?: Record<string, unknown>;
  matched_terms?: string[];
  raw_ref?: Record<string, unknown>;
};

export type DashboardOpportunity = {
  id: string;
  type: "creator" | "keyword" | "competitor" | "content";
  name: string;
  display_title?: string;
  display_subtitle?: string;
  target_url?: string | null;
  platform?: string | null;
  score: number;
  score_breakdown?: {
    heat_growth: number;
    sample_confidence: number;
    competition_gap: number;
    actionability: number;
  };
  risk_tags?: OpportunityRiskTag[];
  evidence_summary?: string[];
  sample_scope?: {
    window: string;
    platforms: string[];
    sample_count: number;
    last_updated_at?: string | null;
  };
  trend?: {
    change_24h: number;
    points_7d: Array<Record<string, unknown>>;
    points_14d: Array<Record<string, unknown>>;
    points_30d: Array<Record<string, unknown>>;
  };
  actions?: OpportunityAction[] | string[];
  samples?: OpportunitySample[];
  feedback_state?: "valid" | "false_positive" | "watch" | null;
  change_24h?: number;
  trend_7d?: number;
  confidence?: DashboardConfidence;
  reason?: string;
  evidence_count?: number;
  payload?: Record<string, unknown>;
  detail?: { summary: string[]; trend_30d: Array<Record<string, unknown>>; evidence: unknown };
};

export type DashboardAction = {
  title: string;
  reason: string;
  target_type: string;
  action: string;
  payload: Record<string, unknown>;
};

export type DashboardSummary = {
  decision: {
    headline: string;
    confidence: DashboardConfidence;
    sample_status: DashboardSampleStatus;
    sample_summary: string;
    risk_notes: string[];
    evidence_count: number;
  };
  actions: { do_now: DashboardAction[]; watch_today: DashboardAction[]; defer: DashboardAction[] };
  monitoring: {
    running_jobs: number;
    pending_jobs?: number;
    completed_jobs?: number;
    failed_jobs?: number;
    job_status_counts?: Record<string, number>;
    today_collected: number;
    errors: number;
    monitor_pools: number;
    realtime_jobs: number;
    last_updated_at?: string | null;
  };
  opportunities: DashboardOpportunity[];
  top_opportunities?: DashboardOpportunity[];
  watchlist?: DashboardOpportunity[];
  ignored_opportunities?: DashboardOpportunity[];
  diagnostics?: Array<{ code: string; title: string; body: string; action?: string }>;
  type_decisions?: Partial<
    Record<
      DashboardOpportunity["type"],
      {
        headline: string;
        confidence: DashboardConfidence;
        sample_status: DashboardSampleStatus;
        sample_summary: string;
        risk_notes: string[];
        evidence_count: number;
      }
    >
  >;
  type_diagnostics?: Partial<
    Record<DashboardOpportunity["type"], Array<{ code: string; title: string; body: string; action?: string }>>
  >;
  scoring_profile?: { weights: Record<string, number>; window: string };
};

export type DatabaseStats = {
  total_collected: number;
  research_posts: number;
  research_comments: number;
  raw_records: number;
  creator_profiles: number;
  entity_tags: number;
  creator_candidates: number;
  by_platform: {
    posts?: Record<string, number>;
    comments?: Record<string, number>;
    raw_records?: Record<string, number>;
  };
  raw_platform_tables?: Record<string, Record<string, number>>;
  raw_platform_totals?: Record<string, number>;
};

export type AiInsightSummary = {
  run: null | {
    id: number;
    status: string;
    input_summary?: Record<string, unknown>;
    created_at?: string;
  };
  hotspots: Array<Record<string, unknown>>;
  topic_ideas: Array<Record<string, unknown>>;
};

export type AiTopicIdeasSummary = {
  topic_ideas: Array<Record<string, unknown>>;
};

export type TodayIntelligenceSummary = {
  status: "completed" | "fallback" | "running" | "missing" | "stale" | "error";
  source: "ai" | "rules" | "none";
  project_id?: string | null;
  project?: {
    id?: string | null;
    requested_id?: string | null;
    name?: string | null;
    primary_goal?: string | null;
    platforms?: string[];
    scene_pack_id?: number | null;
    sample_status?: string | null;
    recommended_action?: string | null;
  } | null;
  generated_at?: string | null;
  expires_at?: string | null;
  error?: string | null;
  provider?: { name?: string | null; model?: string | null } | null;
  executive_summary?: string;
  actions?: Array<Record<string, unknown>>;
  opportunity_explanations?: Array<Record<string, unknown>>;
  risk_explanations?: Array<Record<string, unknown>>;
  sample_quality_explanation?: Record<string, unknown>;
  data_bias_notes?: string[];
  assumptions?: string[];
  input_summary?: Record<string, unknown>;
  ai_status?: {
    status?: string | null;
    source?: string | null;
    generated_at?: string | null;
    expires_at?: string | null;
    provider?: { name?: string | null; model?: string | null } | null;
    error?: string | null;
  };
  dashboard: DashboardSummary;
  database_stats: DatabaseStats;
};

export type ResearchJob = {
  id: number;
  name: string;
  topic: string;
  keywords: string[];
  platforms: string[];
  status: string;
  collection_mode?: string;
  comment_policy?: {
    max_posts_per_job?: number | null;
    [key: string]: unknown;
  };
};

export type PostRecord = {
  id: number;
  platform: string;
  platform_post_id: string;
  title?: string | null;
  content?: string | null;
  url?: string | null;
  publish_time?: string | null;
  engagement_json?: Record<string, unknown>;
};

export type CommentRecord = {
  id: number;
  platform: string;
  platform_comment_id: string;
  platform_post_id?: string | null;
  content?: string | null;
  publish_time?: string | null;
  like_count?: number | null;
};

export type RawRecord = {
  id: number;
  platform: string;
  source_type: string;
  source_id?: string | null;
  payload_hash: string;
  fetched_at?: string | null;
  parser_version?: string;
};

export type AIResult = {
  id: number;
  analysis_job_id?: number;
  target_type: string;
  target_id: string;
  result_json: Record<string, unknown>;
  model: string;
  prompt_version?: string;
  created_at?: string;
};

export type AIProviderConfig = {
  id: number;
  name: string;
  base_url: string;
  model: string;
  timeout?: number;
  max_concurrency?: number;
  default_params?: Record<string, unknown>;
  enabled: boolean;
  api_key_set: boolean;
};

export type AIPromptTemplate = {
  id: number;
  name: string;
  task_type: string;
  platform: string;
  version: string;
  enabled: boolean;
};

export type AIAnalysisJob = {
  id: number;
  research_job_id: number;
  task_type: string;
  scope: Record<string, unknown>;
  status: string;
  provider_config_id: number;
  prompt_template_id: number;
  created_at?: string;
};

export type AIJobStatus = {
  job?: ResearchJob;
  stats: {
    posts: number;
    comments: number;
    authors?: number;
    raw_records?: number;
  };
  providers: AIProviderConfig[];
  prompts: AIPromptTemplate[];
  analysis_jobs: AIAnalysisJob[];
  results_count: number;
  can_run: boolean;
  diagnostics: Array<{ code: string; message: string }>;
};

export type GrowthProjectAction = {
  kind: string;
  label: string;
};

export type GrowthProjectSampleStatus = {
  kind: string;
  label: string;
  project_state?: string;
};

export type GrowthProjectMetrics = {
  jobs: number;
  posts: number;
  comments: number;
  raw_records: number;
  creators: number;
  failed_jobs: number;
  running_jobs: number;
  pending_jobs: number;
};

export type GrowthProjectSummary = {
  id: string;
  project_record_id?: number;
  name: string;
  primary_goal: "topic_discovery" | "creator_discovery" | "keyword_expansion" | "competitor_monitoring" | "mixed_research";
  platforms: string[];
  status: string;
  sample_status: GrowthProjectSampleStatus;
  recommended_action: GrowthProjectAction;
  opportunity_score: number | null;
  last_collected_at?: string | null;
  metrics: GrowthProjectMetrics;
  job_ids: number[];
};

export type GrowthProjectDetail = {
  project: GrowthProjectSummary;
  status_bar: {
    recommended_action: string;
    sample_status: string;
    opportunity_score: number | null;
  };
  overview: {
    current_judgment: string;
    recommended_actions: GrowthProjectAction[];
    sample_status: GrowthProjectSampleStatus;
    collection_health: GrowthProjectMetrics;
  };
  ai_insights: {
    summary: string;
    missing_data: string[];
  };
  sample_data: {
    posts: number;
    comments: number;
    creators: number;
    raw_records: number;
  };
  keywords: Array<{ keyword: string; type: string; source: string; status?: string }>;
  collection_records: Array<{
    id: number;
    name: string;
    platforms: string[];
    collection_mode: string;
    keywords: string[];
    status: string;
    posts: number;
    comments: number;
    raw_records: number;
    updated_at?: string | null;
  }>;
  settings: {
    primary_goal: string;
    platforms: string[];
    scene_pack_id?: number | null;
    comment_collection_enabled?: boolean;
    refresh_cadence: string;
    custom_interval_value?: number | null;
    custom_interval_unit?: "hours" | "days" | null;
    refresh_time_utc8?: string | null;
    daily_collection_limit_per_platform?: number | null;
  };
};

export type GrowthProjectCollectionProgress = {
  project_id: string;
  status: "idle" | "queued" | "running" | "completed" | "empty" | "failed" | "cancelled" | string;
  current_job_id?: number | null;
  running_job_id?: number | null;
  queued_jobs: Array<{
    job_id: number;
    project_id?: string | null;
    queue_position: number;
    enqueued_at?: string | null;
  }>;
  queue: {
    running_job_id?: number | null;
    queued_jobs: Array<{
      job_id: number;
      project_id?: string | null;
      queue_position: number;
      enqueued_at?: string | null;
    }>;
    queue_length: number;
  };
  progress: {
    percent: number;
    sample_percent?: number;
    step_percent?: number;
    unit_counts: Record<string, number>;
    sample_counts: {
      posts: number;
      comments: number;
      raw_records: number;
      creators: number;
    };
    target_counts?: {
      posts?: number;
    };
    progress_basis?: "samples" | "steps" | string;
    job?: ResearchJob | null;
    latest_event?: {
      id?: number;
      job_id?: number;
      platform?: string | null;
      event_type?: string;
      message?: string;
      stats_json?: Record<string, unknown> | null;
      created_at?: string | null;
    } | null;
    events?: Array<{
      id?: number;
      job_id?: number;
      platform?: string | null;
      event_type?: string;
      message?: string;
      stats_json?: Record<string, unknown> | null;
      created_at?: string | null;
    }>;
    crawler?: {
      status?: string;
      platform?: string | null;
      crawler_type?: string | null;
      started_at?: string | null;
      latest_log?: {
        level?: string;
        message?: string;
        timestamp?: string;
      } | null;
      log_count?: number;
    } | null;
  };
  automation?: {
    enabled: boolean;
    job_id?: number | null;
    interval_minutes?: number | null;
    next_run_at?: string | null;
    last_scheduled_at?: string | null;
    daemon: {
      configured_enabled: boolean;
      running: boolean;
      mode?: string;
      interval_seconds: number;
      started_at?: string | null;
      last_tick_at?: string | null;
      last_success_at?: string | null;
      last_error?: string | null;
      last_enqueued_jobs: Array<{
        job_id: number;
        project_id?: string | null;
        queue_position?: number | null;
      }>;
    };
  };
};

export type GrowthProjectCollectionSortMode =
  | "relevance"
  | "latest"
  | "most_liked"
  | "most_commented"
  | "most_collected";

export type GrowthProjectCollectionTimePreset = "all" | "1d" | "7d" | "30d" | "180d";

export type GrowthProjectCollectionFillStrategy = "prefer_fill";

export type GrowthProjectKeywordType = "core" | "expanded" | "excluded" | "pending";

export type GrowthProjectKeywordStatus = "active" | "pending" | "excluded" | "inactive";

export type GrowthProjectKeywordScope =
  | "all_project"
  | "selected_project"
  | "all_project_plus_extra"
  | "selected_project_plus_extra"
  | "extra_only";

export type GrowthProjectCollectionRunPayload = {
  platforms: string[];
  keyword_scope: GrowthProjectKeywordScope;
  selected_keywords: string[];
  extra_keywords: string[];
  persist_to_project: boolean;
  target_posts_per_platform: number;
  collection_window_days: number | null;
  prefer_latest_posts: boolean;
  sort_mode: GrowthProjectCollectionSortMode;
  time_preset: GrowthProjectCollectionTimePreset;
  time_start: string | null;
  time_end: string | null;
  max_results_per_keyword_per_platform: number;
  fill_strategy: GrowthProjectCollectionFillStrategy;
  max_extra_pages: number;
};

export type BackgroundTaskProgress = {
  percent?: number;
  stage?: string;
  label?: string;
};

export type BackgroundTaskItem = {
  id: string;
  type: "crawler" | "research_execution" | "research_queue" | "creator_search" | "ai_analysis" | string;
  title: string;
  status: "queued" | "running" | "stopping" | "completed" | "failed" | "cancelled" | "unknown" | string;
  progress?: BackgroundTaskProgress;
  source?: string;
  started_at?: string | null;
  updated_at?: string | null;
  cancellable: boolean;
  cancel_reason?: string | null;
  deletable?: boolean;
  delete_reason?: string | null;
  related_job_id?: number | null;
  detail?: Record<string, unknown> | null;
};

export type BackgroundTaskSummary = {
  total: number;
  running: number;
  queued: number;
  cancellable: number;
  deletable?: number;
  failed: number;
  completed: number;
  cancelled: number;
};

export type GrowthProjectCreatePayload = {
  name: string;
  scene_pack_id?: number;
  primary_goal: GrowthProjectSummary["primary_goal"];
  platforms: string[];
  keywords: string[];
  collection_depth: "lightweight" | "standard" | "deep";
  refresh_cadence: "off" | "daily" | "three_days" | "weekly";
  refresh_time_utc8?: string | null;
  daily_collection_limit_per_platform?: number;
  auto_ai_analysis: boolean;
  start_immediately?: boolean;
};

export type GrowthProjectUpdatePayload = {
  name?: string;
  primary_goal?: GrowthProjectSummary["primary_goal"];
  platforms?: string[];
  scene_pack_id?: number;
  scene_pack_keyword_mode?: "replace" | "append" | "link_only";
  comment_collection_enabled?: boolean;
  refresh_cadence?: "off" | "daily" | "three_days" | "weekly" | "custom_hours" | "custom_days";
  custom_interval_value?: number;
  custom_interval_unit?: "hours" | "days";
  refresh_time_utc8?: string | null;
  daily_collection_limit_per_platform?: number;
  keywords?: Array<{
    keyword: string;
    keyword_type: GrowthProjectKeywordType;
    source: string;
    status: GrowthProjectKeywordStatus;
  }>;
};

export type GrowthProjectKeywordAISuggestPayload = {
  input_text: string;
  count?: number;
};

export type GrowthProjectKeywordAISuggestion = {
  keyword: string;
  keyword_type: Extract<GrowthProjectKeywordType, "core" | "expanded" | "excluded">;
  reason?: string | null;
  confidence?: number | null;
  source?: "ai" | "ai_imported" | string;
  raw?: Record<string, unknown>;
};

export type GrowthProjectKeywordAISuggestResponse = {
  suggestions: GrowthProjectKeywordAISuggestion[];
  provider?: {
    name?: string | null;
    model?: string | null;
  };
  context?: {
    project_id?: string;
    project_name?: string;
    primary_goal?: string;
    platforms?: string[];
    requested_count?: number;
    existing_keyword_count?: number;
  };
};

export type ScenePackOption = {
  id: number;
  vertical_id: number;
  name: string;
  description?: string | null;
  default_platforms: string[];
  primary_goal: GrowthProjectSummary["primary_goal"];
  default_collection_depth: GrowthProjectCreatePayload["collection_depth"];
  default_ai_template?: string | null;
  source?: string;
  archived?: boolean;
  enabled: boolean;
};

export type ResearchTab =
  | "today"
  | "projects"
  | "content_production"
  | "creators"
  | "content_tracking"
  | "lead_attribution"
  | "competitors"
  | "keyword_heat"
  | "admin"
  | "settings"
  | "data_board"
  | "key_insights"
  | "topic_tracking"
  | "account_analysis"
  | "content_library"
  | "reports_center"
  | "ai_assistant";

export type SideNavConfigItem = {
  tab: ResearchTab;
  visible: boolean;
  sort_order: number;
};

export type SideNavConfigValue = {
  items: SideNavConfigItem[];
};

export type SideNavConfigResponse = {
  key: string;
  value: SideNavConfigValue;
  updated_at?: string | null;
};

export type PendingExecution = {
  title: string;
  action: string;
  targetType: DashboardOpportunity["type"];
  platform?: string | null;
  payload: Record<string, unknown>;
};

export type AttributionModel = "first_touch" | "last_touch" | "linear";

export type LeadAttributionConfig = {
  default_model: AttributionModel;
  window_days: number;
  enabled_dimensions: Array<"platform" | "keyword" | "content" | "creator">;
  dedupe_by: "external_lead_id" | "phone_hash" | "wechat_hash";
};

export type LeadAttributionFunnelStep = {
  key: string;
  label: string;
  value: number;
  rate: number | null;
};

export type LeadAttributionRow = {
  dimension_key: string;
  credit: number;
  lead_count: number;
  qualified_lead_count: number;
  wechat_added_count: number;
  first_reply_count: number;
  conversion_count?: number;
  deal_count: number;
  deal_amount: number;
  cost?: number;
  cpl?: number | null;
  cost_per_qualified_lead?: number | null;
  roi?: number | null;
  title?: string;
  platform?: string | null;
  source_keyword?: string | null;
  meta_json?: Array<Record<string, unknown>>;
};

export type LeadAttributionSummaryPayload = {
  project_id: number | string;
  project_name: string;
  scope?: "project" | "global";
  summary: {
    lead_count: number;
    qualified_lead_count: number;
    wechat_added_count: number;
    first_reply_count: number;
    deal_lead_count: number;
    deal_count: number;
    deal_amount: number;
    qualified_lead_rate?: number | null;
    lead_to_wechat_rate?: number | null;
    wechat_to_reply_rate?: number | null;
    reply_to_deal_rate?: number | null;
    cost?: number;
    cpl?: number | null;
    cost_per_qualified_lead?: number | null;
    roi?: number | null;
    model: AttributionModel;
    date_from?: string | null;
    date_to?: string | null;
  };
  funnel: LeadAttributionFunnelStep[];
  top_platforms: LeadAttributionRow[];
  top_keywords: LeadAttributionRow[];
  top_contents: LeadAttributionRow[];
  top_creators: LeadAttributionRow[];
  diagnostics: Array<{ code: string; title: string; body: string }>;
  sample_analysis?: {
    mode: "sample_analysis";
    summary: {
      job_count: number;
      raw_record_count: number;
      post_count: number;
      comment_count: number;
      creator_count: number;
      intent_comment_count: number;
      intent_comment_rate: number;
    };
    platform_rows: Array<{
      dimension_key: string;
      platform?: string | null;
      post_count: number;
      comment_count: number;
      sample_count: number;
    }>;
    top_contents: Array<{
      post_id?: number | null;
      title: string;
      platform?: string | null;
      publish_time?: string | null;
      engagement_score: number;
      url?: string | null;
    }>;
    top_keywords: Array<{
      keyword: string;
      sample_count: number;
      hit_count: number;
      score: number;
    }>;
    intent_terms: Array<{ term: string; count: number }>;
    diagnostics: Array<{ code: string; title: string; body: string }>;
  };
};

export type LeadListItem = {
  id: number;
  project_id: number;
  external_lead_id?: string | null;
  lead_status: string;
  lead_score?: number | null;
  owner?: string | null;
  name_masked?: string | null;
  phone_hash?: string | null;
  wechat_hash?: string | null;
  source_platform?: string | null;
  source_keyword?: string | null;
  first_touch_at?: string | null;
  last_touch_at?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  meta_json?: Record<string, unknown>;
};

export type LeadTouchpoint = {
  id: number;
  lead_id: number;
  project_id: number;
  touch_type: string;
  platform?: string | null;
  source_keyword?: string | null;
  creator_id?: string | null;
  post_id?: number | null;
  raw_record_id?: number | null;
  touch_time?: string | null;
  session_key?: string | null;
  weight_hint?: number | null;
  evidence_json?: Record<string, unknown>;
  created_at?: string | null;
};

export type LeadConversionEvent = {
  id: number;
  lead_id: number;
  project_id: number;
  event_type: string;
  event_value?: number | null;
  event_count?: number;
  event_time?: string | null;
  source_system?: string | null;
  operator?: string | null;
  payload_json?: Record<string, unknown>;
  created_at?: string | null;
};

export type LeadAttributionExplanation = {
  model: AttributionModel | string;
  window_days: number;
  conversion_summary: {
    event_types: string[];
    deal_amount: number;
  };
  top_dimensions: Partial<
    Record<"platform" | "keyword" | "content" | "creator", { dimension_key: string; credit: number }>
  >;
  touchpoint_summary: {
    touch_count: number;
    first_touch_at?: string | null;
    last_touch_at?: string | null;
    winning_touchpoint_id?: number | null;
    winning_touch_type?: string | null;
  };
  narrative: string;
};

export type LeadDetailResponse = {
  lead: LeadListItem;
  touchpoints: LeadTouchpoint[];
  conversion_events: LeadConversionEvent[];
  attribution: Array<{
    id?: number;
    project_id: number;
    lead_id: number;
    conversion_event_id: number;
    model: string;
    dimension: string;
    dimension_key: string;
    credit: number;
    window_days?: number;
    meta_json?: Record<string, unknown>;
    computed_at?: string | null;
  }>;
  attribution_explanation: LeadAttributionExplanation;
};

export type LeadTimelineEntry = {
  kind: "touchpoint" | "conversion_event";
  time?: string | null;
  payload: LeadTouchpoint | LeadConversionEvent;
  model?: string;
  role?: "winning" | "assist" | "out_of_window" | "after_conversion" | "unattributed";
  related_conversion_event_ids?: number[];
  winning_conversion_event_ids?: number[];
  window_days?: number;
  conversion_count?: number;
};

export type LeadTimelineResponse = {
  lead_id: number;
  timeline: LeadTimelineEntry[];
};
