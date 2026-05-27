import React from "react";
import { createRoot } from "react-dom/client";
import type { Root } from "react-dom/client";
import { AlertTriangle, Play, X, Construction } from "lucide-react";
import { SideNav } from "./components/SideNav";
import { AppHeader, type AppHeaderNotification, type AppHeaderProject } from "./components/AppHeader";
import { Button, ConfirmDialog } from "./components/ui";
import { AuthPage, type AuthMode } from "./pages/AuthPage";
import { api, ApiError } from "./utils/api";
import {
  configurableNavItems,
  defaultSideNavConfig,
  firstVisibleConfigurableTab,
  normalizeSideNavConfig,
} from "./navigation";
import {
  authInitial,
  clearAuthSession,
  getStoredAuthSession,
  isPlatformAdmin,
  saveAuthSession,
  type AuthSession,
} from "./utils/authSession";
import { labelOpportunityType, labelPlatform } from "./utils/format";
import {
  fallbackAiInsights,
  fallbackDashboard,
  fallbackDatabaseStats,
} from "./lib/growthProjectFallbacks";
import type {
  AIResult,
  AiInsightSummary,
  AiTopicIdeasSummary,
  BackgroundTaskItem,
  CommentRecord,
  DatabaseStats,
  DashboardOpportunity,
  DashboardSummary,
  GrowthProjectCreatePayload,
  GrowthProjectCollectionRunPayload,
  GrowthProjectCollectionProgress,
  GrowthProjectDetail,
  GrowthProjectSummary,
  GrowthProjectUpdatePayload,
  PendingExecution,
  PostRecord,
  RawRecord,
  ResearchJob,
  ResearchTab,
  SideNavConfigResponse,
  SideNavConfigValue,
  TodayIntelligenceSummary,
} from "./types";
import "./styles.css";
import "./components/shell.css";
import "./competitor_monitor/styles.css";

const TodayIntelligencePage = React.lazy(() =>
  import("./pages/GrowthIntelligencePages").then((module) => ({
    default: module.TodayIntelligencePage,
  })),
);
const ProjectsHubPage = React.lazy(() =>
  import("./pages/GrowthIntelligencePages").then((module) => ({
    default: module.ProjectsHubPage,
  })),
);
const KeywordHeatPage = React.lazy(() =>
  import("./pages/GrowthIntelligencePages").then((module) => ({
    default: module.KeywordHeatPage,
  })),
);
const SettingsHubPage = React.lazy(() =>
  import("./pages/GrowthIntelligencePages").then((module) => ({
    default: module.SettingsHubPage,
  })),
);
const CompetitorMonitorPage = React.lazy(() =>
  import("./competitor_monitor/CompetitorMonitorWorkbench").then((module) => ({
    default: module.CompetitorMonitorWorkbench,
  })),
);
const ContentTrackingPage = React.lazy(() =>
  import("./pages/ContentTrackingPageRedesign").then((module) => ({
    default: module.ContentTrackingPage,
  })),
);
const ContentProductionPage = React.lazy(() =>
  import("./pages/ContentProductionPage").then((module) => ({
    default: module.ContentProductionPage,
  })),
);
const ContentStrategyCenterPage = React.lazy(() =>
  import("./pages/ContentStrategyCenterPage").then((module) => ({
    default: module.ContentStrategyCenterPage,
  })),
);
const LeadAttributionPage = React.lazy(() =>
  import("./pages/LeadAttributionPage").then((module) => ({
    default: module.LeadAttributionPage,
  })),
);
const CreatorDiscoveryPage = React.lazy(() =>
  import("./pages/creator-discovery").then((module) => ({
    default: module.CreatorDiscoveryPage,
  })),
);
const AdminConsolePage = React.lazy(() =>
  import("./pages/AdminConsolePage").then((module) => ({
    default: module.AdminConsolePage,
  })),
);

const TAB_TITLES: Partial<Record<ResearchTab, string>> = {
  today: "今日情报",
  projects: "项目工作台",
  creators: "达人发现",
  competitors: "友商监控",
  content_tracking: "内容追踪",
  key_insights: "内容策略中心",
  lead_attribution: "线索归因",
  keyword_heat: "关键词热度",
  admin: "管理后台",
  settings: "设置",
};

const RESEARCH_TAB_VALUES: readonly ResearchTab[] = [
  "today",
  "projects",
  "content_production",
  "creators",
  "content_tracking",
  "lead_attribution",
  "competitors",
  "keyword_heat",
  "admin",
  "settings",
  "data_board",
  "key_insights",
  "topic_tracking",
  "account_analysis",
  "content_library",
  "reports_center",
  "ai_assistant",
];

function parseResearchTab(value: string | null): ResearchTab | null {
  if (!value) return null;
  return RESEARCH_TAB_VALUES.includes(value as ResearchTab) ? (value as ResearchTab) : null;
}

function readResearchUrlState() {
  const params = new URLSearchParams(window.location.search);
  const trackerId = Number.parseInt(params.get("trackerId") || params.get("tracker_id") || "", 10);
  return {
    tab: parseResearchTab(params.get("tab")),
    projectId: params.get("projectId") || params.get("project_id") || null,
    trackerId: Number.isFinite(trackerId) && trackerId > 0 ? trackerId : null,
  };
}

