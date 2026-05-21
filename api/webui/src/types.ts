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
  keywords: Array<{ keyword: string; type: string; source: string }>;
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
      event_type?: string;
      message?: string;
      created_at?: string | null;
    } | null;
  };
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
  | "overview"
  | "tasks"
  | "background_tasks"
  | "opportunities"
  | "creators"
  | "keyword_library"
  | "competitors"
  | "content_tracking"
  | "data"
  | "ai"
  | "export"
  | "config";

export type PendingExecution = {
  title: string;
  action: string;
  targetType: DashboardOpportunity["type"];
  platform?: string | null;
  payload: Record<string, unknown>;
};
