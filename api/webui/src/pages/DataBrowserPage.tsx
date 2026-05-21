import React from "react";
import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Database,
  FileSearch,
  ListFilter,
  Play,
  RefreshCw,
  RotateCcw,
  Search,
} from "lucide-react";
import { Area, AreaChart, Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { buildKeywordHitRows, buildPublishDateRows, ChartCard, platformRows } from "../components/charts";
import { Badge, Button, Card, CardDescription, CardHeader, CardTitle } from "../components/ui";
import { api } from "../utils/api";
import { compactJson, formatDateTime, formatNumber, labelPlatform } from "../utils/format";
import type { AIResult, CommentRecord, PostRecord, RawRecord, ResearchJob } from "../types";

type DataKind = "posts" | "comments" | "raw" | "ai";
type TaskFilter = "with_data" | "all" | "pending" | "completed" | "failed";

type JobStats = {
  posts: number;
  comments: number;
  authors?: number;
  raw_records?: number;
};

type TaskSummary = {
  posts: number;
  comments: number;
  raw: number;
  ai: number;
  loaded: boolean;
};

type ResearchEvent = {
  id: number;
  job_id: number;
  platform?: string | null;
  event_type: string;
  message: string;
  stats_json?: Record<string, unknown> | string | null;
  created_at?: string | null;
};

const EMPTY_SUMMARY: TaskSummary = { posts: 0, comments: 0, raw: 0, ai: 0, loaded: false };
const FAILURE_EVENT_TYPES = new Set(["crawler_start_failed", "execution_failed", "crawl_unit_failed"]);
const FILTERS: Array<{ value: TaskFilter; label: string }> = [
  { value: "with_data", label: "有数据" },
  { value: "all", label: "全部" },
  { value: "pending", label: "待执行" },
  { value: "completed", label: "已完成" },
  { value: "failed", label: "失败" },
];

export function DataBrowserPage({
  selectedJob,
  jobs,
  selectedJobId,
  setSelectedJobId,
  posts,
  comments,
  rawRecords,
  aiResults,
}: {
  selectedJob: ResearchJob | null;
  jobs: ResearchJob[];
  selectedJobId: number | null;
  setSelectedJobId: (id: number) => void;
  posts: PostRecord[];
  comments: CommentRecord[];
  rawRecords: RawRecord[];
  aiResults: AIResult[];
}) {
  const [kind, setKind] = React.useState<DataKind>("posts");
  const [query, setQuery] = React.useState("");
  const [taskPanelOpen, setTaskPanelOpen] = React.useState(false);
  const [eventPanelOpen, setEventPanelOpen] = React.useState(false);
  const [taskFilter, setTaskFilter] = React.useState<TaskFilter>("with_data");
  const [taskSummaries, setTaskSummaries] = React.useState<Record<number, TaskSummary>>({});
  const [events, setEvents] = React.useState<ResearchEvent[]>([]);
  const [statsLoaded, setStatsLoaded] = React.useState(false);
  const [eventsLoaded, setEventsLoaded] = React.useState(false);

  const selectedCounts = React.useMemo(
    () => ({
      posts: posts.length,
      comments: comments.length,
      raw: rawRecords.length,
      ai: aiResults.length,
      loaded: true,
    }),
    [aiResults.length, comments.length, posts.length, rawRecords.length],
  );

  React.useEffect(() => {
    if (!jobs.length) {
      setTaskSummaries({});
      setStatsLoaded(true);
      return;
    }

    let cancelled = false;
    setStatsLoaded(false);

    async function loadTaskSummaries() {
      const entries = await Promise.all(
        jobs.map(async (job) => {
          try {
            const [statsResponse, aiResponse] = await Promise.allSettled([
              api<JobStats>(`/api/research/jobs/${job.id}/stats`),
              api<{ results: AIResult[] }>(`/api/research/jobs/${job.id}/ai/results`),
            ]);
            const stats = statsResponse.status === "fulfilled" ? statsResponse.value : null;
            const results = aiResponse.status === "fulfilled" ? aiResponse.value.results || [] : [];
            return [
              job.id,
              {
                posts: stats?.posts || 0,
                comments: stats?.comments || 0,
                raw: stats?.raw_records || 0,
                ai: results.length,
                loaded: true,
              },
            ] as const;
          } catch {
            return [job.id, { ...EMPTY_SUMMARY, loaded: true }] as const;
          }
        }),
      );

      if (!cancelled) {
        setTaskSummaries(Object.fromEntries(entries));
        setStatsLoaded(true);
      }
    }

    void loadTaskSummaries();
    return () => {
      cancelled = true;
    };
  }, [jobs]);

  React.useEffect(() => {
    if (!selectedJobId) {
      setEvents([]);
      setEventsLoaded(true);
      return;
    }

    let cancelled = false;
    setEventsLoaded(false);
    api<{ events: ResearchEvent[] }>(`/api/research/jobs/${selectedJobId}/events?limit=20`)
      .then((payload) => {
        if (!cancelled) setEvents(payload.events || []);
      })
      .catch(() => {
        if (!cancelled) setEvents([]);
      })
      .finally(() => {
        if (!cancelled) setEventsLoaded(true);
      });

    return () => {
      cancelled = true;
    };
  }, [selectedJobId]);

  const currentSummary = selectedJobId
    ? { ...(taskSummaries[selectedJobId] || EMPTY_SUMMARY), ...selectedCounts }
    : selectedCounts;
  const currentTotal = totalCount(currentSummary);
  const hasCurrentData = currentTotal > 0;
  const latestFailure = events.find((event) => FAILURE_EVENT_TYPES.has(event.event_type)) || null;
  const rows = kind === "posts" ? posts : kind === "comments" ? comments : kind === "raw" ? rawRecords : aiResults;
  const filteredRows = rows.filter((row) => JSON.stringify(row).toLowerCase().includes(query.toLowerCase()));
  const sortedJobs = React.useMemo(
    () => sortJobsForDataBrowser(jobs, taskSummaries, selectedJobId),
    [jobs, selectedJobId, taskSummaries],
  );
  const visibleJobs = sortedJobs.filter((job) => matchesTaskFilter(job, taskSummaries[job.id], taskFilter));
  const firstDataJob = sortedJobs.find((job) => totalCount(taskSummaries[job.id]) > 0);
  const statusView = getStatusView(selectedJob, currentSummary, latestFailure);

  function selectFirstDataJob() {
    if (!firstDataJob) return;
    setSelectedJobId(firstDataJob.id);
    setTaskPanelOpen(false);
  }

  return (
    <section className="data-browser">
      <div className="title-row compact data-browser-title">
        <div>
          <p className="eyebrow">DATA AUDIT</p>
          <h1>数据浏览</h1>
          <p>{selectedJob ? `当前任务：#${selectedJob.id} ${selectedJob.name}` : "请选择任务后查看采集数据"}</p>
        </div>
        <div className="search-box compact">
          <Search size={16} />
          <input value={query} onChange={(event) => setQuery(event.target.value)} aria-label="搜索当前数据" placeholder="搜索当前数据" />
        </div>
      </div>

      <TaskSummaryPanel
        selectedJob={selectedJob}
        summary={currentSummary}
        statusView={statusView}
        taskPanelOpen={taskPanelOpen}
        eventPanelOpen={eventPanelOpen}
        onToggleTasks={() => setTaskPanelOpen((open) => !open)}
        onToggleEvents={() => setEventPanelOpen((open) => !open)}
      />

      {taskPanelOpen && (
        <TaskSwitchPanel
          jobs={visibleJobs}
          summaries={taskSummaries}
          selectedJobId={selectedJobId}
          statsLoaded={statsLoaded}
          filter={taskFilter}
          setFilter={setTaskFilter}
          onSelect={(id) => {
            setSelectedJobId(id);
            setTaskPanelOpen(false);
          }}
        />
      )}

      {eventPanelOpen && (
        <EventPanel events={events} eventsLoaded={eventsLoaded} latestFailure={latestFailure} />
      )}

      <DataBrowserInsights selectedJob={selectedJob} posts={posts} comments={comments} rawRecords={rawRecords} aiResults={aiResults} />

      <DataKindTabs kind={kind} setKind={setKind} summary={currentSummary} />

      {filteredRows.length ? (
        <SampleCardList kind={kind} rows={filteredRows} />
      ) : (
        <ActionableEmptyState
          selectedJob={selectedJob}
          statusView={statusView}
          hasDataTask={!!firstDataJob}
          onSelectDataTask={selectFirstDataJob}
          onShowEvents={() => setEventPanelOpen(true)}
        />
      )}

      <DiagnosticStrip
        statsLoaded={statsLoaded}
        hasCurrentData={hasCurrentData}
        latestFailure={latestFailure}
      />
    </section>
  );
}

function TaskSummaryPanel({
  selectedJob,
  summary,
  statusView,
  taskPanelOpen,
  eventPanelOpen,
  onToggleTasks,
  onToggleEvents,
}: {
  selectedJob: ResearchJob | null;
  summary: TaskSummary;
  statusView: ReturnType<typeof getStatusView>;
  taskPanelOpen: boolean;
  eventPanelOpen: boolean;
  onToggleTasks: () => void;
  onToggleEvents: () => void;
}) {
  return (
    <Card className={`data-task-summary ${statusView.tone}`}>
      <div className="data-task-main">
        <div>
          <div className="data-task-kicker">
            <span>当前任务</span>
            <Badge tone={statusView.badgeTone}>{statusView.label}</Badge>
          </div>
          <h2>{selectedJob ? `#${selectedJob.id} ${selectedJob.name}` : "未选择任务"}</h2>
          <p>{statusView.description}</p>
        </div>
        <div className="data-task-actions">
          <Button variant="primary" onClick={onToggleTasks}>
            <ListFilter size={16} />
            {taskPanelOpen ? "收起任务" : "切换任务"}
          </Button>
          <Button variant={eventPanelOpen ? "primary" : "ghost"} onClick={onToggleEvents}>
            <FileSearch size={16} />
            查看日志
          </Button>
          <Button variant="ghost" disabled title="请从任务工作台执行重新采集">
            <RefreshCw size={16} />
            重新采集
          </Button>
          <Button variant="ghost" disabled title="请从任务工作台执行回填">
            <RotateCcw size={16} />
            回填旧数据
          </Button>
        </div>
      </div>
      <div className="data-task-metrics">
        <TaskMetric label="帖子" value={summary.posts} />
        <TaskMetric label="评论" value={summary.comments} />
        <TaskMetric label="Raw" value={summary.raw} />
        <TaskMetric label="AI" value={summary.ai} />
      </div>
    </Card>
  );
}

function TaskMetric({ label, value }: { label: string; value: number }) {
  return (
    <div className="data-task-metric">
      <strong>{formatNumber(value)}</strong>
      <span>{label}</span>
    </div>
  );
}

function TaskSwitchPanel({
  jobs,
  summaries,
  selectedJobId,
  statsLoaded,
  filter,
  setFilter,
  onSelect,
}: {
  jobs: ResearchJob[];
  summaries: Record<number, TaskSummary>;
  selectedJobId: number | null;
  statsLoaded: boolean;
  filter: TaskFilter;
  setFilter: (filter: TaskFilter) => void;
  onSelect: (id: number) => void;
}) {
  return (
    <Card className="task-switch-panel">
      <div className="task-switch-head">
        <div>
          <strong>任务列表</strong>
          <span>{statsLoaded ? "有数据任务优先显示" : "正在读取任务统计"}</span>
        </div>
        <div className="task-filter-tabs">
          {FILTERS.map((item) => (
            <Button key={item.value} size="sm" variant={filter === item.value ? "primary" : "ghost"} onClick={() => setFilter(item.value)}>
              {item.label}
            </Button>
          ))}
        </div>
      </div>
      <div className="task-row-list">
        {jobs.length ? (
          jobs.map((job) => (
            <TaskRow
              key={job.id}
              job={job}
              summary={summaries[job.id] || EMPTY_SUMMARY}
              active={selectedJobId === job.id}
              onSelect={() => onSelect(job.id)}
            />
          ))
        ) : (
          <div className="task-row-empty">当前筛选下没有任务</div>
        )}
      </div>
    </Card>
  );
}

function TaskRow({
  job,
  summary,
  active,
  onSelect,
}: {
  job: ResearchJob;
  summary: TaskSummary;
  active: boolean;
  onSelect: () => void;
}) {
  const status = getTaskRowStatus(job, summary);
  return (
    <button type="button" className={`task-row ${active ? "active" : ""}`} onClick={onSelect}>
      <div className="task-row-title">
        <strong>#{job.id}</strong>
        <span>{job.name}</span>
      </div>
      <Badge tone={status.badgeTone}>{status.label}</Badge>
      <div className="task-row-counts">
        <span>帖子 {formatNumber(summary.posts)}</span>
        <span>评论 {formatNumber(summary.comments)}</span>
        <span>Raw {formatNumber(summary.raw)}</span>
        <span>AI {formatNumber(summary.ai)}</span>
      </div>
    </button>
  );
}

function EventPanel({
  events,
  eventsLoaded,
  latestFailure,
}: {
  events: ResearchEvent[];
  eventsLoaded: boolean;
  latestFailure: ResearchEvent | null;
}) {
  return (
    <Card className="event-panel">
      <CardHeader>
        <div>
          <CardTitle>任务日志</CardTitle>
          <CardDescription>
            {latestFailure ? `最近失败：${latestFailure.event_type}` : "最近 20 条任务事件"}
          </CardDescription>
        </div>
      </CardHeader>
      <div className="event-list">
        {!eventsLoaded && <div className="task-row-empty">正在读取日志</div>}
        {eventsLoaded && !events.length && <div className="task-row-empty">暂无任务事件</div>}
        {eventsLoaded &&
          events.map((event) => (
            <div className={`event-row ${FAILURE_EVENT_TYPES.has(event.event_type) ? "failed" : ""}`} key={event.id}>
              <span>{formatDateTime(event.created_at)}</span>
              <strong>{event.event_type}</strong>
              <p>{event.message}</p>
            </div>
          ))}
      </div>
    </Card>
  );
}

function DataKindTabs({
  kind,
  setKind,
  summary,
}: {
  kind: DataKind;
  setKind: (kind: DataKind) => void;
  summary: TaskSummary;
}) {
  const items: Array<{ kind: DataKind; label: string; count: number }> = [
    { kind: "posts", label: "帖子", count: summary.posts },
    { kind: "comments", label: "评论", count: summary.comments },
    { kind: "raw", label: "原始记录", count: summary.raw },
    { kind: "ai", label: "AI 结果", count: summary.ai },
  ];
  return (
    <div className="data-kind-tabs" role="tablist" aria-label="数据类型">
      {items.map((item) => (
        <button key={item.kind} type="button" className={kind === item.kind ? "active" : ""} onClick={() => setKind(item.kind)}>
          {item.label} <strong>{formatNumber(item.count)}</strong>
        </button>
      ))}
    </div>
  );
}

function ActionableEmptyState({
  selectedJob,
  statusView,
  hasDataTask,
  onSelectDataTask,
  onShowEvents,
}: {
  selectedJob: ResearchJob | null;
  statusView: ReturnType<typeof getStatusView>;
  hasDataTask: boolean;
  onSelectDataTask: () => void;
  onShowEvents: () => void;
}) {
  const title = selectedJob ? statusView.emptyTitle : "请选择任务";
  const body = selectedJob ? statusView.emptyBody : "选择任务后，这里会展示可检索的数据样本。";
  return (
    <div className={`data-empty-state ${statusView.tone}`}>
      <div className="data-empty-icon">
        {statusView.tone === "danger" ? <AlertTriangle size={28} /> : <Database size={28} />}
      </div>
      <strong>{title}</strong>
      <p>{body}</p>
      <div className="data-empty-actions">
        <Button variant="primary" disabled={!hasDataTask} onClick={onSelectDataTask}>
          <Database size={16} />
          切换到有数据任务
        </Button>
        <Button variant="ghost" onClick={onShowEvents}>
          <FileSearch size={16} />
          查看失败原因
        </Button>
        <Button variant="ghost" disabled title="请从任务工作台执行回填">
          <RotateCcw size={16} />
          执行回填
        </Button>
        <Button variant="ghost" disabled title="请从任务工作台重新采集">
          <Play size={16} />
          重新采集
        </Button>
      </div>
    </div>
  );
}

function DiagnosticStrip({
  statsLoaded,
  hasCurrentData,
  latestFailure,
}: {
  statsLoaded: boolean;
  hasCurrentData: boolean;
  latestFailure: ResearchEvent | null;
}) {
  return (
    <div className="diagnostic-strip">
      <div className={statsLoaded ? "ok" : "warning"}>
        <CheckCircle2 size={16} />
        <span>{statsLoaded ? "数据库连接正常" : "正在读取数据库"}</span>
      </div>
      <div className={hasCurrentData ? "ok" : "warning"}>
        {hasCurrentData ? <CheckCircle2 size={16} /> : <AlertTriangle size={16} />}
        <span>{hasCurrentData ? "当前任务已有样本" : "当前任务无样本"}</span>
      </div>
      <div className={latestFailure ? "danger" : "ok"}>
        {latestFailure ? <AlertTriangle size={16} /> : <CheckCircle2 size={16} />}
        <span>{latestFailure ? `最近失败事件：${latestFailure.event_type}` : "未发现失败事件"}</span>
      </div>
    </div>
  );
}

function DataBrowserInsights({
  selectedJob,
  posts,
  comments,
  rawRecords,
  aiResults,
}: {
  selectedJob: ResearchJob | null;
  posts: PostRecord[];
  comments: CommentRecord[];
  rawRecords: RawRecord[];
  aiResults: AIResult[];
}) {
  const platforms = platformRows(posts, comments);
  const publishRows = buildPublishDateRows(posts, comments);
  const keywordRows = buildKeywordHitRows(posts, selectedJob);
  const dates = [...posts.map((item) => item.publish_time), ...comments.map((item) => item.publish_time)].filter(Boolean).sort() as string[];
  const lastDate = dates.length ? dates[dates.length - 1] : null;
  const qualityRows = [
    { label: "有标题", value: posts.filter((item) => item.title).length, total: posts.length },
    { label: "有正文", value: posts.filter((item) => item.content).length, total: posts.length },
    {
      label: "有时间",
      value: posts.filter((item) => item.publish_time).length + comments.filter((item) => item.publish_time).length,
      total: posts.length + comments.length,
    },
    { label: "AI 覆盖", value: aiResults.length, total: Math.max(1, posts.length + comments.length) },
  ];
  return (
    <section className="data-insights">
      <Card className="metric-card compact">
        <span>样本数</span>
        <strong>{formatNumber(posts.length + comments.length)}</strong>
        <small>帖子 {posts.length} / 评论 {comments.length}</small>
      </Card>
      <Card className="metric-card compact">
        <span>时间范围</span>
        <strong>{dates[0] ? formatDateTime(dates[0]) : "-"}</strong>
        <small>{lastDate ? `至 ${formatDateTime(lastDate)}` : "暂无发布时间"}</small>
      </Card>
      <ChartCard title="平台分布" subtitle="判断信号是否平台单一" empty={!platforms.length}>
        <ResponsiveContainer width="100%" height={220}>
          <BarChart data={platforms}>
            <CartesianGrid strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="platform" tickFormatter={labelPlatform} />
            <YAxis />
            <Tooltip />
            <Bar dataKey="posts" fill="#04786f" radius={[6, 6, 0, 0]} />
            <Bar dataKey="comments" fill="#2563eb" radius={[6, 6, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </ChartCard>
      <ChartCard title="发布时间分布" subtitle="判断数据是否过旧" empty={!publishRows.length}>
        <ResponsiveContainer width="100%" height={220}>
          <AreaChart data={publishRows}>
            <CartesianGrid strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="date" />
            <YAxis />
            <Tooltip />
            <Area dataKey="posts" stackId="1" fill="#e3f4f1" stroke="#04786f" />
            <Area dataKey="comments" stackId="1" fill="#eaf1ff" stroke="#2563eb" />
          </AreaChart>
        </ResponsiveContainer>
      </ChartCard>
      <ChartCard title="关键词命中" subtitle="判断样本与机会是否相关" empty={!keywordRows.length}>
        <ResponsiveContainer width="100%" height={220}>
          <BarChart data={keywordRows} layout="vertical">
            <CartesianGrid strokeDasharray="3 3" horizontal={false} />
            <XAxis type="number" />
            <YAxis type="category" dataKey="keyword" width={90} />
            <Tooltip />
            <Bar dataKey="count" fill="#ff9f1c" radius={[0, 6, 6, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </ChartCard>
      <Card className="data-quality">
        <CardHeader>
          <div>
            <CardTitle>数据质量</CardTitle>
            <CardDescription>Raw {rawRecords.length} / AI {aiResults.length}</CardDescription>
          </div>
        </CardHeader>
        {qualityRows.map((row) => (
          <div className="quality-row" key={row.label}>
            <span>{row.label}</span>
            <div>
              <i style={{ width: `${Math.round((row.value / Math.max(1, row.total)) * 100)}%` }} />
            </div>
            <strong>{row.value}/{row.total}</strong>
          </div>
        ))}
      </Card>
    </section>
  );
}

function SampleCardList({
  kind,
  rows,
}: {
  kind: DataKind;
  rows: Array<PostRecord | CommentRecord | RawRecord | AIResult>;
}) {
  return <div className="sample-card-list">{rows.map((row) => <SampleCard key={`${kind}-${row.id}`} kind={kind} row={row} />)}</div>;
}

function SampleCard({
  kind,
  row,
}: {
  kind: DataKind;
  row: PostRecord | CommentRecord | RawRecord | AIResult;
}) {
  const [open, setOpen] = React.useState(false);
  if (kind === "posts") {
    const item = row as PostRecord;
    return (
      <RecordCard open={open} setOpen={setOpen} title={item.title || "无标题"} subtitle={`${labelPlatform(item.platform)} / ${formatDateTime(item.publish_time)}`} meta={compactJson(item.engagement_json)} raw={item}>
        <p>{item.content?.slice(0, 180) || item.url || "-"}</p>
      </RecordCard>
    );
  }
  if (kind === "comments") {
    const item = row as CommentRecord;
    return (
      <RecordCard open={open} setOpen={setOpen} title={item.content?.slice(0, 90) || "无内容评论"} subtitle={`${labelPlatform(item.platform)} / ${formatDateTime(item.publish_time)}`} meta={`点赞 ${item.like_count || 0}`} raw={item}>
        <p>帖子 ID：{item.platform_post_id || "-"}</p>
      </RecordCard>
    );
  }
  if (kind === "raw") {
    const item = row as RawRecord;
    return (
      <RecordCard open={open} setOpen={setOpen} title={`${item.source_type} / ${item.source_id || "-"}`} subtitle={`${labelPlatform(item.platform)} / ${formatDateTime(item.fetched_at)}`} meta={item.payload_hash} raw={item}>
        <p>解析版本：{item.parser_version || "-"}</p>
      </RecordCard>
    );
  }
  const item = row as AIResult;
  return (
    <RecordCard open={open} setOpen={setOpen} title={`${item.target_type} ${item.target_id}`} subtitle={`${item.model} / ${formatDateTime(item.created_at)}`} meta={compactJson(item.result_json)} raw={item}>
      <p>{compactJson(item.result_json)}</p>
    </RecordCard>
  );
}

function RecordCard({
  open,
  setOpen,
  title,
  subtitle,
  meta,
  raw,
  children,
}: {
  open: boolean;
  setOpen: (open: boolean) => void;
  title: string;
  subtitle: string;
  meta: string;
  raw: unknown;
  children: React.ReactNode;
}) {
  return (
    <Card className="sample-card">
      <div className="sample-card-head">
        <button type="button" onClick={() => setOpen(!open)} className="expand-button">
          {open ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
        </button>
        <div>
          <strong>{title}</strong>
          <span>{subtitle}</span>
        </div>
        <Badge tone="muted">{meta}</Badge>
      </div>
      <div className="sample-card-body">{children}</div>
      {open && <pre className="json-detail">{JSON.stringify(raw, null, 2)}</pre>}
    </Card>
  );
}

function totalCount(summary?: TaskSummary) {
  if (!summary) return 0;
  return summary.posts + summary.comments + summary.raw + summary.ai;
}

function sortJobsForDataBrowser(
  jobs: ResearchJob[],
  summaries: Record<number, TaskSummary>,
  selectedJobId: number | null,
) {
  const statusRank: Record<string, number> = { failed: 0, running: 1, pending: 2, completed: 3 };
  return [...jobs].sort((a, b) => {
    if (a.id === selectedJobId) return -1;
    if (b.id === selectedJobId) return 1;
    const aHasData = totalCount(summaries[a.id]) > 0 ? 1 : 0;
    const bHasData = totalCount(summaries[b.id]) > 0 ? 1 : 0;
    if (aHasData !== bHasData) return bHasData - aHasData;
    return (statusRank[a.status] ?? 4) - (statusRank[b.status] ?? 4) || b.id - a.id;
  });
}

function matchesTaskFilter(job: ResearchJob, summary: TaskSummary | undefined, filter: TaskFilter) {
  if (filter === "all") return true;
  if (filter === "with_data") return totalCount(summary) > 0;
  if (filter === "failed") return job.status === "failed";
  if (filter === "completed") return job.status === "completed";
  return job.status === "pending" || job.status === "queued" || job.status === "running";
}

function getTaskRowStatus(job: ResearchJob, summary: TaskSummary) {
  if (totalCount(summary) > 0) return { label: "有数据", badgeTone: "success" as const };
  if (job.status === "failed") return { label: "失败", badgeTone: "danger" as const };
  if (job.status === "pending" || job.status === "queued") return { label: "待执行", badgeTone: "warning" as const };
  if (job.status === "running") return { label: "运行中", badgeTone: "warning" as const };
  if (job.status === "completed") return { label: "无样本", badgeTone: "muted" as const };
  return { label: job.status, badgeTone: "muted" as const };
}

function getStatusView(selectedJob: ResearchJob | null, summary: TaskSummary, latestFailure: ResearchEvent | null) {
  if (!selectedJob) {
    return {
      label: "未选择",
      description: "请选择一个任务查看数据。",
      emptyTitle: "请选择任务",
      emptyBody: "选择任务后，这里会展示可检索的数据样本。",
      tone: "muted",
      badgeTone: "muted" as const,
    };
  }
  const count = totalCount(summary);
  if (selectedJob.status === "failed" || latestFailure) {
    return {
      label: "采集失败",
      description: latestFailure?.message || "任务失败，未生成可浏览样本。",
      emptyTitle: "采集失败，未生成样本",
      emptyBody: "查看失败原因后，可从任务工作台重新采集或执行回填。",
      tone: "danger",
      badgeTone: "danger" as const,
    };
  }
  if (count > 0) {
    return {
      label: "有数据",
      description: "当前任务已有可检索样本。",
      emptyTitle: "当前类型暂无数据",
      emptyBody: "当前任务有样本，但所选数据类型没有记录。可以切换到其他数据类型。",
      tone: "success",
      badgeTone: "success" as const,
    };
  }
  if (selectedJob.status === "pending" || selectedJob.status === "queued") {
    return {
      label: "待执行",
      description: "任务尚未执行，暂时没有样本。",
      emptyTitle: "任务尚未执行",
      emptyBody: "任务仍在等待执行。可以切换到有数据任务，或从任务工作台启动采集。",
      tone: "warning",
      badgeTone: "warning" as const,
    };
  }
  if (selectedJob.status === "running") {
    return {
      label: "运行中",
      description: "任务正在运行，数据可能稍后出现。",
      emptyTitle: "任务正在运行",
      emptyBody: "采集完成或回填完成后，这里会显示可检索样本。",
      tone: "warning",
      badgeTone: "warning" as const,
    };
  }
  if (selectedJob.status === "completed") {
    return {
      label: "无样本",
      description: "任务已完成，但没有回填到研究样本。",
      emptyTitle: "当前任务暂无样本",
      emptyBody: "建议切换到有数据任务，或从任务工作台执行回填/重新采集。",
      tone: "muted",
      badgeTone: "muted" as const,
    };
  }
  return {
    label: selectedJob.status,
    description: "当前状态下暂无可浏览样本。",
    emptyTitle: "当前任务暂无样本",
    emptyBody: "可以切换到有数据任务，或从任务工作台继续处理。",
    tone: "muted",
    badgeTone: "muted" as const,
  };
}
