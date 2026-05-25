import React from "react";
import {
  ChevronDown,
  ExternalLink,
  FileSearch,
  Info,
  RefreshCw,
  Search,
  WandSparkles,
} from "lucide-react";
import { Button, Card } from "../components/ui";
import { api, ApiError } from "../utils/api";

type SubTab = "input" | "trackers" | "records";

type ContentTracker = {
  id: number;
  name?: string | null;
  description?: string | null;
  platforms?: string[] | null;
  included_keywords?: string[] | null;
  excluded_keywords?: string[] | null;
  tracking_mode?: string | null;
  schedule_interval_minutes?: number | null;
  enabled: boolean;
  latest_analysis_run_id?: number | null;
  latest_analysis_snapshot_id?: number | null;
  updated_at?: string | null;
};

type TrackerFormState = {
  name: string;
  description: string;
  platformsText: string;
  includedKeywordsText: string;
  excludedKeywordsText: string;
  scheduleIntervalMinutes: string;
  enabled: boolean;
};

type CollectionFormState = {
  lookbackDays: string;
  limitPerPlatform: string;
  platforms: string[];
  keywordsText: string;
};

type TrackerAnalysisRun = {
  id: number;
  tracker_id: number;
  status?: string | null;
  analysis_version?: string | null;
  window_days?: number | null;
  sample_count?: number | null;
  candidate_count?: number | null;
  sample_quality_score?: number | null;
  trend_strength_score?: number | null;
  noise_rate?: number | null;
  decision_confidence?: number | null;
  started_at?: string | null;
  completed_at?: string | null;
  summary?: Record<string, unknown> | null;
};

type DistributionMap = Record<string, number>;

type SampleKeywordHit = {
  term?: string | null;
  count?: number | null;
  context?: string | null;
};

type SampleFingerprint = {
  content_type?: string | null;
  pain_point?: string | null;
  audience?: string | null;
  conversion_intent?: string | null;
};

type SampleEvidence = {
  pattern_summary?: string | null;
  ai_selection_reason?: string | null;
  sample_note?: string | null;
};

type SampleRow = {
  platform?: string | null;
  platform_post_id: string;
  author_id?: string | null;
  author_name?: string | null;
  title?: string | null;
  url?: string | null;
  publish_time?: string | null;
  candidate_level?: string | null;
  similarity_score?: number | null;
  engagement_total?: number | null;
  matched_keywords?: SampleKeywordHit[] | null;
  fingerprint?: SampleFingerprint | null;
  evidence?: SampleEvidence | null;
  selection_source?: string | null;
  ai_relevance_score?: number | null;
  market_validation_status?: string | null;
};

type TrackerAnalysisSnapshot = {
  id: number;
  tracker_id: number;
  run_id: number;
  snapshot_date?: string | null;
  status?: string | null;
  overview?: {
    status?: string | null;
    judgement_confidence?: string | null;
    headline?: string | null;
    sample_quality_score?: number | null;
    sample_quality_grade?: string | null;
    updated_at?: string | null;
    sample_size?: {
      content_count_24h?: number | null;
      content_count_7d?: number | null;
      creator_count_7d?: number | null;
      platform_count?: number | null;
    } | null;
    growth?: {
      content_growth_rate?: number | null;
      engagement_growth_rate?: number | null;
      new_creator_growth_rate?: number | null;
      viral_ratio_change?: number | null;
    } | null;
    data_quality?: {
      time_continuity?: number | null;
      snapshot_coverage?: number | null;
      history_baseline_ready?: number | null;
    } | null;
  } | null;
  trends?: {
    trend_strength_score?: number | null;
    content_growth_rate?: number | null;
    engagement_growth_rate?: number | null;
    new_creator_growth_rate?: number | null;
    current_viral_ratio?: number | null;
    viral_ratio_change?: number | null;
    platform_distribution?: DistributionMap | null;
  } | null;
  keywords?: {
    keyword_rows?: Array<{
      keyword?: string | null;
      type?: string | null;
      hit_content_count?: number | null;
      hit_creator_count?: number | null;
      avg_similarity?: number | null;
      avg_engagement?: number | null;
      viral_rate?: number | null;
      noise_rate?: number | null;
      keyword_value_score?: number | null;
      recommended_action?: string | null;
    }> | null;
    high_value_keywords?: Array<{ keyword?: string | null; keyword_value_score?: number | null }> | null;
    noise_keywords?: Array<{ keyword?: string | null; noise_rate?: number | null }> | null;
    recommended_include_keywords?: string[] | null;
    recommended_exclude_keywords?: string[] | null;
    ai_keyword_strategy?: {
      recommended_include_keywords?: string[] | null;
      recommended_exclude_keywords?: string[] | null;
      keyword_notes?: string[] | null;
    } | null;
    ai_tracker_suggestions?: {
      included_keywords?: string[] | null;
      excluded_keywords?: string[] | null;
      split_tracker_suggestions?: string[] | null;
      platform_notes?: string[] | null;
    } | null;
  } | null;
  patterns?: {
    content_type_distribution?: DistributionMap | null;
    audience_distribution?: DistributionMap | null;
    pain_point_distribution?: DistributionMap | null;
    conversion_intent_distribution?: DistributionMap | null;
    pattern_clusters?: Array<{
      cluster_key?: string | null;
      content_type?: string | null;
      audience?: string | null;
      conversion_intent?: string | null;
      topic?: string | null;
      sample_count?: number | null;
      creator_count?: number | null;
      engagement_total?: number | null;
      pattern_spread?: number | null;
      cluster_value_score?: number | null;
    }> | null;
    pattern_stability?: number | null;
    pattern_variant_rate?: number | null;
    ai_pattern_insights?: {
      summary?: string | null;
      patterns?: Array<{
        name?: string | null;
        description?: string | null;
        sample_keys?: string[] | null;
      }> | null;
    } | null;
  } | null;
  creators?: {
    creator_count?: number | null;
    new_creator_count?: number | null;
    repeat_creator_count?: number | null;
    new_creator_ratio?: number | null;
    repeat_creator_ratio?: number | null;
    top_creator_dependency?: number | null;
    creator_spread_score?: number | null;
    top_creators?: Array<{
      author_id?: string | null;
      platform?: string | null;
      post_count?: number | null;
      engagement_total?: number | null;
      avg_similarity?: number | null;
      is_new_creator?: boolean | null;
    }> | null;
    emerging_creators?: Array<{
      author_id?: string | null;
      platform?: string | null;
      post_count?: number | null;
      engagement_total?: number | null;
      avg_similarity?: number | null;
      is_new_creator?: boolean | null;
    }> | null;
  } | null;
  samples?: {
    representative_samples?: SampleRow[] | null;
    hot_samples?: SampleRow[] | null;
    early_signal_samples?: SampleRow[] | null;
    all_samples?: SampleRow[] | null;
  } | null;
  risks?: {
    tracker_noise_rate?: number | null;
    platform_concentration?: number | null;
    risk_notes?: string[] | null;
    ai_noise_diagnosis?: {
      summary?: string | null;
      noise_terms?: string[] | null;
      suggested_exclude_keywords?: string[] | null;
      off_topic_reasons?: string[] | null;
    } | null;
  } | null;
  decisions?: {
    conclusion_type?: string | null;
    headline?: string | null;
    decision_confidence_score?: number | null;
    decision_confidence_label?: string | null;
    recommended_actions?: Array<{ action?: string | null; reason?: string | null }> | null;
    ai_explanation?: {
      headline?: string | null;
      summary?: string | null;
      evidence?: string[] | null;
      recommended_actions?: Array<{ action?: string | null; reason?: string | null }> | null;
    } | null;
  } | null;
  meta?: Record<string, unknown> | null;
};

type LatestAnalysisResponse = {
  tracker: ContentTracker;
  run: TrackerAnalysisRun;
  snapshot: TrackerAnalysisSnapshot;
};

type AnalysisHistoryResponse = {
  tracker: ContentTracker;
  snapshots: TrackerAnalysisSnapshot[];
};

type CollectionRun = {
  id: number;
  status?: string | null;
  phase?: string | null;
  mode?: string | null;
  job_id?: number | null;
  analysis_run_id?: number | null;
  summary?: Record<string, unknown> | null;
  error?: { message?: string | null } | null;
  created_at?: string | null;
  updated_at?: string | null;
  completed_at?: string | null;
};

type CollectionRunResponse = {
  tracker?: ContentTracker | null;
  run: CollectionRun;
};

type CollectionRunsResponse = {
  tracker?: ContentTracker | null;
  runs: CollectionRun[];
};

type AnalysisCacheEntry = {
  latest: LatestAnalysisResponse | null;
  history: TrackerAnalysisSnapshot[];
  cachedAt: number;
};

type LoadAnalysisOptions = {
  force?: boolean;
  preferCache?: boolean;
  silent?: boolean;
};

const TRACKER_ANALYSIS_CACHE = new Map<number, AnalysisCacheEntry>();
const TRACKER_COLLECTION_RUN_CACHE = new Map<number, CollectionRun | null>();
const TRACKER_ANALYSIS_CACHE_TTL_MS = 5 * 60 * 1000;
let LAST_SELECTED_TRACKER_ID: number | null = null;
let LAST_CONTENT_TRACKING_SUBTAB: SubTab = "input";

type TrackerKeywordSuggestionResponse = {
  suggestions: {
    included_keywords?: string[] | null;
    excluded_keywords?: string[] | null;
    expanded_keywords?: string[] | null;
    platform_keywords?: Record<string, string[] | null> | null;
    reason?: string | null;
  };
  provider?: {
    name?: string | null;
    model?: string | null;
  } | null;
};

type DistributionRow = {
  name: string;
  value: number;
};

type ActionRow = {
  action: string;
  reason: string;
};

type NormalizedTracker = {
  id: number;
  name: string;
  description: string;
  platforms: string[];
  includedKeywords: string[];
  excludedKeywords: string[];
  scheduleIntervalMinutes: number;
  enabled: boolean;
  updatedAt: string | null;
};

type NormalizedSample = {
  key: string;
  platform: string;
  platformLabel: string;
  title: string;
  url: string | null;
  authorName: string;
  publishTime: string | null;
  similarityScore: number | null;
  engagementTotal: number;
  patternSummary: string;
  candidateLevel: string;
  selectionReason: string;
  marketValidationStatus: string;
};

