import React from "react";
import {
  Activity,
  AlertTriangle,
  BarChart3,
  Bot,
  CheckCircle2,
  Database,
  Download,
  FileJson,
  Filter,
  Gauge,
  KeyRound,
  Loader2,
  MonitorCheck,
  Play,
  Plus,
  RefreshCw,
  Search,
  Settings,
  Users,
} from "lucide-react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { ApiError, api } from "../utils/api";
import { compactJson, formatDateTime, formatNumber, labelPlatform } from "../utils/format";
import { Badge, Button, Card, CardDescription, CardHeader, CardTitle } from "../components/ui";
import type {
  AIResult,
  AiInsightSummary,
  AiTopicIdeasSummary,
  CommentRecord,
  DatabaseStats,
  DashboardSummary,
  PostRecord,
  RawRecord,
  ResearchJob,
} from "../types";

type UnknownRecord = Record<string, unknown>;
type CompetitorFetchStatus = { status: "running" | "success" | "error"; message: string; progress?: number };
type PersistedCompetitorFetchTask = { competitorId: number; taskId: string; name: string; daysBack?: number };

const COMPETITOR_FETCH_TASKS_KEY = "mediaCrawler.competitorFetchTasks";
const CREATOR_SEARCH_TASK_KEY = "mediaCrawler.creatorSearchTaskId";

type CreatorSearchResponse = {
  intent?: UnknownRecord | null;
  diagnostics?: UnknownRecord;
  realtime?: CreatorSearchRealtimeDiagnostics;
  progress?: CreatorSearchProgress;
  results: UnknownRecord[];
};

type CreatorSearchTask = {
  task_id: string;
  status: string;
  request?: UnknownRecord;
  progress?: CreatorSearchProgress;
  result?: CreatorSearchResponse | null;
  error?: string | null;
};

type CreatorSearchProgress = {
  stage: string;
  label: string;
  percent: number;
};

type CreatorSearchRealtimeDiagnostics = {
  enabled?: boolean;
  status?: string;
  platforms?: string[];
  unsupported_platforms?: string[];
  created_profiles?: number;
  created_candidates?: number;
  error?: string | null;
};