function writeResearchUrlState(tab: ResearchTab, projectId: string | null, trackerId: number | null) {
  if (window.location.pathname !== "/research") return;
  const params = new URLSearchParams(window.location.search);
  params.set("tab", tab);
  if (projectId) {
    params.set("projectId", projectId);
  } else {
    params.delete("projectId");
  }
  if (tab === "key_insights" && trackerId) {
    params.set("trackerId", String(trackerId));
  } else {
    params.delete("trackerId");
  }
  params.delete("project_id");
  params.delete("tracker_id");
  const query = params.toString();
  const nextUrl = `${window.location.pathname}${query ? `?${query}` : ""}`;
  if (`${window.location.pathname}${window.location.search}` !== nextUrl) {
    window.history.replaceState(null, "", nextUrl);
  }
}

const DEFAULT_COLLECTION_RUN_PAYLOAD: GrowthProjectCollectionRunPayload = {
  platforms: [],
  keyword_scope: "all_project",
  selected_keywords: [],
  extra_keywords: [],
  persist_to_project: false,
  target_posts_per_platform: 50,
  collection_window_days: 7,
  prefer_latest_posts: true,
  sort_mode: "latest",
  time_preset: "7d",
  time_start: null,
  time_end: null,
  max_results_per_keyword_per_platform: 50,
  fill_strategy: "prefer_fill",
  max_extra_pages: 3,
};

const NOTIFICATION_TASK_STATUSES = new Set(["queued", "pending", "running", "stopping", "failed", "error"]);

function shouldNotifyForBackgroundTask(task: BackgroundTaskItem) {
  return NOTIFICATION_TASK_STATUSES.has(String(task.status || "").toLowerCase());
}

function labelBackgroundTaskSource(task: BackgroundTaskItem) {
  const source = task.source || task.type;
  const labels: Record<string, string> = {
    crawler: "爬虫任务",
    research: "研究任务",
    growth_project: "项目采集",
    creator_search: "达人搜索",
    content_search: "内容搜索",
    ai_analysis: "AI 分析",
    research_execution: "采集执行",
    research_queue: "采集队列",
  };
  return labels[source] || source || "后台任务";
}

function notificationFromBackgroundTask(task: BackgroundTaskItem): AppHeaderNotification {
  return {
    id: task.id,
    title: task.title,
    body: task.progress?.label || task.progress?.stage || "等待状态更新",
    status: String(task.status || "unknown").toLowerCase(),
    source: labelBackgroundTaskSource(task),
    updatedAt: task.updated_at || task.started_at || null,
    progress: typeof task.progress?.percent === "number" ? task.progress.percent : null,
  };
}

function normalizeCollectionRunPayload(
  targetOrPayload?: number | GrowthProjectCollectionRunPayload,
  collectionWindowDays?: number | null,
  preferLatestPosts?: boolean,
): GrowthProjectCollectionRunPayload {
  if (typeof targetOrPayload === "object" && targetOrPayload !== null) {
    return { ...DEFAULT_COLLECTION_RUN_PAYLOAD, ...targetOrPayload };
  }

  return {
    ...DEFAULT_COLLECTION_RUN_PAYLOAD,
    target_posts_per_platform: targetOrPayload ?? DEFAULT_COLLECTION_RUN_PAYLOAD.target_posts_per_platform,
    collection_window_days: collectionWindowDays ?? DEFAULT_COLLECTION_RUN_PAYLOAD.collection_window_days,
    prefer_latest_posts: preferLatestPosts ?? DEFAULT_COLLECTION_RUN_PAYLOAD.prefer_latest_posts,
  };
}