type NormalizedSnapshotView = {
  statusLabel: string;
  confidenceLabel: string;
  headline: string;
  statusSummary: string;
  sampleQualityScore: number | null;
  sampleQualityGrade: string;
  trendStrengthScore: number | null;
  sampleCount24h: number;
  sampleCount7d: number;
  creatorCount7d: number;
  platformCount: number;
  patternRows: DistributionRow[];
  painRows: DistributionRow[];
  audienceRows: DistributionRow[];
  keywordRows: Array<{
    keyword: string;
    type: string;
    hitContentCount: number;
    hitCreatorCount: number;
    avgSimilarity: number | null;
    avgEngagement: number | null;
    viralRate: number | null;
    noiseRate: number | null;
    keywordValueScore: number | null;
    recommendedAction: string;
  }>;
  highValueKeywords: string[];
  recommendedIncludeKeywords: string[];
  noiseKeywords: string[];
  recommendedExcludeKeywords: string[];
  aiKeywordNotes: string[];
  aiTrackerSuggestions: string[];
  representativeSamples: NormalizedSample[];
  hotSamples: NormalizedSample[];
  earlySignalSamples: NormalizedSample[];
  riskNotes: string[];
  aiNoiseSummary: string;
  aiNoiseTerms: string[];
  aiPatternSummary: string;
  aiPatternRows: ActionRow[];
  aiDecisionSummary: string;
  aiDecisionEvidence: string[];
  recommendedActions: ActionRow[];
  creatorCount: number;
  newCreatorCount: number;
  repeatCreatorCount: number;
  creatorSpreadScore: number | null;
  topCreatorDependency: number | null;
  patternStability: number | null;
  patternVariantRate: number | null;
};

const DEFAULT_TRACKER_FORM: TrackerFormState = {
  name: "",
  description: "",
  platformsText: "xhs,dy",
  includedKeywordsText: "",
  excludedKeywordsText: "",
  scheduleIntervalMinutes: "720",
  enabled: true,
};

const DEFAULT_COLLECTION_PLATFORMS = ["xhs", "dy"];
const COLLECTION_PLATFORM_OPTIONS = ["xhs", "dy", "ks", "bili", "wb", "zhihu", "tieba"];
const COLLECTION_REQUEST_CONFIG = {
  lookbackDays: 7,
  limitPerPlatform: 50,
};

type ContentTrackingPageProps = {
  focusTrackerId?: number | null;
  selectedProjectName?: string | null;
  onUseTrackerForStrategy?: (trackerId: number) => void;
};

function BottomInsightCard({
  title,
  children,
  footer = "查看更多",
  className,
}: {
  title: string;
  children: React.ReactNode;
  footer?: string;
  className?: string;
}) {
  return (
    <Card className={`ct-insight-card${className ? ` ${className}` : ""}`}>
      <div className="ct-section-head">
        <h4>{title}</h4>
      </div>
      {children}
      <button type="button" className="ct-card-more">
        {footer}
      </button>
    </Card>
  );
}

function SampleSourceTitle({ item }: { item: NormalizedSample }) {
  const meta = [item.platformLabel, item.authorName !== "-" ? item.authorName : "", formatDateTime(item.publishTime)]
    .filter(Boolean)
    .join(" · ");
  const title = meta ? `${item.title} · ${meta}` : item.title;

  if (!item.url) {
    return (
      <span className="ct-sample-source-text" title={title}>
        {item.title}
      </span>
    );
  }

  return (
    <a className="ct-sample-source-link" href={item.url} target="_blank" rel="noreferrer" title={title}>
      <span>{item.title}</span>
      <ExternalLink size={12} aria-hidden="true" />
    </a>
  );
}

function DonutChartMock({ total, label }: { total: number; label: string }) {
  return (
    <div className="ct-donut">
      <div className="ct-donut-core">
        <span>{label}</span>
        <strong>总量 {formatCount(total)}</strong>
      </div>
    </div>
  );
}