function useEndpoint<T>(path: string, fallback: T) {
  const [data, setData] = React.useState<T>(fallback);
  const [error, setError] = React.useState<string | null>(null);
  const [loading, setLoading] = React.useState(false);

  const reload = React.useCallback(async () => {
    setLoading(true);
    try {
      setData(await api<T>(path));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, [path]);

  React.useEffect(() => {
    void reload();
  }, [reload]);

  return { data, error, loading, reload };
}

function asRecord(value: unknown): UnknownRecord {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as UnknownRecord) : {};
}

function text(value: unknown, fallback = "-") {
  return value === null || value === undefined || value === "" ? fallback : String(value);
}

function number(value: unknown) {
  const next = Number(value);
  return Number.isFinite(next) ? next : 0;
}

function array(value: unknown): UnknownRecord[] {
  return Array.isArray(value) ? value.map(asRecord) : [];
}

function textArray(value: unknown): string[] {
  return Array.isArray(value) ? value.map((item) => text(item, "")).filter(Boolean) : [];
}

function optionalNumber(value: string) {
  const trimmed = value.trim();
  if (!trimmed) return undefined;
  const next = Number(trimmed);
  return Number.isFinite(next) ? next : undefined;
}

function formatOptionalNumber(value: unknown) {
  if (value === null || value === undefined || value === "") return "-";
  return formatNumber(number(value));
}

function formatPercent(value: unknown) {
  const next = number(value);
  if (!next) return "-";
  const normalized = next > 1 ? next : next * 100;
  return `${normalized.toFixed(normalized >= 10 ? 0 : 1)}%`;
}

function sleepMs(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function loadPersistedCompetitorFetchTasks(): PersistedCompetitorFetchTask[] {
  try {
    const raw = window.localStorage.getItem(COMPETITOR_FETCH_TASKS_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed
      .map((item) => asRecord(item))
      .map((item) => ({
        competitorId: number(item.competitorId),
        taskId: text(item.taskId, ""),
        name: text(item.name, ""),
        daysBack: number(item.daysBack) || undefined,
      }))
      .filter((item) => item.competitorId > 0 && item.taskId);
  } catch {
    return [];
  }
}

function persistCompetitorFetchTask(task: PersistedCompetitorFetchTask) {
  const tasks = loadPersistedCompetitorFetchTasks().filter((item) => item.competitorId !== task.competitorId);
  tasks.push(task);
  window.localStorage.setItem(COMPETITOR_FETCH_TASKS_KEY, JSON.stringify(tasks));
}

function removePersistedCompetitorFetchTask(competitorId: number) {
  const tasks = loadPersistedCompetitorFetchTasks().filter((item) => item.competitorId !== competitorId);
  window.localStorage.setItem(COMPETITOR_FETCH_TASKS_KEY, JSON.stringify(tasks));
}

function countBy(items: UnknownRecord[], getKey: (item: UnknownRecord) => string) {
  const counts = new Map<string, number>();
  items.forEach((item) => {
    const key = getKey(item) || "unknown";
    counts.set(key, (counts.get(key) || 0) + 1);
  });
  return [...counts.entries()].map(([name, value]) => ({ name, value }));
}

function PageHero({ icon, title, description }: { icon: React.ReactNode; title: string; description: string }) {
  return (
    <div className="module-hero">
      <div className="module-hero-icon">{icon}</div>
      <div>
        <span>Research Console</span>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
    </div>
  );
}

function MetricCard({ label, value, note, icon }: { label: string; value: React.ReactNode; note?: string; icon?: React.ReactNode }) {
  return (
    <Card className="metric-card">
      <div className="metric-icon">{icon}</div>
      <div>
        <span>{label}</span>
        <strong>{value}</strong>
        {note && <small>{note}</small>}
      </div>
    </Card>
  );
}

const COLORS = ["#04786f", "#2563eb", "#ff9f1c", "#ef4444", "#101820", "#94a3b8"];
const STATUS_COLORS: Record<string, string> = {
  pending: "#ff9f1c",
  running: "#04786f",
  completed: "#2563eb",
  failed: "#ef4444",
  error: "#ef4444",
  unknown: "#94a3b8",
};
const STATUS_LABELS: Record<string, string> = {
  pending: "等待执行",
  running: "运行中",
  completed: "已完成",
  failed: "失败",
  error: "错误",
  unknown: "未知",
};

function countJobStatus(jobs: ResearchJob[]) {
  const counts = new Map<string, number>();
  jobs.forEach((job) => {
    const key = job.status || "unknown";
    counts.set(key, (counts.get(key) || 0) + 1);
  });
  return [...counts.entries()].map(([name, value]) => ({ name, value }));
}

function MiniBarChart({
  data,
  formatter,
  height = 178,
}: {
  data: Array<{ name: string; value: number }>;
  formatter?: (value: string) => string;
  height?: number;
}) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data}>
        <CartesianGrid strokeDasharray="3 3" vertical={false} />
        <XAxis dataKey="name" tickFormatter={formatter} />
        <YAxis allowDecimals={false} />
        <Tooltip />
        <Bar dataKey="value" fill="#04786f" radius={[6, 6, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}

function MiniPieChart({ data, height = 178 }: { data: Array<{ name: string; value: number }>; height?: number }) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <PieChart>
        <Pie data={data} dataKey="value" nameKey="name" outerRadius={76}>
          {data.map((row, index) => (
            <Cell key={row.name} fill={STATUS_COLORS[row.name] || COLORS[index % COLORS.length]} />
          ))}
        </Pie>
        <Tooltip />
      </PieChart>
    </ResponsiveContainer>
  );
}

function ChartLegend({
  rows,
  colorFor,
  labelFor,
}: {
  rows: Array<{ name: string; value: number }>;
  colorFor?: (name: string, index: number) => string;
  labelFor?: (name: string) => string;
}) {
  return (
    <div className="chart-legend">
      {rows.map((row, index) => (
        <span key={row.name}>
          <i style={{ background: colorFor?.(row.name, index) || COLORS[index % COLORS.length] }} />
          {labelFor?.(row.name) || row.name}: {formatNumber(row.value)}
        </span>
      ))}
    </div>
  );
}

function buildOverviewRiskNotes({
  dashboard,
  databaseStats,
  aiCount,
  jobs,
}: {
  dashboard: DashboardSummary;
  databaseStats: DatabaseStats;
  aiCount: number;
  jobs: ResearchJob[];
}) {
  const notes = [...(dashboard.decision.risk_notes || [])];
  if (!databaseStats.research_posts) {
    notes.push("缺少帖子样本，无法判断内容供给和关键词热度。");
  }
  if (!databaseStats.research_comments) {
    notes.push("评论样本为 0，互动质量和用户反馈维度暂时缺失。");
  }
  if (Object.keys(databaseStats.by_platform?.posts || {}).length <= 1 && databaseStats.research_posts > 0) {
    notes.push("样本集中在单一平台，跨平台验证不足。");
  }
  if (!aiCount) {
    notes.push("暂无 AI 洞察产出，报告和选题建议需要先确认成本后生成。");
  }
  if (jobs.some((job) => ["failed", "error"].includes(job.status))) {
    notes.push("存在失败采集任务，需要先查看日志再扩大监控范围。");
  }
  return notes.length ? notes : ["暂无风险备注，建议继续观察样本覆盖和更新时间。"];
}

export function OverviewPage({
  dashboard,
  databaseStats,
  aiInsights,
  aiTopicIdeas,
  jobs,
}: {
  dashboard: DashboardSummary;
  databaseStats: DatabaseStats;
  aiInsights: AiInsightSummary;
  aiTopicIdeas: AiTopicIdeasSummary;
  jobs: ResearchJob[];
  onRefresh: () => Promise<void>;
}) {
  const jobStatus = countJobStatus(jobs);
  const platformSignals = Object.entries(databaseStats.by_platform?.posts || {}).map(([name, value]) => ({ name, value }));
  const opportunityRows = (dashboard.top_opportunities || dashboard.opportunities || []).slice(0, 5);
  const aiCount = (aiInsights.hotspots?.length || 0) + (aiInsights.topic_ideas?.length || 0) + (aiTopicIdeas.topic_ideas?.length || 0);
  const riskNotes = buildOverviewRiskNotes({ dashboard, databaseStats, aiCount, jobs });

  return (
    <section className="module-page overview-page">
      <PageHero icon={<Gauge size={30} />} title="总览" description="老板/运营视角先看今天是否有机会、数据是否足够、任务是否健康。" />
      <div className="module-metric-grid">
        <MetricCard label="今日结论" value={dashboard.decision.confidence === "high" ? "高可信" : dashboard.decision.confidence === "medium" ? "待验证" : "缺样本"} note={dashboard.decision.sample_summary} icon={<CheckCircle2 size={18} />} />
        <MetricCard label="任务状态" value={`${dashboard.monitoring.running_jobs || 0}/${jobs.length}`} note={`运行中 / 全部；待执行 ${dashboard.monitoring.pending_jobs || jobStatus.find((row) => row.name === "pending")?.value || 0}`} icon={<Play size={18} />} />
        <MetricCard label="样本量" value={formatNumber(databaseStats.research_posts + databaseStats.research_comments)} note={`帖子 ${databaseStats.research_posts} / 评论 ${databaseStats.research_comments} / raw ${databaseStats.raw_records}`} icon={<Database size={18} />} />
        <MetricCard label="AI 产出" value={formatNumber(aiCount)} note={aiInsights.run ? `洞察运行 ${aiInsights.run.status}` : "暂无 AI 洞察运行"} icon={<Bot size={18} />} />
      </div>
      <div className="overview-main-grid">
        <Card className="overview-opportunity-card">
          <CardHeader>
            <div>
              <CardTitle>今日机会摘要</CardTitle>
              <CardDescription>{dashboard.decision.headline}</CardDescription>
            </div>
          </CardHeader>
          {opportunityRows.length ? (
            <div className="module-list">
              {opportunityRows.map((item) => (
                <div className="module-row static" key={item.id}>
                  <div>
                    <strong>{item.target_url ? <a href={item.target_url} target="_blank" rel="noreferrer">{item.display_title || item.name}</a> : item.display_title || item.name}</strong>
                    <em>{item.display_subtitle || `${labelPlatform(item.platform)} · ${item.type}`}</em>
                    <span>{item.reason || item.evidence_summary?.[0] || "等待更多证据解释"}</span>
                  </div>
                  <Badge tone={item.score >= 75 ? "success" : "warning"}>{Math.round(item.score)}</Badge>
                </div>
              ))}
            </div>
          ) : (
            <EmptyState title="暂无机会结论" body="先运行采集任务，或切到增长机会决策查看诊断项。" />
          )}
        </Card>
        <div className="overview-chart-column">
          <Card className="overview-chart-card">
            <CardHeader>
              <div>
                <CardTitle>任务状态分布</CardTitle>
                <CardDescription>判断采集链路是否卡在 pending/running/failed。</CardDescription>
              </div>
            </CardHeader>
            {jobStatus.length ? (
              <>
                <MiniPieChart data={jobStatus} />
                <ChartLegend rows={jobStatus} colorFor={(name, index) => STATUS_COLORS[name] || COLORS[index % COLORS.length]} labelFor={(name) => STATUS_LABELS[name] || name} />
              </>
            ) : <div className="chart-empty">暂无任务状态</div>}
          </Card>
          <Card className="overview-chart-card">
            <CardHeader>
              <div>
                <CardTitle>平台样本分布</CardTitle>
                <CardDescription>来自全库统计，检查是否存在平台单一风险。</CardDescription>
              </div>
            </CardHeader>
            {platformSignals.length ? (
              <>
                <MiniBarChart data={platformSignals} formatter={labelPlatform} />
                <ChartLegend rows={platformSignals} labelFor={labelPlatform} />
              </>
            ) : <div className="chart-empty">暂无平台样本</div>}
          </Card>
        </div>
      </div>
      <Card className="overview-risk-card">
        <CardHeader>
          <div>
            <CardTitle>风险提醒</CardTitle>
            <CardDescription>只展示可审计的风险，不假装有结论。</CardDescription>
          </div>
        </CardHeader>
        <div className="module-note-list">
          {riskNotes.map((note) => <p key={note}>{note}</p>)}
        </div>
      </Card>
    </section>
  );
}

export function TaskWorkbenchPage({
  jobs,
  selectedJobId,
  setSelectedJobId,
  posts,
  comments,
  rawRecords,
  aiResults,
  onOpenData,
  onOpenAi,
}: {
  jobs: ResearchJob[];
  selectedJobId: number | null;
  setSelectedJobId: (id: number) => void;
  posts: PostRecord[];
  comments: CommentRecord[];
  rawRecords: RawRecord[];
  aiResults: AIResult[];
  onOpenData: () => void;
  onOpenAi: () => void;
}) {
  return (
    <section className="module-page">
      <PageHero icon={<Activity size={30} />} title="任务工作台" description="管理采集、补抓和分析任务。" />
      <div className="module-metric-grid">
        <MetricCard label="任务" value={jobs.length} icon={<Activity size={18} />} />
        <MetricCard label="帖子" value={posts.length} icon={<FileJson size={18} />} />
        <MetricCard label="评论" value={comments.length} icon={<FileJson size={18} />} />
        <MetricCard label="AI" value={aiResults.length} icon={<Bot size={18} />} />
      </div>
      <Card>
        <CardHeader>
          <div>
            <CardTitle>任务列表</CardTitle>
            <CardDescription>选择任务后可查看数据或进入 AI 分析。</CardDescription>
          </div>
          <div className="result-actions">
            <Button variant="ghost" onClick={onOpenData}><Database size={16} />查看数据</Button>
            <Button variant="ghost" onClick={onOpenAi}><Bot size={16} />AI 分析</Button>
          </div>
        </CardHeader>
        <RecordList rows={jobs as unknown as UnknownRecord[]} titleKeys={["id", "name"]} metaKeys={["status", "platform", "type"]} onSelect={(row) => setSelectedJobId(number(row.id))} selectedId={selectedJobId} />
      </Card>
    </section>
  );
}

export function CreatorDiscoveryPage() {
  const candidates = useEndpoint<{ candidates: UnknownRecord[] }>("/api/creator-search/candidate-pool?include_profile_candidates=true", { candidates: [] });
  const pools = useEndpoint<{ pools: UnknownRecord[] }>("/api/creator-search/monitor-pools", { pools: [] });
  const [query, setQuery] = React.useState("K12教育 + 单亲妈妈");
  const [platforms, setPlatforms] = React.useState<string[]>(["xhs", "dy"]);
  const [followerMin, setFollowerMin] = React.useState("");
  const [activityMin, setActivityMin] = React.useState("1");
  const [limit, setLimit] = React.useState("50");
  const [searchResult, setSearchResult] = React.useState<CreatorSearchResponse | null>(null);
  const [searching, setSearching] = React.useState(false);
  const [includeRealtime, setIncludeRealtime] = React.useState(false);
  const [searchProgress, setSearchProgress] = React.useState<CreatorSearchProgress | null>(null);
  const [resultsUpdating, setResultsUpdating] = React.useState(false);
  const [activeTaskId, setActiveTaskId] = React.useState<string | null>(null);
  const [searchError, setSearchError] = React.useState<string | null>(null);
  const [selectedCreators, setSelectedCreators] = React.useState<Set<string>>(new Set());
  const [message, setMessage] = React.useState<string | null>(null);

  const rows = candidates.data.candidates || [];
  const resultRows = searchResult?.results || [];
  const activeRows = resultRows.length ? resultRows : rows;
  const platformRows = countBy(activeRows, (item) => text(item.platform, "unknown"));
  const selectedRows = resultRows.filter((item) => selectedCreators.has(creatorRowKey(item)));

  React.useEffect(() => {
    const savedTaskId = window.localStorage.getItem(CREATOR_SEARCH_TASK_KEY);
    if (savedTaskId) {
      setActiveTaskId(savedTaskId);
      setSearching(true);
      setResultsUpdating(Boolean(searchResult));
      setSearchProgress(creatorSearchStage("database"));
    }
  }, []);

  React.useEffect(() => {
    if (!activeTaskId) return;
    let stopped = false;
    async function pollTask() {
      while (!stopped) {
        try {
          const task = await api<CreatorSearchTask>(`/api/creator-search/search-tasks/${activeTaskId}`);
          if (stopped) return;
          applyCreatorSearchTask(task);
          if (["completed", "failed", "cancelled"].includes(task.status)) return;
          await sleepMs(1000);
        } catch (err) {
          if (!stopped) {
            setSearchError(err instanceof Error ? err.message : String(err));
            setSearching(false);
            setResultsUpdating(false);
          }
          return;
        }
      }
    }
    void pollTask();
    return () => {
      stopped = true;
    };
  }, [activeTaskId]);

  function applyCreatorSearchTask(task: CreatorSearchTask) {
    if (task.request && "include_realtime" in task.request) {
      setIncludeRealtime(Boolean(task.request.include_realtime));
    }
    if (task.progress) setSearchProgress(task.progress);
    if (task.status === "completed" && task.result) {
      setSearchResult(task.result);
      setSearching(false);
      setResultsUpdating(false);
      setActiveTaskId(null);
      window.localStorage.removeItem(CREATOR_SEARCH_TASK_KEY);
      void candidates.reload();
      return;
    }
    if (task.status === "failed") {
      setSearchError(task.error || "筛选任务失败");
      setSearching(false);
      setResultsUpdating(false);
      setActiveTaskId(null);
      window.localStorage.removeItem(CREATOR_SEARCH_TASK_KEY);
      return;
    }
    if (task.status === "cancelled") {
      setMessage("筛选任务已取消");
      setSearching(false);
      setResultsUpdating(false);
      setActiveTaskId(null);
      window.localStorage.removeItem(CREATOR_SEARCH_TASK_KEY);
      return;
    }
    setSearching(true);
  }

  async function runCreatorSearch(event?: React.FormEvent) {
    event?.preventDefault();
    setSearching(true);
    setResultsUpdating(Boolean(searchResult));
    setSearchProgress(includeRealtime ? creatorSearchStage("database") : null);
    setSearchError(null);
    setMessage(null);
    setSelectedCreators(new Set());
    try {
      const task = await api<CreatorSearchTask>("/api/creator-search/search-tasks", {
        method: "POST",
        body: JSON.stringify({
          raw_query: query.trim(),
          platforms,
          follower_min: optionalNumber(followerMin),
          recent_activity_min: optionalNumber(activityMin),
          limit: optionalNumber(limit) || 50,
          include_realtime: includeRealtime,
        }),
      });
      window.localStorage.setItem(CREATOR_SEARCH_TASK_KEY, task.task_id);
      setActiveTaskId(task.task_id);
      applyCreatorSearchTask(task);
    } catch (err) {
      setSearchError(err instanceof Error ? err.message : String(err));
      setSearching(false);
      setResultsUpdating(false);
    }
  }

  async function saveSelectedToCandidatePool() {
    for (const item of selectedRows) {
      await api<UnknownRecord>("/api/creator-search/candidate-pool", {
        method: "POST",
        body: JSON.stringify({
          platform: text(item.platform, ""),
          creator_id: text(item.creator_id, ""),
          pool_name: "keyword-search",
          match_score: number(item.match_score),
          matched_tags: array(item.matched_tags),
          evidence: {
            raw_query: query,
            evidence: item.evidence || [],
            representative_posts: item.representative_posts || [],
          },
          notes: "前端关键词筛选加入候选池",
        }),
      });
    }
    setMessage(`已加入候选池：${selectedRows.length} 位达人`);
    setSelectedCreators(new Set());
    await candidates.reload();
  }

  async function enrichSelectedMetrics() {
    const result = await api<UnknownRecord>("/api/creator-search/profile-metrics/enrich", {
      method: "POST",
      body: JSON.stringify({ creators: selectedRows }),
    });
    setMessage(`主页指标补全完成：成功 ${text(result.enriched_count, "0")}，失败 ${text(result.failed_count, "0")}`);
    await runCreatorSearch();
    await candidates.reload();
  }

  return (
    <section className="module-page creators-page">
      <PageHero icon={<Users size={30} />} title="达人发现" description="按关键词、标签、互动和内容表现筛选可跟进达人，并审计候选池来源。" />
      <div className="module-metric-grid">
        <MetricCard label="筛选结果" value={formatNumber(resultRows.length)} note={searchResult ? "当前关键词命中" : "等待筛选"} icon={<Filter size={18} />} />
        <MetricCard label="候选达人" value={formatNumber(rows.length)} note="candidate-pool + 本地画像" icon={<Users size={18} />} />
        <MetricCard label="监控池" value={formatNumber((pools.data.pools || []).length)} note="长期跟进分组" icon={<MonitorCheck size={18} />} />
        <MetricCard label="覆盖平台" value={formatNumber(platformRows.length)} note="当前列表平台数" icon={<BarChart3 size={18} />} />
      </div>

      <Card className="creator-search-card">
        <CardHeader>
          <div>
            <CardTitle>关键词筛选</CardTitle>
            <CardDescription>例如输入“K12教育 + 单亲妈妈”，从本地达人画像和内容样本中筛出达人。</CardDescription>
          </div>
        </CardHeader>
        <form className="creator-search-form" onSubmit={runCreatorSearch}>
          <label className="wide">
            <span>关键词组合</span>
            <input value={query} onChange={(event) => setQuery(event.target.value)} />
          </label>
          <fieldset>
            <legend>平台</legend>
            <div className="checks-grid">
              {["xhs", "dy"].map((platform) => (
                <label className="check" key={platform}>
                  <input type="checkbox" checked={platforms.includes(platform)} onChange={(event) => setPlatforms(toggleValue(platforms, platform, event.target.checked))} />
                  {labelPlatform(platform)}
                </label>
              ))}
            </div>
          </fieldset>
          <label>
            <span>最低粉丝数</span>
            <input value={followerMin} onChange={(event) => setFollowerMin(event.target.value)} inputMode="numeric" placeholder="不限" />
          </label>
          <label>
            <span>近 30 天发文数</span>
            <input value={activityMin} onChange={(event) => setActivityMin(event.target.value)} inputMode="numeric" />
          </label>
          <label>
            <span>返回数量</span>
            <input value={limit} onChange={(event) => setLimit(event.target.value)} inputMode="numeric" />
          </label>
          <label className="creator-realtime-toggle">
            <input
              type="checkbox"
              checked={includeRealtime}
              onChange={(event) => setIncludeRealtime(event.target.checked)}
              disabled={searching}
            />
            <span>实时搜索小红书/抖音</span>
          </label>
          <div className="creator-search-actions">
            <Button variant="primary" disabled={searching || !query.trim() || !platforms.length}>{searching ? <Loader2 size={16} className="spin" /> : <Search size={16} />}筛选达人</Button>
            <Button type="button" variant="ghost" onClick={() => void runCreatorSearch()} disabled={searching || !query.trim()}><RefreshCw size={16} />刷新结果</Button>
          </div>
          {(searching || searchProgress) && (
            <div className="creator-search-progress">
              <div>
                <span>{searchProgress?.label || "Preparing realtime search"}</span>
                <strong>{formatNumber(searchProgress?.percent || 0)}%</strong>
              </div>
              <div className="creator-search-progress-track">
                <i style={{ width: `${Math.min(100, Math.max(4, searchProgress?.percent || 4))}%` }} />
              </div>
            </div>
          )}
        </form>
        {searchResult?.realtime && ["failed", "partial"].includes(text(searchResult.realtime.status, "")) && (
          <div className="creator-realtime-warning">
            <AlertTriangle size={16} />
            <span>{text(searchResult.realtime.error, "实时搜索部分失败，已展示可用的数据库结果。")}</span>
          </div>
        )}
        {searchError && <p className="inline-alert danger">{searchError}</p>}
        {message && <p className="inline-alert">{message}</p>}
      </Card>

      {searchResult && (
        <Card>
          <CardHeader>
            <div>
              <CardTitle>筛选结果</CardTitle>
              <CardDescription>优先按匹配分排序，证据来自标签或文本命中。</CardDescription>
            </div>
            <div className="result-actions">
              <Badge tone="muted">已选 {selectedRows.length}</Badge>
              <Button size="sm" variant="primary" onClick={saveSelectedToCandidatePool} disabled={!selectedRows.length}><Plus size={15} />加入候选池</Button>
              <Button size="sm" variant="ghost" onClick={enrichSelectedMetrics} disabled={!selectedRows.length}><RefreshCw size={15} />补全主页指标</Button>
            </div>
          </CardHeader>
          {resultRows.length ? <CreatorResultList rows={resultRows} selected={selectedCreators} updating={resultsUpdating} onToggle={(row, checked) => setSelectedCreators(toggleSelected(selectedCreators, creatorRowKey(row), checked))} /> : <EmptyState title="没有匹配达人" body="降低筛选条件，或先补充采集样本。" />}
        </Card>
      )}

      <div className="module-grid two">
        <Card>
          <CardHeader>
            <div>
              <CardTitle>候选达人池</CardTitle>
              <CardDescription>展开后优先展示业务可读信息，调试 JSON 默认隐藏。</CardDescription>
            </div>
          </CardHeader>
          {rows.length ? <RecordList rows={rows} titleKeys={["display_name", "nickname", "creator_id"]} titleLinkKey="profile_url" metaKeys={["platform", "pool_name", "source"]} /> : <EmptyState title="暂无候选达人" body="先执行关键词筛选并加入候选池。" />}
        </Card>
        <Card>
          <CardHeader>
            <div>
              <CardTitle>平台分布</CardTitle>
              <CardDescription>判断候选达人是否过度集中在单个平台。</CardDescription>
            </div>
          </CardHeader>
          <SimpleBars rows={platformRows} formatter={labelPlatform} />
        </Card>
      </div>
    </section>
  );
}

function CreatorResultList({ rows, selected, updating, onToggle }: { rows: UnknownRecord[]; selected: Set<string>; updating?: boolean; onToggle: (row: UnknownRecord, checked: boolean) => void }) {
  return (
    <div className={`creator-result-list ${updating ? "is-updating" : ""}`}>
      {rows.map((row) => {
        const key = creatorRowKey(row);
        const tags = array(row.matched_tags).slice(0, 4);
        const evidence = array(row.representative_posts).length ? array(row.representative_posts).slice(0, 2) : array(row.evidence).slice(0, 2);
        return (
          <article className="creator-result-row" key={key}>
            <label className="check"><input type="checkbox" checked={selected.has(key)} onChange={(event) => onToggle(row, event.target.checked)} /></label>
            <div className="creator-result-main">
              <div className="creator-result-title">
                <strong>{row.profile_url ? <a href={text(row.profile_url, "")} target="_blank" rel="noreferrer">{text(row.display_name || row.creator_id)}</a> : text(row.display_name || row.creator_id)}</strong>
                <Badge tone="muted">{labelPlatform(text(row.platform))}</Badge>
              </div>
              <div className="creator-source-badges">
                {creatorSourceLabels(row).map((label) => (
                  <Badge key={label} tone={label === "Realtime" ? "warning" : "success"}>{label === "Database" ? "数据库" : "实时"}</Badge>
                ))}
              </div>
              <div className="creator-result-meta">
                <span>粉丝 {formatOptionalNumber(candidateMetric(row, "follower_count"))}</span>
                <span>{text(row.platform) === "dy" ? "获赞" : "总赞"} {formatOptionalNumber(candidateMetric(row, "total_like_count") || candidateMetric(row, "interaction_count"))}</span>
                <span>收藏 {formatOptionalNumber(candidateMetric(row, "total_collect_count"))}</span>
                <span>近 30 天 {formatOptionalNumber(row.recent_post_count_30d)} 篇</span>
                <span>互动率 {formatPercent(row.avg_engagement_rate)}</span>
              </div>
              <div className="chips">{tags.length ? tags.map((tag, index) => <span key={index}>{candidateTagLabel(tag)}</span>) : <span>文本命中</span>}</div>
              <div className="creator-evidence">{evidence.map((item, index) => <p key={index}>{candidateEvidenceText(item)}</p>)}</div>
            </div>
            <div className="creator-score"><strong>{Math.round(number(row.match_score))}</strong><span>匹配分</span></div>
          </article>
        );
      })}
    </div>
  );
}

function creatorRowKey(row: UnknownRecord) {
  return `${text(row.platform, "unknown")}:${text(row.creator_id || row.account_id, "unknown")}`;
}

function creatorSearchStage(stage: string): CreatorSearchProgress {
  const stages: Record<string, CreatorSearchProgress> = {
    database: { stage: "database", label: "Searching database", percent: 20 },
    realtime: { stage: "realtime", label: "Searching realtime platforms", percent: 50 },
    persistence: { stage: "persistence", label: "Saving creator profiles", percent: 75 },
    merging: { stage: "merging", label: "Merging results", percent: 90 },
    complete: { stage: "complete", label: "Complete", percent: 100 },
  };
  return stages[stage] || stages.database;
}

function creatorSourceLabels(row: UnknownRecord) {
  const labels = textArray(row.source_labels);
  if (labels.length) return labels;
  const source = text(row.source_type, "local");
  if (source === "realtime") return ["Realtime"];
  if (source === "mixed") return ["Database", "Realtime"];
  return ["Database"];
}

function toggleSelected(current: Set<string>, key: string, checked: boolean) {
  const next = new Set(current);
  if (checked) next.add(key);
  else next.delete(key);
  return next;
}

function toggleValue(values: string[], value: string, checked: boolean) {
  if (checked) return values.includes(value) ? values : [...values, value];
  return values.filter((item) => item !== value);
}

export function KeywordLibraryPage() {
  const keywords = useEndpoint<{ keywords: UnknownRecord[] }>("/api/keyword-library/keywords", { keywords: [] });
  const packs = useEndpoint<{ scene_packs: UnknownRecord[] }>("/api/keyword-library/scene-packs", { scene_packs: [] });
  const providers = useEndpoint<{ providers: UnknownRecord[] }>("/api/research/ai/providers", { providers: [] });
  const scenePacks = packs.data.scene_packs || [];
  const keywordRows = keywords.data.keywords || [];
  const packNameById = new Map(scenePacks.map((pack) => [number(pack.id), text(pack.name, `场景包 ${text(pack.id)}`)]));
  const loading = packs.loading || keywords.loading;
  const error = packs.error || keywords.error;
  const [formMode, setFormMode] = React.useState<"scene_pack" | "keyword">("keyword");
  const [editingScenePackId, setEditingScenePackId] = React.useState<number | null>(null);
  const [editingKeywordId, setEditingKeywordId] = React.useState<number | null>(null);
  const [scenePackForm, setScenePackForm] = React.useState(() => emptyScenePackForm());
  const [keywordForm, setKeywordForm] = React.useState(() => emptyKeywordForm());
  const [saving, setSaving] = React.useState<string | null>(null);
  const [message, setMessage] = React.useState<string | null>(null);
  const [aiProviderId, setAiProviderId] = React.useState("");
  const [aiSuggestions, setAiSuggestions] = React.useState<UnknownRecord[]>([]);
  const [selectedAiSuggestions, setSelectedAiSuggestions] = React.useState<Set<string>>(new Set());
  const [aiLoading, setAiLoading] = React.useState(false);
  const nextVerticalId = React.useMemo(
    () => Math.max(0, ...scenePacks.map((pack) => number(pack.vertical_id))) + 1,
    [scenePacks],
  );

  React.useEffect(() => {
    if (!keywordForm.scene_pack_id && scenePacks[0]?.id) {
      setKeywordForm((current) => ({ ...current, scene_pack_id: String(scenePacks[0].id) }));
    }
  }, [keywordForm.scene_pack_id, scenePacks]);

  React.useEffect(() => {
    const enabledProvider = (providers.data.providers || []).find((provider) => provider.enabled && provider.api_key_set);
    if (!aiProviderId && enabledProvider?.id) setAiProviderId(String(enabledProvider.id));
  }, [aiProviderId, providers.data.providers]);

  const reloadKeywordLibrary = async () => {
    await Promise.all([packs.reload(), keywords.reload()]);
  };

  const startNewScenePack = () => {
    setFormMode("scene_pack");
    setEditingScenePackId(null);
    setScenePackForm(emptyScenePackForm(nextVerticalId));
    setAiSuggestions([]);
    setSelectedAiSuggestions(new Set());
    setMessage(null);
  };

  const startEditScenePack = (row: UnknownRecord) => {
    setFormMode("scene_pack");
    setEditingScenePackId(number(row.id));
    setScenePackForm({
      vertical_id: text(row.vertical_id, "1"),
      name: text(row.name, ""),
      description: text(row.description, ""),
      weight: text(row.weight, "1"),
      default_platforms: joinTextList(row.default_platforms),
      enabled: row.enabled !== false,
    });
    setAiSuggestions([]);
    setSelectedAiSuggestions(new Set());
    setMessage(null);
  };

  const startNewKeyword = () => {
    setFormMode("keyword");
    setEditingKeywordId(null);
    setKeywordForm(emptyKeywordForm(scenePacks[0]?.id));
    setMessage(null);
  };

  const startEditKeyword = (row: UnknownRecord) => {
    setFormMode("keyword");
    setEditingKeywordId(number(row.id));
    setKeywordForm({
      scene_pack_id: text(row.scene_pack_id, scenePacks[0]?.id ? String(scenePacks[0].id) : ""),
      keyword: text(row.keyword, ""),
      keyword_type: text(row.keyword_type, "secondary"),
      platform: text(row.platform, ""),
      weight: text(row.weight, "1"),
      reason: text(row.reason, ""),
      usage_flags: joinTextList(row.usage_flags),
      enabled: row.enabled !== false,
    });
    setMessage(null);
  };

  const saveScenePack = async (event: React.FormEvent) => {
    event.preventDefault();
    const payload = {
      vertical_id: editingScenePackId ? number(scenePackForm.vertical_id) || 1 : nextVerticalId,
      name: scenePackForm.name.trim(),
      description: scenePackForm.description.trim() || null,
      weight: number(scenePackForm.weight) || 1,
      default_platforms: splitList(scenePackForm.default_platforms),
      enabled: scenePackForm.enabled,
    };
    if (!payload.name) {
      setMessage("请填写场景包名称");
      return;
    }
    setSaving("scene_pack");
    try {
      await api<UnknownRecord>(
        editingScenePackId ? `/api/keyword-library/scene-packs/${editingScenePackId}` : "/api/keyword-library/scene-packs",
        {
          method: editingScenePackId ? "PATCH" : "POST",
          body: JSON.stringify(payload),
        },
      );
      setMessage(editingScenePackId ? "场景包已更新" : "场景包已新增");
      setEditingScenePackId(null);
      setScenePackForm(emptyScenePackForm(Math.max(nextVerticalId, payload.vertical_id + 1)));
      await reloadKeywordLibrary();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : String(err));
    } finally {
      setSaving(null);
    }
  };

  const saveKeyword = async (event: React.FormEvent) => {
    event.preventDefault();
    const payload = {
      scene_pack_id: number(keywordForm.scene_pack_id),
      keyword: keywordForm.keyword.trim(),
      keyword_type: keywordForm.keyword_type,
      platform: keywordForm.platform || null,
      weight: number(keywordForm.weight) || 1,
      reason: keywordForm.reason.trim() || null,
      usage_flags: splitList(keywordForm.usage_flags),
      platform_overrides: {},
      enabled: keywordForm.enabled,
    };
    if (!payload.scene_pack_id || !payload.keyword) {
      setMessage("请先选择场景包并填写关键词");
      return;
    }
    setSaving("keyword");
    try {
      await api<UnknownRecord>(
        editingKeywordId ? `/api/keyword-library/keywords/${editingKeywordId}` : "/api/keyword-library/keywords",
        {
          method: editingKeywordId ? "PATCH" : "POST",
          body: JSON.stringify(payload),
        },
      );
      setMessage(editingKeywordId ? "关键词已更新" : "关键词已新增");
      setEditingKeywordId(null);
      setKeywordForm(emptyKeywordForm(scenePacks[0]?.id));
      await reloadKeywordLibrary();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : String(err));
    } finally {
      setSaving(null);
    }
  };

  const toggleScenePack = async (row: UnknownRecord) => {
    const id = number(row.id);
    setSaving(`scene_pack-${id}`);
    try {
      await api<UnknownRecord>(`/api/keyword-library/scene-packs/${id}`, {
        method: "PATCH",
        body: JSON.stringify({ enabled: row.enabled === false }),
      });
      await reloadKeywordLibrary();
    } finally {
      setSaving(null);
    }
  };

  const toggleKeyword = async (row: UnknownRecord) => {
    const id = number(row.id);
    setSaving(`keyword-${id}`);
    try {
      await api<UnknownRecord>(`/api/keyword-library/keywords/${id}`, {
        method: "PATCH",
        body: JSON.stringify({ enabled: row.enabled === false }),
      });
      await reloadKeywordLibrary();
    } finally {
      setSaving(null);
    }
  };

  const deleteScenePack = async (row: UnknownRecord) => {
    const id = number(row.id);
    if (!window.confirm(`删除场景包「${text(row.name)}」？只有没有关键词的场景包才能删除。`)) return;
    setSaving(`delete-scene_pack-${id}`);
    try {
      await api<UnknownRecord>(`/api/keyword-library/scene-packs/${id}`, { method: "DELETE" });
      setMessage("场景包已删除");
      await reloadKeywordLibrary();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : String(err));
    } finally {
      setSaving(null);
    }
  };

  const deleteKeyword = async (row: UnknownRecord) => {
    const id = number(row.id);
    if (!window.confirm(`删除关键词「${text(row.keyword)}」？删除后可以重新新增同名关键词。`)) return;
    setSaving(`delete-keyword-${id}`);
    try {
      await api<UnknownRecord>(`/api/keyword-library/keywords/${id}`, { method: "DELETE" });
      setMessage("关键词已删除");
      if (editingKeywordId === id) setEditingKeywordId(null);
      await reloadKeywordLibrary();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : String(err));
    } finally {
      setSaving(null);
    }
  };

  const generateAiKeywords = async () => {
    if (!aiProviderId) {
      setMessage("请先在 AI 分析/配置中添加并启用 AI Provider");
      return;
    }
    const existingKeywords = keywordRows
      .filter((row) => editingScenePackId && number(row.scene_pack_id) === editingScenePackId)
      .map((row) => text(row.keyword, ""))
      .filter(Boolean);
    const inputText = [
      `场景包：${scenePackForm.name}`,
      scenePackForm.description ? `描述：${scenePackForm.description}` : "",
      existingKeywords.length ? `已有关键词：${existingKeywords.join("、")}` : "",
    ].filter(Boolean).join("\n");
    if (!scenePackForm.name.trim() && !scenePackForm.description.trim()) {
      setMessage("请先填写场景包名称或描述，再生成关键词");
      return;
    }
    setAiLoading(true);
    setMessage(null);
    try {
      const result = await api<{ suggestions: UnknownRecord[] }>("/api/keyword-library/ai/expand", {
        method: "POST",
        body: JSON.stringify({
          input_text: inputText,
          vertical_id: number(scenePackForm.vertical_id) || undefined,
          scene_pack_id: editingScenePackId || undefined,
          target_platforms: splitList(scenePackForm.default_platforms),
          provider_config_id: number(aiProviderId),
        }),
      });
      setAiSuggestions(result.suggestions || []);
      setSelectedAiSuggestions(new Set((result.suggestions || []).map((item) => aiSuggestionKey(item))));
      setMessage(`AI 已生成 ${result.suggestions?.length || 0} 个候选关键词`);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : String(err));
    } finally {
      setAiLoading(false);
    }
  };

  const addSelectedAiKeywords = async () => {
    const scenePackId = editingScenePackId || number(keywordForm.scene_pack_id);
    const selected = aiSuggestions.filter((item) => selectedAiSuggestions.has(aiSuggestionKey(item)));
    if (!scenePackId) {
      setMessage("请先保存或选择一个场景包，再加入 AI 候选关键词");
      return;
    }
    if (!selected.length) {
      setMessage("请先勾选要加入的候选关键词");
      return;
    }
    setSaving("ai-keywords");
    try {
      for (const item of selected) {
        await api<UnknownRecord>("/api/keyword-library/keywords", {
          method: "POST",
          body: JSON.stringify({
            scene_pack_id: scenePackId,
            keyword: text(item.keyword, ""),
            keyword_type: text(item.keyword_type, "secondary"),
            platform: item.platform || null,
            weight: number(item.weight) || 1,
            reason: text(item.reason, "AI 扩词建议"),
            usage_flags: textArray(item.usage_flags).length ? textArray(item.usage_flags) : ["creator_discovery", "content_tracking", "keyword_heat"],
            platform_overrides: {},
            enabled: true,
          }),
        });
      }
      setMessage(`已加入 ${selected.length} 个 AI 候选关键词`);
      setAiSuggestions([]);
      setSelectedAiSuggestions(new Set());
      await reloadKeywordLibrary();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : String(err));
    } finally {
      setSaving(null);
    }
  };

  return (
    <section className="module-page keyword-library-page">
      <PageHero icon={<KeyRound size={30} />} title="关键词库" description="维护关键词组、场景包、同义词和排除词。" />
      <div className="module-metric-grid">
        <MetricCard label="场景包" value={loading ? "..." : scenePacks.length} note={error || "业务分组"} icon={<Database size={18} />} />
        <MetricCard label="关键词" value={loading ? "..." : keywordRows.length} note="可用于采集、达人发现和热度监控" icon={<KeyRound size={18} />} />
      </div>
      <Card className="keyword-editor-card">
        <CardHeader>
          <div>
            <CardTitle>{formMode === "scene_pack" ? (editingScenePackId ? "编辑场景包" : "新增场景包") : (editingKeywordId ? "编辑关键词" : "新增关键词")}</CardTitle>
            <CardDescription>保存后自动刷新列表；停用记录可被同名新增复用，删除后可重新新增。</CardDescription>
          </div>
          <div className="result-actions">
            <Button type="button" variant={formMode === "scene_pack" ? "primary" : "ghost"} onClick={startNewScenePack}><Plus size={16} />新增场景包</Button>
            <Button type="button" variant={formMode === "keyword" ? "primary" : "ghost"} onClick={startNewKeyword}><Plus size={16} />新增关键词</Button>
          </div>
        </CardHeader>
        {formMode === "scene_pack" ? (
          <form className="keyword-maintenance-form scene-pack-form" onSubmit={saveScenePack}>
            <label className="wide">
              场景包名称
              <input value={scenePackForm.name} onChange={(event) => setScenePackForm((current) => ({ ...current, name: event.target.value }))} placeholder="例如：K12教育 / 单亲妈妈" />
            </label>
            <label className="wide">
              默认平台
              <input value={scenePackForm.default_platforms} onChange={(event) => setScenePackForm((current) => ({ ...current, default_platforms: event.target.value }))} placeholder="xhs、dy、wb" />
            </label>
            <label className="wide">
              描述
              <textarea rows={2} value={scenePackForm.description} onChange={(event) => setScenePackForm((current) => ({ ...current, description: event.target.value }))} />
            </label>
            <label className="check">
              <input type="checkbox" checked={scenePackForm.enabled} onChange={(event) => setScenePackForm((current) => ({ ...current, enabled: event.target.checked }))} />
              启用
            </label>
            <div className="result-actions form-actions">
              <Button type="submit" variant="primary" disabled={saving === "scene_pack"}>{saving === "scene_pack" ? <Loader2 size={16} className="spin" /> : <Plus size={16} />}保存场景包</Button>
              <Button type="button" variant="ghost" onClick={() => void generateAiKeywords()} disabled={aiLoading}>{aiLoading ? <Loader2 size={16} className="spin" /> : <Bot size={16} />}AI 生成关键词</Button>
              {editingScenePackId ? <Button type="button" variant="ghost" onClick={startNewScenePack}>取消编辑</Button> : null}
            </div>
            <div className="ai-keyword-tools">
              <label>
                AI Provider
                <select value={aiProviderId} onChange={(event) => setAiProviderId(event.target.value)}>
                  <option value="">请选择 AI Provider</option>
                  {(providers.data.providers || []).map((provider) => (
                    <option key={text(provider.id)} value={text(provider.id)} disabled={!provider.enabled || !provider.api_key_set}>
                      {text(provider.name)} / {text(provider.model)}{provider.enabled && provider.api_key_set ? "" : "（不可用）"}
                    </option>
                  ))}
                </select>
              </label>
              {providers.error ? <p>{providers.error}</p> : null}
              {aiSuggestions.length ? (
                <div className="ai-suggestion-list">
                  {aiSuggestions.map((item) => {
                    const key = aiSuggestionKey(item);
                    return (
                      <label className="check ai-suggestion-row" key={key}>
                        <input type="checkbox" checked={selectedAiSuggestions.has(key)} onChange={(event) => setSelectedAiSuggestions(toggleSet(selectedAiSuggestions, key, event.target.checked))} />
                        <strong>{text(item.keyword)}</strong>
                        <span>{KEYWORD_TYPE_LABELS[text(item.keyword_type, "")] || text(item.keyword_type, "扩展词")} / 权重 {text(item.weight, "1")} / {text(item.reason, "AI 建议")}</span>
                      </label>
                    );
                  })}
                  <Button type="button" variant="primary" onClick={() => void addSelectedAiKeywords()} disabled={saving === "ai-keywords"}>
                    {saving === "ai-keywords" ? <Loader2 size={16} className="spin" /> : <Plus size={16} />}加入选中关键词
                  </Button>
                </div>
              ) : null}
            </div>
          </form>
        ) : (
          <form className="keyword-maintenance-form" onSubmit={saveKeyword}>
            <label>
              所属场景包
              <select value={keywordForm.scene_pack_id} onChange={(event) => setKeywordForm((current) => ({ ...current, scene_pack_id: event.target.value }))}>
                <option value="">请选择</option>
                {scenePacks.map((pack) => <option key={text(pack.id)} value={text(pack.id)}>{text(pack.name)}</option>)}
              </select>
            </label>
            <label className="wide">
              关键词
              <input value={keywordForm.keyword} onChange={(event) => setKeywordForm((current) => ({ ...current, keyword: event.target.value }))} placeholder="例如：升学焦虑" />
            </label>
            <label>
              类型
              <select value={keywordForm.keyword_type} onChange={(event) => setKeywordForm((current) => ({ ...current, keyword_type: event.target.value }))}>
                {KEYWORD_TYPE_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
              </select>
            </label>
            <label>
              平台
              <select value={keywordForm.platform} onChange={(event) => setKeywordForm((current) => ({ ...current, platform: event.target.value }))}>
                <option value="">全平台</option>
                {PLATFORM_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
              </select>
            </label>
            <label>
              权重
              <input value={keywordForm.weight} onChange={(event) => setKeywordForm((current) => ({ ...current, weight: event.target.value }))} />
            </label>
            <label className="wide">
              用途
              <input value={keywordForm.usage_flags} onChange={(event) => setKeywordForm((current) => ({ ...current, usage_flags: event.target.value }))} placeholder="creator_discovery、content_tracking、keyword_heat" />
            </label>
            <label className="wide">
              原因
              <textarea rows={2} value={keywordForm.reason} onChange={(event) => setKeywordForm((current) => ({ ...current, reason: event.target.value }))} />
            </label>
            <label className="check">
              <input type="checkbox" checked={keywordForm.enabled} onChange={(event) => setKeywordForm((current) => ({ ...current, enabled: event.target.checked }))} />
              启用
            </label>
            <div className="result-actions form-actions">
              <Button type="submit" variant="primary" disabled={saving === "keyword" || !scenePacks.length}>{saving === "keyword" ? <Loader2 size={16} className="spin" /> : <Plus size={16} />}保存关键词</Button>
              {editingKeywordId ? <Button type="button" variant="ghost" onClick={startNewKeyword}>取消编辑</Button> : null}
            </div>
          </form>
        )}
        {message ? <p className="keyword-form-message">{message}</p> : null}
      </Card>
      <div className="keyword-library-grid">
        <Card>
          <CardHeader>
            <div>
              <CardTitle>场景包</CardTitle>
              <CardDescription>按业务场景组织关键词，不展示底层数据结构。</CardDescription>
            </div>
          </CardHeader>
          {scenePacks.length ? <KeywordScenePackList rows={scenePacks} onEdit={startEditScenePack} onToggle={toggleScenePack} onDelete={deleteScenePack} saving={saving} /> : <EmptyState title="暂无场景包" body={packs.error || "当前还没有可展示的场景包。"} />}
        </Card>
        <Card>
          <CardHeader>
            <div>
              <CardTitle>关键词明细</CardTitle>
              <CardDescription>只展示关键词、类型、平台、权重和用途。</CardDescription>
            </div>
          </CardHeader>
          {keywordRows.length ? <KeywordDetailList rows={keywordRows} packNameById={packNameById} onEdit={startEditKeyword} onToggle={toggleKeyword} onDelete={deleteKeyword} saving={saving} editingKeywordId={editingKeywordId} keywordForm={keywordForm} setKeywordForm={setKeywordForm} onSave={saveKeyword} onCancel={startNewKeyword} scenePacks={scenePacks} /> : <EmptyState title="暂无关键词" body={keywords.error || "当前还没有可展示的关键词。"} />}
        </Card>
      </div>
    </section>
  );
}

const KEYWORD_TYPE_LABELS: Record<string, string> = {
  primary: "主词",
  secondary: "扩展词",
  synonym: "同义词",
  negative: "排除词",
  platform_adapted: "平台适配",
  ai_suggested: "AI 建议",
};

const KEYWORD_TYPE_OPTIONS = Object.entries(KEYWORD_TYPE_LABELS).map(([value, label]) => ({ value, label }));
const PLATFORM_OPTIONS = ["xhs", "dy", "wb", "tieba", "bili", "ks", "zhihu"].map((value) => ({ value, label: labelPlatform(value) }));

function KeywordScenePackList({ rows, onEdit, onToggle, onDelete, saving }: { rows: UnknownRecord[]; onEdit: (row: UnknownRecord) => void; onToggle: (row: UnknownRecord) => void; onDelete: (row: UnknownRecord) => void; saving: string | null }) {
  return (
    <div className="module-list">
      {rows.map((row, index) => (
        <div className="record-card keyword-record" key={`${text(row.id)}-${index}`}>
          <div className="record-card-head">
            <div>
              <strong>{text(row.name, `场景包 ${index + 1}`)}</strong>
              <span>{text(row.description, "暂无描述")}</span>
            </div>
            <div className="keyword-row-actions">
              <Badge tone={row.enabled === false ? "muted" : "success"}>{row.enabled === false ? "停用" : "启用"}</Badge>
              <Button type="button" size="sm" variant="ghost" onClick={() => onEdit(row)}><Settings size={14} />编辑</Button>
              <Button type="button" size="sm" variant="ghost" onClick={() => void onToggle(row)} disabled={saving === `scene_pack-${text(row.id)}`}>{row.enabled === false ? "启用" : "停用"}</Button>
              <Button type="button" size="sm" variant="danger" onClick={() => void onDelete(row)} disabled={saving === `delete-scene_pack-${text(row.id)}`}>删除</Button>
            </div>
          </div>
          <div className="keyword-record-detail">
            <span>默认平台: {joinTextList(row.default_platforms) || "-"}</span>
            <span>权重: {text(row.weight, "1")}</span>
            <span>创建: {formatDateTime(text(row.created_at, ""))}</span>
          </div>
        </div>
      ))}
    </div>
  );
}

function KeywordDetailList({
  rows,
  packNameById,
  onEdit,
  onToggle,
  onDelete,
  saving,
  editingKeywordId,
  keywordForm,
  setKeywordForm,
  onSave,
  onCancel,
  scenePacks,
}: {
  rows: UnknownRecord[];
  packNameById: Map<number, string>;
  onEdit: (row: UnknownRecord) => void;
  onToggle: (row: UnknownRecord) => void;
  onDelete: (row: UnknownRecord) => void;
  saving: string | null;
  editingKeywordId: number | null;
  keywordForm: ReturnType<typeof emptyKeywordForm>;
  setKeywordForm: React.Dispatch<React.SetStateAction<ReturnType<typeof emptyKeywordForm>>>;
  onSave: (event: React.FormEvent) => Promise<void>;
  onCancel: () => void;
  scenePacks: UnknownRecord[];
}) {
  return (
    <div className="module-list">
      {rows.map((row, index) => {
        const isEditing = editingKeywordId === number(row.id);
        return (
          <div className="record-card keyword-record" key={`${text(row.id)}-${index}`}>
            <div className="record-card-head">
              <div>
                <strong>{text(row.keyword, `关键词 ${index + 1}`)}</strong>
                <span>{packNameById.get(number(row.scene_pack_id)) || `场景包 ${text(row.scene_pack_id)}`}</span>
              </div>
              <div className="keyword-row-actions">
                <Badge tone={row.enabled === false ? "muted" : "default"}>{KEYWORD_TYPE_LABELS[text(row.keyword_type, "")] || text(row.keyword_type, "未分类")}</Badge>
                <Button type="button" size="sm" variant="ghost" onClick={() => onEdit(row)}><Settings size={14} />编辑</Button>
                <Button type="button" size="sm" variant="ghost" onClick={() => void onToggle(row)} disabled={saving === `keyword-${text(row.id)}`}>{row.enabled === false ? "启用" : "停用"}</Button>
                <Button type="button" size="sm" variant="danger" onClick={() => void onDelete(row)} disabled={saving === `delete-keyword-${text(row.id)}`}>删除</Button>
              </div>
            </div>
            <div className="keyword-record-detail">
              <span>平台: {row.platform ? labelPlatform(text(row.platform)) : "全平台"}</span>
              <span>权重: {text(row.weight, "1")}</span>
              <span>用途: {joinTextList(row.usage_flags) || "-"}</span>
              {row.reason ? <span>原因: {text(row.reason)}</span> : null}
            </div>
            {isEditing ? (
              <form className="keyword-inline-form" onSubmit={onSave}>
                <label>
                  场景包
                  <select value={keywordForm.scene_pack_id} onChange={(event) => setKeywordForm((current) => ({ ...current, scene_pack_id: event.target.value }))}>
                    {scenePacks.map((pack) => <option key={text(pack.id)} value={text(pack.id)}>{text(pack.name)}</option>)}
                  </select>
                </label>
                <label>
                  关键词
                  <input value={keywordForm.keyword} onChange={(event) => setKeywordForm((current) => ({ ...current, keyword: event.target.value }))} />
                </label>
                <label>
                  类型
                  <select value={keywordForm.keyword_type} onChange={(event) => setKeywordForm((current) => ({ ...current, keyword_type: event.target.value }))}>
                    {KEYWORD_TYPE_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                  </select>
                </label>
                <label>
                  平台
                  <select value={keywordForm.platform} onChange={(event) => setKeywordForm((current) => ({ ...current, platform: event.target.value }))}>
                    <option value="">全平台</option>
                    {PLATFORM_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                  </select>
                </label>
                <label>
                  权重
                  <input value={keywordForm.weight} onChange={(event) => setKeywordForm((current) => ({ ...current, weight: event.target.value }))} />
                </label>
                <label className="wide">
                  用途
                  <input value={keywordForm.usage_flags} onChange={(event) => setKeywordForm((current) => ({ ...current, usage_flags: event.target.value }))} />
                </label>
                <label className="wide">
                  原因
                  <textarea rows={2} value={keywordForm.reason} onChange={(event) => setKeywordForm((current) => ({ ...current, reason: event.target.value }))} />
                </label>
                <label className="check">
                  <input type="checkbox" checked={keywordForm.enabled} onChange={(event) => setKeywordForm((current) => ({ ...current, enabled: event.target.checked }))} />
                  启用
                </label>
                <div className="result-actions form-actions">
                  <Button type="submit" size="sm" variant="primary" disabled={saving === "keyword"}>{saving === "keyword" ? <Loader2 size={14} className="spin" /> : null}保存</Button>
                  <Button type="button" size="sm" variant="ghost" onClick={onCancel}>取消</Button>
                </div>
              </form>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}

function joinTextList(value: unknown) {
  if (!Array.isArray(value)) return "";
  return value.map((item) => text(item, "")).filter(Boolean).join("、");
}

function splitList(value: string) {
  return value
    .split(/[、,，\s]+/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function toggleSet(current: Set<string>, key: string, selected: boolean) {
  const next = new Set(current);
  if (selected) next.add(key);
  else next.delete(key);
  return next;
}

function aiSuggestionKey(item: UnknownRecord) {
  return `${text(item.keyword)}-${text(item.keyword_type, "secondary")}-${text(item.platform, "all")}`;
}

function emptyScenePackForm(verticalId = 1) {
  return {
    vertical_id: String(verticalId),
    name: "",
    description: "",
    weight: "1",
    default_platforms: "xhs、dy",
    enabled: true,
  };
}

function emptyKeywordForm(scenePackId?: unknown) {
  return {
    scene_pack_id: scenePackId ? String(scenePackId) : "",
    keyword: "",
    keyword_type: "secondary",
    platform: "",
    weight: "1",
    reason: "",
    usage_flags: "creator_discovery、content_tracking、keyword_heat",
    enabled: true,
  };
}

export function CompetitorMonitorPage() {
  const accounts = useEndpoint<{ competitors: UnknownRecord[] }>("/api/competitors?enabled_only=true", { competitors: [] });
  const snapshots = useEndpoint<{ snapshots: UnknownRecord[] }>("/api/competitors/public-flow/latest?limit=30", { snapshots: [] });
  const recommendations = useEndpoint<{ recommendations: UnknownRecord[] }>("/api/competitors/recommendations?limit=10", { recommendations: [] });
  const [running, setRunning] = React.useState<string | null>(null);
  const [actionResult, setActionResult] = React.useState<string | null>(null);
  const [fetchStatusById, setFetchStatusById] = React.useState<Record<number, CompetitorFetchStatus>>({});
  const activeFetchTaskIds = React.useRef<Set<string>>(new Set());
  const [fetchDaysById, setFetchDaysById] = React.useState<Record<number, number>>({});
  const [editingCompetitorId, setEditingCompetitorId] = React.useState<number | null>(null);
  const [competitorEdit, setCompetitorEdit] = React.useState({
    displayName: "",
    profileUrl: "",
    notes: "",
    enabled: true,
  });
  const [newCompetitor, setNewCompetitor] = React.useState({
    platform: "xhs",
    creatorId: "",
    profileUrl: "",
    displayName: "",
  });

  const runAction = async (key: string, path: string, body?: UnknownRecord, method = "POST") => {
    setRunning(key);
    try {
      const result = await api<UnknownRecord>(path, {
        method,
        body: body ? JSON.stringify(body) : undefined,
      });
      const resultName = text(result.display_name || result.creator_id || result.name, "");
      setActionResult(resultName ? `${key}: ${resultName}` : `${key}: ${compactJson(result).slice(0, 160)}`);
      void accounts.reload();
      void snapshots.reload();
      void recommendations.reload();
      return result;
    } catch (err) {
      setActionResult(err instanceof Error ? err.message : String(err));
      throw err;
    } finally {
      setRunning(null);
    }
  };

  const pollCompetitorFetchTask = React.useCallback(
    async ({ competitorId, taskId, name }: PersistedCompetitorFetchTask, lockGlobalAction = false) => {
      if (!taskId || activeFetchTaskIds.current.has(taskId)) return;
      activeFetchTaskIds.current.add(taskId);
      if (lockGlobalAction) setRunning("立即获取数据");
      setFetchStatusById((current) => ({
        ...current,
        [competitorId]: current[competitorId] || { status: "running", message: `正在获取「${name || competitorId}」的数据...`, progress: 0 },
      }));
      try {
        let finalTask: UnknownRecord = {};
        for (let attempt = 0; attempt < 180; attempt += 1) {
          try {
            finalTask = await api<UnknownRecord>(`/api/competitors/fetch-tasks/${taskId}`);
          } catch (err) {
            if (err instanceof ApiError && err.status === 404) {
              throw new Error("上次采集任务已过期，可能是后端刚重启或任务被清理；请重新点击立即获取数据。");
            }
            throw err;
          }
          const status = text(finalTask.status, "");
          const progress = number(finalTask.progress);
          setFetchStatusById((current) => ({
            ...current,
            [competitorId]: {
              status: status === "failed" ? "error" : "running",
              message: `${formatOptionalNumber(progress)}% · ${text(finalTask.message, "正在执行...")}`,
              progress,
            },
          }));
          if (status === "completed" || status === "failed") break;
          await sleepMs(1000);
        }
        const status = text(finalTask.status, "");
        if (status === "failed") {
          const error = asRecord(finalTask.error);
          throw new Error(text(error.message || finalTask.message, "采集失败"));
        }
        setFetchStatusById((current) => ({
          ...current,
          [competitorId]: {
            status: "success",
            message: text(finalTask.message, "采集流程执行完成，请刷新快照查看结果。"),
            progress: 100,
          },
        }));
        removePersistedCompetitorFetchTask(competitorId);
        void accounts.reload();
        void snapshots.reload();
        void recommendations.reload();
      } catch (err) {
        removePersistedCompetitorFetchTask(competitorId);
        setFetchStatusById((current) => ({
          ...current,
          [competitorId]: { status: "error", message: err instanceof Error ? err.message : String(err), progress: 100 },
        }));
      } finally {
        activeFetchTaskIds.current.delete(taskId);
        if (lockGlobalAction) setRunning(null);
      }
    },
    [accounts.reload, recommendations.reload, snapshots.reload],
  );

  React.useEffect(() => {
    loadPersistedCompetitorFetchTasks().forEach((task) => {
      setFetchStatusById((current) => ({
        ...current,
        [task.competitorId]: { status: "running", message: `正在恢复「${task.name || task.competitorId}」的数据采集进度...`, progress: 0 },
      }));
      void pollCompetitorFetchTask(task);
    });
  }, [pollCompetitorFetchTask]);

  const fetchCompetitorNow = async (row: UnknownRecord) => {
    const competitorId = number(row.id);
    const name = text(row.display_name || row.creator_id);
    const daysBack = fetchDaysById[competitorId] || 7;
    setFetchStatusById((current) => ({ ...current, [competitorId]: { status: "running", message: `正在获取「${name}」近 ${daysBack} 天的数据...`, progress: 0 } }));
    setRunning("立即获取数据");
    try {
      const task = await api<UnknownRecord>(`/api/competitors/${competitorId}/fetch-now`, {
        method: "POST",
        body: JSON.stringify({ latest_limit: 50, days_back: daysBack, execute_now: true }),
      });
      const taskId = text(task.task_id, "");
      if (!taskId) {
        throw new Error("后端没有返回采集任务 ID。");
      }
      persistCompetitorFetchTask({ competitorId, taskId, name, daysBack });
      await pollCompetitorFetchTask({ competitorId, taskId, name, daysBack }, true);
    } catch (err) {
      setRunning(null);
      setFetchStatusById((current) => ({
        ...current,
        [competitorId]: { status: "error", message: err instanceof Error ? err.message : String(err), progress: 100 },
      }));
    }
  };

  const refreshCompetitorName = async (row: UnknownRecord) => {
    const competitorId = number(row.id);
    setFetchStatusById((current) => ({ ...current, [competitorId]: { status: "running", message: "正在刷新昵称..." } }));
    try {
      const result = await runAction("刷新昵称", `/api/competitors/${competitorId}/refresh-profile`);
      const competitor = asRecord(result.competitor);
      const diagnostics = asRecord(result.diagnostics);
      const displayName = text(competitor.display_name, "");
      setFetchStatusById((current) => ({
        ...current,
        [competitorId]: {
          status: displayName ? "success" : "error",
          message: displayName
            ? `昵称已更新为「${displayName}」。`
            : competitorProfileDiagnosticMessage(result, diagnostics),
        },
      }));
    } catch (err) {
      setFetchStatusById((current) => ({
        ...current,
        [competitorId]: { status: "error", message: err instanceof Error ? err.message : String(err) },
      }));
    }
  };

  const createManualCompetitor = async (event: React.FormEvent) => {
    event.preventDefault();
    const profileUrl = newCompetitor.profileUrl.trim();
    const creatorId = newCompetitor.creatorId.trim();
    const displayName = newCompetitor.displayName.trim();
    if (!profileUrl && !creatorId) {
      setActionResult("新增友商: 请填写主页 URL 或账号 ID");
      return;
    }
    if (profileUrl) {
      await runAction("新增友商", "/api/competitors/from-url", {
        platform: newCompetitor.platform,
        profile_url: profileUrl,
        display_name: displayName || undefined,
      });
    } else {
      await runAction("新增友商", "/api/competitors", {
        platform: newCompetitor.platform,
        creator_id: creatorId,
        display_name: displayName || undefined,
        enabled: true,
      });
    }
    setNewCompetitor({ platform: "xhs", creatorId: "", profileUrl: "", displayName: "" });
  };

  const startEditCompetitor = (row: UnknownRecord) => {
    setEditingCompetitorId(number(row.id));
    setCompetitorEdit({
      displayName: text(row.display_name, ""),
      profileUrl: text(row.profile_url, ""),
      notes: text(row.notes, ""),
      enabled: row.enabled !== false,
    });
  };

  const saveCompetitorEdit = async (competitorId: number) => {
    await runAction(
      "保存友商",
      `/api/competitors/${competitorId}`,
      {
        display_name: competitorEdit.displayName.trim() || undefined,
        profile_url: competitorEdit.profileUrl.trim() || undefined,
        notes: competitorEdit.notes.trim() || undefined,
        enabled: competitorEdit.enabled,
      },
      "PATCH",
    );
    setEditingCompetitorId(null);
  };

  const deleteCompetitor = async (row: UnknownRecord) => {
    const name = text(row.display_name || row.creator_id);
    if (!window.confirm(`确认删除友商「${name}」？历史快照会保留。`)) return;
    await runAction("删除友商", `/api/competitors/${number(row.id)}`, undefined, "DELETE");
  };

  return (
    <section className="module-page">
      <PageHero icon={<Activity size={30} />} title="友商监控" description="监控竞品内容、互动和趋势变化。" />
      <div className="module-metric-grid">
        <MetricCard label="启用友商" value={accounts.loading ? "..." : accounts.data.competitors.length} note={accounts.error || "公开主页最新内容"} icon={<Database size={18} />} />
        <MetricCard label="公开流量快照" value={snapshots.loading ? "..." : snapshots.data.snapshots.length} note={snapshots.error || "累计值 + 增量值"} icon={<BarChart3 size={18} />} />
        <MetricCard label="疑似友商" value={recommendations.loading ? "..." : recommendations.data.recommendations.length} note={recommendations.error || "候选池推荐，人工确认"} icon={<Users size={18} />} />
      </div>
      <Card className="creator-search-card">
        <CardHeader>
          <CardTitle>新增友商</CardTitle>
          <CardDescription>优先粘贴小红书/抖音主页 URL；如果已经知道账号 ID，也可以直接录入。</CardDescription>
        </CardHeader>
        <form className="competitor-add-form" onSubmit={createManualCompetitor}>
          <label>
            平台
            <select value={newCompetitor.platform} onChange={(event) => setNewCompetitor((current) => ({ ...current, platform: event.target.value }))}>
              <option value="xhs">小红书</option>
              <option value="dy">抖音</option>
            </select>
          </label>
          <label>
            主页 URL
            <input
              value={newCompetitor.profileUrl}
              onChange={(event) => setNewCompetitor((current) => ({ ...current, profileUrl: event.target.value }))}
              placeholder="https://www.xiaohongshu.com/user/profile/..."
            />
          </label>
          <label>
            账号 ID
            <input
              value={newCompetitor.creatorId}
              onChange={(event) => setNewCompetitor((current) => ({ ...current, creatorId: event.target.value }))}
              placeholder="URL 为空时填写"
            />
          </label>
          <label>
            昵称
            <input
              value={newCompetitor.displayName}
              onChange={(event) => setNewCompetitor((current) => ({ ...current, displayName: event.target.value }))}
              placeholder="可选"
            />
          </label>
          <Button type="submit" variant="primary" disabled={running !== null}>
            {running === "新增友商" ? <Loader2 size={16} className="spin" /> : <Plus size={16} />}新增友商
          </Button>
        </form>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>公开流量链路</CardTitle>
          <CardDescription>同步每日 3 次采集任务，并按最新 50 条内容重建累计值、增量值和异常信号。</CardDescription>
        </CardHeader>
        <div className="result-actions">
          <Button
            type="button"
            variant="primary"
            onClick={() => void runAction("同步监控任务", "/api/competitors/monitor-jobs/sync", { interval_minutes: 480, latest_limit: 50 })}
            disabled={running !== null}
          >
            {running === "同步监控任务" ? <Loader2 size={16} className="spin" /> : <MonitorCheck size={16} />}同步监控任务
          </Button>
          <Button
            type="button"
            variant="ghost"
            onClick={() => void runAction("重建公开流量快照", "/api/competitors/public-flow/rebuild-all", { latest_limit: 50 })}
            disabled={running !== null}
          >
            {running === "重建公开流量快照" ? <Loader2 size={16} className="spin" /> : <RefreshCw size={16} />}重建公开流量快照
          </Button>
        </div>
        {actionResult && <p className="candidate-muted">{actionResult}</p>}
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>启用友商</CardTitle>
          <CardDescription>管理需要监控的友商账号，可立即获取该账号最新公开数据。</CardDescription>
        </CardHeader>
        {accounts.data.competitors.length ? (
          <div className="module-list">
            {accounts.data.competitors.map((row, index) => {
              const competitorId = number(row.id);
              const isEditing = editingCompetitorId === competitorId;
              return (
                <div className="record-card" key={`${text(row.platform)}-${text(row.creator_id)}-${index}`}>
                  <div className="record-card-head competitor-row-head">
                    <div>
                      <strong>{text(row.display_name || row.creator_id)}</strong>
                      <span>{labelPlatform(text(row.platform))} · creator_id: {text(row.creator_id)} · enabled: {text(row.enabled)} · updated_at: {text(row.updated_at)}</span>
                      {!row.display_name && <span className="competitor-name-missing">未获取昵称，可点击“刷新昵称”或编辑手动填写</span>}
                    </div>
                    <div className="result-actions">
                      <select
                        className="competitor-fetch-range"
                        value={fetchDaysById[competitorId] || 7}
                        onChange={(event) => setFetchDaysById((current) => ({ ...current, [competitorId]: number(event.target.value) || 7 }))}
                        disabled={running !== null || fetchStatusById[competitorId]?.status === "running"}
                        aria-label="获取数据时间范围"
                      >
                        <option value={1}>近 1 天</option>
                        <option value={7}>近 7 天</option>
                        <option value={30}>近 30 天</option>
                        <option value={90}>近 90 天</option>
                      </select>
                      <Button type="button" variant="primary" size="sm" onClick={() => void fetchCompetitorNow(row)} disabled={running !== null || fetchStatusById[competitorId]?.status === "running"}>
                        {fetchStatusById[competitorId]?.status === "running" ? <Loader2 size={14} className="spin" /> : <Play size={14} />}立即获取数据
                      </Button>
                      {!row.display_name && (
                        <Button type="button" variant="ghost" size="sm" onClick={() => void refreshCompetitorName(row)} disabled={running !== null}>
                          <RefreshCw size={14} />刷新昵称
                        </Button>
                      )}
                      <Button type="button" variant="ghost" size="sm" onClick={() => startEditCompetitor(row)} disabled={running !== null}>
                        <Settings size={14} />编辑
                      </Button>
                      <Button type="button" variant="danger" size="sm" onClick={() => void deleteCompetitor(row)} disabled={running !== null}>
                        删除
                      </Button>
                    </div>
                  </div>
                  {fetchStatusById[competitorId] && (
                    <div className={`competitor-inline-status ${fetchStatusById[competitorId].status}`}>
                      {fetchStatusById[competitorId].progress !== undefined && (
                        <div className="competitor-progress-bar"><span style={{ width: `${Math.min(100, Math.max(0, fetchStatusById[competitorId].progress || 0))}%` }} /></div>
                      )}
                      {fetchStatusById[competitorId].message}
                    </div>
                  )}
                  {isEditing && (
                    <div className="competitor-edit-panel">
                      <label>
                        昵称
                        <input value={competitorEdit.displayName} onChange={(event) => setCompetitorEdit((current) => ({ ...current, displayName: event.target.value }))} />
                      </label>
                      <label>
                        主页 URL
                        <input value={competitorEdit.profileUrl} onChange={(event) => setCompetitorEdit((current) => ({ ...current, profileUrl: event.target.value }))} />
                      </label>
                      <label>
                        备注
                        <input value={competitorEdit.notes} onChange={(event) => setCompetitorEdit((current) => ({ ...current, notes: event.target.value }))} />
                      </label>
                      <label className="check competitor-enabled-check">
                        <input type="checkbox" checked={competitorEdit.enabled} onChange={(event) => setCompetitorEdit((current) => ({ ...current, enabled: event.target.checked }))} />
                        启用
                      </label>
                      <div className="result-actions">
                        <Button type="button" variant="primary" onClick={() => void saveCompetitorEdit(competitorId)} disabled={running !== null}>保存</Button>
                        <Button type="button" variant="ghost" onClick={() => setEditingCompetitorId(null)} disabled={running !== null}>取消</Button>
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        ) : <EmptyState title="暂无启用友商" body={accounts.error || "先通过人工录入或 URL 添加要监控的友商账号。"} />}
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>疑似友商推荐</CardTitle>
          <CardDescription>从 A/B 档候选达人中识别商业化账号，确认后加入友商池。</CardDescription>
        </CardHeader>
        {recommendations.data.recommendations.length ? (
          <div className="module-list">
            {recommendations.data.recommendations.map((row, index) => {
              const payload = asRecord(row.create_payload);
              return (
                <div className="record-card" key={`${text(row.platform)}-${text(row.creator_id)}-${index}`}>
                  <div className="record-card-head">
                    <div>
                      <strong>{text(row.display_name || row.creator_id)}</strong>
                      <span>{labelPlatform(text(row.platform))} · 推荐分 {formatOptionalNumber(row.recommendation_score)} · {textArray(row.reasons).join("；")}</span>
                    </div>
                    <Button
                      type="button"
                      variant="primary"
                      size="sm"
                      onClick={() => void runAction("加入友商池", "/api/competitors/from-candidate", payload)}
                      disabled={running !== null}
                    >
                      <Plus size={14} />加入友商池
                    </Button>
                  </div>
                </div>
              );
            })}
          </div>
        ) : <EmptyState title="暂无疑似友商" body={recommendations.error || "候选池里暂时没有足够商业化信号的账号。"} />}
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>最新公开流量快照</CardTitle>
          <CardDescription>展示最近生成的友商公开互动累计值、增量值和异常证据。</CardDescription>
        </CardHeader>
        {snapshots.data.snapshots.length ? (
          <CompetitorSnapshotList snapshots={snapshots.data.snapshots} competitors={accounts.data.competitors} />
        ) : <EmptyState title="暂无公开流量快照" body={snapshots.error || "先同步监控任务并完成一次采集，或手动重建公开流量快照。"} />}
      </Card>
    </section>
  );
}

function competitorProfileDiagnosticMessage(result: UnknownRecord, diagnostics: UnknownRecord) {
  const parts = [text(result.message, "未获取到昵称。")];
  parts.push(`后端读取 TikHub key: ${diagnostics.has_tikhub_api_key ? "是" : "否"}`);
  parts.push(`友商主页 URL: ${diagnostics.has_profile_url ? "有" : "无"}`);
  parts.push(`TikHub 状态: ${text(diagnostics.tikhub, "-")}`);
  if (!diagnostics.has_tikhub_api_key) {
    parts.push("请在启动后端的同一个终端设置 TIKHUB_API_KEY 并重启后端。");
  }
  if (!diagnostics.has_profile_url) {
    parts.push("请编辑友商，补充主页 URL。");
  }
  return parts.join(" ");
}

function CompetitorSnapshotList({ snapshots, competitors }: { snapshots: UnknownRecord[]; competitors: UnknownRecord[] }) {
  const competitorById = new Map(competitors.map((item) => [number(item.id), item]));
  return (
    <div className="competitor-snapshot-grid">
      {snapshots.slice(0, 12).map((snapshot, index) => {
        const evidence = asRecord(snapshot.evidence);
        const publicFlow = asRecord(evidence.public_flow);
        const cumulative = asRecord(publicFlow.cumulative);
        const delta = asRecord(publicFlow.delta);
        const anomalies = array(evidence.anomalies);
        const competitor = competitorById.get(number(snapshot.competitor_id));
        const title = text(competitor?.display_name || competitor?.creator_id || `友商 #${text(snapshot.competitor_id)}`);
        return (
          <article className="competitor-snapshot-card" key={`${text(snapshot.id)}-${index}`}>
            <div className="competitor-snapshot-head">
              <div>
                <strong>{title}</strong>
                <span>{labelPlatform(text(snapshot.platform))} · {text(snapshot.snapshot_date)}</span>
              </div>
              <Badge tone={anomalies.length ? "warning" : "muted"}>{anomalies.length ? `${anomalies.length} 个异常` : "正常"}</Badge>
            </div>
            <div className="competitor-snapshot-metrics">
              <CandidateMetric label="累计互动" value={formatOptionalNumber(snapshot.total_flow_count)} />
              <CandidateMetric label="本次新增" value={formatOptionalNumber(delta.total_interaction)} />
              <CandidateMetric label="点赞新增" value={formatOptionalNumber(delta.like)} />
              <CandidateMetric label="评论新增" value={formatOptionalNumber(delta.comment)} />
              <CandidateMetric label="收藏新增" value={formatOptionalNumber(delta.collect)} />
              <CandidateMetric label="采集内容" value={formatOptionalNumber(publicFlow.deduped_post_count)} />
            </div>
            <div className="competitor-snapshot-foot">
              <span>累计点赞 {formatOptionalNumber(cumulative.like)}</span>
              <span>累计评论 {formatOptionalNumber(cumulative.comment)}</span>
              <span>爆文率 {formatPercent(snapshot.hot_post_rate)}</span>
            </div>
            {anomalies.length > 0 && (
              <div className="competitor-anomaly-list">
                {anomalies.slice(0, 3).map((item, anomalyIndex) => (
                  <span key={anomalyIndex}>{text(item.title || item.type)}：{text(item.reason, "")}</span>
                ))}
              </div>
            )}
          </article>
        );
      })}
    </div>
  );
}

export function ContentTrackingPage() {
  const trackers = useEndpoint<{ trackers: UnknownRecord[] }>("/api/content-tracking/trackers", { trackers: [] });
  const [title, setTitle] = React.useState("K12教育爆款内容");
  const [sourceText, setSourceText] = React.useState("单亲妈妈如何陪伴孩子学习？这几个K12教育方法，比盲目报班更重要。");
  const [platform, setPlatform] = React.useState("all");
  const [keywords, setKeywords] = React.useState<UnknownRecord[]>([]);
  const [selectedKeywords, setSelectedKeywords] = React.useState<Set<string>>(new Set());
  const [candidates, setCandidates] = React.useState<UnknownRecord[]>([]);
  const [comments, setComments] = React.useState<UnknownRecord[]>([]);
  const [localSummary, setLocalSummary] = React.useState<UnknownRecord | null>(null);
  const [insights, setInsights] = React.useState<string[]>([]);
  const [aiReport, setAiReport] = React.useState<UnknownRecord | null>(null);
  const [trackerName, setTrackerName] = React.useState("K12内容追踪");
  const [trackerAnalysis, setTrackerAnalysis] = React.useState<UnknownRecord | null>(null);
  const [hasSearched, setHasSearched] = React.useState(false);
  const [running, setRunning] = React.useState<string | null>(null);
  const [message, setMessage] = React.useState<string | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [realtimeSearchEnabled, setRealtimeSearchEnabled] = React.useState(false);
  const [realtimeProgress, setRealtimeProgress] = React.useState(0);
  const [realtimeStage, setRealtimeStage] = React.useState("");
  const [realtimeMetadata, setRealtimeMetadata] = React.useState<UnknownRecord | null>(null);

  const selectedTerms = [...selectedKeywords];
  const platformPayload = platform === "all" ? [] : [platform];
  const platformQuery = platform === "all" ? undefined : platform;
  const realtimeSupportedPlatform = platform === "all" || platform === "xhs" || platform === "dy";

  async function runExtractKeywords() {
    setRunning("extract");
    setError(null);
    setMessage("AI 正在提取关键词");
    try {
      const response = await api<{ keywords: UnknownRecord[]; source?: string; provider?: UnknownRecord }>("/api/content-tracking/extract-keywords", {
        method: "POST",
        body: JSON.stringify({
          title,
          text: sourceText,
          platform: platformQuery,
          scene_pack_ids: [],
        }),
      });
      const rows = response.keywords || [];
      setKeywords(rows);
      setSelectedKeywords(new Set(rows.filter((item) => text(item.keyword_type) !== "negative").map((item) => text(item.keyword, "")).filter(Boolean)));
      setCandidates([]);
      setComments([]);
      setLocalSummary(null);
      setInsights([]);
      setAiReport(null);
      setHasSearched(false);
      resetRealtimeProgress();
      setMessage(rows.length ? (response.source === "ai" ? "AI 已提取 " + rows.length + " 个关键词" : "AI 不可用，已用本地关键词库提取 " + rows.length + " 个关键词") : "AI 和本地关键词库都未提取到关键词，可直接用正文里的词搜索");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setRunning(null);
    }
  }

  function setRealtimeStep(progress: number, stage: string) {
    setRealtimeProgress(progress);
    setRealtimeStage(stage);
  }

  function resetRealtimeProgress() {
    setRealtimeProgress(0);
    setRealtimeStage("");
    setRealtimeMetadata(null);
  }

  async function runLocalSearch() {
    const terms = selectedTerms.length ? selectedTerms : keywordFallback(sourceText);
    if (!terms.length) {
      setError("请先提取或选择至少一个关键词");
      return;
    }
    if (realtimeSearchEnabled && !realtimeSupportedPlatform) {
      setError("实时搜索暂只支持小红书和抖音");
      return;
    }
    setRunning("search");
    setError(null);
    setMessage(null);
    setHasSearched(true);
    if (realtimeSearchEnabled) {
      setRealtimeStep(10, "准备实时搜索");
    } else {
      resetRealtimeProgress();
    }
    try {
      if (realtimeSearchEnabled) {
        setRealtimeStep(35, platform === "all" ? "正在搜索小红书和抖音" : platform === "xhs" ? "正在搜索小红书" : "正在搜索抖音");
      }
      const similarPromise = api<{ candidates: UnknownRecord[]; realtime?: UnknownRecord }>("/api/content-tracking/search-similar", {
        method: "POST",
        body: JSON.stringify({
          keywords: terms,
          platforms: platformPayload,
          realtime: realtimeSearchEnabled,
          limit: 50,
        }),
      });
      if (realtimeSearchEnabled) {
        setRealtimeStep(65, "正在写入内容库");
      }
      const analysisPromise = api<UnknownRecord>("/api/content-tracking/analyze", {
        method: "POST",
        body: JSON.stringify({ query: terms.join(" "), platform: platformQuery, limit: 30 }),
      });
      const [similar, analysis] = await Promise.all([similarPromise, analysisPromise]);
      if (realtimeSearchEnabled) {
        setRealtimeStep(85, "正在刷新本地结果");
      }
      setCandidates(similar.candidates || []);
      setComments(array(analysis.comments));
      setLocalSummary(asRecord(analysis.summary));
      setInsights(textArray(analysis.insights));
      setRealtimeMetadata(asRecord(similar.realtime));
      if (realtimeSearchEnabled) {
        setRealtimeStep(100, "搜索完成");
        setMessage(`实时搜索完成，找到 ${similar.candidates?.length || 0} 条同类内容`);
      } else {
        setMessage(`本地库找到 ${similar.candidates?.length || 0} 条同类内容`);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setRunning(null);
    }
  }

  async function runAiAnalysis() {
    const terms = selectedTerms.length ? selectedTerms : keywordFallback(sourceText);
    if (!terms.length) {
      setError("请先提取或选择至少一个关键词");
      return;
    }
    setRunning("ai");
    setError(null);
    setMessage(null);
    try {
      const response = await api<{ analysis: UnknownRecord; provider: UnknownRecord }>("/api/content-tracking/ai-analysis", {
        method: "POST",
        body: JSON.stringify({
          title,
          text: sourceText,
          platform: platformQuery,
          keywords: terms,
          candidates: candidates.slice(0, 20),
          comments: comments.slice(0, 30),
        }),
      });
      setAiReport(response.analysis);
      setMessage(`AI 分析已完成：${text(response.provider.name)} / ${text(response.provider.model)}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setRunning(null);
    }
  }

  async function saveTracker() {
    const terms = selectedTerms.length ? selectedTerms : keywordFallback(sourceText);
    if (!terms.length) {
      setError("请先选择追踪关键词");
      return;
    }
    setRunning("save");
    setError(null);
    setMessage(null);
    try {
      const tracker = await api<UnknownRecord>("/api/content-tracking/trackers", {
        method: "POST",
        body: JSON.stringify({
          name: trackerName.trim() || `${terms[0]}内容追踪`,
          description: title || sourceText.slice(0, 80),
          platforms: platformPayload,
          included_keywords: terms,
          excluded_keywords: textArray(asRecord(aiReport?.tracking_suggestions).excluded_keywords),
          seed_refs: [{ title: title || sourceText.slice(0, 40), text: sourceText.slice(0, 180) }],
        }),
      });
      setMessage(`已保存追踪器 #${text(tracker.id)}`);
      await trackers.reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setRunning(null);
    }
  }

  async function runTrackerAnalysis(trackerId: number) {
    setRunning(`tracker-${trackerId}`);
    setError(null);
    setTrackerAnalysis(null);
    try {
      const response = await api<UnknownRecord>(`/api/content-tracking/trackers/${trackerId}/analysis`, { method: "POST" });
      setTrackerAnalysis(response);
      setMessage(`追踪器 #${trackerId} 分析快照已生成`);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setRunning(null);
    }
  }

  function toggleKeyword(keyword: string) {
    setSelectedKeywords((current) => {
      const next = new Set(current);
      if (next.has(keyword)) next.delete(keyword);
      else next.add(keyword);
      return next;
    });
  }

  return (
    <section className="module-page content-tracking-workbench">
      <PageHero icon={<FileJson size={30} />} title="内容跟踪" description="基于本地数据库定位关键词、搜索同类内容，并用 env 中转站 API 做 AI 分析。" />
      <div className="content-tracking-shell">
        <Card className="content-source-panel">
          <CardHeader>
            <div>
              <CardTitle>原文输入</CardTitle>
              <CardDescription>粘贴标题、正文或评论，系统只从本地库找证据。</CardDescription>
            </div>
          </CardHeader>
          <div className="content-form-grid">
            <label>
              标题
              <input value={title} onChange={(event) => setTitle(event.target.value)} />
            </label>
            <label>
              平台
              <select
                value={platform}
                onChange={(event) => {
                  const nextPlatform = event.target.value;
                  setPlatform(nextPlatform);
                  if (nextPlatform !== "all" && nextPlatform !== "xhs" && nextPlatform !== "dy") {
                    setRealtimeSearchEnabled(false);
                    resetRealtimeProgress();
                  }
                }}
              >
                <option value="all">全部平台</option>
                <option value="xhs">小红书</option>
                <option value="dy">抖音</option>
                <option value="bili">B站</option>
                <option value="wb">微博</option>
                <option value="zhihu">知乎</option>
              </select>
            </label>
          </div>
          <label className="content-textarea-label">
            正文
            <textarea value={sourceText} onChange={(event) => setSourceText(event.target.value)} />
          </label>
          <div className="content-source-preview">{highlightTerms(`${title}\n${sourceText}`, selectedTerms)}</div>
          <label className={`content-realtime-toggle ${!realtimeSupportedPlatform ? "disabled" : ""}`}>
            <input
              type="checkbox"
              checked={realtimeSearchEnabled}
              disabled={!realtimeSupportedPlatform || Boolean(running)}
              onChange={(event) => {
                setRealtimeSearchEnabled(event.target.checked);
                if (!event.target.checked) resetRealtimeProgress();
              }}
            />
            <span>
              <strong>是否实时搜索</strong>
              <small>{realtimeSupportedPlatform ? "勾选后会先通过 TikHub 搜索小红书、抖音并入库" : "实时搜索暂只支持小红书和抖音"}</small>
            </span>
          </label>
          <div className="content-action-row">
            <Button type="button" variant="primary" onClick={() => void runExtractKeywords()} disabled={Boolean(running)}>
              {running === "extract" ? <Loader2 size={16} className="spin" /> : <KeyRound size={16} />}提取关键词
            </Button>
            <Button type="button" variant="ghost" onClick={() => void runLocalSearch()} disabled={Boolean(running)}>
              {running === "search" ? <Loader2 size={16} className="spin" /> : <Search size={16} />}
              {realtimeSearchEnabled ? "实时搜索并入库" : "搜索同类内容"}
            </Button>
            <Button type="button" variant="ghost" onClick={() => void runAiAnalysis()} disabled={Boolean(running)}>
              {running === "ai" ? <Loader2 size={16} className="spin" /> : <Bot size={16} />}AI 分析
            </Button>
          </div>
          {realtimeSearchEnabled && (running === "search" || realtimeProgress > 0) && (
            <div className="content-realtime-progress" aria-live="polite">
              <div className="content-realtime-progress-header">
                <span>{realtimeStage || "等待实时搜索"}</span>
                <strong>{realtimeProgress}%</strong>
              </div>
              <div className="content-realtime-progress-track">
                <span style={{ width: `${realtimeProgress}%` }} />
              </div>
              {realtimeMetadata && (
                <small>
                  Job #{text(realtimeMetadata.job_id)} · {text(realtimeMetadata.status, "-")} · 匹配 {formatOptionalNumber(realtimeMetadata.matched_count)} 条
                </small>
              )}
            </div>
          )}
          {(message || error) && <div className={`content-status ${error ? "error" : ""}`}>{error || message}</div>}
        </Card>

        <Card className="content-keyword-panel">
          <CardHeader>
            <div>
              <CardTitle>关键词定位</CardTitle>
              <CardDescription>勾选后进入本地搜索和追踪器。</CardDescription>
            </div>
            <Badge tone="muted">{selectedTerms.length}/{keywords.length || keywordFallback(sourceText).length}</Badge>
          </CardHeader>
          {keywords.length ? (
            <div className="content-keyword-list">
              {keywords.map((item, index) => {
                const keyword = text(item.keyword, "");
                return (
                  <button className={`content-keyword-row ${selectedKeywords.has(keyword) ? "active" : ""}`} key={`${keyword}-${index}`} onClick={() => toggleKeyword(keyword)}>
                    <span>
                      <strong>{keyword}</strong>
                      <em>{text(item.keyword_type, "local")} · {formatConfidence(item.confidence)}</em>
                    </span>
                    <small>{text(item.evidence_text, "无证据片段")}</small>
                  </button>
                );
              })}
            </div>
          ) : (
            <EmptyState title="等待关键词" body="点击“提取关键词”，或先用正文中的词搜索本地内容。" />
          )}
          {insights.length > 0 && (
            <div className="content-insight-list">
              {insights.map((item) => <p key={item}>{item}</p>)}
            </div>
          )}
        </Card>

        <Card className="content-ai-panel">
          <CardHeader>
            <div>
              <CardTitle>AI 分析</CardTitle>
              <CardDescription>AI 只读取当前本地候选内容和评论样本。</CardDescription>
            </div>
          </CardHeader>
          {aiReport ? <ContentAiReport report={aiReport} /> : <EmptyState title="暂无 AI 结论" body="先搜索同类内容，再点击 AI 分析生成结构化报告。" />}
        </Card>
      </div>

      <div className="content-result-grid">
        <Card>
          <CardHeader>
            <div>
              <CardTitle>本地同类内容</CardTitle>
              <CardDescription>
                {localSummary ? `帖子 ${formatOptionalNumber(localSummary.matched_posts)} / 评论 ${formatOptionalNumber(localSummary.matched_comments)}` : "按相似度和互动数据排序。"}
              </CardDescription>
            </div>
            <Badge tone={candidates.length ? "success" : "muted"}>{candidates.length} 条</Badge>
          </CardHeader>
          {candidates.length ? (
            <ContentCandidateList rows={candidates} />
          ) : hasSearched ? (
            <EmptyState title="暂无同类内容" body="本地数据库暂未命中；可以扩大平台范围或减少关键词。" />
          ) : (
            <EmptyState title="等待搜索" body="关键词定位完成后，点击“搜索同类内容”读取本地帖子库。" />
          )}
        </Card>
        <Card>
          <CardHeader>
            <div>
              <CardTitle>追踪器</CardTitle>
              <CardDescription>保存当前关键词，并生成本地分析快照。</CardDescription>
            </div>
          </CardHeader>
          <div className="tracker-create-row">
            <input value={trackerName} onChange={(event) => setTrackerName(event.target.value)} />
            <Button type="button" variant="primary" onClick={() => void saveTracker()} disabled={Boolean(running)}>
              {running === "save" ? <Loader2 size={16} className="spin" /> : <Plus size={16} />}保存
            </Button>
          </div>
          <div className="tracker-list">
            {trackers.data.trackers.length ? trackers.data.trackers.map((tracker) => {
              const trackerId = number(tracker.id);
              return (
                <article className="tracker-row" key={trackerId || text(tracker.name)}>
                  <div>
                    <strong>{text(tracker.name)}</strong>
                    <span>{textArray(tracker.included_keywords).join("、") || "未设置关键词"}</span>
                  </div>
                  <Button type="button" variant="ghost" size="sm" onClick={() => void runTrackerAnalysis(trackerId)} disabled={!trackerId || Boolean(running)}>
                    {running === `tracker-${trackerId}` ? <Loader2 size={14} className="spin" /> : <RefreshCw size={14} />}分析
                  </Button>
                </article>
              );
            }) : <EmptyState title="暂无追踪器" body={trackers.error || "保存当前关键词后，这里会出现追踪任务。"} />}
          </div>
          {trackerAnalysis && (
            <div className="tracker-analysis-box">
              <strong>最近快照</strong>
              <span>候选内容 {formatOptionalNumber(asRecord(trackerAnalysis.summary).total_candidates)}</span>
              <SimpleBars rows={array(asRecord(trackerAnalysis.summary).top_keywords).map((item) => ({ name: text(item.name), value: number(item.value) }))} />
            </div>
          )}
        </Card>
      </div>
    </section>
  );
}

function ContentAiReport({ report }: { report: UnknownRecord }) {
  const suggestions = asRecord(report.tracking_suggestions);
  return (
    <div className="content-ai-report">
      <section>
        <h3>主题判断</h3>
        <p>{text(report.topic_summary, "AI 未返回主题摘要")}</p>
      </section>
      <section>
        <h3>关键词价值</h3>
        <div className="ai-keyword-judgement">
          {array(report.keyword_judgement).map((item, index) => (
            <span key={`${text(item.keyword)}-${index}`}>
              <strong>{text(item.keyword)}</strong>
              <em>{text(item.value)} / {text(item.tracking_action)}</em>
              {text(item.reason, "")}
            </span>
          ))}
        </div>
      </section>
      <ReportList title="同类内容模式" rows={textArray(report.similar_content_patterns)} />
      <ReportList title="评论反馈" rows={textArray(report.comment_feedback)} />
      <ReportList title="机会点" rows={textArray(report.opportunities)} />
      <ReportList title="风险提示" rows={textArray(report.risk_notes)} />
      <section>
        <h3>追踪建议</h3>
        <p>纳入：{textArray(suggestions.included_keywords).join("、") || "-"}</p>
        <p>排除：{textArray(suggestions.excluded_keywords).join("、") || "-"}</p>
      </section>
    </div>
  );
}

function ReportList({ title, rows }: { title: string; rows: string[] }) {
  if (!rows.length) return null;
  return (
    <section>
      <h3>{title}</h3>
      <ul>{rows.map((item) => <li key={item}>{item}</li>)}</ul>
    </section>
  );
}

function ContentCandidateList({ rows }: { rows: UnknownRecord[] }) {
  return (
    <div className="content-candidate-list">
      {rows.slice(0, 30).map((row, index) => {
        const evidence = asRecord(row.evidence);
        const snippets = textArray(evidence.snippets);
        return (
          <article className="content-candidate-card" key={`${text(row.platform_post_id || row.post_id)}-${index}`}>
            <div className="content-candidate-head">
              <div>
                <strong>{text(row.title, `内容 ${index + 1}`)}</strong>
                <span>{labelPlatform(text(row.platform))} · 相似度 {formatOptionalNumber(row.similarity_score)} · {text(row.publish_time, "未知时间")}</span>
              </div>
              {text(row.url, "") && <a href={text(row.url)} target="_blank" rel="noreferrer">打开</a>}
            </div>
            <div className="content-candidate-tags">
              {array(row.matched_keywords).map((hit, hitIndex) => <span key={hitIndex}>{text(hit.term)} × {formatOptionalNumber(hit.count)}</span>)}
            </div>
            <p>{snippets[0] || text(evidence.context, "暂无证据片段")}</p>
            <div className="content-candidate-metrics">
              <span>赞 {formatOptionalNumber(asRecord(row.engagement).liked_count || asRecord(row.engagement).like_count)}</span>
              <span>评 {formatOptionalNumber(asRecord(row.engagement).comment_count || asRecord(row.engagement).comments_count)}</span>
              <span>藏 {formatOptionalNumber(asRecord(row.engagement).collected_count || asRecord(row.engagement).collect_count)}</span>
            </div>
          </article>
        );
      })}
    </div>
  );
}

function keywordFallback(value: string) {
  return uniqueStringList(value.split(/[\s,，。！？、+]+/).map((item) => item.trim()).filter((item) => item.length >= 2)).slice(0, 8);
}

function uniqueStringList(values: string[]) {
  return [...new Set(values.filter(Boolean))];
}

function highlightTerms(value: string, terms: string[]) {
  const active = terms.filter(Boolean).sort((a, b) => b.length - a.length);
  if (!active.length) return value;
  const pattern = new RegExp(`(${active.map(escapeRegExp).join("|")})`, "gi");
  return value.split(pattern).map((part, index) => {
    const matched = active.some((term) => term.toLowerCase() === part.toLowerCase());
    return matched ? <mark key={`${part}-${index}`}>{part}</mark> : <React.Fragment key={`${part}-${index}`}>{part}</React.Fragment>;
  });
}

function escapeRegExp(value: string) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

export function AiAnalysisPage({ aiResults }: { selectedJob: ResearchJob | null; posts: PostRecord[]; comments: CommentRecord[]; aiResults: AIResult[]; onRefresh: () => void }) {
  return <SimpleDataPage icon={<Bot size={30} />} title="AI 分析" description="运行内容理解、标签、摘要和报告辅助分析。" rows={aiResults as unknown as UnknownRecord[]} />;
}

export function ExportCenterPage({ jobs, posts, comments, rawRecords, aiResults }: { jobs: ResearchJob[]; posts: PostRecord[]; comments: CommentRecord[]; rawRecords: RawRecord[]; aiResults: AIResult[] }) {
  const rows = [
    { name: "任务", value: jobs.length },
    { name: "帖子", value: posts.length },
    { name: "评论", value: comments.length },
    { name: "Raw", value: rawRecords.length },
    { name: "AI", value: aiResults.length },
  ];
  return <SimpleDataPage icon={<Download size={30} />} title="导出中心" description="导出研究样本、候选达人和 AI 分析结果。" rows={rows} />;
}

export function ConfigPage() {
  const options = useEndpoint<UnknownRecord>("/api/research/options", {});
  return (
    <section className="module-page">
      <PageHero icon={<Settings size={30} />} title="配置" description="查看研究后台当前配置和平台能力。" />
      <Card><pre className="json-detail">{JSON.stringify(options.data, null, 2)}</pre></Card>
    </section>
  );
}

function SimpleRemotePage({ icon, title, description, endpoint, dataKey }: { icon: React.ReactNode; title: string; description: string; endpoint: string; dataKey: string }) {
  const data = useEndpoint<UnknownRecord>(endpoint, {});
  const rows = array(data.data[dataKey]);
  return <SimpleDataPage icon={icon} title={title} description={description} rows={rows} loading={data.loading} error={data.error} />;
}

function SimpleDataPage({ icon, title, description, rows, loading, error }: { icon: React.ReactNode; title: string; description: string; rows: UnknownRecord[]; loading?: boolean; error?: string | null }) {
  return (
    <section className="module-page">
      <PageHero icon={icon} title={title} description={description} />
      <div className="module-metric-grid">
        <MetricCard label="记录" value={loading ? "..." : rows.length} note={error || "本地数据库"} icon={<Database size={18} />} />
      </div>
      <Card>
        {rows.length ? <RecordList rows={rows} titleKeys={["name", "title", "id", "target_id"]} metaKeys={["status", "platform", "value", "created_at"]} /> : <EmptyState title="暂无数据" body={error || "当前模块还没有可展示记录。"} />}
      </Card>
    </section>
  );
}

function RecordList({ rows, titleKeys, titleLinkKey, metaKeys, onSelect, selectedId }: { rows: UnknownRecord[]; titleKeys: string[]; titleLinkKey?: string; metaKeys: string[]; onSelect?: (row: UnknownRecord) => void; selectedId?: number | null }) {
  const [expanded, setExpanded] = React.useState<number | null>(null);
  return (
    <div className="module-list">
      {rows.slice(0, 30).map((row, index) => {
        const title = titleKeys.map((key) => row[key]).find(Boolean);
        const titleLink = titleLinkKey ? text(row[titleLinkKey], "") : "";
        const meta = metaKeys.map((key) => row[key] === undefined || row[key] === null || row[key] === "" ? null : `${key}: ${text(row[key]).slice(0, 42)}`).filter(Boolean).join(" · ");
        const isCandidate = isCreatorCandidateRecord(row);
        return (
          <div className={`record-card ${selectedId === number(row.id) ? "active" : ""}`} key={`${text(title)}-${index}`}>
            <button className="record-card-head" onClick={() => { onSelect?.(row); setExpanded(expanded === index ? null : index); }}>
              <div>
                <strong>{titleLink ? <a href={titleLink} target="_blank" rel="noreferrer" onClick={(event) => event.stopPropagation()}>{text(title, `记录 ${index + 1}`)}</a> : text(title, `记录 ${index + 1}`)}</strong>
                <span>{meta || compactJson(row)}</span>
              </div>
              <Badge tone="muted">{expanded === index ? "收起" : "展开"}</Badge>
            </button>
            {expanded === index && (isCandidate ? <CreatorCandidateDetail row={row} /> : <pre className="json-detail">{JSON.stringify(row, null, 2)}</pre>)}
          </div>
        );
      })}
    </div>
  );
}

function isCreatorCandidateRecord(row: UnknownRecord) {
  return Boolean(row.creator_id && row.platform && (row.pool_name || row.matched_tags || row.evidence || row.profile_url));
}

function CreatorCandidateDetail({ row }: { row: UnknownRecord }) {
  const evidenceRecord = asRecord(row.evidence);
  const query = text(evidenceRecord.raw_query || evidenceRecord.query, "");
  const matchedTags = array(row.matched_tags);
  const directEvidence = array(evidenceRecord.evidence || row.evidence);
  const representativePosts = array(evidenceRecord.representative_posts || row.representative_posts);
  const evidenceItems = (representativePosts.length ? representativePosts : directEvidence).slice(0, 4);
  const reason = candidateMatchReason(row, matchedTags, evidenceItems, query);
  return (
    <div className="candidate-detail">
      <section>
        <div className="candidate-section-title">基础信息</div>
        <div className="candidate-basic-grid">
          <CandidateMetric label="昵称" value={text(row.display_name || row.nickname || row.creator_id)} href={text(row.profile_url, "")} />
          <CandidateMetric label="平台" value={labelPlatform(text(row.platform))} />
          <CandidateMetric label="粉丝" value={formatOptionalNumber(candidateMetric(row, "follower_count"))} />
          <CandidateMetric label={text(row.platform) === "dy" ? "获赞" : "总赞"} value={formatOptionalNumber(candidateMetric(row, "total_like_count") || candidateMetric(row, "interaction_count"))} />
          <CandidateMetric label="收藏" value={formatOptionalNumber(candidateMetric(row, "total_collect_count"))} />
          <CandidateMetric label="作品数" value={formatOptionalNumber(candidateMetric(row, "post_count"))} />
        </div>
      </section>
      <section>
        <div className="candidate-section-title">匹配原因</div>
        <p className="candidate-reason">{reason}</p>
      </section>
      <section>
        <div className="candidate-section-title">证据内容</div>
        {evidenceItems.length ? (
          <div className="candidate-evidence-list">
            {evidenceItems.map((item, index) => (
              <article key={index}>
                <strong>{text(item.title || item.platform_post_id || item.note_id || item.aweme_id || item.term, `证据 ${index + 1}`)}</strong>
                <p>{candidateEvidenceText(item)}</p>
                {text(item.url || item.note_url || item.aweme_url, "") && <a href={text(item.url || item.note_url || item.aweme_url, "")} target="_blank" rel="noreferrer">打开内容</a>}
              </article>
            ))}
          </div>
        ) : <p className="candidate-muted">暂无可展示的帖子/视频证据。</p>}
      </section>
      <section>
        <div className="candidate-section-title">标签</div>
        {matchedTags.length ? (
          <div className="candidate-tag-list">
            {matchedTags.map((tag, index) => <span key={index}>{candidateTagLabel(tag)}<em>{formatConfidence(tag.confidence)}</em></span>)}
          </div>
        ) : <p className="candidate-muted">暂无结构化标签，当前主要依赖文本命中。</p>}
      </section>
      <details className="candidate-debug">
        <summary>调试信息</summary>
        <pre className="json-detail">{JSON.stringify(row, null, 2)}</pre>
      </details>
    </div>
  );
}

function CandidateMetric({ label, value, href }: { label: string; value: string; href?: string }) {
  return (
    <div className="candidate-metric">
      <span>{label}</span>
      {href ? <a href={href} target="_blank" rel="noreferrer">{value}</a> : <strong>{value}</strong>}
    </div>
  );
}

function candidateMetric(row: UnknownRecord, key: string) {
  const metrics = asRecord(asRecord(row.tag_summary_json).profile_metrics);
  return row[key] || metrics[key];
}

function candidateTagLabel(tag: UnknownRecord) {
  const evidence = asRecord(tag.evidence_json);
  return text(tag.tag_name || evidence.tag_name || tag.name || tag.term || tag.keyword, "命中标签");
}

function candidateEvidenceText(item: UnknownRecord) {
  const matches = array(item.matches);
  if (matches.length) {
    return matches
      .slice(0, 2)
      .map((match) => {
        const field = evidenceFieldLabel(text(match.field, ""));
        const term = text(match.matched_term || match.term, "");
        const context = text(match.context || match.matched_text, "");
        return `${field}${term ? `命中“${term}”` : "命中"}：${context}`;
      })
      .join("；");
  }
  const title = text(item.title || item.platform_post_id || item.note_id || item.aweme_id || item.term, "");
  const content = text(item.content || item.body || item.reason || item.summary, "");
  if (title && content && title !== content) return `${title}；${content}`;
  return title || content || "暂无摘要";
}

function evidenceFieldLabel(field: string) {
  return ({ title: "标题", content: "正文", desc: "正文", bio: "简介", profile: "主页" } as Record<string, string>)[field] || (field ? `${field} ` : "");
}

function candidateMatchReason(row: UnknownRecord, tags: UnknownRecord[], evidence: UnknownRecord[], query?: string) {
  const terms = new Set<string>();
  tags.forEach((tag) => terms.add(candidateTagLabel(tag)));
  evidence.forEach((item) => {
    array(item.matches).forEach((match) => {
      if (match.matched_term) terms.add(text(match.matched_term));
    });
    if (item.term) terms.add(text(item.term));
  });
  const termText = [...terms].filter(Boolean).slice(0, 6).join("、");
  const score = Math.round(number(row.match_score));
  const base = query ? `围绕“${query}”筛选，` : "";
  if (termText) return `${base}该达人命中了 ${termText} 等标签或内容证据，匹配分 ${score}。`;
  if (score > 0) return `${base}该达人来自候选池评分结果，匹配分 ${score}；建议结合证据内容继续复核。`;
  return `${base}该达人来自本地候选池，目前缺少可读匹配原因，建议重新执行关键词筛选或打标。`;
}

function formatConfidence(value: unknown) {
  const confidence = number(value);
  if (!confidence) return "";
  const normalized = confidence > 1 ? confidence : confidence * 100;
  return `${Math.round(normalized)}%`;
}

function SimpleBars({ rows, formatter }: { rows: Array<{ name: string; value: number }>; formatter?: (name: string) => string }) {
  if (!rows.length) return <div className="chart-empty">暂无数据</div>;
  const max = Math.max(...rows.map((row) => row.value), 1);
  return (
    <div className="score-bars">
      {rows.map((row) => (
        <div className="score-bar" key={row.name}>
          <span>{formatter ? formatter(row.name) : row.name}</span>
          <div><i style={{ width: `${Math.max(4, (row.value / max) * 100)}%` }} /></div>
          <b>{row.value}</b>
        </div>
      ))}
    </div>
  );
}

function EmptyState({ title, body }: { title: string; body: string }) {
  return (
    <div className="diagnostic-empty">
      <AlertTriangle size={18} />
      <div>
        <h2>{title}</h2>
        <p>{body}</p>
      </div>
    </div>
  );
}