function App({ session, onLogout }: { session: AuthSession; onLogout: () => void }) {

  const initialUrlStateRef = React.useRef(readResearchUrlState());
  const [tab, setTab] = React.useState<ResearchTab>(initialUrlStateRef.current.tab || "projects");
  const canUseAdmin = isPlatformAdmin(session);
  const [sideNavConfig, setSideNavConfig] = React.useState<SideNavConfigValue>(() => defaultSideNavConfig());
  const [dashboard, setDashboard] = React.useState<DashboardSummary>(fallbackDashboard);
  const [databaseStats, setDatabaseStats] = React.useState<DatabaseStats>(fallbackDatabaseStats);
  const [todayIntelligence, setTodayIntelligence] = React.useState<TodayIntelligenceSummary | null>(null);
  const [aiInsights, setAiInsights] = React.useState<AiInsightSummary>(fallbackAiInsights);
  const [aiTopicIdeas, setAiTopicIdeas] = React.useState<AiTopicIdeasSummary>({ topic_ideas: [] });
  const [jobs, setJobs] = React.useState<ResearchJob[]>([]);
  const [backgroundTasks, setBackgroundTasks] = React.useState<BackgroundTaskItem[]>([]);
  const [backgroundTasksLoading, setBackgroundTasksLoading] = React.useState(true);
  const [backgroundTaskError, setBackgroundTaskError] = React.useState<string | null>(null);
  const [growthProjects, setGrowthProjects] = React.useState<GrowthProjectSummary[]>([]);
  const [selectedProjectId, setSelectedProjectId] = React.useState<string | null>(initialUrlStateRef.current.projectId);
  const [strategySourceTrackerId, setStrategySourceTrackerId] = React.useState<number | null>(
    initialUrlStateRef.current.trackerId,
  );
  const [contentTrackingFocusTrackerId, setContentTrackingFocusTrackerId] = React.useState<number | null>(
    initialUrlStateRef.current.tab === "content_tracking" ? initialUrlStateRef.current.trackerId : null,
  );
  const [selectedProjectDetail, setSelectedProjectDetail] = React.useState<GrowthProjectDetail | null>(null);
  const [selectedProjectProgress, setSelectedProjectProgress] = React.useState<GrowthProjectCollectionProgress | null>(null);
  const [isProjectDetailLoading, setIsProjectDetailLoading] = React.useState(false);
  const [selectedJobId, setSelectedJobId] = React.useState<number | null>(null);
  const [posts, setPosts] = React.useState<PostRecord[]>([]);
  const [comments, setComments] = React.useState<CommentRecord[]>([]);
  const [rawRecords, setRawRecords] = React.useState<RawRecord[]>([]);
  const [aiResults, setAiResults] = React.useState<AIResult[]>([]);
  const [pendingExecution, setPendingExecution] = React.useState<PendingExecution | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [loading, setLoading] = React.useState(false);
  const projectDetailCacheRef = React.useRef(new Map<string, GrowthProjectDetail>());
  const projectProgressCacheRef = React.useRef(new Map<string, GrowthProjectCollectionProgress>());
  const projectDetailRequestIdRef = React.useRef(0);
  const projectProgressRequestIdRef = React.useRef(0);
  const todayIntelligenceRequestIdRef = React.useRef(0);
  const projectDetailAbortRef = React.useRef<AbortController | null>(null);
  const projectProgressAbortRef = React.useRef<AbortController | null>(null);
  const backgroundTasksLoadedRef = React.useRef(false);
  const selectedJob = jobs.find((job) => job.id === selectedJobId) || null;
  const selectedProjectSummary =
    growthProjects.find((project) => project.id === selectedProjectId) || selectedProjectDetail?.project || null;
  const selectedProjectRecordId =
    selectedProjectSummary?.project_record_id
    ?? (selectedProjectId && /^\d+$/.test(selectedProjectId) ? Number(selectedProjectId) : null);
  const headerProjects = React.useMemo<AppHeaderProject[]>(
    () =>
      growthProjects.map((project) => ({
        id: project.id,
        name: project.name,
        status: project.sample_status?.label || project.status,
        platforms: project.platforms,
      })),
    [growthProjects],
  );
  const headerNotifications = React.useMemo<AppHeaderNotification[]>(
    () =>
      backgroundTasks
        .filter(shouldNotifyForBackgroundTask)
        .map(notificationFromBackgroundTask),
    [backgroundTasks],
  );
  const shouldLoadProjectContext =
    tab === "projects"
    || tab === "keyword_heat"
    || tab === "key_insights"
    || tab === "creators"
    || tab === "competitors";
  const shouldLoadKeywordHeatContext = tab === "keyword_heat";
  const shouldPollProjectProgress =
    (tab === "projects" || tab === "key_insights") &&
    !!selectedProjectId &&
    (selectedProjectProgress?.status === "running" || selectedProjectProgress?.status === "queued");
  const visibleTabSet = React.useMemo(() => {
    const tabs = new Set<ResearchTab>(configurableNavItems(sideNavConfig).map((item) => item.tab));
    tabs.add("settings");
    if (canUseAdmin) tabs.add("admin");
    return tabs;
  }, [canUseAdmin, sideNavConfig]);

  React.useEffect(() => {
    if (tab === "admin" && !canUseAdmin) {
      setTab("projects");
    }
  }, [canUseAdmin, tab]);

  React.useEffect(() => {
    if (visibleTabSet.has(tab)) return;
    setTab(firstVisibleConfigurableTab(sideNavConfig));
  }, [sideNavConfig, tab, visibleTabSet]);

  const loadSideNavConfig = React.useCallback(async () => {
    try {
      const data = await api<SideNavConfigResponse>("/api/research/ui/side-nav-config");
      setSideNavConfig(normalizeSideNavConfig(data.value));
    } catch {
      setSideNavConfig(defaultSideNavConfig());
    }
  }, []);

  const loadDashboardSummary = React.useCallback(async () => {
    const data = await api<DashboardSummary>("/api/reports/dashboard-summary");
    setDashboard({ ...fallbackDashboard(), ...data });
  }, []);

  const loadTodayIntelligence = React.useCallback(async (projectId = selectedProjectId) => {
    const requestId = ++todayIntelligenceRequestIdRef.current;
    const query = projectId ? `?project_id=${encodeURIComponent(projectId)}` : "";
    const data = await api<TodayIntelligenceSummary>(`/api/reports/today-intelligence${query}`);
    if (requestId !== todayIntelligenceRequestIdRef.current) return;
    setTodayIntelligence(data);
    setDashboard({ ...fallbackDashboard(), ...(data.dashboard || {}) });
    setDatabaseStats({ ...fallbackDatabaseStats(), ...(data.database_stats || {}) });
  }, [selectedProjectId]);

  const regenerateTodayIntelligence = React.useCallback(async (projectId = selectedProjectId) => {
    const requestId = ++todayIntelligenceRequestIdRef.current;
    const data = await api<TodayIntelligenceSummary>("/api/reports/today-intelligence/run", {
      method: "POST",
      body: JSON.stringify({ force: true, project_id: projectId || undefined }),
    });
    if (requestId !== todayIntelligenceRequestIdRef.current) return;
    setTodayIntelligence(data);
    setDashboard({ ...fallbackDashboard(), ...(data.dashboard || {}) });
    setDatabaseStats({ ...fallbackDatabaseStats(), ...(data.database_stats || {}) });
  }, [selectedProjectId]);

  const loadJobs = React.useCallback(async () => {
    const data = await api<{ jobs: ResearchJob[] }>("/api/research/jobs");
    const nextJobs = data.jobs || [];
    setJobs(nextJobs);
    setSelectedJobId((current) => current ?? nextJobs[0]?.id ?? null);
  }, []);

  const loadGrowthProjects = React.useCallback(async () => {
    const data = await api<{ projects: GrowthProjectSummary[] }>("/api/research/growth-projects");
    const projects = data.projects || [];
    setGrowthProjects(projects);
    setSelectedProjectId((current) => {
      if (current && projects.some((project) => project.id === current)) {
        return current;
      }
      return projects[0]?.id ?? null;
    });
  }, []);

  const loadDatabaseStats = React.useCallback(async () => {
    const data = await api<DatabaseStats>("/api/research/database/stats");
    setDatabaseStats({ ...fallbackDatabaseStats(), ...data });
  }, []);

  const loadAiOverview = React.useCallback(async () => {
    const [insightsResult, topicIdeasResult] = await Promise.allSettled([
      api<AiInsightSummary>("/api/reports/ai-insights/latest"),
      api<AiTopicIdeasSummary>("/api/reports/ai-topic-ideas"),
    ]);
    if (insightsResult.status === "fulfilled") {
      setAiInsights({ ...fallbackAiInsights(), ...insightsResult.value });
    }
    if (topicIdeasResult.status === "fulfilled") {
      setAiTopicIdeas({ topic_ideas: topicIdeasResult.value.topic_ideas || [] });
    }
  }, []);

  const loadSelected = React.useCallback(async (jobId: number | null) => {
    if (!jobId) return;
    const [postsResult, commentsResult, rawResult, aiResult] = await Promise.allSettled([
      api<{ posts: PostRecord[] }>(`/api/research/jobs/${jobId}/posts?limit=200`),
      api<{ comments: CommentRecord[] }>(`/api/research/jobs/${jobId}/comments?limit=200`),
      api<{ raw_records: RawRecord[] }>(`/api/research/jobs/${jobId}/raw-records?limit=100`),
      api<{ results: AIResult[] }>(`/api/research/jobs/${jobId}/ai/results`),
    ]);
    if (postsResult.status === "fulfilled") setPosts(postsResult.value.posts || []);
    if (commentsResult.status === "fulfilled") setComments(commentsResult.value.comments || []);
    if (rawResult.status === "fulfilled") setRawRecords(rawResult.value.raw_records || []);
    if (aiResult.status === "fulfilled") setAiResults(aiResult.value.results || []);
  }, []);

  const loadSelectedProject = React.useCallback(async (projectId: string | null) => {
    if (!projectId) {
      projectDetailAbortRef.current?.abort();
      setSelectedProjectDetail(null);
      setSelectedProjectProgress(null);
      setIsProjectDetailLoading(false);
      return;
    }

    const requestId = ++projectDetailRequestIdRef.current;
    projectDetailAbortRef.current?.abort();
    const controller = new AbortController();
    projectDetailAbortRef.current = controller;

    const cachedDetail = projectDetailCacheRef.current.get(projectId) || null;
    setSelectedProjectDetail(cachedDetail);
    setIsProjectDetailLoading(true);

    try {
      const detail = await api<GrowthProjectDetail>(`/api/research/growth-projects/${encodeURIComponent(projectId)}`, { signal: controller.signal });
      if (requestId !== projectDetailRequestIdRef.current) return;
      projectDetailCacheRef.current.set(projectId, detail);
      setSelectedProjectDetail(detail);
    } catch (err) {
      if ((err as Error).name === "AbortError") return;
      if (requestId !== projectDetailRequestIdRef.current) return;
      projectDetailCacheRef.current.delete(projectId);
      setSelectedProjectDetail(null);
      if (err instanceof ApiError && err.status === 404) {
        setSelectedProjectId((current) => (current === projectId ? null : current));
        return;
      }
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      if (requestId === projectDetailRequestIdRef.current) {
        setIsProjectDetailLoading(false);
      }
    }
  }, []);

  const loadBackgroundTasks = React.useCallback(async () => {
    if (!backgroundTasksLoadedRef.current) {
      setBackgroundTasksLoading(true);
    }
    try {
      const data = await api<{ tasks: BackgroundTaskItem[] }>("/api/background-tasks");
      setBackgroundTasks(data.tasks || []);
      setBackgroundTaskError(null);
    } catch (err) {
      setBackgroundTasks([]);
      setBackgroundTaskError(err instanceof Error ? err.message : String(err));
    } finally {
      backgroundTasksLoadedRef.current = true;
      setBackgroundTasksLoading(false);
    }
  }, []);

  const loadSelectedProjectProgress = React.useCallback(async (projectId: string | null) => {
    if (!projectId) {
      projectProgressAbortRef.current?.abort();
      setSelectedProjectProgress(null);
      return;
    }

    const requestId = ++projectProgressRequestIdRef.current;
    projectProgressAbortRef.current?.abort();
    const controller = new AbortController();
    projectProgressAbortRef.current = controller;

    const cachedProgress = projectProgressCacheRef.current.get(projectId) || null;
    if (cachedProgress) {
      setSelectedProjectProgress(cachedProgress);
    }

    try {
      const progress = await api<GrowthProjectCollectionProgress>(
        `/api/research/growth-projects/${encodeURIComponent(projectId)}/collection/progress`,
        { signal: controller.signal },
      );
      if (requestId !== projectProgressRequestIdRef.current) return;
      projectProgressCacheRef.current.set(projectId, progress);
      setSelectedProjectProgress(progress);
    } catch (err) {
      if ((err as Error).name === "AbortError") return;
      if (requestId !== projectProgressRequestIdRef.current) return;
      projectProgressCacheRef.current.delete(projectId);
      setSelectedProjectProgress(null);
      if (err instanceof ApiError && err.status === 404) {
        setSelectedProjectId((current) => (current === projectId ? null : current));
        return;
      }
      setError(err instanceof Error ? err.message : String(err));
    }
  }, []);

  const refreshAll = React.useCallback(async () => {
    const tasks: Promise<unknown>[] = [];
    if (tab === "today") {
      tasks.push(loadTodayIntelligence(selectedProjectId), loadJobs(), loadGrowthProjects(), loadAiOverview());
    } else if (tab === "projects") {
      tasks.push(loadGrowthProjects());
    } else if (tab === "keyword_heat") {
      tasks.push(loadJobs(), loadGrowthProjects(), loadDatabaseStats());
    } else if (tab === "key_insights") {
      tasks.push(loadGrowthProjects());
    } else if (tab === "creators" || tab === "competitors") {
      tasks.push(loadGrowthProjects());
    }
    if (tasks.length === 0) {
      setError(null);
      return;
    }
    setLoading(true);
    try {
      await Promise.allSettled(tasks);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, [tab, selectedProjectId, loadTodayIntelligence, loadJobs, loadGrowthProjects, loadDatabaseStats, loadAiOverview]);

  React.useEffect(() => { void refreshAll(); }, [refreshAll]);
  React.useEffect(() => { void loadSideNavConfig(); }, [loadSideNavConfig]);
  React.useEffect(() => {
    void loadBackgroundTasks();
    const interval = window.setInterval(() => {
      void loadBackgroundTasks();
    }, 5000);
    return () => window.clearInterval(interval);
  }, [loadBackgroundTasks]);
  React.useEffect(() => {
    const handleSideNavConfigUpdated = (event: Event) => {
      const detail = (event as CustomEvent<SideNavConfigValue>).detail;
      if (detail) {
        setSideNavConfig(normalizeSideNavConfig(detail));
      }
    };
    window.addEventListener("side-nav-config:updated", handleSideNavConfigUpdated);
    return () => window.removeEventListener("side-nav-config:updated", handleSideNavConfigUpdated);
  }, []);
  React.useEffect(() => {
    if (!shouldLoadKeywordHeatContext) return;
    void loadSelected(selectedJobId);
  }, [loadSelected, selectedJobId, shouldLoadKeywordHeatContext]);
  React.useEffect(() => {
    if (!shouldLoadProjectContext) return;
    void loadSelectedProject(selectedProjectId);
  }, [loadSelectedProject, selectedProjectId, shouldLoadProjectContext]);
  React.useEffect(() => {
    if (!shouldLoadProjectContext) return;
    void loadSelectedProjectProgress(selectedProjectId);
  }, [loadSelectedProjectProgress, selectedProjectId, shouldLoadProjectContext]);
  React.useEffect(() => {
    if (!shouldPollProjectProgress) return;
    if (!selectedProjectId) return;
    const interval = window.setInterval(() => {
      void loadSelectedProjectProgress(selectedProjectId);
    }, 2000);
    return () => window.clearInterval(interval);
  }, [loadSelectedProjectProgress, selectedProjectId, shouldPollProjectProgress]);

  React.useEffect(() => {
    writeResearchUrlState(tab, selectedProjectId, strategySourceTrackerId);
  }, [selectedProjectId, strategySourceTrackerId, tab]);

  function changeTab(nextTab: ResearchTab) {
    if (nextTab !== "key_insights") {
      setStrategySourceTrackerId(null);
    }
    if (nextTab !== "content_tracking") {
      setContentTrackingFocusTrackerId(null);
    }
    setTab(nextTab);
  }

  function openContentStrategy(trackerId: number | null = null) {
    setStrategySourceTrackerId(trackerId);
    setTab("key_insights");
  }

  function openContentTracking(trackerId: number | null = null) {
    setContentTrackingFocusTrackerId(trackerId);
    setTab("content_tracking");
  }

  async function createGrowthProject(payload: GrowthProjectCreatePayload) {
    const result = await api<{ project_id: string; project_record_id?: number | null; job: ResearchJob }>("/api/research/growth-projects", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    await Promise.allSettled([loadJobs(), loadGrowthProjects()]);
    setSelectedProjectId(result.project_id);
  }

  async function updateGrowthProject(projectId: string, payload: GrowthProjectUpdatePayload) {
    const result = await api<{ project_id?: string; project: GrowthProjectSummary }>(`/api/research/growth-projects/${encodeURIComponent(projectId)}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    });
    const nextProjectId = result.project_id || projectId;
    if (nextProjectId !== projectId) {
      projectDetailCacheRef.current.delete(projectId);
      projectProgressCacheRef.current.delete(projectId);
    }
    await Promise.allSettled([loadJobs(), loadGrowthProjects(), loadSelectedProject(nextProjectId), loadSelectedProjectProgress(nextProjectId)]);
    if (result.project?.name) {
      setSelectedProjectId(nextProjectId);
    }
  }

  async function deleteGrowthProject(projectId: string) {
    await api<Record<string, unknown>>(`/api/research/growth-projects/${encodeURIComponent(projectId)}`, {
      method: "DELETE",
    });
    await Promise.allSettled([loadJobs(), loadGrowthProjects()]);
    setSelectedProjectDetail(null);
    setSelectedProjectProgress(null);
    setSelectedProjectId(null);
  }

  async function controlGrowthProject(
    projectId: string,
    action: "run-now" | "pause" | "stop-current-run" | "archive",
    body?: unknown,
  ) {
    const path = action === "archive"
      ? `/api/research/growth-projects/${encodeURIComponent(projectId)}/archive`
      : `/api/research/growth-projects/${encodeURIComponent(projectId)}/collection/${action}`;
    await api<Record<string, unknown>>(path, {
      method: "POST",
      body: body ? JSON.stringify(body) : undefined,
    });
    if (action === "archive") {
      projectDetailCacheRef.current.delete(projectId);
      projectProgressCacheRef.current.delete(projectId);
      setSelectedProjectDetail(null);
      setSelectedProjectProgress(null);
      await Promise.allSettled([loadJobs(), loadGrowthProjects()]);
      return;
    }
    await Promise.allSettled([loadJobs(), loadGrowthProjects(), loadSelectedProject(projectId), loadSelectedProjectProgress(projectId)]);
  }

  async function submitOpportunityFeedback(
    opportunity: DashboardOpportunity,
    feedback: "valid" | "false_positive" | "watch",
    note = "",
  ) {
    await api<{ feedback: Record<string, unknown> }>("/api/reports/opportunity-feedback", {
      method: "POST",
      body: JSON.stringify({
        opportunity_id: opportunity.id,
        opportunity_type: opportunity.type,
        opportunity_name: opportunity.name,
        feedback,
        note,
        payload: { score: opportunity.score, risk_tags: opportunity.risk_tags || [] },
      }),
    });
    if (tab === "today") {
      await loadTodayIntelligence(selectedProjectId);
    } else {
      await loadDashboardSummary();
    }
  }

  function requestOpportunityExecution(opportunity: DashboardOpportunity) {
    const action = executableAction(opportunity);
    setPendingExecution({
      title: opportunity.name,
      action: action?.kind || "prefill_collection_task",
      targetType: opportunity.type,
      platform: opportunity.platform,
      payload: action?.payload || opportunity.payload || {},
    });
  }

  return (
    <div className="app-shell app-shell--side">
      <SideNav tab={tab} onChange={changeTab} showAdmin={canUseAdmin} config={sideNavConfig} />
      <div className="app-shell__main">
        <AppHeader
          title={selectedProjectSummary?.name || (growthProjects.length ? "选择项目" : TAB_TITLES[tab] || "暂无项目")}
          loading={loading}
          onRefresh={refreshAll}
          notifications={headerNotifications}
          notificationsLoading={backgroundTasksLoading}
          notificationError={backgroundTaskError}
          projects={headerProjects}
          selectedProjectId={selectedProjectId}
          onSelectProject={setSelectedProjectId}
          currentUser={{
            email: session.user.email,
            displayName: session.user.display_name,
            organizationName: session.organization.name,
            role: `${canUseAdmin ? "platform admin" : "member"} · ${session.organization.name}`,
            initial: authInitial(session),
          }}
          onLogout={onLogout}
        />
        <main className="workspace">
          {error && <div className="notice error"><AlertTriangle size={16} />{error}</div>}
          <React.Suspense fallback={<WorkspaceLoadingState title={TAB_TITLES[tab]} />}>
            {tab === "today" && (
              <TodayIntelligencePage
                dashboard={dashboard}
                databaseStats={databaseStats}
                aiInsights={aiInsights}
                aiTopicIdeas={aiTopicIdeas}
                todayIntelligence={todayIntelligence}
                onRefresh={refreshAll}
                onRegenerate={regenerateTodayIntelligence}
                onExecute={requestOpportunityExecution}
                onFeedback={submitOpportunityFeedback}
              />
            )}
            {tab === "projects" && (
              <ProjectsHubPage
                projects={growthProjects}
                selectedProjectId={selectedProjectId}
                selectedProjectDetail={selectedProjectDetail}
                selectedProjectProgress={selectedProjectProgress}
                isProjectDetailLoading={isProjectDetailLoading}
                onSelectProject={setSelectedProjectId}
                onCreateProject={createGrowthProject}
                onUpdateProject={updateGrowthProject}
                onDeleteProject={deleteGrowthProject}
                onStartCollection={(projectId, payload) =>
                  controlGrowthProject(projectId, "run-now", normalizeCollectionRunPayload(payload))}
                onPauseCollection={(projectId) => controlGrowthProject(projectId, "pause")}
                onStopCurrentRun={(projectId) => controlGrowthProject(projectId, "stop-current-run")}
                onArchiveProject={(projectId) => controlGrowthProject(projectId, "archive")}
                onOpenData={() => openContentTracking()}
                onOpenAi={() => openContentStrategy()}
              />
            )}
            {tab === "content_production" && <ContentProductionPage />}
            {tab === "creators" && (
              <CreatorDiscoveryPage
                selectedProjectId={selectedProjectId}
                selectedProjectRecordId={selectedProjectRecordId}
                selectedProjectName={selectedProjectSummary?.name || null}
              />
            )}
            {tab === "competitors" && (
              <CompetitorMonitorPage
                selectedProjectId={selectedProjectId}
                selectedProjectRecordId={selectedProjectRecordId}
                selectedProjectName={selectedProjectSummary?.name || null}
              />
            )}
            {tab === "content_tracking" && (
              <ContentTrackingPage
                focusTrackerId={contentTrackingFocusTrackerId}
                selectedProjectRecordId={selectedProjectRecordId}
                selectedProjectName={selectedProjectSummary?.name || null}
                onUseTrackerForStrategy={(trackerId) => openContentStrategy(trackerId)}
              />
            )}
            {tab === "lead_attribution" && <LeadAttributionPage />}
            {tab === "keyword_heat" && (
              <KeywordHeatPage
                selectedProjectDetail={selectedProjectDetail}
                jobs={jobs}
                posts={posts}
                databaseStats={databaseStats}
              />
            )}
            {tab === "admin" && canUseAdmin && <AdminConsolePage session={session} />}
            {tab === "settings" && <SettingsHubPage />}
            {tab === "data_board" && <PlaceholderPage title="Data Board" subtitle="Cross-project dashboards and trend views are coming soon." />}
            {tab === "key_insights" && (
              <ContentStrategyCenterPage
                selectedProjectId={selectedProjectId}
                selectedProjectDetail={selectedProjectDetail}
                selectedProjectProgress={selectedProjectProgress}
                sourceTrackerId={strategySourceTrackerId}
                onClearSourceTracker={() => setStrategySourceTrackerId(null)}
                onOpenSourceTracker={(trackerId) => openContentTracking(trackerId)}
                onUpdateProject={(projectId, payload) => updateGrowthProject(projectId, payload)}
              />
            )}
            {tab === "topic_tracking" && <PlaceholderPage title="Topic Tracking" subtitle="Topic, hot trend, and long-tail monitoring will be available soon." />}
            {tab === "account_analysis" && <PlaceholderPage title="Account Analysis" subtitle="Creator and brand account profiling is coming soon." />}
            {tab === "content_library" && <PlaceholderPage title="Content Library" subtitle="A unified library for captured posts, videos, and winning assets is coming soon." />}
            {tab === "reports_center" && <PlaceholderPage title="Reports Center" subtitle="Scheduled reports, subscriptions, and sharing are coming soon." />}
            {tab === "ai_assistant" && <PlaceholderPage title="AI Assistant" subtitle="A conversational research assistant will be available soon." />}
          </React.Suspense>
        </main>
      </div>
      <ConfirmExecutionModal
        execution={pendingExecution}
        onCancel={() => setPendingExecution(null)}
        onConfirm={() => setPendingExecution(null)}
      />
    </div>
  );
}

function RootApp() {
  const [path, setPath] = React.useState(() => window.location.pathname);
  const [session, setSession] = React.useState<AuthSession | null>(() => getStoredAuthSession());

  const navigate = React.useCallback((nextPath: string) => {
    if (window.location.pathname !== nextPath) {
      window.history.pushState(null, "", nextPath);
    }
    setPath(window.location.pathname);
  }, []);

  React.useEffect(() => {
    const syncPath = () => setPath(window.location.pathname);
    const handleUnauthorized = () => {
      clearAuthSession();
      setSession(null);
      navigate("/login");
    };

    window.addEventListener("popstate", syncPath);
    window.addEventListener("auth:unauthorized", handleUnauthorized);
    return () => {
      window.removeEventListener("popstate", syncPath);
      window.removeEventListener("auth:unauthorized", handleUnauthorized);
    };
  }, [navigate]);

  React.useEffect(() => {
    if (!session && path !== "/login" && path !== "/register") {
      navigate("/login");
      return;
    }
    if (session && (path === "/" || path === "/login" || path === "/register")) {
      navigate("/research");
    }
  }, [navigate, path, session]);

  React.useEffect(() => {
    if (!session?.accessToken) return;
    let active = true;
    void api<CurrentUserContext>("/api/me")
      .then((context) => {
        if (!active) return;
        setSession((current) => {
          if (!current || current.accessToken !== session.accessToken) return current;
          const nextSession: AuthSession = {
            ...current,
            user: context.user,
            organization: context.organization,
            membership: context.membership,
            permissions: context.permissions || { is_platform_admin: false },
          };
          saveAuthSession(nextSession);
          return nextSession;
        });
      })
      .catch(() => undefined);
    return () => {
      active = false;
    };
  }, [session?.accessToken]);

  const handleAuthenticated = React.useCallback(
    (nextSession: AuthSession) => {
      saveAuthSession(nextSession);
      setSession(nextSession);
      navigate("/research");
    },
    [navigate],
  );

  const handleNavigateAuth = React.useCallback(
    (mode: AuthMode) => {
      navigate(mode === "register" ? "/register" : "/login");
    },
    [navigate],
  );

  const handleLogout = React.useCallback(() => {
    const refreshToken = session?.refreshToken;
    clearAuthSession();
    setSession(null);
    navigate("/login");
    if (refreshToken) {
      void api<{ revoked: boolean }>("/api/auth/logout", {
        method: "POST",
        body: JSON.stringify({ refresh_token: refreshToken }),
      }).catch(() => undefined);
    }
  }, [navigate, session?.refreshToken]);

  if (!session) {
    return (
      <AuthPage
        mode={path === "/register" ? "register" : "login"}
        onAuthenticated={handleAuthenticated}
        onNavigate={handleNavigateAuth}
      />
    );
  }

  return (
    <App
      key={`${session.user.id}:${session.organization.id}`}
      session={session}
      onLogout={handleLogout}
    />
  );
}

type CurrentUserContext = {
  user: AuthSession["user"];
  organization: AuthSession["organization"];
  membership: AuthSession["membership"];
  permissions?: AuthSession["permissions"];
};

function WorkspaceLoadingState({ title }: { title?: string }) {
  return (
    <div className="placeholder-page">
      <div className="placeholder-page-card">
        <Construction size={48} />
        <h1>{title || "Loading module"}</h1>
        <p>Module is loading on demand. Please wait a moment.</p>
        <span className="placeholder-page-hint">The first visit may be slower than later visits.</span>
      </div>
    </div>
  );
}

function PlaceholderPage({ title, subtitle }: { title: string; subtitle: string }) {
  return (
    <div className="placeholder-page">
      <div className="placeholder-page-card">
        <Construction size={48} />
        <h1>{title}</h1>
        <p>{subtitle}</p>
        <span className="placeholder-page-hint">该模块正在开发中，敬请期待。</span>
      </div>
    </div>
  );
}

function executableAction(opportunity: DashboardOpportunity) {
  const actions = (opportunity.actions || []).map((action) =>
    typeof action === "string"
      ? {
          kind: action,
          label: action === "view_evidence" ? "查看证据" : "预填任务",
          risk: action === "view_evidence" ? "low" : "high",
          payload: opportunity.payload || {},
        }
      : action,
  );
  return actions.find((action) => action.risk === "high") || actions.find((action) => action.kind !== "view_evidence");
}

function ConfirmExecutionModal({
  execution,
  onCancel,
  onConfirm,
}: {
  execution: PendingExecution | null;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  return (
    <ConfirmDialog
      open={!!execution}
      onOpenChange={(open) => {
        if (!open) onCancel();
      }}
      title="确认高风险动作"
      description="真实采集、扩大监控、AI 成本或敏感导出需要确认后执行。"
    >
      {execution && (
        <>
          <div className="confirm-grid">
            <span>对象</span><strong>{execution.title}</strong>
            <span>类型</span><strong>{labelOpportunityType(execution.targetType)}</strong>
            <span>平台</span><strong>{labelPlatform(execution.platform)}</strong>
            <span>动作</span><strong>{execution.action}</strong>
          </div>
          <pre className="json-detail">{JSON.stringify(execution.payload, null, 2)}</pre>
          <div className="button-row right">
            <Button variant="ghost" onClick={onCancel}><X size={16} />取消</Button>
            <Button variant="primary" onClick={onConfirm}><Play size={16} />确认</Button>
          </div>
        </>
      )}
    </ConfirmDialog>
  );
}

const rootElement = document.getElementById("root") as (HTMLElement & { __growthIntelRoot?: Root }) | null;

if (!rootElement) {
  throw new Error("Root element #root not found");
}

const root = rootElement.__growthIntelRoot ?? createRoot(rootElement);
rootElement.__growthIntelRoot = root;
root.render(<React.StrictMode><RootApp /></React.StrictMode>);