export function ContentTrackingPage({
  focusTrackerId = null,
  selectedProjectName = null,
  onUseTrackerForStrategy,
}: ContentTrackingPageProps = {}) {
  const [subTab, setSubTab] = React.useState<SubTab>(LAST_CONTENT_TRACKING_SUBTAB);
  const [trackers, setTrackers] = React.useState<ContentTracker[]>([]);
  const [selectedTrackerId, setSelectedTrackerId] = React.useState<number | null>(null);
  const [latestAnalysis, setLatestAnalysis] = React.useState<LatestAnalysisResponse | null>(null);
  const [history, setHistory] = React.useState<TrackerAnalysisSnapshot[]>([]);
  const [query, setQuery] = React.useState("");
  const [trackerMenuOpen, setTrackerMenuOpen] = React.useState(false);
  const [trackersLoading, setTrackersLoading] = React.useState(false);
  const [analysisLoading, setAnalysisLoading] = React.useState(false);
  const [running, setRunning] = React.useState(false);
  const [collecting, setCollecting] = React.useState(false);
  const [collectionRun, setCollectionRun] = React.useState<CollectionRun | null>(null);
  const [savingTracker, setSavingTracker] = React.useState(false);
  const [suggestingTrackerKeywords, setSuggestingTrackerKeywords] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [trackerForm, setTrackerForm] = React.useState<TrackerFormState>(DEFAULT_TRACKER_FORM);
  const [collectionForm, setCollectionForm] = React.useState<CollectionFormState>({
    lookbackDays: String(COLLECTION_REQUEST_CONFIG.lookbackDays),
    limitPerPlatform: String(COLLECTION_REQUEST_CONFIG.limitPerPlatform),
    platforms: DEFAULT_COLLECTION_PLATFORMS,
    keywordsText: "",
  });
  const mountedRef = React.useRef(false);
  const selectedTrackerIdRef = React.useRef<number | null>(null);
  const analysisRequestSeqRef = React.useRef(0);
  const watchedCollectionRunRef = React.useRef<number | null>(null);

  const normalizedTrackers = React.useMemo(
    () => safeArray(trackers).map(normalizeTracker),
    [trackers],
  );

  const filteredTrackers = React.useMemo(() => {
    const keyword = query.trim().toLowerCase();
    if (!keyword) return normalizedTrackers;
    return normalizedTrackers.filter((tracker) => {
      const haystack = [
        tracker.name,
        tracker.description,
        ...tracker.includedKeywords,
        ...tracker.excludedKeywords,
      ]
        .join(" ")
        .toLowerCase();
      return haystack.includes(keyword);
    });
  }, [normalizedTrackers, query]);

  const trackerMenuItems = React.useMemo(
    () => filteredTrackers.slice(0, 12),
    [filteredTrackers],
  );

  const selectedTracker = React.useMemo(
    () => normalizedTrackers.find((item) => item.id === selectedTrackerId) || null,
    [normalizedTrackers, selectedTrackerId],
  );

  React.useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  React.useEffect(() => {
    selectedTrackerIdRef.current = selectedTrackerId;
    if (selectedTrackerId) {
      LAST_SELECTED_TRACKER_ID = selectedTrackerId;
    }
  }, [selectedTrackerId]);

  React.useEffect(() => {
    LAST_CONTENT_TRACKING_SUBTAB = subTab;
  }, [subTab]);

  const snapshotView = React.useMemo(
    () => normalizeSnapshotView(latestAnalysis?.snapshot),
    [latestAnalysis],
  );

  const historyRows = React.useMemo(
    () => safeArray(history).map((item) => ({
      id: item.id,
      snapshotDate: item.snapshot_date || "-",
      statusLabel: formatStatusLabel(item.overview?.status || item.status),
      headline: item.decisions?.headline?.trim() || "分析已完成，暂未生成明确结论",
      trendStrengthScore: safeRounded(item.trends?.trend_strength_score),
      sampleQualityScore: safeRounded(item.overview?.sample_quality_score),
    })),
    [history],
  );

  const hasTrackers = normalizedTrackers.length > 0;
  const hasSelectedTracker = Boolean(selectedTracker);
  const hasAnalysis = Boolean(latestAnalysis?.snapshot);
  const isInitialLoading = trackersLoading && !hasTrackers;
  const noSnapshotYet = hasSelectedTracker && !hasAnalysis && !analysisLoading && !running;
  const collectionLookbackDays = clampInteger(
    collectionForm.lookbackDays,
    COLLECTION_REQUEST_CONFIG.lookbackDays,
    1,
    30,
  );
  const collectionLimitPerPlatform = clampInteger(
    collectionForm.limitPerPlatform,
    COLLECTION_REQUEST_CONFIG.limitPerPlatform,
    1,
    200,
  );
  const collectionPlatforms = collectionForm.platforms;
  const collectionKeywordLabels = splitCsv(collectionForm.keywordsText);
  const collectionConfigError = !collectionKeywordLabels.length
    ? "请先填写搜索关键词。"
    : !collectionPlatforms.length
      ? "请至少选择一个采集平台。"
      : null;
  const collectionLatestLog = safeString(collectionRun?.summary?.latest_log);
  const collectionStatusMessage = collectionRun
    ? `采集任务：${formatCollectionStatusLabel(collectionRun.status)} / ${formatCollectionPhaseLabel(collectionRun.phase)}${
        collectionLatestLog ? ` · ${collectionLatestLog}` : ""
      }`
    : null;
  const collectedPostCount = safeNullableNumber(
    collectionRun?.summary?.collected_post_count as number | null | undefined,
  );
  const collectionFooterMessage = `${collectionConfigError ||
    collectionStatusMessage ||
    "采集新内容入库，并在完成后刷新追踪分析。"}${
    typeof collectedPostCount === "number" ? ` 已采集 ${collectedPostCount} 条。` : ""
  }`;
  const collectionFooterClassName = collectionConfigError
    ? "ct-collection-warning"
    : collectionStatusMessage
      ? "ct-collection-status-line"
      : undefined;

  const trackerSummaryMessage = hasSelectedTracker
    ? selectedTracker?.enabled
      ? "当前追踪器已启用，可直接查看分析或重新运行分析。"
      : "当前追踪器已停用，历史分析仍然可查看。"
    : isInitialLoading
      ? "正在加载追踪器..."
      : hasTrackers
        ? "请选择一个追踪器查看分析。"
        : "数据库中还没有可用追踪器，请先创建。";

  const analysisStatusMessage = running
    ? "分析任务运行中，页面会保留最近一次成功结果。"
    : analysisLoading
      ? "正在加载分析结果..."
      : noSnapshotYet
        ? "该追踪器尚未生成首次分析，点击“运行分析”开始。"
        : hasAnalysis
          ? snapshotView.statusSummary
          : "请选择追踪器后查看分析结果。";

  const loadTrackers = React.useCallback(async () => {
    setTrackersLoading(true);
    try {
      const data = await api<{ trackers: ContentTracker[] }>("/api/content-tracking/trackers");
      const nextTrackers = safeArray(data.trackers);
      setTrackers(nextTrackers);
      setSelectedTrackerId((current) => {
        if (current && nextTrackers.some((item) => item.id === current)) {
          return current;
        }
        if (LAST_SELECTED_TRACKER_ID && nextTrackers.some((item) => item.id === LAST_SELECTED_TRACKER_ID)) {
          return LAST_SELECTED_TRACKER_ID;
        }
        return nextTrackers.find((item) => item.enabled)?.id ?? nextTrackers[0]?.id ?? null;
      });
      setError(null);
    } catch (err) {
      setTrackers([]);
      setSelectedTrackerId(null);
      setError(readErrorMessage(err, "加载追踪器失败"));
    } finally {
      setTrackersLoading(false);
    }
  }, []);

  const loadTrackerAnalysis = React.useCallback(async (
    trackerId: number | null,
    options: LoadAnalysisOptions = {},
  ) => {
    if (!trackerId) {
      setLatestAnalysis(null);
      setHistory([]);
      return;
    }

    const cached = TRACKER_ANALYSIS_CACHE.get(trackerId);
    const canUseFreshCache = Boolean(
      cached &&
        options.preferCache &&
        !options.force &&
        Date.now() - cached.cachedAt < TRACKER_ANALYSIS_CACHE_TTL_MS,
    );
    if (cached && options.preferCache) {
      setLatestAnalysis(cached.latest);
      setHistory(cached.history);
    }
    if (canUseFreshCache) {
      return;
    }

    const requestSeq = (analysisRequestSeqRef.current += 1);
    if (!options.silent || !cached) {
      setAnalysisLoading(true);
    }
    try {
      const [latest, historyData] = await Promise.all([
        loadLatestAnalysis(trackerId),
        api<AnalysisHistoryResponse>(`/api/content-tracking/trackers/${trackerId}/analysis/history`),
      ]);
      const history = safeArray(historyData.snapshots);
      TRACKER_ANALYSIS_CACHE.set(trackerId, {
        latest,
        history,
        cachedAt: Date.now(),
      });
      if (requestSeq === analysisRequestSeqRef.current || selectedTrackerIdRef.current === trackerId) {
        setLatestAnalysis(latest);
        setHistory(history);
      }
      setError(null);
    } catch (err) {
      if (!cached) {
        setLatestAnalysis(null);
        setHistory([]);
      }
      setError(readErrorMessage(err, "加载分析结果失败"));
    } finally {
      if (requestSeq === analysisRequestSeqRef.current || selectedTrackerIdRef.current === trackerId) {
        setAnalysisLoading(false);
      }
    }
  }, []);

  const followCollectionRun = React.useCallback(async (
    run: CollectionRun,
    trackerId: number,
  ) => {
    if (!isCollectionRunActive(run)) return;
    if (watchedCollectionRunRef.current === run.id) return;

    watchedCollectionRunRef.current = run.id;
    if (mountedRef.current && selectedTrackerIdRef.current === trackerId) {
      setCollecting(true);
    }
    try {
      const finished = await waitForCollectionRun(run.id, trackerId);
      if (finished.status === "failed") {
        setError(finished.error?.message || "采集任务失败");
        return;
      }
      if (finished.status === "succeeded") {
        await loadTrackerAnalysis(trackerId, { force: true, silent: true });
      }
    } catch (err) {
      if (mountedRef.current && selectedTrackerIdRef.current === trackerId) {
        setError(readErrorMessage(err, "恢复采集任务状态失败"));
      }
    } finally {
      if (watchedCollectionRunRef.current === run.id) {
        watchedCollectionRunRef.current = null;
      }
      if (mountedRef.current && selectedTrackerIdRef.current === trackerId) {
        setCollecting(false);
      }
    }
  }, [loadTrackerAnalysis]);

  const restoreLatestCollectionRun = React.useCallback(async (trackerId: number | null) => {
    if (!trackerId) {
      setCollectionRun(null);
      setCollecting(false);
      return;
    }

    const cachedRun = TRACKER_COLLECTION_RUN_CACHE.get(trackerId);
    if (cachedRun !== undefined && mountedRef.current && selectedTrackerIdRef.current === trackerId) {
      setCollectionRun(cachedRun);
      if (isCollectionRunActive(cachedRun)) {
        setCollecting(true);
      }
    }

    try {
      const latestRun = await loadLatestCollectionRun(trackerId);
      TRACKER_COLLECTION_RUN_CACHE.set(trackerId, latestRun);
      if (mountedRef.current && selectedTrackerIdRef.current === trackerId) {
        setCollectionRun(latestRun);
        setCollecting(Boolean(latestRun && isCollectionRunActive(latestRun)));
      }
      if (!latestRun) return;

      const cachedAnalysisRunId = TRACKER_ANALYSIS_CACHE.get(trackerId)?.latest?.run?.id ?? null;
      if (
        latestRun.status === "succeeded" &&
        latestRun.analysis_run_id &&
        latestRun.analysis_run_id !== cachedAnalysisRunId
      ) {
        await loadTrackerAnalysis(trackerId, { force: true, silent: true });
      }
      if (isCollectionRunActive(latestRun)) {
        void followCollectionRun(latestRun, trackerId);
      }
    } catch {
      if (cachedRun === undefined && mountedRef.current && selectedTrackerIdRef.current === trackerId) {
        setCollectionRun(null);
      }
    }
  }, [followCollectionRun, loadTrackerAnalysis]);

  React.useEffect(() => {
    void loadTrackers();
  }, [loadTrackers]);

  React.useEffect(() => {
    if (!focusTrackerId) return;
    if (!normalizedTrackers.some((tracker) => tracker.id === focusTrackerId)) return;
    setSelectedTrackerId(focusTrackerId);
    setSubTab("input");
    setTrackerMenuOpen(false);
  }, [focusTrackerId, normalizedTrackers]);

  React.useEffect(() => {
    void loadTrackerAnalysis(selectedTrackerId, { preferCache: true, silent: true });
    void restoreLatestCollectionRun(selectedTrackerId);
  }, [loadTrackerAnalysis, restoreLatestCollectionRun, selectedTrackerId]);

  React.useEffect(() => {
    if (!selectedTracker) {
      setTrackerForm(DEFAULT_TRACKER_FORM);
      setCollectionForm({
        lookbackDays: String(COLLECTION_REQUEST_CONFIG.lookbackDays),
        limitPerPlatform: String(COLLECTION_REQUEST_CONFIG.limitPerPlatform),
        platforms: DEFAULT_COLLECTION_PLATFORMS,
        keywordsText: "",
      });
      return;
    }

    setTrackerForm({
      name: selectedTracker.name,
      description: selectedTracker.description,
      platformsText: selectedTracker.platforms.join(","),
      includedKeywordsText: selectedTracker.includedKeywords.join(","),
      excludedKeywordsText: selectedTracker.excludedKeywords.join(","),
      scheduleIntervalMinutes: `${selectedTracker.scheduleIntervalMinutes}`,
      enabled: selectedTracker.enabled,
    });
    setCollectionForm({
      lookbackDays: String(COLLECTION_REQUEST_CONFIG.lookbackDays),
      limitPerPlatform: String(COLLECTION_REQUEST_CONFIG.limitPerPlatform),
      platforms: selectedTracker.platforms.length
        ? selectedTracker.platforms
        : DEFAULT_COLLECTION_PLATFORMS,
      keywordsText: selectedTracker.includedKeywords.join(","),
    });
  }, [selectedTracker]);

  async function rerunAnalysis() {
    if (!selectedTrackerId) return;
    setRunning(true);
    try {
      await api(`/api/content-tracking/trackers/${selectedTrackerId}/analysis`, {
        method: "POST",
      });
      await loadTrackerAnalysis(selectedTrackerId);
      setError(null);
    } catch (err) {
      setError(readErrorMessage(err, "运行分析失败"));
    } finally {
      setRunning(false);
    }
  }

  function toggleCollectionPlatform(platform: string, checked: boolean) {
    setCollectionForm((current) => {
      const currentPlatforms = current.platforms.filter(Boolean);
      const nextPlatforms = checked
        ? Array.from(new Set([...currentPlatforms, platform]))
        : currentPlatforms.filter((item) => item !== platform);
      return {
        ...current,
        platforms: nextPlatforms,
      };
    });
  }

  async function waitForCollectionRun(runId: number, trackerId: number): Promise<CollectionRun> {
    let latest: CollectionRun | null = null;
    for (;;) {
      const data = await api<CollectionRunResponse>(`/api/content-tracking/collection-runs/${runId}`);
      latest = data.run;
      TRACKER_COLLECTION_RUN_CACHE.set(trackerId, latest);
      if (mountedRef.current && selectedTrackerIdRef.current === trackerId) {
        setCollectionRun(latest);
      }
      if (latest.status === "succeeded" || latest.status === "failed") {
        return latest;
      }
      await new Promise((resolve) => window.setTimeout(resolve, 1200));
    }
  }

  async function collectAndAnalyze() {
    if (!selectedTrackerId) return;
    if (collectionConfigError) {
      setError(collectionConfigError);
      return;
    }
    setCollecting(true);
    setCollectionRun(null);
    try {
      const created = await api<CollectionRunResponse>(
        `/api/content-tracking/trackers/${selectedTrackerId}/collect-and-analyze`,
        {
          method: "POST",
          body: JSON.stringify({
            lookback_days: collectionLookbackDays,
            limit_per_platform: collectionLimitPerPlatform,
            platforms: collectionPlatforms,
            keywords: collectionKeywordLabels,
          }),
        },
      );
      setCollectionRun(created.run);
      TRACKER_COLLECTION_RUN_CACHE.set(selectedTrackerId, created.run);
      const finished = await waitForCollectionRun(created.run.id, selectedTrackerId);
      if (finished.status === "failed") {
        throw new Error(finished.error?.message || "采集任务失败");
      }
      await loadTrackerAnalysis(selectedTrackerId, { force: true });
      setError(null);
    } catch (err) {
      setError(readErrorMessage(err, "采集并分析失败"));
    } finally {
      setCollecting(false);
    }
  }

  async function suggestTrackerKeywords() {
    const payload = buildTrackerPayload(trackerForm);
    if (!payload.name && !trackerForm.description.trim() && payload.included_keywords.length === 0) {
      setError("请先填写追踪器名称、描述或已有关键词。");
      return;
    }
    setSuggestingTrackerKeywords(true);
    try {
      const data = await api<TrackerKeywordSuggestionResponse>(
        "/api/content-tracking/tracker-keyword-suggestions",
        {
          method: "POST",
          body: JSON.stringify({
            name: payload.name,
            description: payload.description,
            platforms: payload.platforms,
            included_keywords: payload.included_keywords,
            excluded_keywords: payload.excluded_keywords,
          }),
        },
      );
      const suggestions = data.suggestions || {};
      const included = mergeStrings(
        payload.included_keywords,
        safeArray(suggestions.included_keywords),
        safeArray(suggestions.expanded_keywords),
      );
      const excluded = mergeStrings(payload.excluded_keywords, safeArray(suggestions.excluded_keywords));
      const platformKeywordValues = Object.values(suggestions.platform_keywords || {}).flatMap((items) =>
        safeArray(items),
      );
      setTrackerForm((current) => ({
        ...current,
        includedKeywordsText: included.join(","),
        excludedKeywordsText: excluded.join(","),
      }));
      setCollectionForm((current) => ({
        ...current,
        keywordsText: mergeStrings(splitCsv(current.keywordsText), included, platformKeywordValues).join(","),
      }));
      setError(null);
    } catch (err) {
      setError(readErrorMessage(err, "AI 优化关键词失败"));
    } finally {
      setSuggestingTrackerKeywords(false);
    }
  }

  async function saveTracker(mode: "create" | "update") {
    const payload = buildTrackerPayload(trackerForm);
    if (!payload.name || payload.included_keywords.length === 0) {
      setError("追踪器名称和包含关键词不能为空。");
      return;
    }

    setSavingTracker(true);
    try {
      if (mode === "create") {
        const created = await api<ContentTracker>("/api/content-tracking/trackers", {
          method: "POST",
          body: JSON.stringify(payload),
        });
        await loadTrackers();
        setSelectedTrackerId(created.id);
        setRunning(true);
        await api(`/api/content-tracking/trackers/${created.id}/analysis`, {
          method: "POST",
        });
        await loadTrackerAnalysis(created.id);
      } else {
        if (!selectedTrackerId) {
          setError("请先选择要编辑的追踪器。");
          return;
        }
        await api<ContentTracker>(`/api/content-tracking/trackers/${selectedTrackerId}`, {
          method: "PATCH",
          body: JSON.stringify(payload),
        });
        await loadTrackers();
        await loadTrackerAnalysis(selectedTrackerId);
      }
      setError(null);
    } catch (err) {
      setError(readErrorMessage(err, mode === "create" ? "创建追踪器失败" : "保存追踪器失败"));
    } finally {
      setSavingTracker(false);
      setRunning(false);
    }
  }

  async function toggleTrackerEnabled(tracker: NormalizedTracker) {
    try {
      await api<ContentTracker>(`/api/content-tracking/trackers/${tracker.id}`, {
        method: "PATCH",
        body: JSON.stringify({ enabled: !tracker.enabled }),
      });
      await loadTrackers();
      if (tracker.id === selectedTrackerId) {
        await loadTrackerAnalysis(tracker.id);
      }
      setError(null);
    } catch (err) {
      setError(readErrorMessage(err, `${tracker.enabled ? "停用" : "启用"}追踪器失败`));
    }
  }

  async function softDeleteTracker(tracker: NormalizedTracker) {
    const confirmed = window.confirm(`停用追踪器“${tracker.name}”？历史分析记录会保留。`);
    if (!confirmed) return;

    try {
      await api<{ status: string; tracker: ContentTracker }>(
        `/api/content-tracking/trackers/${tracker.id}`,
        {
          method: "DELETE",
        },
      );
      await loadTrackers();
      if (tracker.id === selectedTrackerId) {
        setLatestAnalysis(null);
        setHistory([]);
      }
      setError(null);
    } catch (err) {
      setError(readErrorMessage(err, "停用追踪器失败"));
    }
  }

  function resetTrackerForm() {
    if (!selectedTracker) {
      setTrackerForm(DEFAULT_TRACKER_FORM);
      return;
    }

    setTrackerForm({
      name: selectedTracker.name,
      description: selectedTracker.description,
      platformsText: selectedTracker.platforms.join(","),
      includedKeywordsText: selectedTracker.includedKeywords.join(","),
      excludedKeywordsText: selectedTracker.excludedKeywords.join(","),
      scheduleIntervalMinutes: `${selectedTracker.scheduleIntervalMinutes}`,
      enabled: selectedTracker.enabled,
    });
  }

  function prepareNewTracker() {
    setSelectedTrackerId(null);
    setLatestAnalysis(null);
    setHistory([]);
    setTrackerForm(DEFAULT_TRACKER_FORM);
    setError(null);
  }

  function selectTrackerForAnalysis(trackerId: number) {
    setSelectedTrackerId(trackerId);
    setSubTab("input");
    setTrackerMenuOpen(false);
    setError(null);
  }

  function selectTrackerForEditing(trackerId: number) {
    setSelectedTrackerId(trackerId);
    setSubTab("trackers");
    setTrackerMenuOpen(false);
    setError(null);
  }

  return (
    <section className="module-page ct-page">
      <div className="ct-topbar">
        <div className="ct-topbar-title">
          <FileSearch size={17} />
          <h2>内容追踪</h2>
          <Info size={16} />
        </div>
        <div className="ct-topbar-controls">
          <div className="ct-tracker-switcher">
            <button
              type="button"
              className="ct-select-pill"
              onClick={() => setTrackerMenuOpen((current) => !current)}
              aria-expanded={trackerMenuOpen}
              aria-haspopup="listbox"
              disabled={!hasTrackers && trackersLoading}
            >
              {selectedTracker?.name || "请选择追踪器"}
              <ChevronDown size={16} />
            </button>
            {trackerMenuOpen && (
              <div className="ct-tracker-menu" role="listbox">
                {trackerMenuItems.length > 0 ? (
                  trackerMenuItems.map((tracker) => (
                    <button
                      type="button"
                      key={tracker.id}
                      className={`ct-tracker-menu-item${tracker.id === selectedTrackerId ? " active" : ""}`}
                      onClick={() => selectTrackerForAnalysis(tracker.id)}
                      role="option"
                      aria-selected={tracker.id === selectedTrackerId}
                    >
                      <span className="ct-tracker-menu-main">
                        <strong>{tracker.name}</strong>
                        <em>{tracker.enabled ? "启用中" : "已停用"}</em>
                      </span>
                      <span className="ct-tracker-menu-meta">
                        {tracker.platforms.map(platformLabel).join(" / ") || "未配置平台"}
                      </span>
                      <span className="ct-tracker-menu-meta">
                        {tracker.includedKeywords.join("、") || "未配置关键词"}
                      </span>
                    </button>
                  ))
                ) : (
                  <div className="ct-tracker-menu-empty">
                    {trackersLoading ? "正在加载追踪器..." : "没有匹配的追踪器"}
                  </div>
                )}
              </div>
            )}
          </div>
          <label className="ct-search-box">
            <Search size={16} />
            <input
              value={query}
              onFocus={() => setTrackerMenuOpen(true)}
              onChange={(event) => {
                setQuery(event.target.value);
                setTrackerMenuOpen(true);
              }}
              placeholder="搜索追踪器或关键词"
            />
          </label>
        </div>
      </div>

      <div className="ct-subtabs">
        <button
          type="button"
          className={subTab === "input" ? "active" : ""}
          onClick={() => setSubTab("input")}
        >
          分析概览
        </button>
        <button
          type="button"
          className={subTab === "trackers" ? "active" : ""}
          onClick={() => setSubTab("trackers")}
        >
          追踪器列表
        </button>
        <button
          type="button"
          className={subTab === "records" ? "active" : ""}
          onClick={() => setSubTab("records")}
        >
          分析记录
        </button>
      </div>

      {error && <div className="notice error">{error}</div>}

      {subTab === "input" && (
        <div className="ct-main-grid">
          <div className="ct-content-area">
            <div className="ct-top-content-grid">
              <Card className="ct-input-card">
                <div className="ct-section-head">
                  <h3>当前追踪器</h3>
                  <button type="button" className="ct-link-btn" onClick={() => void loadTrackers()}>
                    <RefreshCw size={14} />
                    刷新列表
                  </button>
                </div>
                {selectedTracker ? (
                  <>
                    <div className="ct-keyword-group">
                      <span>名称</span>
                      <div className="ct-chip-list">
                        <span className="ct-chip passive">{selectedTracker.name}</span>
                      </div>
                    </div>
                    <div className="ct-keyword-group">
                      <span>平台</span>
                      <div className="ct-chip-list">
                        {selectedTracker.platforms.length > 0 ? (
                          selectedTracker.platforms.map((platform) => (
                            <span
                              key={platform}
                              className={`ct-platform-badge ${platformBadgeClass(platform)}`}
                            >
                              {platformLabel(platform)}
                            </span>
                          ))
                        ) : (
                          <span className="ct-chip passive">未配置平台</span>
                        )}
                      </div>
                    </div>
                    <div className="ct-keyword-group">
                      <span>包含关键词</span>
                      <div className="ct-chip-list">
                        {selectedTracker.includedKeywords.length > 0 ? (
                          selectedTracker.includedKeywords.map((keyword) => (
                            <button type="button" key={keyword} className="ct-chip">
                              {keyword}
                            </button>
                          ))
                        ) : (
                          <span className="ct-chip passive">未配置关键词</span>
                        )}
                      </div>
                    </div>
                    <div className="ct-keyword-group">
                      <span>排除关键词</span>
                      <div className="ct-chip-list">
                        {selectedTracker.excludedKeywords.length > 0 ? (
                          selectedTracker.excludedKeywords.map((keyword) => (
                            <button type="button" key={keyword} className="ct-chip passive">
                              {keyword}
                            </button>
                          ))
                        ) : (
                          <span className="ct-chip passive">暂无排除关键词</span>
                        )}
                      </div>
                    </div>
                    <div className="ct-input-footer">
                      <span>
                        {trackerSummaryMessage}
                        {selectedProjectName ? ` 可作为「${selectedProjectName}」的策略来源。` : ""}
                      </span>
                      {onUseTrackerForStrategy && (
                        <Button
                          type="button"
                          variant="ghost"
                          onClick={() => onUseTrackerForStrategy(selectedTracker.id)}
                        >
                          <WandSparkles size={15} />
                          用于策略分析
                        </Button>
                      )}
                      <Button
                        type="button"
                        onClick={() => void rerunAnalysis()}
                        disabled={running || collecting || analysisLoading}
                      >
                        <WandSparkles size={15} />
                        {running ? "分析中..." : "重新分析"}
                      </Button>
                    </div>
                  </>
                ) : (
                  <div className="ct-secondary-state">
                    <Card className="ct-secondary-card">
                      <p>{trackerSummaryMessage}</p>
                    </Card>
                  </div>
                )}
              </Card>

              {selectedTracker && (
                <Card className="ct-keyword-card">
                  <div className="ct-section-head">
                    <h3>内容采集</h3>
                    <Button
                      type="button"
                      onClick={() => void collectAndAnalyze()}
                      disabled={running || collecting || analysisLoading || Boolean(collectionConfigError)}
                    >
                      <RefreshCw size={15} />
                      {collecting ? "采集中..." : "采集并分析"}
                    </Button>
                  </div>
                  <div className="ct-collection-config">
                    <div className="ct-collection-row">
                      <label>采集范围</label>
                      <div className="ct-collection-inline-field">
                        <span>最近</span>
                        <input
                          type="number"
                          min={1}
                          max={30}
                          value={collectionForm.lookbackDays}
                          onChange={(event) =>
                            setCollectionForm((current) => ({
                              ...current,
                              lookbackDays: event.target.value,
                            }))
                          }
                        />
                        <span>天</span>
                      </div>
                    </div>
                    <div className="ct-collection-row">
                      <label>单平台上限</label>
                      <div className="ct-collection-inline-field">
                        <input
                          type="number"
                          min={1}
                          max={200}
                          value={collectionForm.limitPerPlatform}
                          onChange={(event) =>
                            setCollectionForm((current) => ({
                              ...current,
                              limitPerPlatform: event.target.value,
                            }))
                          }
                        />
                        <span>条内容</span>
                      </div>
                    </div>
                    <div className="ct-collection-row">
                      <label>采集平台</label>
                      <div className="ct-collection-value">
                        {COLLECTION_PLATFORM_OPTIONS.map((platform) => (
                          <label
                            key={platform}
                            className={`ct-collection-toggle ${collectionPlatforms.includes(platform) ? "active" : ""}`}
                          >
                            <input
                              type="checkbox"
                              checked={collectionPlatforms.includes(platform)}
                              onChange={(event) =>
                                toggleCollectionPlatform(platform, event.target.checked)
                              }
                            />
                            <span>{platformLabel(platform)}</span>
                          </label>
                        ))}
                      </div>
                    </div>
                    <div className="ct-collection-row">
                      <label>搜索关键词</label>
                      <div className="ct-collection-value">
                        <textarea
                          value={collectionForm.keywordsText}
                          onChange={(event) =>
                            setCollectionForm((current) => ({
                              ...current,
                              keywordsText: event.target.value,
                            }))
                          }
                          placeholder="多个关键词用逗号或换行分隔"
                          rows={2}
                        />
                      </div>
                    </div>
                    <div className="ct-collection-row">
                      <label>采集方式</label>
                      <strong>按关键词搜索，采集后自动刷新分析</strong>
                    </div>
                  </div>
                  <div className="ct-input-footer">
                    <span className={collectionFooterClassName} title={collectionFooterMessage}>
                      {collectionFooterMessage}
                    </span>
                  </div>
                </Card>
              )}

              <Card className="ct-keyword-card">
                <div className="ct-section-head">
                  <h3>关键词分析</h3>
                  <button
                    type="button"
                    className="ct-link-btn"
                    onClick={() => selectedTrackerId && void loadTrackerAnalysis(selectedTrackerId)}
                    disabled={!selectedTrackerId || analysisLoading}
                  >
                    <RefreshCw size={14} />
                    刷新分析
                  </button>
                </div>
                <div className="ct-keyword-groups">
                  <div className="ct-keyword-group">
                    <span>高价值关键词</span>
                    <div className="ct-chip-list">
                      {renderChipList(snapshotView.highValueKeywords, "暂无高价值关键词")}
                    </div>
                  </div>
                  <div className="ct-keyword-group">
                    <span>推荐扩词</span>
                    <div className="ct-chip-list">
                      {renderChipList(snapshotView.recommendedIncludeKeywords, "暂无扩词建议")}
                    </div>
                  </div>
                  <div className="ct-keyword-group">
                    <span>噪音词</span>
                    <div className="ct-chip-list">
                      {renderChipList(snapshotView.noiseKeywords, "当前未识别到明显噪音词", true)}
                    </div>
                  </div>
                  <div className="ct-keyword-group">
                    <span>推荐排除词</span>
                    <div className="ct-chip-list">
                      {renderChipList(snapshotView.recommendedExcludeKeywords, "暂无排除词建议", true)}
                    </div>
                  </div>
                </div>
                {snapshotView.aiKeywordNotes.length > 0 || snapshotView.aiTrackerSuggestions.length > 0 ? (
                  <div className="ct-ai-note-list">
                    {snapshotView.aiKeywordNotes.slice(0, 3).map((item) => (
                      <p key={`keyword-note-${item}`}>{item}</p>
                    ))}
                    {snapshotView.aiTrackerSuggestions.slice(0, 3).map((item) => (
                      <p key={`tracker-suggestion-${item}`}>{item}</p>
                    ))}
                  </div>
                ) : null}
              </Card>
            </div>

            <Card className="ct-result-table-card">
              <div className="ct-section-head">
                <h3>
                  代表样本 <span>({snapshotView.representativeSamples.length} 条)</span>
                </h3>
              </div>
              <div className="ct-filter-row">
                <span className="ct-filter-label">状态：</span>
                <button type="button" className="ct-filter">
                  {snapshotView.statusLabel} <ChevronDown size={14} />
                </button>
                <button type="button" className="ct-filter">
                  置信度：{snapshotView.confidenceLabel} <ChevronDown size={14} />
                </button>
                <button type="button" className="ct-filter">
                  样本质量：{snapshotView.sampleQualityGrade} <ChevronDown size={14} />
                </button>
                <div className="ct-filter-actions">
                  <button
                    type="button"
                    className="ct-ghost-btn"
                    onClick={() => void rerunAnalysis()}
                    disabled={!selectedTrackerId || running || analysisLoading}
                  >
                    重跑
                  </button>
                  <button
                    type="button"
                    className="ct-ghost-btn"
                    onClick={() => selectedTrackerId && void loadTrackerAnalysis(selectedTrackerId)}
                    disabled={!selectedTrackerId || analysisLoading}
                  >
                    刷新
                  </button>
                </div>
              </div>
              <div className="ct-table-wrap">
                <table className="ct-table">
                  <thead>
                    <tr>
                      <th>平台</th>
                      <th>内容标题</th>
                      <th>作者</th>
                      <th>发布时间</th>
                      <th>相似度</th>
                      <th>互动量</th>
                      <th>模式</th>
                      <th>等级</th>
                    </tr>
                  </thead>
                  <tbody>
                    {snapshotView.representativeSamples.length > 0 ? (
                      snapshotView.representativeSamples.map((row) => (
                        <tr key={row.key}>
                          <td>
                            <span className={`ct-platform-badge ${platformBadgeClass(row.platform)}`}>
                              {row.platformLabel}
                            </span>
                          </td>
                          <td>
                            {row.url ? (
                              <a
                                className="ct-title-link"
                                href={row.url}
                                target="_blank"
                                rel="noreferrer"
                                title={row.title}
                              >
                                {row.title}
                              </a>
                            ) : (
                              row.title
                            )}
                            {row.selectionReason ? (
                              <em className="ct-sample-reason">{row.selectionReason}</em>
                            ) : null}
                          </td>
                          <td>{row.authorName}</td>
                          <td>{formatDateTime(row.publishTime)}</td>
                          <td className="ct-emphasis">{formatSimilarityScore(row.similarityScore)}</td>
                          <td>{formatCount(row.engagementTotal)}</td>
                          <td>{row.patternSummary}</td>
                          <td>{row.candidateLevel}</td>
                        </tr>
                      ))
                    ) : (
                      <tr>
                        <td colSpan={8}>{analysisStatusMessage}</td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
              <div className="ct-pagination">
                <span>运行 ID：{latestAnalysis?.run?.id ?? "-"}</span>
                <div className="ct-pagination-controls">
                  <button type="button">
                    {formatCount(safeNumber(latestAnalysis?.run?.sample_count))} 当前样本
                  </button>
                  <button type="button">
                    {formatCount(safeNumber(latestAnalysis?.run?.candidate_count))} 全部候选
                  </button>
                </div>
              </div>
            </Card>

            <div className="ct-bottom-grid">
              <BottomInsightCard title="内容模式分析" className="ct-pattern-card">
                <div className="ct-pattern-panel">
                  <DonutChartMock total={snapshotView.sampleCount7d} label="7天样本" />
                  <div className="ct-pattern-legend">
                    {snapshotView.patternRows.length > 0 ? (
                      snapshotView.patternRows.map((row) => (
                        <div key={row.name}>
                          <span>{row.name}</span>
                          <strong>{row.value}</strong>
                        </div>
                      ))
                    ) : (
                      <div>
                        <span>暂无模式分布数据</span>
                        <strong>-</strong>
                      </div>
                    )}
                  </div>
                </div>
                <small>
                  模式稳定度：{formatPercent(snapshotView.patternStability)} / 变种率：
                  {formatPercent(snapshotView.patternVariantRate)}
                </small>
                {snapshotView.aiPatternSummary || snapshotView.aiPatternRows.length > 0 ? (
                  <div className="ct-ai-note-list compact">
                    {snapshotView.aiPatternSummary ? <p>{snapshotView.aiPatternSummary}</p> : null}
                    {snapshotView.aiPatternRows.slice(0, 3).map((item) => (
                      <p key={`${item.action}-${item.reason}`}>
                        <strong>{item.action}</strong> {item.reason}
                      </p>
                    ))}
                  </div>
                ) : null}
              </BottomInsightCard>

              <BottomInsightCard title="高价值关键词 TOP5">
                <div className="ct-rank-list">
                  {snapshotView.keywordRows.length > 0 ? (
                    snapshotView.keywordRows.slice(0, 5).map((item, index) => (
                      <div key={item.keyword}>
                        <span>{index + 1}</span>
                        <p>{item.keyword}</p>
                        <strong>{safeRounded(item.keywordValueScore, "-")}</strong>
                      </div>
                    ))
                  ) : (
                    <div>
                      <span>-</span>
                      <p>暂无关键词分析结果</p>
                      <strong>-</strong>
                    </div>
                  )}
                </div>
              </BottomInsightCard>

              <BottomInsightCard title="高频痛点 TOP5">
                <div className="ct-rank-list">
                  {snapshotView.painRows.length > 0 ? (
                    snapshotView.painRows.slice(0, 5).map((item, index) => (
                      <div key={item.name}>
                        <span>{index + 1}</span>
                        <p>{item.name}</p>
                        <strong>{item.value}</strong>
                      </div>
                    ))
                  ) : (
                    <div>
                      <span>-</span>
                      <p>暂无高频痛点</p>
                      <strong>-</strong>
                    </div>
                  )}
                </div>
              </BottomInsightCard>

              <BottomInsightCard title="受众分布">
                <div className="ct-comment-list">
                  {snapshotView.audienceRows.length > 0 ? (
                    snapshotView.audienceRows.slice(0, 5).map((item) => (
                      <div key={item.name}>
                        <p>{item.name}</p>
                        <strong>{item.value}</strong>
                      </div>
                    ))
                  ) : (
                    <div>
                      <p>暂无明确受众标签</p>
                      <strong>-</strong>
                    </div>
                  )}
                </div>
              </BottomInsightCard>
            </div>
          </div>

          <div className="ct-right-column">
            <Card className="ct-tracker-card">
              <div className="ct-section-head">
                <h3>分析结论</h3>
              </div>
              <div className="ct-form-block">
                <label>结论</label>
                <div className="ct-input-like">{snapshotView.headline}</div>
              </div>
              <div className="ct-form-block">
                <label>判断摘要</label>
                <div className="ct-input-like">{snapshotView.statusSummary}</div>
              </div>
              {snapshotView.aiDecisionSummary || snapshotView.aiDecisionEvidence.length > 0 ? (
                <div className="ct-form-block">
                  <label>AI 解读</label>
                  <div className="ct-ai-note-list">
                    {snapshotView.aiDecisionSummary ? <p>{snapshotView.aiDecisionSummary}</p> : null}
                    {snapshotView.aiDecisionEvidence.slice(0, 3).map((item) => (
                      <p key={`ai-evidence-${item}`}>{item}</p>
                    ))}
                  </div>
                </div>
              ) : null}
              <div className="ct-form-grid">
                <div className="ct-form-block">
                  <label>状态</label>
                  <div className="ct-input-like">{snapshotView.statusLabel}</div>
                </div>
                <div className="ct-form-block">
                  <label>置信度</label>
                  <div className="ct-input-like">{snapshotView.confidenceLabel}</div>
                </div>
              </div>
              <div className="ct-form-grid">
                <div className="ct-form-block">
                  <label>样本质量</label>
                  <div className="ct-input-like">
                    {snapshotView.sampleQualityScore === null
                      ? "-"
                      : safeRounded(snapshotView.sampleQualityScore, "-")}
                  </div>
                </div>
                <div className="ct-form-block">
                  <label>趋势强度</label>
                  <div className="ct-input-like">
                    {snapshotView.trendStrengthScore === null
                      ? "-"
                      : safeRounded(snapshotView.trendStrengthScore, "-")}
                  </div>
                </div>
              </div>
              <div className="ct-form-block">
                <label>推荐动作</label>
                <div className="ct-comment-list">
                  {snapshotView.recommendedActions.length > 0 ? (
                    snapshotView.recommendedActions.slice(0, 3).map((item) => (
                      <div key={`${item.action}-${item.reason}`}>
                        <p>{item.action}</p>
                        <strong>{item.reason}</strong>
                      </div>
                    ))
                  ) : (
                    <div>
                      <p>暂无明确动作建议</p>
                      <strong>当前数据不足以生成具体动作。</strong>
                    </div>
                  )}
                </div>
              </div>
              <div className="ct-form-block">
                <label>风险提示</label>
                <div className="ct-chip-list">
                  {snapshotView.riskNotes.length > 0 ? (
                    snapshotView.riskNotes.slice(0, 3).map((note) => (
                      <span key={note} className="ct-chip passive">
                        {note}
                      </span>
                    ))
                  ) : (
                    <span className="ct-chip passive">当前未发现明显风险</span>
                  )}
                </div>
                {snapshotView.aiNoiseSummary || snapshotView.aiNoiseTerms.length > 0 ? (
                  <div className="ct-ai-note-list compact">
                    {snapshotView.aiNoiseSummary ? <p>{snapshotView.aiNoiseSummary}</p> : null}
                    {snapshotView.aiNoiseTerms.slice(0, 5).map((item) => (
                      <p key={`noise-${item}`}>{item}</p>
                    ))}
                  </div>
                ) : null}
              </div>
              <div className="ct-tracker-actions">
                <button
                  type="button"
                  className="ct-ghost-btn"
                  onClick={() => selectedTrackerId && void loadTrackerAnalysis(selectedTrackerId)}
                  disabled={!selectedTrackerId || analysisLoading}
                >
                  刷新
                </button>
                <Button
                  type="button"
                  onClick={() => void rerunAnalysis()}
                  disabled={running || !selectedTrackerId || analysisLoading}
                >
                  {running ? "分析中..." : "运行分析"}
                </Button>
              </div>
            </Card>

            <BottomInsightCard title="创作者扩散" className="ct-feature-card">
              <ul className="ct-feature-list">
                <li>创作者总数：{snapshotView.creatorCount}</li>
                <li>新增创作者：{snapshotView.newCreatorCount}</li>
                <li>复发创作者：{snapshotView.repeatCreatorCount}</li>
                <li>扩散分：{snapshotView.creatorSpreadScore === null ? "-" : safeRounded(snapshotView.creatorSpreadScore, "-")}</li>
                <li>头部依赖度：{formatPercent(snapshotView.topCreatorDependency)}</li>
              </ul>
            </BottomInsightCard>

            <BottomInsightCard title="早期信号样本">
              <div className="ct-comment-list">
                {snapshotView.earlySignalSamples.length > 0 ? (
                  snapshotView.earlySignalSamples.slice(0, 5).map((item) => (
                    <div key={item.key}>
                      <p>
                        <SampleSourceTitle item={item} />
                      </p>
                      <strong>{formatSimilarityScore(item.similarityScore)}</strong>
                    </div>
                  ))
                ) : (
                  <div>
                    <p>暂无早期信号样本</p>
                    <strong>等待新的高相似内容出现。</strong>
                  </div>
                )}
              </div>
            </BottomInsightCard>

            <BottomInsightCard title="爆款样本">
              <div className="ct-comment-list">
                {snapshotView.hotSamples.length > 0 ? (
                  snapshotView.hotSamples.slice(0, 5).map((item) => (
                    <div key={item.key}>
                      <p>
                        <SampleSourceTitle item={item} />
                      </p>
                      <strong>{formatCount(item.engagementTotal)}</strong>
                    </div>
                  ))
                ) : (
                  <div>
                    <p>暂无爆款样本</p>
                    <strong>当前还没有高互动代表内容。</strong>
                  </div>
                )}
              </div>
            </BottomInsightCard>
          </div>
        </div>
      )}

      {subTab === "trackers" && (
        <div className="ct-secondary-state">
          <Card className="ct-secondary-card">
            <div className="ct-section-head">
              <h3>{selectedTrackerId ? "编辑追踪器" : "创建追踪器"}</h3>
              <span className="ct-status-badge">{selectedTrackerId ? `ID ${selectedTrackerId}` : "new"}</span>
            </div>
            <div className="ct-form-block">
              <label>名称</label>
              <input
                value={trackerForm.name}
                onChange={(event) => setTrackerForm((current) => ({ ...current, name: event.target.value }))}
                placeholder="例如：新手养猫 / 猫粮测评追踪"
              />
            </div>
            <div className="ct-form-block">
              <label>描述</label>
              <textarea
                value={trackerForm.description}
                onChange={(event) =>
                  setTrackerForm((current) => ({ ...current, description: event.target.value }))
                }
                placeholder="补充追踪范围、目标和说明"
                rows={3}
              />
            </div>
            <div className="ct-form-grid">
              <div className="ct-form-block">
                <label>平台</label>
                <input
                  value={trackerForm.platformsText}
                  onChange={(event) =>
                    setTrackerForm((current) => ({ ...current, platformsText: event.target.value }))
                  }
                  placeholder="xhs,dy,bili"
                />
              </div>
              <div className="ct-form-block">
                <label>刷新频率(分钟)</label>
                <input
                  value={trackerForm.scheduleIntervalMinutes}
                  onChange={(event) =>
                    setTrackerForm((current) => ({
                      ...current,
                      scheduleIntervalMinutes: event.target.value,
                    }))
                  }
                  placeholder="720"
                />
              </div>
            </div>
            <div className="ct-form-block">
              <label>包含关键词</label>
              <textarea
                value={trackerForm.includedKeywordsText}
                onChange={(event) =>
                  setTrackerForm((current) => ({
                    ...current,
                    includedKeywordsText: event.target.value,
                  }))
                }
                placeholder="猫粮测评,新手养猫,猫粮推荐"
                rows={3}
              />
            </div>
            <div className="ct-form-block">
              <label>排除关键词</label>
              <textarea
                value={trackerForm.excludedKeywordsText}
                onChange={(event) =>
                  setTrackerForm((current) => ({
                    ...current,
                    excludedKeywordsText: event.target.value,
                  }))
                }
                placeholder="抽奖,广告,赞助"
                rows={2}
              />
            </div>
            <div className="ct-form-block">
              <label>
                <input
                  type="checkbox"
                  checked={trackerForm.enabled}
                  onChange={(event) =>
                    setTrackerForm((current) => ({ ...current, enabled: event.target.checked }))
                  }
                />
                启用追踪器
              </label>
            </div>
            <div className="ct-tracker-actions">
              <button type="button" className="ct-ghost-btn" onClick={prepareNewTracker}>
                新建
              </button>
              <button
                type="button"
                className="ct-ghost-btn"
                onClick={() => void suggestTrackerKeywords()}
                disabled={suggestingTrackerKeywords || savingTracker}
              >
                <WandSparkles size={14} />
                {suggestingTrackerKeywords ? "AI 优化中..." : "AI 优化关键词"}
              </button>
              <button type="button" className="ct-ghost-btn" onClick={resetTrackerForm}>
                重置
              </button>
              <Button
                type="button"
                onClick={() => void saveTracker(selectedTrackerId ? "update" : "create")}
                disabled={savingTracker}
              >
                {savingTracker ? "保存中..." : selectedTrackerId ? "保存修改" : "创建追踪器"}
              </Button>
            </div>
          </Card>
          {filteredTrackers.length > 0 ? (
            filteredTrackers.map((tracker) => (
              <Card key={tracker.id} className="ct-secondary-card">
                <div className="ct-section-head">
                  <h3>{tracker.name}</h3>
                  <span className="ct-status-badge">{tracker.enabled ? "启用中" : "已停用"}</span>
                </div>
                <p>平台：{tracker.platforms.map(platformLabel).join(" / ") || "-"}</p>
                <p>包含关键词：{tracker.includedKeywords.join("、") || "-"}</p>
                <p>排除关键词：{tracker.excludedKeywords.join("、") || "-"}</p>
                <p>刷新频率：每 {tracker.scheduleIntervalMinutes} 分钟</p>
                <div className="ct-tracker-actions">
                  <button
                    type="button"
                    className="ct-ghost-btn"
                    onClick={() => selectTrackerForAnalysis(tracker.id)}
                  >
                    查看分析
                  </button>
                  {onUseTrackerForStrategy && (
                    <button
                      type="button"
                      className="ct-ghost-btn"
                      onClick={() => onUseTrackerForStrategy(tracker.id)}
                    >
                      查看策略建议
                    </button>
                  )}
                  <button
                    type="button"
                    className="ct-ghost-btn"
                    onClick={() => selectTrackerForEditing(tracker.id)}
                  >
                    编辑
                  </button>
                  <button type="button" className="ct-ghost-btn" onClick={() => void toggleTrackerEnabled(tracker)}>
                    {tracker.enabled ? "停用" : "启用"}
                  </button>
                  <button type="button" className="ct-ghost-btn" onClick={() => void softDeleteTracker(tracker)}>
                    软删除
                  </button>
                </div>
              </Card>
            ))
          ) : (
            <Card className="ct-secondary-card">
              <p>{trackersLoading ? "正在加载追踪器..." : "没有匹配的追踪器。"}</p>
            </Card>
          )}
        </div>
      )}

      {subTab === "records" && (
        <div className="ct-secondary-state">
          {historyRows.length > 0 ? (
            historyRows.map((item) => (
              <Card key={item.id} className="ct-secondary-card">
                <div className="ct-section-head">
                  <h3>{item.snapshotDate}</h3>
                  <span className="ct-status-badge">{item.statusLabel}</span>
                </div>
                <p>结论：{item.headline}</p>
                <p>趋势强度：{item.trendStrengthScore}</p>
                <p>样本质量：{item.sampleQualityScore}</p>
              </Card>
            ))
          ) : (
            <Card className="ct-secondary-card">
              <p>
                {selectedTrackerId
                  ? "该追踪器还没有分析记录，先运行一次分析。"
                  : "请先选择追踪器。"}
              </p>
            </Card>
          )}
        </div>
      )}
    </section>
  );
}

async function loadLatestAnalysis(trackerId: number): Promise<LatestAnalysisResponse | null> {
  try {
    return await api<LatestAnalysisResponse>(`/api/content-tracking/trackers/${trackerId}/analysis`);
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) {
      return null;
    }
    throw err;
  }
}

async function loadLatestCollectionRun(trackerId: number): Promise<CollectionRun | null> {
  const data = await api<CollectionRunsResponse>(
    `/api/content-tracking/trackers/${trackerId}/collection-runs?limit=1`,
  );
  return safeArray(data.runs)[0] ?? null;
}

function isCollectionRunActive(run: CollectionRun | null | undefined) {
  const status = (run?.status || "").trim().toLowerCase();
  return status === "queued" || status === "running";
}

function normalizeTracker(tracker: ContentTracker): NormalizedTracker {
  return {
    id: tracker.id,
    name: tracker.name?.trim() || "未命名追踪器",
    description: tracker.description?.trim() || "",
    platforms: safeArray(tracker.platforms).map((item) => item.trim()).filter(Boolean),
    includedKeywords: safeArray(tracker.included_keywords).map((item) => item.trim()).filter(Boolean),
    excludedKeywords: safeArray(tracker.excluded_keywords).map((item) => item.trim()).filter(Boolean),
    scheduleIntervalMinutes: Math.max(1, safeNumber(tracker.schedule_interval_minutes, 720)),
    enabled: Boolean(tracker.enabled),
    updatedAt: tracker.updated_at || null,
  };
}

function normalizeSnapshotView(snapshot: TrackerAnalysisSnapshot | null | undefined): NormalizedSnapshotView {
  const highValueKeywords = uniqueDisplayTerms(safeArray(snapshot?.keywords?.high_value_keywords)
    .map((item) => item.keyword?.trim() || "")
    .filter(Boolean));
  const highValueTermSet = new Set(highValueKeywords.map(normalizeKeywordIdentity));

  const recommendedIncludeKeywords = uniqueDisplayTerms(safeArray(snapshot?.keywords?.recommended_include_keywords)
    .map((item) => item.trim())
    .filter(Boolean), highValueTermSet);
  const includeTermSet = new Set([
    ...highValueKeywords.map(normalizeKeywordIdentity),
    ...recommendedIncludeKeywords.map(normalizeKeywordIdentity),
  ]);

  const noiseKeywords = uniqueDisplayTerms(safeArray(snapshot?.keywords?.noise_keywords)
    .map((item) => item.keyword?.trim() || "")
    .filter(Boolean), includeTermSet);
  const noiseTermSet = new Set(noiseKeywords.map(normalizeKeywordIdentity));

  const recommendedExcludeKeywords = uniqueDisplayTerms(safeArray(snapshot?.keywords?.recommended_exclude_keywords)
    .map((item) => item.trim())
    .filter(Boolean), new Set([...includeTermSet, ...noiseTermSet]));

  const recommendedActions = safeArray(snapshot?.decisions?.recommended_actions)
    .map((item) => ({
      action: item.action?.trim() || "待补充动作",
      reason: item.reason?.trim() || "暂无原因说明",
    }))
    .filter((item) => item.action);

  const riskNotes = safeArray(snapshot?.risks?.risk_notes)
    .map((item) => item.trim())
    .filter(Boolean);
  const aiKeywordNotes = safeArray(snapshot?.keywords?.ai_keyword_strategy?.keyword_notes)
    .map((item) => item.trim())
    .filter(Boolean);
  const aiTrackerSuggestions = [
    ...safeArray(snapshot?.keywords?.ai_tracker_suggestions?.included_keywords),
    ...safeArray(snapshot?.keywords?.ai_tracker_suggestions?.excluded_keywords),
    ...safeArray(snapshot?.keywords?.ai_tracker_suggestions?.split_tracker_suggestions),
    ...safeArray(snapshot?.keywords?.ai_tracker_suggestions?.platform_notes),
  ]
    .map((item) => item.trim())
    .filter(Boolean);
  const aiPatternRows = safeArray(snapshot?.patterns?.ai_pattern_insights?.patterns)
    .map((item) => ({
      action: item.name?.trim() || "AI 模式",
      reason: item.description?.trim() || "-",
    }))
    .filter((item) => item.action || item.reason);
  const aiNoiseTerms = [
    ...safeArray(snapshot?.risks?.ai_noise_diagnosis?.noise_terms),
    ...safeArray(snapshot?.risks?.ai_noise_diagnosis?.suggested_exclude_keywords),
  ]
    .map((item) => item.trim())
    .filter(Boolean);
  const aiDecisionEvidence = safeArray(snapshot?.decisions?.ai_explanation?.evidence)
    .map((item) => item.trim())
    .filter(Boolean);

  const statusLabel = formatStatusLabel(snapshot?.overview?.status || snapshot?.status);
  const confidenceLabel = formatConfidenceLabel(
    snapshot?.decisions?.decision_confidence_label || snapshot?.overview?.judgement_confidence,
  );
  const headline =
    snapshot?.decisions?.headline?.trim() ||
    snapshot?.overview?.headline?.trim() ||
    (snapshot ? "分析已完成，暂未生成明确结论" : "尚未生成分析");

  return {
    statusLabel,
    confidenceLabel,
    headline,
    statusSummary: buildStatusSummary(statusLabel, confidenceLabel, headline, Boolean(snapshot)),
    sampleQualityScore: safeNullableNumber(snapshot?.overview?.sample_quality_score),
    sampleQualityGrade: snapshot?.overview?.sample_quality_grade?.trim() || "待评估",
    trendStrengthScore: safeNullableNumber(snapshot?.trends?.trend_strength_score),
    sampleCount24h: safeNumber(snapshot?.overview?.sample_size?.content_count_24h),
    sampleCount7d: safeNumber(snapshot?.overview?.sample_size?.content_count_7d),
    creatorCount7d: safeNumber(snapshot?.overview?.sample_size?.creator_count_7d),
    platformCount: safeNumber(snapshot?.overview?.sample_size?.platform_count),
    patternRows: topDistributionRows(snapshot?.patterns?.content_type_distribution),
    painRows: topDistributionRows(snapshot?.patterns?.pain_point_distribution),
    audienceRows: topDistributionRows(snapshot?.patterns?.audience_distribution),
    keywordRows: safeArray(snapshot?.keywords?.keyword_rows).map((item) => ({
      keyword: item.keyword?.trim() || "未命名关键词",
      type: item.type?.trim() || "-",
      hitContentCount: safeNumber(item.hit_content_count),
      hitCreatorCount: safeNumber(item.hit_creator_count),
      avgSimilarity: safeNullableNumber(item.avg_similarity),
      avgEngagement: safeNullableNumber(item.avg_engagement),
      viralRate: safeNullableNumber(item.viral_rate),
      noiseRate: safeNullableNumber(item.noise_rate),
      keywordValueScore: safeNullableNumber(item.keyword_value_score),
      recommendedAction: item.recommended_action?.trim() || "-",
    })),
    highValueKeywords,
    recommendedIncludeKeywords,
    noiseKeywords,
    recommendedExcludeKeywords,
    aiKeywordNotes,
    aiTrackerSuggestions,
    representativeSamples: normalizeSamples(snapshot?.samples?.representative_samples),
    hotSamples: normalizeSamples(snapshot?.samples?.hot_samples),
    earlySignalSamples: normalizeSamples(snapshot?.samples?.early_signal_samples),
    riskNotes,
    aiNoiseSummary: snapshot?.risks?.ai_noise_diagnosis?.summary?.trim() || "",
    aiNoiseTerms,
    aiPatternSummary: snapshot?.patterns?.ai_pattern_insights?.summary?.trim() || "",
    aiPatternRows,
    aiDecisionSummary: snapshot?.decisions?.ai_explanation?.summary?.trim() || "",
    aiDecisionEvidence,
    recommendedActions,
    creatorCount: safeNumber(snapshot?.creators?.creator_count),
    newCreatorCount: safeNumber(snapshot?.creators?.new_creator_count),
    repeatCreatorCount: safeNumber(snapshot?.creators?.repeat_creator_count),
    creatorSpreadScore: safeNullableNumber(snapshot?.creators?.creator_spread_score),
    topCreatorDependency: safeNullableNumber(snapshot?.creators?.top_creator_dependency),
    patternStability: safeNullableNumber(snapshot?.patterns?.pattern_stability),
    patternVariantRate: safeNullableNumber(snapshot?.patterns?.pattern_variant_rate),
  };
}

function normalizeSamples(samples: SampleRow[] | null | undefined): NormalizedSample[] {
  return safeArray(samples).map((sample) => {
    const platform = sample.platform?.trim() || "unknown";
    const title = sample.title?.trim() || sample.platform_post_id || "未命名样本";
    const patternSummary =
      sample.fingerprint?.content_type?.trim() ||
      sample.evidence?.pattern_summary?.trim() ||
      "未识别模式";

    return {
      key: `${platform}-${sample.platform_post_id}`,
      platform,
      platformLabel: platformLabel(platform),
      title,
      url: normalizeExternalUrl(sample.url),
      authorName: sample.author_name?.trim() || sample.author_id?.trim() || "-",
      publishTime: sample.publish_time || null,
      similarityScore: safeNullableNumber(sample.similarity_score),
      engagementTotal: safeNumber(sample.engagement_total),
      patternSummary,
      candidateLevel: sample.candidate_level?.trim() || "-",
      selectionReason: sample.evidence?.ai_selection_reason?.trim() || "",
      marketValidationStatus: sample.market_validation_status?.trim() || "",
    };
  });
}

function renderChipList(values: string[], emptyLabel: string, passive = false) {
  if (values.length === 0) {
    return <span className="ct-chip passive">{emptyLabel}</span>;
  }

  return values.slice(0, 10).map((item) => (
    <button type="button" key={item} className={`ct-chip${passive ? " passive" : ""}`}>
      {item}
    </button>
  ));
}

function topDistributionRows(distribution?: DistributionMap | null): DistributionRow[] {
  return Object.entries(distribution || {})
    .filter(([, value]) => typeof value === "number" && !Number.isNaN(value))
    .sort((a, b) => b[1] - a[1])
    .map(([name, value]) => ({ name, value }));
}

function platformLabel(platform: string) {
  const mapping: Record<string, string> = {
    dy: "抖音",
    xhs: "小红书",
    bili: "B站",
    wb: "微博",
    video: "视频号",
    ks: "快手",
    zhihu: "知乎",
    tieba: "贴吧",
  };
  return mapping[platform] || platform;
}

function platformBadgeClass(platform: string) {
  const mapping: Record<string, string> = {
    dy: "ct-platform-douyin",
    xhs: "ct-platform-xhs",
    bili: "ct-platform-bili",
    video: "ct-platform-video",
  };
  return mapping[platform] || "ct-platform-video";
}

function formatDateTime(value?: string | null) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return `${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")} ${String(date.getHours()).padStart(2, "0")}:${String(date.getMinutes()).padStart(2, "0")}`;
}

