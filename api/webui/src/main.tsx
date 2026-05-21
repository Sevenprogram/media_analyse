import React from "react";
import { createRoot } from "react-dom/client";
import { AlertTriangle, Loader2, Play, RefreshCw, X } from "lucide-react";
import { ResearchSidebar } from "./components/sidebar";
import { Button, ConfirmDialog } from "./components/ui";
import { api } from "./utils/api";
import { labelOpportunityType, labelPlatform } from "./utils/format";
import { DataBrowserPage } from "./pages/DataBrowserPage";
import { BackgroundTasksPage } from "./pages/BackgroundTasksPage";
import { GrowthProjectWorkbenchPage } from "./pages/GrowthProjectWorkbenchPage";
import { OpportunityDecisionPage } from "./pages/OpportunityDecisionPage";
import {
  AiAnalysisPage,
  CompetitorMonitorPage,
  ConfigPage,
  ContentTrackingPage,
  CreatorDiscoveryPage,
  ExportCenterPage,
  KeywordLibraryPage,
  OverviewPage,
} from "./pages/ResearchModulePages";
import type {
  AIResult,
  AiInsightSummary,
  AiTopicIdeasSummary,
  CommentRecord,
  DatabaseStats,
  DashboardOpportunity,
  DashboardSummary,
  GrowthProjectCreatePayload,
  GrowthProjectCollectionProgress,
  GrowthProjectDetail,
  GrowthProjectSummary,
  GrowthProjectUpdatePayload,
  PendingExecution,
  PostRecord,
  RawRecord,
  ResearchJob,
  ResearchTab,
} from "./types";
import "./styles.css";

const fallbackDashboard = (): DashboardSummary => ({
  decision: {
    headline: "暂无机会判断",
    confidence: "low",
    sample_status: "insufficient",
    sample_summary: "缺少足够样本，系统不会生成假结论。",
    risk_notes: ["先采集样本后再生成机会榜。"],
    evidence_count: 0,
  },
  actions: { do_now: [], watch_today: [], defer: [] },
  monitoring: { running_jobs: 0, today_collected: 0, errors: 0, monitor_pools: 0, realtime_jobs: 0, last_updated_at: null },
  opportunities: [],
  top_opportunities: [],
  watchlist: [],
  ignored_opportunities: [],
  diagnostics: [{ code: "no_data", title: "暂无机会判断", body: "缺少样本时，系统只显示诊断，不生成假结论。" }],
  scoring_profile: { weights: { heat_growth: 0.35, sample_confidence: 0.25, competition_gap: 0.2, actionability: 0.2 }, window: "7d_plus_24h" },
});

const fallbackDatabaseStats = (): DatabaseStats => ({
  total_collected: 0,
  research_posts: 0,
  research_comments: 0,
  raw_records: 0,
  creator_profiles: 0,
  entity_tags: 0,
  creator_candidates: 0,
  by_platform: { posts: {}, comments: {}, raw_records: {} },
  raw_platform_tables: {},
  raw_platform_totals: {},
});

const fallbackAiInsights = (): AiInsightSummary => ({
  run: null,
  hotspots: [],
  topic_ideas: [],
});

