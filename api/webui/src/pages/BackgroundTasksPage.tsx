import React from "react";
import { AlertTriangle, Bot, Clock3, DatabaseZap, ListChecks, Loader2, RefreshCw, Search, Square, Trash2 } from "lucide-react";
import { Badge, Button, Card, CardDescription, CardHeader, CardTitle, ConfirmDialog } from "../components/ui";
import { api } from "../utils/api";
import type { BackgroundTaskItem, BackgroundTaskSummary } from "../types";

type TaskResponse = {
  tasks: BackgroundTaskItem[];
  summary: BackgroundTaskSummary;
};

type SettingsResponse = {
  research_execution: {
    max_concurrent: number;
    running: number;
    default: number;
    min: number;
    max: number;
  };
};

const emptySummary: BackgroundTaskSummary = {
  total: 0,
  running: 0,
  queued: 0,
  cancellable: 0,
  failed: 0,
  completed: 0,
  cancelled: 0,
  deletable: 0,
};

const filters = [
  { id: "all", label: "全部" },
  { id: "crawler", label: "爬虫" },
  { id: "collection", label: "采集" },
  { id: "creator_search", label: "达人搜索" },
  { id: "content_search", label: "内容搜索" },
  { id: "ai_analysis", label: "AI 分析" },
];

