import React from "react";
import { createRoot } from "react-dom/client";
import { Activity, AlertTriangle, BarChart3, CheckCircle2, Database, Eye, Loader2, Play, RefreshCw, Search, SquarePen, Table2, X } from "lucide-react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
  ZAxis,
} from "recharts";
import "./styles.css";

type DashboardConfidence = "low" | "medium" | "high";
type DashboardSampleStatus = "insufficient" | "limited" | "enough";
type OpportunityRiskTag = "small_sample_spike" | "single_platform_signal" | "stale_data" | "overheated_competition" | "missing_execution_parameters" | "high_cost";
type OpportunityAction = { kind: string; label: string; risk: "low" | "high"; payload: Record<string, unknown> };
type OpportunitySample = {
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
type DashboardOpportunity = {
  id: string;
  type: "creator" | "keyword" | "competitor" | "content";
  name: string;
  platform?: string | null;
  score: number;
  score_breakdown?: { heat_growth: number; sample_confidence: number; competition_gap: number; actionability: number };
  risk_tags?: OpportunityRiskTag[];
  evidence_summary?: string[];
  sample_scope?: { window: string; platforms: string[]; sample_count: number; last_updated_at?: string | null };
  trend?: { change_24h: number; points_7d: Array<Record<string, unknown>>; points_14d: Array<Record<string, unknown>>; points_30d: Array<Record<string, unknown>> };
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
type DashboardAction = { title: string; reason: string; target_type: string; action: string; payload: Record<string, unknown> };
type DashboardSummary = {
  decision: { headline: string; confidence: DashboardConfidence; sample_status: DashboardSampleStatus; sample_summary: string; risk_notes: string[]; evidence_count: number };
  actions: { do_now: DashboardAction[]; watch_today: DashboardAction[]; defer: DashboardAction[] };
  monitoring: { running_jobs: number; today_collected: number; errors: number; monitor_pools: number; realtime_jobs: number; last_updated_at?: string | null };
  opportunities: DashboardOpportunity[];
  top_opportunities?: DashboardOpportunity[];
  watchlist?: DashboardOpportunity[];
  ignored_opportunities?: DashboardOpportunity[];
  diagnostics?: Array<{ code: string; title: string; body: string; action?: string }>;
  scoring_profile?: { weights: Record<string, number>; window: string };
};
type PostRecord = { id: number; platform: string; platform_post_id: string; title?: string | null; content?: string | null; url?: string | null; publish_time?: string | null; engagement_json?: Record<string, unknown> };
type CommentRecord = { id: number; platform: string; platform_comment_id: string; platform_post_id?: string | null; content?: string | null; publish_time?: string | null; like_count?: number | null };
type RawRecord = { id: number; platform: string; source_type: string; source_id?: string | null; payload_hash: string; fetched_at?: string | null; parser_version?: string };
type AIResult = { id: number; target_type: string; target_id: string; result_json: Record<string, unknown>; model: string; created_at?: string };
type ResearchJob = { id: number; name: string; topic: string; keywords: string[]; platforms: string[]; status: string };
type PendingExecution = { title: string; action: string; targetType: DashboardOpportunity["type"]; platform?: string | null; payload: Record<string, unknown> };
type Tab = "overview" | "data";

const CHART_COLORS = ["#04786f", "#101820", "#ff9f1c", "#2563eb", "#ef4444", "#94a3b8"];
const PLATFORM_LABELS: Record<string, string> = { xhs: "小红书", dy: "抖音", ks: "快手", bili: "B站", wb: "微博", weibo: "微博", tieba: "贴吧", zhihu: "知乎" };
const RISK_LABELS: Record<OpportunityRiskTag, string> = {
  small_sample_spike: "小样本突增",
  single_platform_signal: "平台单一",
  stale_data: "数据过旧",
  overheated_competition: "竞争过热",
  missing_execution_parameters: "执行参数缺失",
  high_cost: "成本较高",
};
const scoreParts = [
  ["heat_growth", "热度增长"],
  ["sample_confidence", "样本可信度"],
  ["competition_gap", "竞争空档"],
  ["actionability", "可执行性"],
] as const;

async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(path, { headers: { "Content-Type": "application/json", ...(options.headers || {}) }, ...options });
  if (!response.ok) throw new Error((await response.json().catch(() => ({}))).detail || `HTTP ${response.status}`);
  return response.json() as Promise<T>;
}
const formatNumber = (value?: number) => new Intl.NumberFormat("zh-CN").format(value || 0);
const labelPlatform = (platform?: string | null) => PLATFORM_LABELS[platform || ""] || platform || "-";
const labelOpportunityType = (value: DashboardOpportunity["type"]) => ({ creator: "达人", keyword: "关键词", competitor: "友商", content: "内容" }[value]);
const formatSigned = (value?: number) => `${Number(value || 0) > 0 ? "+" : ""}${Number(value || 0).toFixed(1)}`;
const formatDateTime = (value?: string | null) => {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
};
const fallbackDashboard = (): DashboardSummary => ({
  decision: { headline: "等待数据形成增长判断", confidence: "low", sample_status: "insufficient", sample_summary: "暂无足够样本。", risk_notes: ["先采集样本后再生成机会榜。"], evidence_count: 0 },
  actions: { do_now: [], watch_today: [], defer: [] },
  monitoring: { running_jobs: 0, today_collected: 0, errors: 0, monitor_pools: 0, realtime_jobs: 0, last_updated_at: null },
  opportunities: [],
  top_opportunities: [],
  watchlist: [],
  ignored_opportunities: [],
  diagnostics: [{ code: "no_data", title: "暂无机会判断", body: "先采集样本后再生成机会榜。" }],
  scoring_profile: { weights: { heat_growth: 0.35, sample_confidence: 0.25, competition_gap: 0.2, actionability: 0.2 }, window: "7d_plus_24h" },
});
const fallbackScoreBreakdown = (item: DashboardOpportunity) => item.score_breakdown || {
  heat_growth: Number(item.score || 0),
  sample_confidence: item.confidence === "high" ? 85 : item.confidence === "medium" ? 65 : 35,
  competition_gap: Number(item.score || 0),
  actionability: Number(item.score || 0),
};
const opportunityChange24h = (item: DashboardOpportunity) => Number(item.trend?.change_24h ?? item.change_24h ?? 0);
const opportunityTrendPoints = (item: DashboardOpportunity) => {
  const points = item.trend?.points_7d?.length ? item.trend.points_7d : item.detail?.trend_30d?.slice(-7);
  return (points || []).map((point, index) => ({ label: String(point.date || point.day || point.snapshot_date || index + 1), score: Number(point.score || point.value || point.heat_score || point.count || item.score || 0) }));
};
const opportunityActions = (item: DashboardOpportunity): OpportunityAction[] => (item.actions || []).map((action) => typeof action === "string" ? { kind: action, label: action === "view_evidence" ? "查看证据" : "预填任务", risk: action === "view_evidence" ? "low" : "high", payload: item.payload || {} } : action);
const executableAction = (item: DashboardOpportunity) => opportunityActions(item).find((action) => action.risk === "high") || opportunityActions(item).find((action) => action.kind !== "view_evidence");
const opportunityPayload = (item: DashboardOpportunity) => executableAction(item)?.payload || item.payload || {};
const compactJson = (value?: Record<string, unknown> | null) => !value || !Object.keys(value).length ? "-" : Object.entries(value).slice(0, 4).map(([key, item]) => `${key}: ${typeof item === "object" ? JSON.stringify(item).slice(0, 42) : String(item)}`).join(" / ");

function App() {
  const [tab, setTab] = React.useState<Tab>("overview");
  const [dashboard, setDashboard] = React.useState<DashboardSummary>(fallbackDashboard);
  const [jobs, setJobs] = React.useState<ResearchJob[]>([]);
  const [selectedJobId, setSelectedJobId] = React.useState<number | null>(null);
  const [posts, setPosts] = React.useState<PostRecord[]>([]);
  const [comments, setComments] = React.useState<CommentRecord[]>([]);
  const [rawRecords, setRawRecords] = React.useState<RawRecord[]>([]);
  const [aiResults, setAiResults] = React.useState<AIResult[]>([]);
  const [selectedOpportunity, setSelectedOpportunity] = React.useState<DashboardOpportunity | null>(null);
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
  const refreshAll = React.useCallback(async () => {
    setLoading(true);
    try {
      await Promise.allSettled([loadDashboardSummary(), loadJobs()]);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, [loadDashboardSummary, loadJobs]);

  React.useEffect(() => { void refreshAll(); }, [refreshAll]);
  React.useEffect(() => { void loadSelected(selectedJobId); }, [loadSelected, selectedJobId]);

  async function submitOpportunityFeedback(opportunity: DashboardOpportunity, feedback: "valid" | "false_positive" | "watch", note = "") {
    await api<{ feedback: Record<string, unknown> }>("/api/reports/opportunity-feedback", {
      method: "POST",
      body: JSON.stringify({ opportunity_id: opportunity.id, opportunity_type: opportunity.type, opportunity_name: opportunity.name, feedback, note, payload: { score: opportunity.score, risk_tags: opportunity.risk_tags || [] } }),
    });
    await loadDashboardSummary();
  }
  function requestOpportunityExecution(opportunity: DashboardOpportunity) {
    const action = executableAction(opportunity);
    setPendingExecution({ title: opportunity.name, action: action?.kind || "prefill_collection_task", targetType: opportunity.type, platform: opportunity.platform, payload: opportunityPayload(opportunity) });
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand"><BarChart3 /><strong>MindPulse</strong></div>
        <nav>
          <button className={tab === "overview" ? "active" : ""} onClick={() => setTab("overview")}><Activity size={18} />老板看板</button>
          <button className={tab === "data" ? "active" : ""} onClick={() => setTab("data")}><Table2 size={18} />数据浏览</button>
        </nav>
      </aside>
      <main className="workspace">
        <section className="title-row">
          <div><p className="eyebrow">MINDPULSE / {tab === "overview" ? "老板机会决策" : "数据浏览"}</p><h1>{tab === "overview" ? "老板机会决策看板" : "数据浏览"}</h1><p>用标准化评分、风险、证据和反馈闭环支撑运营决策。</p></div>
          <div className="title-actions"><button onClick={refreshAll}>{loading ? <Loader2 className="spin" size={16} /> : <RefreshCw size={16} />}刷新</button></div>
        </section>
        {error && <div className="notice error"><AlertTriangle size={16} />{error}</div>}
        {tab === "overview" && <BossDashboardOverviewPage dashboard={dashboard} onRefreshDashboard={loadDashboardSummary} onViewOpportunity={setSelectedOpportunity} onRequestExecution={requestOpportunityExecution} />}
        {tab === "data" && <DataPage selectedJob={selectedJob} jobs={jobs} selectedJobId={selectedJobId} setSelectedJobId={setSelectedJobId} posts={posts} comments={comments} rawRecords={rawRecords} aiResults={aiResults} />}
      </main>
      {selectedOpportunity && <OpportunityDetailDrawer opportunity={selectedOpportunity} onClose={() => setSelectedOpportunity(null)} onExecute={requestOpportunityExecution} onFeedback={submitOpportunityFeedback} />}
      {pendingExecution && <ConfirmExecutionModal execution={pendingExecution} onCancel={() => setPendingExecution(null)} onConfirm={() => setPendingExecution(null)} />}
    </div>
  );
}

function BossDashboardOverviewPage({ dashboard, onRefreshDashboard, onViewOpportunity, onRequestExecution }: { dashboard: DashboardSummary; onRefreshDashboard: () => Promise<void>; onViewOpportunity: (item: DashboardOpportunity) => void; onRequestExecution: (item: DashboardOpportunity) => void }) {
  const top = dashboard.top_opportunities?.length ? dashboard.top_opportunities : dashboard.opportunities || [];
  const watchlist = dashboard.watchlist || [];
  const [selectedId, setSelectedId] = React.useState<string | null>(null);
  const selected = [...top, ...watchlist].find((item) => item.id === selectedId) || top[0] || watchlist[0] || null;
  const select = (item: DashboardOpportunity) => { setSelectedId(item.id); onViewOpportunity(item); };
  return (
    <section className="growth-workspace">
      <div className="boss-dashboard-grid wide-main">
        <OpportunityDecisionBoard top={top} watchlist={watchlist} selectedId={selected?.id || null} onSelect={select} />
        <OpportunityExplanationPanel opportunity={selected} onExecute={onRequestExecution} onRefresh={onRefreshDashboard} />
      </div>
      <OpportunityAnalyticsSection opportunities={top} watchlist={watchlist} />
      <DiagnosticPanel diagnostics={dashboard.diagnostics || []} />
      <MonitoringCards monitoring={dashboard.monitoring} />
    </section>
  );
}

function OpportunityDecisionBoard({ top, watchlist, selectedId, onSelect }: { top: DashboardOpportunity[]; watchlist: DashboardOpportunity[]; selectedId: string | null; onSelect: (item: DashboardOpportunity) => void }) {
  return <section className="panel opportunity-decision-board"><div className="panel-head"><div><h2>机会决策榜</h2><p>Top 5 直接决策，观察池保留待验证信号。</p></div><span>{top.length} / {watchlist.length}</span></div><div className="opportunity-list"><strong>Top 5</strong>{top.map((item) => <OpportunityCard key={item.id} item={item} active={item.id === selectedId} onSelect={onSelect} />)}{!top.length && <EmptyState title="暂无 Top 机会" body="样本不足或机会被诊断规则拦截时，会先进入观察池。" />}</div><div className="opportunity-list watch"><strong>观察池</strong>{watchlist.map((item) => <OpportunityCard key={item.id} item={item} active={item.id === selectedId} onSelect={onSelect} />)}{!watchlist.length && <p className="muted">暂无需要观察的机会。</p>}</div></section>;
}
function OpportunityCard({ item, active, onSelect }: { item: DashboardOpportunity; active: boolean; onSelect: (item: DashboardOpportunity) => void }) {
  return <button className={`opportunity-card ${active ? "active" : ""}`} type="button" onClick={() => onSelect(item)}><div className="opportunity-card-head"><span className="type-chip">{labelOpportunityType(item.type)}</span><strong>{Math.round(item.score)}</strong></div><h3>{item.name}</h3><div className="opportunity-meta"><span>{labelPlatform(item.platform)}</span><span>24h {formatSigned(opportunityChange24h(item))}</span><span>{formatNumber(item.sample_scope?.sample_count || item.evidence_count || 0)} 样本</span></div><RiskStrip risks={item.risk_tags || []} /></button>;
}
function OpportunityExplanationPanel({ opportunity, onExecute, onRefresh }: { opportunity: DashboardOpportunity | null; onExecute: (item: DashboardOpportunity) => void; onRefresh: () => Promise<void> }) {
  if (!opportunity) return <section className="panel opportunity-explanation"><div className="panel-head"><h2>解释面板</h2><button onClick={onRefresh}><RefreshCw size={16} />刷新</button></div><EmptyState title="暂无可解释机会" body="采集或回放完成后，这里会显示被选中机会的评分、证据和风险。" /></section>;
  const summaries = opportunity.evidence_summary?.length ? opportunity.evidence_summary : opportunity.detail?.summary || [opportunity.reason || "暂无摘要"];
  return <section className="panel opportunity-explanation"><div className="panel-head"><div><h2>{opportunity.name}</h2><p>{labelOpportunityType(opportunity.type)} / {labelPlatform(opportunity.platform)}</p></div><strong className="score-badge">{Math.round(opportunity.score)}</strong></div><OpportunityScoreBars opportunity={opportunity} /><OpportunityTrendChart opportunity={opportunity} /><PlatformSignalChart opportunities={[opportunity]} /><RiskStrip risks={opportunity.risk_tags || []} /><div className="evidence-summary">{summaries.slice(0, 4).map((item) => <p key={item}>{item}</p>)}</div><div className="button-row"><button type="button" onClick={() => onExecute(opportunity)}><SquarePen size={16} />预填/确认动作</button></div></section>;
}
function OpportunityScoreBars({ opportunity }: { opportunity: DashboardOpportunity }) {
  const breakdown = fallbackScoreBreakdown(opportunity);
  return <div className="score-bars">{scoreParts.map(([key, label]) => <div className="score-bar" key={key}><span>{label}</span><div><i style={{ width: `${Math.max(0, Math.min(100, breakdown[key]))}%` }} /></div><strong>{Math.round(breakdown[key])}</strong></div>)}</div>;
}
function OpportunityTrendChart({ opportunity }: { opportunity: DashboardOpportunity }) {
  const data = opportunityTrendPoints(opportunity);
  return <div className="mini-chart"><div className="chart-note">24h {formatSigned(opportunityChange24h(opportunity))}</div><ResponsiveContainer width="100%" height={150}><LineChart data={data.length ? data : [{ label: "now", score: opportunity.score }]}><CartesianGrid strokeDasharray="3 3" vertical={false} /><XAxis dataKey="label" /><YAxis domain={[0, 100]} /><Tooltip /><Line dataKey="score" stroke="#04786f" strokeWidth={2} dot={false} /></LineChart></ResponsiveContainer></div>;
}
function PlatformSignalChart({ opportunities }: { opportunities: DashboardOpportunity[] }) {
  const rows = opportunities.reduce<Array<{ platform: string; score: number; samples: number }>>((acc, item) => {
    const platforms = item.sample_scope?.platforms?.length ? item.sample_scope.platforms : [item.platform || "unknown"];
    platforms.forEach((platform) => { let row = acc.find((entry) => entry.platform === platform); if (!row) { row = { platform, score: 0, samples: 0 }; acc.push(row); } row.score += item.score; row.samples += item.sample_scope?.sample_count || item.evidence_count || 1; });
    return acc;
  }, []);
  return <ResponsiveContainer width="100%" height={150}><BarChart data={rows}><CartesianGrid strokeDasharray="3 3" vertical={false} /><XAxis dataKey="platform" tickFormatter={labelPlatform} /><YAxis /><Tooltip /><Bar dataKey="score" fill="#2563eb" radius={[6, 6, 0, 0]} /></BarChart></ResponsiveContainer>;
}
function OpportunityAnalyticsSection({ opportunities, watchlist }: { opportunities: DashboardOpportunity[]; watchlist: DashboardOpportunity[] }) {
  const all = [...opportunities, ...watchlist];
  return <section className="opportunity-analytics"><ChartCard title="机会矩阵" subtitle="热度增长 x 竞争空档" empty={!all.length}><OpportunityMatrixChart opportunities={all} /></ChartCard><ChartCard title="风险分布" subtitle="按风险标签聚合" empty={!all.length}><RiskDistributionChart opportunities={all} /></ChartCard><ChartCard title="竞争空档排行" subtitle="优先看高空档机会" empty={!all.length}><CompetitionGapRanking opportunities={all} /></ChartCard></section>;
}
function OpportunityMatrixChart({ opportunities }: { opportunities: DashboardOpportunity[] }) {
  const rows = opportunities.map((item) => ({ name: item.name, heat: fallbackScoreBreakdown(item).heat_growth, gap: fallbackScoreBreakdown(item).competition_gap, size: Math.max(30, item.sample_scope?.sample_count || item.evidence_count || 20) }));
  return <ResponsiveContainer width="100%" height={260}><ScatterChart><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="heat" name="热度" domain={[0, 100]} /><YAxis dataKey="gap" name="空档" domain={[0, 100]} /><ZAxis dataKey="size" range={[60, 320]} /><Tooltip cursor={{ strokeDasharray: "3 3" }} /><Scatter data={rows} fill="#04786f" /></ScatterChart></ResponsiveContainer>;
}
function RiskDistributionChart({ opportunities }: { opportunities: DashboardOpportunity[] }) {
  const counts = new Map<string, number>();
  opportunities.forEach((item) => (item.risk_tags?.length ? item.risk_tags : ["none"]).forEach((risk) => counts.set(risk, (counts.get(risk) || 0) + 1)));
  const rows = [...counts.entries()].map(([name, value]) => ({ name: name === "none" ? "无风险标签" : RISK_LABELS[name as OpportunityRiskTag] || name, value }));
  return <ResponsiveContainer width="100%" height={240}><PieChart><Pie data={rows} dataKey="value" nameKey="name" outerRadius={82}>{rows.map((_, index) => <Cell key={index} fill={CHART_COLORS[index % CHART_COLORS.length]} />)}</Pie><Tooltip /></PieChart></ResponsiveContainer>;
}
function CompetitionGapRanking({ opportunities }: { opportunities: DashboardOpportunity[] }) {
  const rows = opportunities.map((item) => ({ name: item.name, value: fallbackScoreBreakdown(item).competition_gap })).sort((a, b) => b.value - a.value).slice(0, 8);
  return <ResponsiveContainer width="100%" height={240}><BarChart data={rows} layout="vertical"><CartesianGrid strokeDasharray="3 3" horizontal={false} /><XAxis type="number" domain={[0, 100]} /><YAxis type="category" dataKey="name" width={90} /><Tooltip /><Bar dataKey="value" fill="#ff9f1c" radius={[0, 6, 6, 0]} /></BarChart></ResponsiveContainer>;
}
function DiagnosticPanel({ diagnostics }: { diagnostics: Array<{ code: string; title: string; body: string; action?: string }> }) {
  if (!diagnostics.length) return null;
  return <section className="diagnostic-panel">{diagnostics.map((item) => <div className="diagnostic-card" key={item.code}><strong>{item.title}</strong><p>{item.body}</p>{item.action && <small>{item.action}</small>}</div>)}</section>;
}
function MonitoringCards({ monitoring }: { monitoring: DashboardSummary["monitoring"] }) {
  const cards = [{ label: "运行任务", value: monitoring.running_jobs }, { label: "今日采集", value: monitoring.today_collected }, { label: "监控池", value: monitoring.monitor_pools }, { label: "异常", value: monitoring.errors }];
  return <section className="monitoring-cards">{cards.map((item) => <div className="metric-card compact" key={item.label}><span>{item.label}</span><strong>{formatNumber(Number(item.value || 0))}</strong></div>)}</section>;
}
function RiskStrip({ risks }: { risks: OpportunityRiskTag[] }) {
  return <div className="risk-strip">{risks.length ? risks.map((risk) => <span className="risk-chip" key={risk}>{RISK_LABELS[risk] || risk}</span>) : <span className="risk-chip quiet">暂无高风险</span>}</div>;
}

function OpportunityDetailDrawer({ opportunity, onClose, onExecute, onFeedback }: { opportunity: DashboardOpportunity; onClose: () => void; onExecute: (item: DashboardOpportunity) => void; onFeedback: (item: DashboardOpportunity, feedback: "valid" | "false_positive" | "watch") => Promise<void> }) {
  const [busy, setBusy] = React.useState<"valid" | "false_positive" | "watch" | null>(null);
  async function send(feedback: "valid" | "false_positive" | "watch") { setBusy(feedback); try { await onFeedback(opportunity, feedback); if (feedback !== "valid") onClose(); } finally { setBusy(null); } }
  return <div className="drawer-backdrop" role="presentation" onClick={onClose}><aside className="opportunity-drawer" role="dialog" aria-modal="true" aria-label="机会详情" onClick={(event) => event.stopPropagation()}><div className="drawer-head"><div><span className="type-chip">{labelOpportunityType(opportunity.type)}</span><h2>{opportunity.name}</h2><p>{labelPlatform(opportunity.platform)} / 综合分 {Math.round(opportunity.score)}</p></div><button type="button" onClick={onClose}><X size={18} /></button></div><section className="drawer-section"><h3>评分拆解</h3><OpportunityScoreBars opportunity={opportunity} /></section><section className="drawer-section"><h3>样本范围</h3><div className="drawer-metrics"><MiniStat value={opportunity.sample_scope?.window || "-"} label="窗口" /><MiniStat value={formatNumber(opportunity.sample_scope?.sample_count || opportunity.evidence_count || 0)} label="样本数" /><MiniStat value={(opportunity.sample_scope?.platforms || [opportunity.platform || "-"]).map(labelPlatform).join(" / ")} label="平台" /></div></section><section className="drawer-section"><h3>趋势与平台贡献</h3><OpportunityTrendChart opportunity={opportunity} /><PlatformSignalChart opportunities={[opportunity]} /></section><section className="drawer-section"><h3>风险</h3><RiskStrip risks={opportunity.risk_tags || []} /></section><section className="drawer-section"><h3>证据摘要</h3>{(opportunity.evidence_summary?.length ? opportunity.evidence_summary : opportunity.detail?.summary || []).map((item) => <p key={item}>{item}</p>)}</section><section className="drawer-section"><h3>证据样本</h3><EvidenceSamplePanel samples={opportunity.samples || []} /></section><section className="drawer-section"><h3>反馈</h3><div className="feedback-row"><button className={opportunity.feedback_state === "valid" ? "active" : ""} disabled={!!busy} onClick={() => send("valid")}>有效</button><button disabled={!!busy} onClick={() => send("false_positive")}>误判</button><button disabled={!!busy} onClick={() => send("watch")}>先观察</button></div></section><div className="drawer-actions"><button type="button" onClick={onClose}>关闭</button><button className="primary" type="button" onClick={() => onExecute(opportunity)}><Play size={16} />预填/确认执行</button></div></aside></div>;
}
function EvidenceSamplePanel({ samples }: { samples: OpportunitySample[] }) {
  const visible = samples.slice(0, 10);
  if (!visible.length) return <p className="muted">暂无 typed evidence samples。</p>;
  return <div className="evidence-samples">{visible.map((sample, index) => <EvidenceSampleCard key={index} sample={sample} />)}</div>;
}
function EvidenceSampleCard({ sample }: { sample: OpportunitySample }) {
  return <article className="evidence-sample"><div className="evidence-sample-head"><span className="type-chip">{sample.type}</span><span>{labelPlatform(sample.platform)} / {formatDateTime(sample.publish_time)}</span></div><strong>{sample.title || sample.body?.slice(0, 60) || "未命名样本"}</strong>{sample.body && <p>{sample.body}</p>}<small>{compactJson(sample.engagement)}</small>{!!sample.matched_terms?.length && <div className="risk-strip">{sample.matched_terms.map((term) => <span className="risk-chip quiet" key={term}>{term}</span>)}</div>}{sample.url && <a href={sample.url} target="_blank" rel="noreferrer">打开原文</a>}</article>;
}
function ConfirmExecutionModal({ execution, onCancel, onConfirm }: { execution: PendingExecution; onCancel: () => void; onConfirm: () => void }) {
  return <div className="modal-backdrop" role="presentation"><section className="confirm-modal" role="dialog" aria-modal="true" aria-label="确认执行"><div className="panel-head"><div><h2>确认执行高风险动作</h2><p>真实平台搜索或主页采集可能消耗额度，并受平台风控影响。</p></div><button onClick={onCancel}><X size={18} /></button></div><div className="confirm-grid"><span>对象</span><strong>{execution.title}</strong><span>类型</span><strong>{labelOpportunityType(execution.targetType)}</strong><span>平台</span><strong>{labelPlatform(execution.platform)}</strong><span>动作</span><strong>{execution.action}</strong></div><pre className="console-output">{JSON.stringify(execution.payload, null, 2)}</pre><div className="button-row right"><button onClick={onCancel}>取消</button><button className="primary" onClick={onConfirm}><Play size={16} />确认</button></div></section></div>;
}

function DataPage({ selectedJob, jobs, selectedJobId, setSelectedJobId, posts, comments, rawRecords, aiResults }: { selectedJob: ResearchJob | null; jobs: ResearchJob[]; selectedJobId: number | null; setSelectedJobId: (id: number) => void; posts: PostRecord[]; comments: CommentRecord[]; rawRecords: RawRecord[]; aiResults: AIResult[] }) {
  const [kind, setKind] = React.useState<"posts" | "comments" | "raw" | "ai">("posts");
  const [query, setQuery] = React.useState("");
  const rows = kind === "posts" ? posts : kind === "comments" ? comments : kind === "raw" ? rawRecords : aiResults;
  const filtered = rows.filter((row) => JSON.stringify(row).toLowerCase().includes(query.toLowerCase()));
  return <section className="data-browser"><div className="panel"><div className="panel-head"><div><h2>数据浏览</h2><p>{selectedJob ? `当前任务：${selectedJob.name}` : "请选择任务后查看采集数据"}</p></div><div className="search-box compact"><Search size={16} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索当前数据..." /></div></div>{jobs.length > 0 && <div className="segmented">{jobs.slice(0, 8).map((job) => <button key={job.id} className={selectedJobId === job.id ? "active" : ""} onClick={() => setSelectedJobId(job.id)}>{job.name}</button>)}</div>}<DataBrowserInsights selectedJob={selectedJob} posts={posts} comments={comments} rawRecords={rawRecords} aiResults={aiResults} /><div className="segmented"><button className={kind === "posts" ? "active" : ""} onClick={() => setKind("posts")}>帖子 {posts.length}</button><button className={kind === "comments" ? "active" : ""} onClick={() => setKind("comments")}>评论 {comments.length}</button><button className={kind === "raw" ? "active" : ""} onClick={() => setKind("raw")}>原始记录 {rawRecords.length}</button><button className={kind === "ai" ? "active" : ""} onClick={() => setKind("ai")}>AI 结果 {aiResults.length}</button></div>{filtered.length ? <DataTable kind={kind} rows={filtered} /> : <EmptyState title="暂无数据" body="执行采集、回填或 AI 分析后，这里会展示可检索的数据样本。" />}</div></section>;
}
function platformRows(posts: PostRecord[], comments: CommentRecord[]) {
  const counts = new Map<string, { platform: string; posts: number; comments: number }>();
  posts.forEach((post) => { const row = counts.get(post.platform) || { platform: post.platform, posts: 0, comments: 0 }; row.posts += 1; counts.set(post.platform, row); });
  comments.forEach((comment) => { const row = counts.get(comment.platform) || { platform: comment.platform, posts: 0, comments: 0 }; row.comments += 1; counts.set(comment.platform, row); });
  return [...counts.values()];
}
function buildPublishDateRows(posts: PostRecord[], comments: CommentRecord[]) {
  const counts = new Map<string, { date: string; posts: number; comments: number }>();
  posts.forEach((item) => { const date = (item.publish_time || "").slice(0, 10) || "unknown"; const row = counts.get(date) || { date, posts: 0, comments: 0 }; row.posts += 1; counts.set(date, row); });
  comments.forEach((item) => { const date = (item.publish_time || "").slice(0, 10) || "unknown"; const row = counts.get(date) || { date, posts: 0, comments: 0 }; row.comments += 1; counts.set(date, row); });
  return [...counts.values()].sort((a, b) => a.date.localeCompare(b.date)).slice(-14);
}
function buildKeywordHitRows(posts: PostRecord[], selectedJob: ResearchJob | null) {
  const keywords = selectedJob?.keywords?.length ? selectedJob.keywords : Array.from(new Set(posts.map((post) => String(post.engagement_json?.source_keyword || "")).filter(Boolean)));
  return keywords.map((keyword) => ({ keyword, count: posts.filter((post) => `${post.title || ""} ${post.content || ""} ${String(post.engagement_json?.source_keyword || "")}`.toLowerCase().includes(keyword.toLowerCase())).length })).filter((row) => row.count > 0).sort((a, b) => b.count - a.count).slice(0, 8);
}
function DataBrowserInsights({ selectedJob, posts, comments, rawRecords, aiResults }: { selectedJob: ResearchJob | null; posts: PostRecord[]; comments: CommentRecord[]; rawRecords: RawRecord[]; aiResults: AIResult[] }) {
  const platforms = platformRows(posts, comments);
  const publishRows = buildPublishDateRows(posts, comments);
  const keywordRows = buildKeywordHitRows(posts, selectedJob);
  const dates = [...posts.map((item) => item.publish_time), ...comments.map((item) => item.publish_time)].filter(Boolean).sort() as string[];
  const qualityRows = [{ label: "有标题", value: posts.filter((item) => item.title).length, total: posts.length }, { label: "有正文", value: posts.filter((item) => item.content).length, total: posts.length }, { label: "有时间", value: posts.filter((item) => item.publish_time).length + comments.filter((item) => item.publish_time).length, total: posts.length + comments.length }, { label: "AI覆盖", value: aiResults.length, total: Math.max(1, posts.length + comments.length) }];
  const lastDate = dates.length ? dates[dates.length - 1] : null;
  return <section className="data-insights"><div className="metric-card compact"><span>样本数</span><strong>{formatNumber(posts.length + comments.length)}</strong><small>帖子 {posts.length} / 评论 {comments.length}</small></div><div className="metric-card compact"><span>时间范围</span><strong>{dates[0] ? formatDateTime(dates[0]) : "-"}</strong><small>{lastDate ? `至 ${formatDateTime(lastDate)}` : "暂无发布时间"}</small></div><ChartCard title="平台比较" subtitle="帖子与评论量" empty={!platforms.length}><ResponsiveContainer width="100%" height={220}><BarChart data={platforms}><CartesianGrid strokeDasharray="3 3" vertical={false} /><XAxis dataKey="platform" tickFormatter={labelPlatform} /><YAxis /><Tooltip /><Bar dataKey="posts" fill="#04786f" radius={[6, 6, 0, 0]} /><Bar dataKey="comments" fill="#2563eb" radius={[6, 6, 0, 0]} /></BarChart></ResponsiveContainer></ChartCard><ChartCard title="发布时间分布" subtitle="最近 14 个日期桶" empty={!publishRows.length}><ResponsiveContainer width="100%" height={220}><AreaChart data={publishRows}><CartesianGrid strokeDasharray="3 3" vertical={false} /><XAxis dataKey="date" /><YAxis /><Tooltip /><Area dataKey="posts" stackId="1" fill="#04786f" stroke="#04786f" /><Area dataKey="comments" stackId="1" fill="#94a3b8" stroke="#64748b" /></AreaChart></ResponsiveContainer></ChartCard><ChartCard title="关键词命中" subtitle="任务关键词与 source_keyword" empty={!keywordRows.length}><ResponsiveContainer width="100%" height={220}><BarChart data={keywordRows} layout="vertical"><CartesianGrid strokeDasharray="3 3" horizontal={false} /><XAxis type="number" /><YAxis type="category" dataKey="keyword" width={90} /><Tooltip /><Bar dataKey="count" fill="#ff9f1c" radius={[0, 6, 6, 0]} /></BarChart></ResponsiveContainer></ChartCard><div className="panel data-quality"><div className="panel-head compact"><h2>数据质量</h2><span>Raw {rawRecords.length}</span></div>{qualityRows.map((row) => <div className="quality-row" key={row.label}><span>{row.label}</span><div><i style={{ width: `${Math.round((row.value / Math.max(1, row.total)) * 100)}%` }} /></div><strong>{row.value}/{row.total}</strong></div>)}</div></section>;
}
function DataTable({ kind, rows }: { kind: "posts" | "comments" | "raw" | "ai"; rows: Array<PostRecord | CommentRecord | RawRecord | AIResult> }) {
  return <div className="table-wrap data-table"><table><thead>{kind === "posts" && <tr><th>标题</th><th>平台</th><th>ID</th><th>发布时间</th><th>互动</th></tr>}{kind === "comments" && <tr><th>评论</th><th>平台</th><th>帖子 ID</th><th>发布时间</th><th>点赞</th></tr>}{kind === "raw" && <tr><th>来源</th><th>平台</th><th>Hash</th><th>解析版本</th><th>抓取时间</th></tr>}{kind === "ai" && <tr><th>对象</th><th>模型</th><th>结果摘要</th><th>时间</th></tr>}</thead><tbody>{rows.map((row) => { if (kind === "posts") { const item = row as PostRecord; return <tr key={item.id}><td><strong>{item.title || "无标题"}</strong><small>{item.content?.slice(0, 100) || item.url || "-"}</small></td><td>{labelPlatform(item.platform)}</td><td>{item.platform_post_id}</td><td>{formatDateTime(item.publish_time)}</td><td>{compactJson(item.engagement_json)}</td></tr>; } if (kind === "comments") { const item = row as CommentRecord; return <tr key={item.id}><td><strong>{item.content?.slice(0, 120) || "-"}</strong><small>{item.platform_comment_id}</small></td><td>{labelPlatform(item.platform)}</td><td>{item.platform_post_id || "-"}</td><td>{formatDateTime(item.publish_time)}</td><td>{item.like_count || 0}</td></tr>; } if (kind === "raw") { const item = row as RawRecord; return <tr key={item.id}><td><strong>{item.source_type}</strong><small>{item.source_id || "-"}</small></td><td>{labelPlatform(item.platform)}</td><td>{item.payload_hash}</td><td>{item.parser_version || "-"}</td><td>{formatDateTime(item.fetched_at)}</td></tr>; } const item = row as AIResult; return <tr key={item.id}><td><strong>{item.target_type}</strong><small>{item.target_id}</small></td><td>{item.model}</td><td><span className="json-preview">{compactJson(item.result_json)}</span></td><td>{formatDateTime(item.created_at)}</td></tr>; })}</tbody></table></div>;
}

function MiniStat({ value, label }: { value: number | string; label: string }) { return <div className="mini-stat"><strong>{typeof value === "number" ? formatNumber(value) : value}</strong><span>{label}</span></div>; }
function ChartCard({ title, subtitle, children, empty }: { title: string; subtitle: string; children: React.ReactNode; empty?: boolean }) { return <article className="panel chart-card"><div className="panel-head"><div><h2>{title}</h2><p>{subtitle}</p></div></div>{empty ? <EmptyState title="暂无图表数据" body="采集或分析后会自动生成图表。" /> : children}</article>; }
function EmptyState({ title, body }: { title: string; body: string }) { return <div className="empty-state"><Eye size={18} /><strong>{title}</strong><p>{body}</p></div>; }

createRoot(document.getElementById("root")!).render(<App />);