function App() {
  const [tab, setTab] = React.useState<ResearchTab>("overview");
  const [dashboard, setDashboard] = React.useState<DashboardSummary>(fallbackDashboard);
  const [databaseStats, setDatabaseStats] = React.useState<DatabaseStats>(fallbackDatabaseStats);
  const [aiInsights, setAiInsights] = React.useState<AiInsightSummary>(fallbackAiInsights);
  const [aiTopicIdeas, setAiTopicIdeas] = React.useState<AiTopicIdeasSummary>({ topic_ideas: [] });
  const [jobs, setJobs] = React.useState<ResearchJob[]>([]);
  const [growthProjects, setGrowthProjects] = React.useState<GrowthProjectSummary[]>([]);
  const [selectedProjectId, setSelectedProjectId] = React.useState<string | null>(null);
  const [selectedProjectDetail, setSelectedProjectDetail] = React.useState<GrowthProjectDetail | null>(null);
  const [selectedProjectProgress, setSelectedProjectProgress] = React.useState<GrowthProjectCollectionProgress | null>(null);
  const [selectedJobId, setSelectedJobId] = React.useState<number | null>(null);
  const [posts, setPosts] = React.useState<PostRecord[]>([]);
  const [comments, setComments] = React.useState<CommentRecord[]>([]);
  const [rawRecords, setRawRecords] = React.useState<RawRecord[]>([]);
  const [aiResults, setAiResults] = React.useState<AIResult[]>([]);
  const [pendingExecution, setPendingExecution] = React.useState<PendingExecution | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [loading, setLoading] = React.useState(false);
  const selectedJob = jobs.find((job) => job.id === selectedJobId) || null;

  const loadDashboardSummary = React.useCallback(async () => {
    const data = await api<DashboardSummary>("/api/reports/dashboard-summary");
    setDashboard({ ...fallbackDashboard(), ...data });
  }, []);

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
    setSelectedProjectId((current) => current ?? projects[0]?.id ?? null);
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
      setSelectedProjectDetail(null);
      setSelectedProjectProgress(null);
      return;
    }
    const detail = await api<GrowthProjectDetail>(`/api/research/growth-projects/${encodeURIComponent(projectId)}`);
    setSelectedProjectDetail(detail);
  }, []);

  const loadSelectedProjectProgress = React.useCallback(async (projectId: string | null) => {
    if (!projectId) {
      setSelectedProjectProgress(null);
      return;
    }
    const progress = await api<GrowthProjectCollectionProgress>(
      `/api/research/growth-projects/${encodeURIComponent(projectId)}/collection/progress`,
    );
    setSelectedProjectProgress(progress);
  }, []);

  const refreshAll = React.useCallback(async () => {
    setLoading(true);
    try {
      await Promise.allSettled([loadDashboardSummary(), loadJobs(), loadGrowthProjects(), loadDatabaseStats(), loadAiOverview()]);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, [loadDashboardSummary, loadJobs, loadGrowthProjects, loadDatabaseStats, loadAiOverview]);

  React.useEffect(() => { void refreshAll(); }, [refreshAll]);
  React.useEffect(() => { void loadSelected(selectedJobId); }, [loadSelected, selectedJobId]);
  React.useEffect(() => { void loadSelectedProject(selectedProjectId); }, [loadSelectedProject, selectedProjectId]);
  React.useEffect(() => {
    void loadSelectedProjectProgress(selectedProjectId);
    if (!selectedProjectId) return;
    const interval = window.setInterval(() => {
      void loadSelectedProjectProgress(selectedProjectId);
    }, 2000);
    return () => window.clearInterval(interval);
  }, [loadSelectedProjectProgress, selectedProjectId]);

  async function createGrowthProject(payload: GrowthProjectCreatePayload) {
    const result = await api<{ project_id: string; project_record_id?: number | null; job: ResearchJob }>("/api/research/growth-projects", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    await Promise.allSettled([loadJobs(), loadGrowthProjects()]);
    setSelectedProjectId(result.project_id);
  }

  async function updateGrowthProject(projectId: string, payload: GrowthProjectUpdatePayload) {
    const result = await api<{ project: GrowthProjectSummary }>(`/api/research/growth-projects/${encodeURIComponent(projectId)}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    });
    await Promise.allSettled([loadJobs(), loadGrowthProjects(), loadSelectedProject(projectId), loadSelectedProjectProgress(projectId)]);
    if (result.project?.name) {
      setSelectedProjectId(projectId);
    }
  }

  async function deleteGrowthProject(projectId: string) {
    const confirmed = window.confirm("删除项目会将项目从列表归档隐藏，但不会删除已经采集的样本和任务记录。确定继续吗？");
    if (!confirmed) return;
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
    body?: Record<string, unknown>,
  ) {
    const path = action === "archive"
      ? `/api/research/growth-projects/${encodeURIComponent(projectId)}/archive`
      : `/api/research/growth-projects/${encodeURIComponent(projectId)}/collection/${action}`;
    await api<Record<string, unknown>>(path, {
      method: "POST",
      body: body ? JSON.stringify(body) : undefined,
    });
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
    await loadDashboardSummary();
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
    <div className="app-shell">
      <ResearchSidebar active={tab} onChange={setTab} />
      <main className="workspace">
        <Topbar loading={loading} onRefresh={refreshAll} />
        {error && <div className="notice error"><AlertTriangle size={16} />{error}</div>}
        {tab === "overview" && (
          <OverviewPage
            dashboard={dashboard}
            databaseStats={databaseStats}
            aiInsights={aiInsights}
            aiTopicIdeas={aiTopicIdeas}
            jobs={jobs}
            onRefresh={refreshAll}
          />
        )}
        {tab === "tasks" && (
          <GrowthProjectWorkbenchPage
            projects={growthProjects}
            selectedProjectId={selectedProjectId}
            selectedProjectDetail={selectedProjectDetail}
            selectedProjectProgress={selectedProjectProgress}
            onSelectProject={setSelectedProjectId}
            onCreateProject={createGrowthProject}
            onUpdateProject={updateGrowthProject}
            onDeleteProject={deleteGrowthProject}
            onStartCollection={(projectId, targetPostsPerPlatform, collectionWindowDays, preferLatestPosts) => controlGrowthProject(projectId, "run-now", { target_posts_per_platform: targetPostsPerPlatform, collection_window_days: collectionWindowDays, prefer_latest_posts: preferLatestPosts })}
            onPauseCollection={(projectId) => controlGrowthProject(projectId, "pause")}
            onStopCurrentRun={(projectId) => controlGrowthProject(projectId, "stop-current-run")}
            onArchiveProject={(projectId) => controlGrowthProject(projectId, "archive")}
            onOpenData={() => setTab("data")}
            onOpenAi={() => setTab("ai")}
          />
        )}
        {tab === "background_tasks" && <BackgroundTasksPage />}
        {tab === "opportunities" && (
          <OpportunityDecisionPage
            dashboard={dashboard}
            onRefresh={loadDashboardSummary}
            onExecute={requestOpportunityExecution}
            onFeedback={submitOpportunityFeedback}
          />
        )}
        {tab === "data" && (
          <DataBrowserPage
            selectedJob={selectedJob}
            jobs={jobs}
            selectedJobId={selectedJobId}
            setSelectedJobId={setSelectedJobId}
            posts={posts}
            comments={comments}
            rawRecords={rawRecords}
            aiResults={aiResults}
          />
        )}
        {tab === "creators" && <CreatorDiscoveryPage />}
        {tab === "keyword_library" && <KeywordLibraryPage />}
        {tab === "competitors" && <CompetitorMonitorPage />}
        {tab === "content_tracking" && <ContentTrackingPage />}
        {tab === "ai" && (
          <AiAnalysisPage
            selectedJob={selectedJob}
            posts={posts}
            comments={comments}
            aiResults={aiResults}
            onRefresh={() => loadSelected(selectedJobId)}
          />
        )}
        {tab === "export" && (
          <ExportCenterPage
            jobs={jobs}
            posts={posts}
            comments={comments}
            rawRecords={rawRecords}
            aiResults={aiResults}
          />
        )}
        {tab === "config" && <ConfigPage />}
      </main>
      <ConfirmExecutionModal execution={pendingExecution} onCancel={() => setPendingExecution(null)} onConfirm={() => setPendingExecution(null)} />
    </div>
  );
}

function Topbar({ loading, onRefresh }: { loading: boolean; onRefresh: () => Promise<void> }) {
  return (
    <header className="topbar">
      <div>
        <strong>Research Console</strong>
        <span>完整研究工作台：采集、研判、审计、导出</span>
      </div>
      <Button variant="ghost" onClick={onRefresh}>
        {loading ? <Loader2 className="spin" size={16} /> : <RefreshCw size={16} />}
        刷新
      </Button>
    </header>
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

createRoot(document.getElementById("root")!).render(<React.StrictMode><App /></React.StrictMode>);