export function BackgroundTasksPage() {
  const [tasks, setTasks] = React.useState<BackgroundTaskItem[]>([]);
  const [summary, setSummary] = React.useState<BackgroundTaskSummary>(emptySummary);
  const [activeFilter, setActiveFilter] = React.useState("all");
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [cancelTarget, setCancelTarget] = React.useState<BackgroundTaskItem | null>(null);
  const [deleteTarget, setDeleteTarget] = React.useState<BackgroundTaskItem | null>(null);
  const [cancelling, setCancelling] = React.useState(false);
  const [deleting, setDeleting] = React.useState(false);
  const [concurrency, setConcurrency] = React.useState<SettingsResponse["research_execution"] | null>(null);
  const [concurrencyDraft, setConcurrencyDraft] = React.useState(4);
  const [concurrencyDirty, setConcurrencyDirty] = React.useState(false);
  const [savingConcurrency, setSavingConcurrency] = React.useState(false);

  const loadTasks = React.useCallback(async () => {
    setLoading(true);
    try {
      const [data, settings] = await Promise.all([
        api<TaskResponse>("/api/background-tasks"),
        api<SettingsResponse>("/api/background-tasks/settings"),
      ]);
      setTasks(data.tasks || []);
      setSummary({ ...emptySummary, ...(data.summary || {}) });
      setConcurrency(settings.research_execution);
      if (!concurrencyDirty) setConcurrencyDraft(settings.research_execution.max_concurrent);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, [concurrencyDirty]);

  React.useEffect(() => {
    void loadTasks();
    const timer = window.setInterval(() => void loadTasks(), 2000);
    return () => window.clearInterval(timer);
  }, [loadTasks]);

  const filteredTasks = React.useMemo(
    () => tasks.filter((task) => matchesFilter(task, activeFilter)),
    [tasks, activeFilter],
  );

  async function cancelTask() {
    if (!cancelTarget) return;
    setCancelling(true);
    try {
      await api(`/api/background-tasks/${encodeURIComponent(cancelTarget.id)}/cancel`, { method: "POST" });
      setCancelTarget(null);
      await loadTasks();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setCancelling(false);
    }
  }

  async function deleteTask() {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await api(`/api/background-tasks/${encodeURIComponent(deleteTarget.id)}`, { method: "DELETE" });
      setDeleteTarget(null);
      await loadTasks();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setDeleting(false);
    }
  }

  async function saveConcurrency() {
    const nextValue = Math.max(1, Math.min(16, Math.round(concurrencyDraft || 1)));
    setSavingConcurrency(true);
    try {
      const settings = await api<SettingsResponse>("/api/background-tasks/settings/research-execution-concurrency", {
        method: "PUT",
        body: JSON.stringify({ max_concurrent: nextValue }),
      });
      setConcurrency(settings.research_execution);
      setConcurrencyDraft(settings.research_execution.max_concurrent);
      setConcurrencyDirty(false);
      setError(null);
      await loadTasks();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSavingConcurrency(false);
    }
  }

  return (
    <div className="background-task-page">
      <section className="background-task-hero">
        <div>
          <span className="eyebrow">Process-local operations</span>
          <h1>后台任务</h1>
          <p>查看当前 Web 后端进程内正在运行和排队的任务；后端重启后，内存任务不会保留。</p>
        </div>
        <Button variant="ghost" onClick={() => void loadTasks()} disabled={loading}>
          {loading ? <Loader2 size={16} className="spin" /> : <RefreshCw size={16} />}
          刷新
        </Button>
      </section>

      {error && (
        <div className="notice error">
          <AlertTriangle size={16} />
          {error}
        </div>
      )}

      <div className="background-task-summary-grid">
        <TaskMetric label="运行中" value={summary.running} icon={<DatabaseZap size={18} />} tone="success" />
        <TaskMetric label="队列中" value={summary.queued} icon={<Clock3 size={18} />} tone="warning" />
        <TaskMetric label="可取消" value={summary.cancellable} icon={<Square size={18} />} tone="default" />
        <TaskMetric label="最近失败" value={summary.failed} icon={<AlertTriangle size={18} />} tone="danger" />
      </div>

      <Card className="background-task-settings">
        <CardHeader>
          <div>
            <CardTitle>Research concurrency</CardTitle>
            <CardDescription>Limit simultaneous crawler executions in this backend process.</CardDescription>
          </div>
          <div className="background-task-concurrency-control">
            <label>
              Max running
              <input
                type="number"
                min={concurrency?.min || 1}
                max={concurrency?.max || 16}
                value={concurrencyDraft}
                onChange={(event) => {
                  setConcurrencyDraft(Number(event.target.value || 1));
                  setConcurrencyDirty(true);
                }}
              />
            </label>
            <Button
              variant="primary"
              onClick={() => void saveConcurrency()}
              disabled={savingConcurrency || !concurrencyDirty}
            >
              {savingConcurrency ? <Loader2 size={16} className="spin" /> : <DatabaseZap size={16} />}
              Save
            </Button>
            <Badge tone="muted">Running {concurrency?.running ?? summary.running}/{concurrency?.max_concurrent ?? 4}</Badge>
          </div>
        </CardHeader>
      </Card>

      <Card className="background-task-panel">
        <CardHeader>
          <div>
            <CardTitle>任务列表</CardTitle>
            <CardDescription>统一来自爬虫、研究采集队列、达人搜索、内容实时搜索和 AI 分析。</CardDescription>
          </div>
          <div className="background-task-filters">
            {filters.map((filter) => (
              <button
                key={filter.id}
                type="button"
                className={activeFilter === filter.id ? "active" : ""}
                onClick={() => setActiveFilter(filter.id)}
              >
                {filter.label}
              </button>
            ))}
          </div>
        </CardHeader>

        <div className="background-task-list">
          {filteredTasks.length ? (
            filteredTasks.map((task) => (
              <TaskRow
                key={task.id}
                task={task}
                onCancel={() => setCancelTarget(task)}
                onDelete={() => setDeleteTarget(task)}
              />
            ))
          ) : (
            <div className="background-task-empty">
              <ListChecks size={24} />
              <strong>当前没有匹配的后台任务</strong>
              <span>启动采集、达人搜索、内容实时搜索或 AI 分析后，这里会自动刷新。</span>
            </div>
          )}
        </div>
      </Card>

      <ConfirmDialog
        open={Boolean(cancelTarget)}
        onOpenChange={(open) => {
          if (!open && !cancelling) setCancelTarget(null);
        }}
        title="取消后台任务"
        description="取消运行中的采集会尝试停止当前爬虫进程；队列任务会从当前 Web 后端队列移除。"
      >
        {cancelTarget && (
          <div className="background-task-confirm">
            <div>
              <span>任务</span>
              <strong>{cancelTarget.title}</strong>
            </div>
            <div>
              <span>状态</span>
              <strong>{labelStatus(cancelTarget.status)}</strong>
            </div>
            <div className="button-row right">
              <Button variant="ghost" onClick={() => setCancelTarget(null)} disabled={cancelling}>
                保留任务
              </Button>
              <Button variant="danger" onClick={() => void cancelTask()} disabled={cancelling}>
                {cancelling ? <Loader2 size={16} className="spin" /> : <Square size={16} />}
                确认取消
              </Button>
            </div>
          </div>
        )}
      </ConfirmDialog>

      <ConfirmDialog
        open={Boolean(deleteTarget)}
        onOpenChange={(open) => {
          if (!open && !deleting) setDeleteTarget(null);
        }}
        title="删除后台任务"
        description="删除只会清理任务中心里的任务记录；排队任务或没有进程句柄的数据库任务会被标记为已取消，不会删除已采集的数据。"
      >
        {deleteTarget && (
          <div className="background-task-confirm">
            <div>
              <span>任务</span>
              <strong>{deleteTarget.title}</strong>
            </div>
            <div>
              <span>状态</span>
              <strong>{labelStatus(deleteTarget.status)}</strong>
            </div>
            <div className="button-row right">
              <Button variant="ghost" onClick={() => setDeleteTarget(null)} disabled={deleting}>
                保留任务
              </Button>
              <Button variant="danger" onClick={() => void deleteTask()} disabled={deleting}>
                {deleting ? <Loader2 size={16} className="spin" /> : <Trash2 size={16} />}
                确认删除
              </Button>
            </div>
          </div>
        )}
      </ConfirmDialog>
    </div>
  );
}

function TaskMetric({
  label,
  value,
  icon,
  tone,
}: {
  label: string;
  value: number;
  icon: React.ReactNode;
  tone: "default" | "success" | "warning" | "danger";
}) {
  return (
    <div className={`background-task-metric ${tone}`}>
      <div>{icon}</div>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function TaskRow({
  task,
  onCancel,
  onDelete,
}: {
  task: BackgroundTaskItem;
  onCancel: () => void;
  onDelete: () => void;
}) {
  const progress = clampPercent(task.progress?.percent ?? 0);
  return (
    <article className="background-task-row">
      <div className="background-task-main">
        <div className="background-task-title">
          {iconForTask(task)}
          <div>
            <strong>{task.title}</strong>
            <span>{labelType(task)} · {task.source || "unknown"}{task.related_job_id ? ` · Job #${task.related_job_id}` : ""}</span>
          </div>
        </div>
        <Badge tone={badgeTone(task.status)}>{labelStatus(task.status)}</Badge>
      </div>

      <div className="background-task-progress">
        <div>
          <span>{task.progress?.label || task.progress?.stage || "等待状态更新"}</span>
          <strong>{progress}%</strong>
        </div>
        <div className="background-task-progress-track">
          <span style={{ width: `${progress}%` }} />
        </div>
      </div>

      <div className="background-task-meta">
        <span>更新：{formatTime(task.updated_at)}</span>
        <span>开始：{formatTime(task.started_at)}</span>
      </div>

      <details className="background-task-detail">
        <summary>任务详情</summary>
        <pre>{JSON.stringify(task.detail || {}, null, 2)}</pre>
      </details>

      <div className="background-task-actions">
        <div className="background-task-action-buttons">
          <Button variant="danger" size="sm" onClick={onCancel} disabled={!task.cancellable}>
          <Square size={14} />
          取消
          </Button>
          <Button variant="ghost" size="sm" onClick={onDelete} disabled={!task.deletable}>
            <Trash2 size={14} />
            删除
          </Button>
        </div>
        {!task.cancellable && task.cancel_reason && <span>{task.cancel_reason}</span>}
        {!task.deletable && task.delete_reason && <span>{task.delete_reason}</span>}
      </div>
    </article>
  );
}

function matchesFilter(task: BackgroundTaskItem, filter: string) {
  if (filter === "all") return true;
  if (filter === "collection") return task.type === "research_execution" || task.type === "research_queue" || task.source === "growth_project";
  if (filter === "content_search") return task.source === "content_search";
  return task.type === filter || task.source === filter;
}

function iconForTask(task: BackgroundTaskItem) {
  if (task.type === "ai_analysis") return <Bot size={18} />;
  if (task.type === "creator_search" || task.source === "content_search") return <Search size={18} />;
  return <DatabaseZap size={18} />;
}

function labelType(task: BackgroundTaskItem) {
  const labels: Record<string, string> = {
    crawler: "爬虫",
    research_execution: "采集执行",
    research_queue: "采集队列",
    creator_search: "达人搜索",
    ai_analysis: "AI 分析",
  };
  return labels[task.type] || task.type;
}

function labelStatus(status: string) {
  const labels: Record<string, string> = {
    queued: "排队中",
    running: "运行中",
    stopping: "停止中",
    completed: "已完成",
    failed: "失败",
    cancelled: "已取消",
    unknown: "未知",
  };
  return labels[status] || status;
}

function badgeTone(status: string): "default" | "success" | "warning" | "danger" | "muted" {
  if (status === "running") return "success";
  if (status === "queued" || status === "stopping") return "warning";
  if (status === "failed") return "danger";
  if (status === "completed") return "default";
  return "muted";
}

function clampPercent(value: number) {
  if (!Number.isFinite(value)) return 0;
  return Math.max(0, Math.min(100, Math.round(value)));
}

function formatTime(value?: string | null) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("zh-CN", { hour12: false });
}