function formatCount(value: number) {
  if (value >= 10000) {
    return `${(value / 10000).toFixed(1)}w`;
  }
  return `${value}`;
}

function formatPercent(value?: number | null, fractionDigits?: number) {
  if (typeof value !== "number" || Number.isNaN(value)) return "-";
  const digits = typeof fractionDigits === "number" ? fractionDigits : 0;
  return `${(value * 100).toFixed(digits)}%`;
}

function formatSimilarityScore(value?: number | null) {
  if (typeof value !== "number" || Number.isNaN(value)) return "-";
  return `${value.toFixed(value >= 99.5 ? 0 : 1)}%`;
}

function normalizeExternalUrl(value?: string | null) {
  const url = value?.trim();
  if (!url) return null;
  return /^https?:\/\//i.test(url) ? url : null;
}

function safeArray<T>(value: T[] | null | undefined): T[] {
  return Array.isArray(value) ? value : [];
}

function safeNumber(value: number | null | undefined, fallback = 0) {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function clampInteger(value: string, fallback: number, min: number, max: number) {
  const parsed = Number.parseInt(value, 10);
  if (!Number.isFinite(parsed)) return fallback;
  return Math.min(max, Math.max(min, parsed));
}

function safeNullableNumber(value: number | null | undefined) {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function safeString(value: unknown) {
  return typeof value === "string" ? value.trim() : "";
}

function normalizeKeywordIdentity(value: string) {
  return value.trim().toLowerCase().replace(/\s+/g, " ");
}

function uniqueDisplayTerms(values: string[], excluded: Set<string> = new Set()) {
  const seen = new Set(excluded);
  const rows: string[] = [];
  values.forEach((value) => {
    const item = value.trim();
    const identity = normalizeKeywordIdentity(item);
    if (!identity || seen.has(identity)) return;
    seen.add(identity);
    rows.push(item);
  });
  return rows;
}

function safeRounded(value: number | null | undefined, fallback: string | number = 0) {
  if (typeof value !== "number" || Number.isNaN(value)) return fallback;
  return Math.round(value);
}

function formatStatusLabel(status?: string | null) {
  const normalized = (status || "").trim().toLowerCase();
  const mapping: Record<string, string> = {
    warming: "升温",
    stable: "稳定",
    cooling: "衰减",
    declining: "衰减",
    heating_up: "升温",
    sample_insufficient: "样本不足",
    insufficient_sample: "样本不足",
    insufficient: "样本不足",
    high_noise: "噪音偏高",
    noise_high: "噪音偏高",
    noisy: "噪音偏高",
    ready: "已完成",
    completed: "已完成",
    observing: "观察中",
    pending: "待分析",
    failed: "分析失败",
  };
  if (!normalized) return "未生成分析";
  return mapping[normalized] || status || "待判断";
}

function formatCollectionStatusLabel(status?: string | null) {
  const normalized = (status || "").trim().toLowerCase();
  const mapping: Record<string, string> = {
    queued: "排队中",
    running: "运行中",
    succeeded: "已完成",
    failed: "失败",
  };
  if (!normalized) return "排队中";
  return mapping[normalized] || status || "待确认";
}

function formatCollectionPhaseLabel(phase?: string | null) {
  const normalized = (phase || "").trim().toLowerCase();
  const mapping: Record<string, string> = {
    queued: "等待开始",
    preparing: "准备采集",
    collecting: "正在采集",
    analyzing: "正在分析",
    completed: "已完成",
    failed: "失败",
  };
  if (!normalized) return "等待开始";
  return mapping[normalized] || phase || "待确认";
}

function formatConfidenceLabel(confidence?: string | null) {
  const normalized = (confidence || "").trim().toLowerCase();
  const mapping: Record<string, string> = {
    high: "高",
    medium: "中",
    low: "低",
    insufficient: "不足",
  };
  if (!normalized) return "-";
  return mapping[normalized] || confidence || "-";
}

function buildStatusSummary(
  statusLabel: string,
  confidenceLabel: string,
  headline: string,
  hasSnapshot: boolean,
) {
  if (!hasSnapshot) {
    return "尚未生成分析结果，请先运行一次分析。";
  }
  if (confidenceLabel === "-") {
    return `${statusLabel}。${headline}`;
  }
  return `当前处于${statusLabel}阶段，判断置信度${confidenceLabel}。${headline}`;
}

function readErrorMessage(error: unknown, fallback = "加载失败") {
  if (error instanceof ApiError) {
    if (error.status === 502 || error.status === 503 || error.status === 504) {
      return "无法连接后端服务，请确认 API 服务已启动。";
    }
    if (error.status === 404) {
      return "请求的资源不存在。";
    }
    return error.message || fallback;
  }
  if (error instanceof Error) {
    return error.message || fallback;
  }
  return fallback;
}

function buildTrackerPayload(form: TrackerFormState) {
  return {
    name: form.name.trim(),
    description: form.description.trim() || null,
    platforms: splitCsv(form.platformsText),
    included_keywords: splitCsv(form.includedKeywordsText),
    excluded_keywords: splitCsv(form.excludedKeywordsText),
    schedule_interval_minutes: Math.max(
      1,
      Number.parseInt(form.scheduleIntervalMinutes || "720", 10) || 720,
    ),
    enabled: form.enabled,
  };
}

function mergeStrings(...groups: Array<Array<string | null | undefined>>) {
  const seen = new Set<string>();
  const rows: string[] = [];
  groups.flat().forEach((value) => {
    const item = String(value || "").trim();
    if (!item || seen.has(item)) return;
    seen.add(item);
    rows.push(item);
  });
  return rows;
}

function splitCsv(value: string) {
  return value
    .split(/[\n,，]/)
    .map((item) => item.trim())
    .filter(Boolean);
}
