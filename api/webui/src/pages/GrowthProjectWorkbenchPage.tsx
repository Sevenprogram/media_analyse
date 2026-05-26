import React from "react";
import {
  AlertTriangle,
  BarChart3,
  Clock,
  Database,
  Download,
  FileJson,
  Layers,
  MessageSquare,
  Pause,
  Play,
  Plus,
  RefreshCw,
  RotateCcw,
  Save,
  Search,
  Share2,
  ShieldCheck,
  Sparkles,
  Target,
  TrendingUp,
  X,
} from "lucide-react";
import { Button, ConfirmDialog, Drawer } from "../components/ui";
import { api } from "../utils/api";
import { formatDateTime, formatNumber, labelPlatform, parseDateTime } from "../utils/format";
import type {
  GrowthProjectCollectionProgress,
  GrowthProjectCollectionRunPayload,
  GrowthProjectCreatePayload,
  GrowthProjectDetail,
  GrowthProjectKeywordAISuggestResponse,
  GrowthProjectKeywordStatus,
  GrowthProjectKeywordType,
  GrowthProjectSummary,
  GrowthProjectUpdatePayload,
} from "../types";

const GOAL_LABELS: Record<GrowthProjectSummary["primary_goal"], string> = {
  topic_discovery: "内容研究",
  creator_discovery: "达人研究",
  keyword_expansion: "市场研究",
  competitor_monitoring: "竞品研究",
  mixed_research: "综合研究",
};

const GOAL_OPTIONS = [
  { value: "mixed_research", label: "综合研究" },
  { value: "topic_discovery", label: "内容研究" },
  { value: "creator_discovery", label: "达人研究" },
  { value: "keyword_expansion", label: "市场研究" },
  { value: "competitor_monitoring", label: "竞品研究" },
] as const;

const REFRESH_OPTIONS = [
  { value: "off", label: "手动" },
  { value: "daily", label: "每天" },
  { value: "three_days", label: "每 3 天" },
  { value: "weekly", label: "每周" },
  { value: "custom_hours", label: "按小时" },
  { value: "custom_days", label: "按天" },
] as const;

const PROJECT_PLATFORM_OPTIONS = ["xhs", "dy", "wb", "bili", "ks", "zhihu", "tieba"];
const COLLECTION_PLATFORMS = ["xhs", "dy"];
const DEFAULT_DAILY_COLLECTION_LIMIT_PER_PLATFORM = 50;

const KEYWORD_TYPE_LABELS: Record<GrowthProjectKeywordType, string> = {
  core: "核心词",
  expanded: "扩展词",
  excluded: "排除词",
  pending: "待确认",
};

const DEFAULT_PROJECT_NAME = "2026 Summer 教育项目";

const DEFAULT_COLLECTION_CONTROLS: GrowthProjectCollectionRunPayload = {
  platforms: [],
  keyword_scope: "all_project",
  selected_keywords: [],
  extra_keywords: [],
  persist_to_project: false,
  target_posts_per_platform: DEFAULT_DAILY_COLLECTION_LIMIT_PER_PLATFORM,
  collection_window_days: 7,
  prefer_latest_posts: true,
  sort_mode: "latest",
  time_preset: "7d",
  time_start: null,
  time_end: null,
  max_results_per_keyword_per_platform: DEFAULT_DAILY_COLLECTION_LIMIT_PER_PLATFORM,
  fill_strategy: "prefer_fill",
  max_extra_pages: 3,
};

type RefreshCadence = NonNullable<GrowthProjectUpdatePayload["refresh_cadence"]>;

type ConfigKeywordDraft = NonNullable<GrowthProjectUpdatePayload["keywords"]>[number] & {
  id: string;
};

type KeywordCandidateDraft = {
  id: string;
  keyword: string;
  keyword_type: GrowthProjectKeywordType;
  source: string;
  status: GrowthProjectKeywordStatus;
  reason?: string | null;
  confidence?: number | null;
};

type WorkspaceTab = "overview" | "config" | "plan" | "history";

function createId(prefix: string) {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
}

function keywordStatusForType(keywordType: GrowthProjectKeywordType): GrowthProjectKeywordStatus {
  if (keywordType === "excluded") return "excluded";
  if (keywordType === "pending") return "pending";
  return "active";
}

function normalizeKeywordType(value: string): GrowthProjectKeywordType {
  if (value === "core" || value === "expanded" || value === "excluded" || value === "pending") {
    return value;
  }
  return "expanded";
}

function keywordKey(value: string) {
  return value.trim().toLocaleLowerCase();
}

function toInteger(value: number, fallback: number, min = 0) {
  if (!Number.isFinite(value)) return fallback;
  return Math.max(min, Math.trunc(value));
}

function supportedCollectionPlatforms(platforms: string[]) {
  return COLLECTION_PLATFORMS.filter((platform) => platforms.includes(platform));
}

function keywordDraftsFromDetail(detail: GrowthProjectDetail | null): ConfigKeywordDraft[] {
  return (detail?.keywords || []).map((item) => {
    const keywordType = normalizeKeywordType(item.type || "core");
    return {
      id: createId("project-keyword"),
      keyword: item.keyword,
      keyword_type: keywordType,
      source: item.source || "manual",
      status:
        item.status === "active" || item.status === "pending" || item.status === "excluded" || item.status === "inactive"
          ? item.status
          : keywordStatusForType(keywordType),
    };
  });
}

function buildProjectKeywordDraft(
  keyword: string,
  keywordType: GrowthProjectKeywordType,
  source = "manual",
): ConfigKeywordDraft {
  return {
    id: createId("project-keyword"),
    keyword,
    keyword_type: keywordType,
    source,
    status: keywordStatusForType(keywordType),
  };
}

function buildKeywordCandidateDraft(
  keyword: string,
  keywordType: GrowthProjectKeywordType,
  options?: { source?: string; reason?: string | null; confidence?: number | null },
): KeywordCandidateDraft {
  return {
    id: createId("keyword-candidate"),
    keyword,
    keyword_type: keywordType,
    source: options?.source || "ai",
    status: keywordStatusForType(keywordType),
    reason: options?.reason || null,
    confidence: options?.confidence ?? null,
  };
}

function mergeProjectKeywords(
  current: ConfigKeywordDraft[],
  additions: Array<Pick<ConfigKeywordDraft, "keyword" | "keyword_type" | "source">>,
): ConfigKeywordDraft[] {
  const next = [...current];
  const indexByKeyword = new Map(next.map((item, index) => [keywordKey(item.keyword), index]));
  for (const addition of additions) {
    const keyword = addition.keyword.trim();
    if (!keyword) continue;
    const keywordType = normalizeKeywordType(addition.keyword_type);
    const existingIndex = indexByKeyword.get(keywordKey(keyword));
    if (existingIndex === undefined) {
      next.push(buildProjectKeywordDraft(keyword, keywordType, addition.source || "manual"));
      indexByKeyword.set(keywordKey(keyword), next.length - 1);
      continue;
    }
    next[existingIndex] = {
      ...next[existingIndex],
      keyword,
      keyword_type: keywordType,
      source: addition.source || next[existingIndex].source || "manual",
      status: keywordStatusForType(keywordType),
    };
  }
  return next;
}

function mergeCandidateKeywords(current: KeywordCandidateDraft[], additions: KeywordCandidateDraft[]): KeywordCandidateDraft[] {
  const next = [...current];
  const indexByKeyword = new Map(next.map((item, index) => [keywordKey(item.keyword), index]));
  for (const addition of additions) {
    const key = keywordKey(addition.keyword);
    if (!key) continue;
    const existingIndex = indexByKeyword.get(key);
    if (existingIndex === undefined) {
      next.push(addition);
      indexByKeyword.set(key, next.length - 1);
      continue;
    }
    next[existingIndex] = {
      ...next[existingIndex],
      keyword: addition.keyword,
      keyword_type: addition.keyword_type,
      source: addition.source || next[existingIndex].source,
      status: keywordStatusForType(addition.keyword_type),
      reason: addition.reason ?? next[existingIndex].reason ?? null,
      confidence: addition.confidence ?? next[existingIndex].confidence ?? null,
    };
  }
  return next;
}

function parseBulkKeywords(value: string): string[] {
  return value
    .split(/[\n,，;；]+/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function normalizedKeywordPayload(keywords: ConfigKeywordDraft[]): NonNullable<GrowthProjectUpdatePayload["keywords"]> {
  const seen = new Set<string>();
  const result: NonNullable<GrowthProjectUpdatePayload["keywords"]> = [];
  for (const item of keywords) {
    const keyword = item.keyword.trim();
    if (!keyword) continue;
    const keywordType = normalizeKeywordType(item.keyword_type);
    const key = keywordKey(keyword);
    if (seen.has(key)) continue;
    seen.add(key);
    result.push({
      keyword,
      keyword_type: keywordType,
      source: item.source || "manual",
      status: keywordStatusForType(keywordType),
    });
  }
  return result;
}

function sortCandidatesByType(candidates: KeywordCandidateDraft[]) {
  const order: Record<GrowthProjectKeywordType, number> = {
    core: 0,
    expanded: 1,
    excluded: 2,
    pending: 3,
  };
  return [...candidates].sort((left, right) => {
    const orderDiff = order[left.keyword_type] - order[right.keyword_type];
    if (orderDiff !== 0) return orderDiff;
    return left.keyword.localeCompare(right.keyword, "zh-Hans-CN");
  });
}

function projectStatus(status: string) {
  if (status === "paused" || status === "idle") return { label: "已暂停", dot: "paused" };
  if (status === "completed") return { label: "已完成", dot: "completed" };
  if (status === "planned" || status === "queued") return { label: "排队中", dot: "planned" };
  if (status === "failed") return { label: "异常", dot: "danger" };
  return { label: "运行中", dot: "active" };
}

function formatRelativeTime(value?: string | null) {
  if (!value) return "暂无采集";
  const date = parseDateTime(value);
  if (!date) return "时间未知";
  const diffMinutes = Math.max(0, Math.round((Date.now() - date.getTime()) / 60000));
  if (diffMinutes < 60) return `${diffMinutes} 分钟前`;
  const diffHours = Math.round(diffMinutes / 60);
  if (diffHours < 24) return `${diffHours} 小时前`;
  const diffDays = Math.round(diffHours / 24);
  return `${diffDays} 天前`;
}

function labelRefreshCadence(value?: string | null) {
  return REFRESH_OPTIONS.find((item) => item.value === value)?.label || "手动";
}

function labelRefreshCadenceWithTime(value?: string | null, refreshTimeUtc8?: string | null) {
  const label = labelRefreshCadence(value);
  if (value === "daily" && refreshTimeUtc8) return `${label} ${refreshTimeUtc8} UTC+8`;
  return label;
}

function validUtc8Time(value: string) {
  return /^([01]\d|2[0-3]):[0-5]\d$/.test(value);
}

function labelAutomationCadence(enabled?: boolean, intervalMinutes?: number | null) {
  if (!enabled) return "手动触发";
  const minutes = Math.max(0, Math.trunc(intervalMinutes || 0));
  if (!minutes) return "自动采集";
  if (minutes % (7 * 24 * 60) === 0) {
    const weeks = Math.max(1, minutes / (7 * 24 * 60));
    return weeks === 1 ? "每周一次" : `每 ${weeks} 周一次`;
  }
  if (minutes % (24 * 60) === 0) {
    const days = Math.max(1, minutes / (24 * 60));
    return days === 1 ? "每天一次" : `每 ${days} 天一次`;
  }
  if (minutes % 60 === 0) {
    const hours = Math.max(1, minutes / 60);
    return hours === 1 ? "每小时一次" : `每 ${hours} 小时一次`;
  }
  return `每 ${minutes} 分钟`;
}

function automationLiveState(progress: GrowthProjectCollectionProgress | null) {
  const automation = progress?.automation;
  const daemon = automation?.daemon;
  if (!automation?.enabled) {
    return {
      label: "未开启",
      dot: "completed",
      note: "当前项目仅支持手动新建采集任务。",
    };
  }
  if (daemon?.running) {
    return {
      label: "自动采集中",
      dot: "active",
      note: "守护进程在线，会按计划自动创建采集任务。",
    };
  }
  if (daemon?.configured_enabled) {
    return {
      label: "等待守护进程",
      dot: "planned",
      note: "自动守护进程正在启动或最近中断。",
    };
  }
  return {
    label: "未激活",
    dot: "danger",
    note: "当前 API 进程未启用自动采集守护进程。",
  };
}

function collectionEventLabel(eventType?: string | null) {
  if (!eventType) return "任务事件";
  const labels: Record<string, string> = {
    execution_started: "任务开始执行",
    execution_failed: "任务执行失败",
    execution_completed: "任务执行完成",
    platform_execution_failed: "平台执行失败",
    crawler_output_captured: "爬虫输出",
    queue_execution_failed: "队列执行失败",
    crawl_unit_started: "采集单元开始",
    crawl_unit_succeeded: "采集单元完成",
    crawl_unit_failed: "采集单元失败",
    crawl_unit_cancelled: "采集单元已取消",
  };
  return labels[eventType] || eventType.replace(/_/g, " ");
}

function collectionEventMessage(event?: {
  message?: string;
  stats_json?: Record<string, unknown> | null;
} | null) {
  if (!event) return "暂无任务事件。";
  const stats = event.stats_json || {};
  const candidates = [stats.warning_or_error_tail, stats.error, stats.detail, event.message];
  for (const value of candidates) {
    if (typeof value === "string" && value.trim()) {
      return value.trim();
    }
  }
  return "暂无任务事件。";
}

function collectionLiveLabel(
  progress: GrowthProjectCollectionProgress | null,
  fallbackStatus: string,
) {
  const statusValue = progress?.status || fallbackStatus;
  if (statusValue === "queued") {
    const queuePosition = progress?.queued_jobs?.[0]?.queue_position;
    return queuePosition ? `排队中 · 第 ${queuePosition} 位` : "排队中";
  }
  if (statusValue === "running") {
    const percent = progress?.progress.sample_percent ?? progress?.progress.percent ?? 0;
    return `爬虫运行中 · ${percent}%`;
  }
  if (statusValue === "failed") return "最近任务异常";
  if (statusValue === "completed") return "最近任务已完成";
  return projectStatus(statusValue).label;
}

function sortCollectionRecords(records: GrowthProjectDetail["collection_records"]) {
  const timestampValue = (value?: string | null) => {
    if (!value) return 0;
    const parsed = Date.parse(value);
    return Number.isFinite(parsed) ? parsed : 0;
  };
  return [...records].sort((left, right) => {
    const timeDiff = timestampValue(right.updated_at) - timestampValue(left.updated_at);
    if (timeDiff !== 0) return timeDiff;
    return right.id - left.id;
  });
}

export function GrowthProjectWorkbenchPage({
  projects,
  selectedProjectId,
  selectedProjectDetail,
  selectedProjectProgress,
  isProjectDetailLoading = false,
  onSelectProject,
  onCreateProject,
  onUpdateProject,
  onDeleteProject,
  onStartCollection,
  onPauseCollection,
  onStopCurrentRun,
  onArchiveProject,
  onOpenData,
  onOpenAi,
}: {
  projects: GrowthProjectSummary[];
  selectedProjectId: string | null;
  selectedProjectDetail: GrowthProjectDetail | null;
  selectedProjectProgress: GrowthProjectCollectionProgress | null;
  isProjectDetailLoading?: boolean;
  onSelectProject: (projectId: string) => void;
  onCreateProject: (payload: GrowthProjectCreatePayload) => Promise<void>;
  onUpdateProject: (projectId: string, payload: GrowthProjectUpdatePayload) => Promise<void>;
  onDeleteProject: (projectId: string) => Promise<void>;
  onStartCollection: (projectId: string, payload: GrowthProjectCollectionRunPayload) => Promise<void>;
  onPauseCollection: (projectId: string) => Promise<void>;
  onStopCurrentRun: (projectId: string) => Promise<void>;
  onArchiveProject: (projectId: string) => Promise<void>;
  onOpenData: () => void;
  onOpenAi: () => void;
}) {
  const [showCreate, setShowCreate] = React.useState(false);
  const [query, setQuery] = React.useState("");
  const [notice, setNotice] = React.useState<string | null>(null);
  const [activeTab, setActiveTab] = React.useState<WorkspaceTab>("overview");
  const [collectionDialogOpen, setCollectionDialogOpen] = React.useState(false);
  const [archiveConfirmTarget, setArchiveConfirmTarget] = React.useState<GrowthProjectSummary | null>(null);
  const [archiveConfirmIntent, setArchiveConfirmIntent] = React.useState<"archive" | "delete">("archive");
  const [archiving, setArchiving] = React.useState(false);
  const [archiveError, setArchiveError] = React.useState<string | null>(null);
  const [collectionControls, setCollectionControls] = React.useState<GrowthProjectCollectionRunPayload>(
    DEFAULT_COLLECTION_CONTROLS,
  );

  const selectedProject =
    projects.find((project) => project.id === selectedProjectId) || projects[0] || null;
  const filteredProjects = projects.filter((project) => {
    if (!query.trim()) return true;
    return project.name.toLowerCase().includes(query.trim().toLowerCase());
  });
  const headerStatus = projectStatus(selectedProjectProgress?.status || selectedProject?.status || "idle");
  const headerLiveText = selectedProject
    ? collectionLiveLabel(selectedProjectProgress, selectedProject.status)
    : null;

  React.useEffect(() => {
    if (!selectedProject) return;
    const projectKeywords = (selectedProjectDetail?.keywords || [])
      .filter((item) => item.type !== "excluded")
      .map((item) => item.keyword);
    setCollectionControls({
      ...DEFAULT_COLLECTION_CONTROLS,
      platforms: supportedCollectionPlatforms(selectedProject.platforms),
      selected_keywords: projectKeywords,
    });
  }, [selectedProject?.id, selectedProject?.platforms, selectedProjectDetail?.keywords]);

  async function startCollection() {
    if (!selectedProject) return;
    try {
      await onStartCollection(selectedProject.id, collectionControls);
      setCollectionDialogOpen(false);
      setActiveTab("history");
      setNotice("采集任务已创建。");
      setNotice("采集任务已创建，已切换到历史任务。");
    } catch (cause) {
      setNotice(cause instanceof Error ? cause.message : String(cause));
    }
  }

  async function pauseCollection() {
    if (!selectedProject) return;
    try {
      await onPauseCollection(selectedProject.id);
      setNotice("已提交暂停请求。");
    } catch (cause) {
      setNotice(cause instanceof Error ? cause.message : String(cause));
    }
  }

  async function stopCollection() {
    if (!selectedProject) return;
    try {
      await onStopCurrentRun(selectedProject.id);
      setNotice("已提交终止请求。");
    } catch (cause) {
      setNotice(cause instanceof Error ? cause.message : String(cause));
    }
  }

  function requestProjectArchive(intent: "archive" | "delete") {
    if (!selectedProject) return;
    setNotice(null);
    setArchiveError(null);
    setArchiveConfirmIntent(intent);
    setArchiveConfirmTarget(selectedProject);
  }

  async function confirmProjectArchive() {
    if (!archiveConfirmTarget) return;
    setArchiving(true);
    try {
      if (archiveConfirmIntent === "delete") {
        await onDeleteProject(archiveConfirmTarget.id);
      } else {
        await onArchiveProject(archiveConfirmTarget.id);
      }
      setArchiveConfirmTarget(null);
      setArchiveError(null);
      setNotice("项目已归档。");
    } catch (cause) {
      setArchiveError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setArchiving(false);
    }
  }

  return (
    <section className="module-page growth-workbench">
      {showCreate && (
        <ProjectCreateDialog
          onClose={() => setShowCreate(false)}
          onCreate={async (payload) => {
            await onCreateProject(payload);
            setShowCreate(false);
          }}
        />
      )}

      <ConfirmDialog
        open={Boolean(archiveConfirmTarget)}
        onOpenChange={(open) => {
          if (!open && !archiving) {
            setArchiveConfirmTarget(null);
            setArchiveError(null);
          }
        }}
        title={archiveConfirmIntent === "delete" ? "删除项目" : "归档项目"}
        description={
          archiveConfirmTarget
            ? `确认${archiveConfirmIntent === "delete" ? "删除" : "归档"}“${archiveConfirmTarget.name}”？项目会从默认列表隐藏，但已采集样本与任务记录会保留。`
            : "确认归档项目？项目会从默认列表隐藏，但已采集样本与任务记录会保留。"
        }
      >
        <div className="project-archive-confirm">
          <div className="project-archive-confirm__summary">
            <AlertTriangle size={18} />
            <div>
              <strong>{archiveConfirmTarget?.name || "当前项目"}</strong>
              <span>该操作只会归档项目入口，不会删除已经采集的样本、证据和历史任务。</span>
            </div>
          </div>
          <div className="project-archive-confirm__effects">
            <span>保留采集记录</span>
            <span>保留样本与证据</span>
            <span>保留历史任务</span>
          </div>
          {archiveError && (
            <div className="project-archive-confirm__error">
              <AlertTriangle size={15} />
              <span>{archiveError}</span>
            </div>
          )}
          <div className="project-archive-confirm__actions">
            <Button
              variant="ghost"
              onClick={() => {
                setArchiveConfirmTarget(null);
                setArchiveError(null);
              }}
              disabled={archiving}
            >
              取消
            </Button>
            <Button variant="danger" onClick={() => void confirmProjectArchive()} disabled={archiving}>
              {archiving ? <RefreshCw size={16} className="spin" /> : <AlertTriangle size={16} />}
              {archiving ? "处理中" : archiveConfirmIntent === "delete" ? "确认删除" : "确认归档"}
            </Button>
          </div>
        </div>
      </ConfirmDialog>

      <div className="growth-project-layout">
        <aside className="growth-project-list-panel">
          <header className="growth-project-list-header">
            <h2>项目列表</h2>
            <button className="new-proj-btn" type="button" onClick={() => setShowCreate(true)}>
              <Plus size={14} /> 新建项目
            </button>
          </header>

          <label className="growth-project-search-box">
            <Search size={14} />
            <input
              value={query}
              onChange={(event) => setQuery(event.currentTarget.value)}
              placeholder="搜索项目名称或关键词"
            />
          </label>

          <div className="growth-project-list">
            {filteredProjects.length ? (
              filteredProjects.map((project) => (
                <button
                  key={project.id}
                  type="button"
                  className={`growth-project-card ${selectedProject?.id === project.id ? "active" : ""}`}
                  onClick={() => onSelectProject(project.id)}
                >
                  <div className="growth-project-card-head">
                    <h3>{project.name}</h3>
                    <span className="growth-project-card-tag">{GOAL_LABELS[project.primary_goal]}</span>
                  </div>
                  <div className="growth-project-card-meta">
                    <span>{projectStatus(project.status).label}</span>
                    <span>{project.last_collected_at ? formatDateTime(project.last_collected_at).slice(0, 16) : "未采集"}</span>
                    <strong>{project.metrics.posts ? `${Math.min(100, Math.round(project.metrics.posts / 3))}%` : "0%"}</strong>
                  </div>
                </button>
              ))
            ) : (
              <div className="growth-project-empty">
                <strong>没有匹配项目</strong>
                <span>可以调整搜索条件，或新建一个项目。</span>
              </div>
            )}
          </div>
        </aside>

        {!selectedProject ? (
          <main className="growth-project-detail growth-project-detail--empty">
            <Target size={34} />
            <h2>选择一个项目</h2>
            <p>项目概览、研究配置和采集计划会集中显示在这里。</p>
          </main>
        ) : (
          <main className="growth-project-detail">
            {isProjectDetailLoading && (
              <div className="growth-project-detail-loading">
                <div className="growth-project-detail-loading-card">
                  <RefreshCw size={18} className="spin" />
                  <span>正在加载项目...</span>
                </div>
              </div>
            )}

            {notice && (
              <div className="growth-project-notice">
                <AlertTriangle size={16} />
                <span>{notice}</span>
                <button type="button" onClick={() => setNotice(null)} aria-label="关闭提示">
                  <X size={14} />
                </button>
              </div>
            )}

            <header className="project-detail-header-row">
              <div className="project-detail-header-left">
                <div className="project-title-line">
                  <h1>{selectedProject.name}</h1>
                  <span className={`project-status-capsule status-${headerStatus.dot}`}>
                    {headerStatus.label}
                  </span>
                </div>
                <div className="project-subtitle-line">
                  <span>研究目标：{GOAL_LABELS[selectedProject.primary_goal]}</span>
                  <span>平台：{selectedProject.platforms.map(labelPlatform).join(" / ") || "未设置"}</span>
                  <span>最近更新：{selectedProject.last_collected_at ? formatDateTime(selectedProject.last_collected_at).slice(0, 16) : "暂无"}</span>
                </div>
              </div>

              <div className="project-detail-header-right">
                {headerLiveText && (
                  <span className={`project-live-state-pill status-${headerStatus.dot}`}>
                    <i />
                    {headerLiveText}
                  </span>
                )}
                <Button variant="ghost" size="sm" onClick={() => void navigator.clipboard?.writeText(window.location.href)}>
                  <Share2 size={14} /> 分享
                </Button>
                <Button variant="primary" size="sm" onClick={() => setCollectionDialogOpen(true)}>
                  <Plus size={14} /> 新建采集任务
                </Button>
              </div>
            </header>

            <CollectionControlsDialog
              open={collectionDialogOpen}
              project={selectedProject}
              detail={selectedProjectDetail}
              controls={collectionControls}
              onClose={() => setCollectionDialogOpen(false)}
              onChange={setCollectionControls}
              onSubmit={() => void startCollection()}
            />

            <nav className="project-detail-tabs-line" aria-label="项目详情导航">
              {[
                ["overview", "项目概览"],
                ["config", "研究配置"],
                ["plan", "采集计划"],
                ["history", "项目操作"],
              ].map(([id, label]) => (
                <button
                  key={id}
                  type="button"
                  className={`project-detail-tab-btn ${activeTab === id ? "active" : ""}`}
                  onClick={() => setActiveTab(id as WorkspaceTab)}
                >
                  {id === "history" ? "历史任务" : label}
                </button>
              ))}
            </nav>

            {activeTab === "overview" && (
              <OverviewPanel
                project={selectedProject}
                detail={selectedProjectDetail}
                progress={selectedProjectProgress}
                onOpenPlan={() => setActiveTab("plan")}
                onOpenConfig={() => setActiveTab("config")}
                onOpenData={onOpenData}
                onOpenAi={onOpenAi}
              />
            )}

            {activeTab === "config" && (
              <ResearchConfigPanel
                project={selectedProject}
                detail={selectedProjectDetail}
                saving={isProjectDetailLoading}
                onSave={(payload) => onUpdateProject(selectedProject.id, payload)}
                onOpenPlan={() => setActiveTab("plan")}
                onDelete={() => requestProjectArchive("delete")}
              />
            )}

            {activeTab === "plan" && (
              <CollectionPlanPanel
                project={selectedProject}
                detail={selectedProjectDetail}
                progress={selectedProjectProgress}
                onCreateTask={() => setCollectionDialogOpen(true)}
                onPause={() => void pauseCollection()}
                onStop={() => void stopCollection()}
                onOpenData={onOpenData}
              />
            )}

            {activeTab === "history" && (
              <ProjectHistoryPanel
                project={selectedProject}
                detail={selectedProjectDetail}
                progress={selectedProjectProgress}
                onCreateTask={() => setCollectionDialogOpen(true)}
                onArchive={() => requestProjectArchive("archive")}
                onPause={() => void pauseCollection()}
                onStop={() => void stopCollection()}
                onOpenData={onOpenData}
                onOpenAi={onOpenAi}
              />
            )}

            <footer className="quick-actions-row-styled">
              <strong>快捷操作</strong>
              <button type="button" onClick={() => setCollectionDialogOpen(true)}>
                <Play size={14} /> 新建采集任务
              </button>
              <button type="button" onClick={onOpenData}>
                <BarChart3 size={14} /> 查看实时数据
              </button>
              <button type="button" onClick={onOpenAi}>
                <FileJson size={14} /> 生成洞察报告
              </button>
              <button type="button" onClick={() => requestProjectArchive("archive")}>
                <Download size={14} /> 归档项目
              </button>
            </footer>
          </main>
        )}
      </div>
    </section>
  );
}

function OverviewPanel({
  project,
  detail,
  progress,
  onOpenPlan,
  onOpenConfig,
  onOpenData,
  onOpenAi,
}: {
  project: GrowthProjectSummary;
  detail: GrowthProjectDetail | null;
  progress: GrowthProjectCollectionProgress | null;
  onOpenPlan: () => void;
  onOpenConfig: () => void;
  onOpenData: () => void;
  onOpenAi: () => void;
}) {
  const keywords = detail?.keywords || [];
  const sampleData = detail?.sample_data;
  const progressStatus = progress?.status || project.status;

  return (
    <div className="research-config-panel">
      <div className="research-config-main">
        <article className="workbench-card config-editor-card">
          <CardHead title="项目概览" badge={projectStatus(progressStatus).label} />

          <div className="config-impact-grid">
            <ConfigImpactItem icon={<Database size={15} />} label="帖子样本" value={formatNumber(sampleData?.posts || project.metrics.posts || 0)} />
            <ConfigImpactItem icon={<MessageSquare size={15} />} label="评论样本" value={formatNumber(sampleData?.comments || project.metrics.comments || 0)} />
            <ConfigImpactItem icon={<TrendingUp size={15} />} label="关键词数" value={`${keywords.length} 条`} />
            <ConfigImpactItem icon={<Clock size={15} />} label="最近采集" value={formatRelativeTime(project.last_collected_at)} />
          </div>

          <div className="config-section-block">
            <div className="config-section-title">
              <Target size={16} />
              <strong>关键词概览</strong>
            </div>
            <div className="config-impact-note">
              {(keywords.length
                ? keywords.map((item) => `${item.keyword}${item.type === "excluded" ? "（排除）" : ""}`).slice(0, 12)
                : ["暂无关键词"]).join(" / ")}
            </div>
          </div>

          <div className="config-section-block">
            <div className="config-section-title">
              <Layers size={16} />
              <strong>平台范围</strong>
            </div>
            <div className="config-impact-note">{project.platforms.map(labelPlatform).join(" / ") || "未设置平台"}</div>
          </div>
        </article>

        <aside className="config-impact-column">
          <article className="workbench-card config-impact-card">
            <CardHead title="下一步" />
            <div className="config-operation-list">
              <button type="button" onClick={onOpenConfig}>
                <Sparkles size={15} />
                <span>
                  <strong>优化研究配置</strong>
                  <small>补关键词、调整排除词、配置 AI 生成。</small>
                </span>
              </button>
              <button type="button" onClick={onOpenPlan}>
                <Database size={15} />
                <span>
                  <strong>配置采集计划</strong>
                  <small>选择采集平台、范围和单次规模。</small>
                </span>
              </button>
              <button type="button" onClick={onOpenData}>
                <BarChart3 size={15} />
                <span>
                  <strong>查看实时数据</strong>
                  <small>进入数据页检查当前样本与抓取结果。</small>
                </span>
              </button>
              <button type="button" onClick={onOpenAi}>
                <FileJson size={15} />
                <span>
                  <strong>生成洞察报告</strong>
                  <small>基于当前样本生成总结与建议。</small>
                </span>
              </button>
            </div>
          </article>
        </aside>
      </div>
    </div>
  );
}

function CollectionPlanPanel({
  project,
  detail,
  progress,
  onCreateTask,
  onPause,
  onStop,
  onOpenData,
}: {
  project: GrowthProjectSummary;
  detail: GrowthProjectDetail | null;
  progress: GrowthProjectCollectionProgress | null;
  onCreateTask: () => void;
  onPause: () => void;
  onStop: () => void;
  onOpenData: () => void;
}) {
  const running = progress?.status === "running" || progress?.status === "queued";
  const activeKeywords = (detail?.keywords || []).filter((item) => item.type !== "excluded").map((item) => item.keyword);
  const dailyCollectionLimit = detail?.settings?.daily_collection_limit_per_platform || DEFAULT_DAILY_COLLECTION_LIMIT_PER_PLATFORM;

  return (
    <div className="research-config-panel">
      <div className="research-config-main">
        <article className="workbench-card config-editor-card">
          <CardHead title="采集计划" badge={running ? "进行中" : "待执行"} />

          <div className="config-impact-grid">
            <ConfigImpactItem icon={<Database size={15} />} label="采集平台" value={supportedCollectionPlatforms(project.platforms).map(labelPlatform).join(" / ") || "未配置"} />
            <ConfigImpactItem icon={<Target size={15} />} label="采集关键词" value={`${activeKeywords.length} 条`} />
            <ConfigImpactItem
              icon={<Clock size={15} />}
              label="刷新频率"
              value={labelRefreshCadenceWithTime(detail?.settings?.refresh_cadence, detail?.settings?.refresh_time_utc8)}
            />
            <ConfigImpactItem icon={<Database size={15} />} label="每日每平台上限" value={`${dailyCollectionLimit} 条`} />
            <ConfigImpactItem icon={<BarChart3 size={15} />} label="项目状态" value={projectStatus(progress?.status || project.status).label} />
          </div>

          <div className="config-impact-note">
            当前计划会优先在 {supportedCollectionPlatforms(project.platforms).map(labelPlatform).join(" / ") || "配置的平台"} 上执行。
            如果项目配置里包含微博、B站、知乎等平台，它们会进入研究范围，但实时采集仍以小红书和抖音为主。
          </div>
        </article>

        <aside className="config-impact-column">
          <article className="workbench-card config-danger-card">
            <CardHead title="计划操作" />
            <div className="config-operation-list">
              <button type="button" onClick={onCreateTask}>
                <Play size={15} />
                <span>
                  <strong>新建采集任务</strong>
                  <small>按当前项目配置启动一次采集。</small>
                </span>
              </button>
              <button type="button" onClick={onPause}>
                <Pause size={15} />
                <span>
                  <strong>暂停采集</strong>
                  <small>对运行中的任务发送暂停请求。</small>
                </span>
              </button>
              <button type="button" className="danger" onClick={onStop}>
                <AlertTriangle size={15} />
                <span>
                  <strong>终止当前任务</strong>
                  <small>立即停止当前采集运行。</small>
                </span>
              </button>
              <button type="button" onClick={onOpenData}>
                <BarChart3 size={15} />
                <span>
                  <strong>查看实时数据</strong>
                  <small>检查本次采集返回的样本。</small>
                </span>
              </button>
            </div>
          </article>
        </aside>
      </div>
    </div>
  );
}

function ProjectHistoryPanelLegacyUnused({
  project,
  detail,
  progress,
  onCreateTask,
  onArchive,
  onPause,
  onStop,
  onOpenData,
  onOpenAi,
}: {
  project: GrowthProjectSummary;
  detail: GrowthProjectDetail | null;
  progress: GrowthProjectCollectionProgress | null;
  onCreateTask: () => void;
  onArchive: () => void;
  onPause: () => void;
  onStop: () => void;
  onOpenData: () => void;
  onOpenAi: () => void;
}) {
  const records = sortCollectionRecords(detail?.collection_records || []);
  const currentStatus = progress?.status || project.status;

  return (
    <div className="research-config-panel">
      <div className="research-config-main">
        <article className="workbench-card config-editor-card">
          <CardHead title="执行历史" badge={projectStatus(currentStatus).label} />

          <div className="config-impact-grid">
            <ConfigImpactItem icon={<Database size={15} />} label="采集记录" value={`${records.length} 条`} />
            <ConfigImpactItem icon={<Clock size={15} />} label="最近采集" value={formatRelativeTime(project.last_collected_at)} />
            <ConfigImpactItem icon={<BarChart3 size={15} />} label="当前状态" value={projectStatus(currentStatus).label} />
            <ConfigImpactItem icon={<TrendingUp size={15} />} label="样本状态" value={detail?.status_bar.sample_status || project.sample_status.label} />
          </div>

          <div className="config-section-block">
            <div className="config-section-title">
              <Database size={16} />
              <strong>最近任务</strong>
            </div>
            {records.length ? (
              <div className="config-operation-list">
                {records.slice(0, 5).map((record) => (
                  <div key={record.id} className="config-impact-note">
                    {record.name} / {record.platforms.map(labelPlatform).join(" / ") || "未配置平台"} / {record.status} / {formatRelativeTime(record.updated_at)}
                  </div>
                ))}
              </div>
            ) : (
              <div className="config-impact-note">暂无可展示的项目任务历史。</div>
            )}
          </div>
        </article>

        <aside className="config-impact-column">
          <article className="workbench-card config-danger-card">
            <CardHead title="历史操作" />
            <div className="config-operation-list">
              <button type="button" onClick={onCreateTask}>
                <Play size={15} />
                <span>
                  <strong>新建采集任务</strong>
                  <small>按当前项目配置新增一次采集执行。</small>
                </span>
              </button>
              <button type="button" onClick={onPause}>
                <Pause size={15} />
                <span>
                  <strong>暂停采集</strong>
                  <small>暂停当前项目的调度或运行中任务。</small>
                </span>
              </button>
              <button type="button" className="danger" onClick={onStop}>
                <AlertTriangle size={15} />
                <span>
                  <strong>终止当前任务</strong>
                  <small>立即停止当前执行链路。</small>
                </span>
              </button>
              <button type="button" onClick={onOpenData}>
                <BarChart3 size={15} />
                <span>
                  <strong>查看数据</strong>
                  <small>打开数据页核对当前样本和记录。</small>
                </span>
              </button>
              <button type="button" onClick={onOpenAi}>
                <FileJson size={15} />
                <span>
                  <strong>查看策略页</strong>
                  <small>跳转到项目级内容策略中心。</small>
                </span>
              </button>
              <button type="button" className="danger" onClick={onArchive}>
                <Download size={15} />
                <span>
                  <strong>归档项目</strong>
                  <small>保留历史样本与任务记录，移出活跃列表。</small>
                </span>
              </button>
            </div>
          </article>
        </aside>
      </div>
    </div>
  );
}

function ProjectActionsPanel({
  project,
  progress,
  onArchive,
  onPause,
  onStop,
  onOpenAi,
}: {
  project: GrowthProjectSummary;
  progress: GrowthProjectCollectionProgress | null;
  onArchive: () => void;
  onPause: () => void;
  onStop: () => void;
  onOpenAi: () => void;
}) {
  return (
    <div className="research-config-panel">
      <div className="research-config-main">
        <article className="workbench-card config-editor-card">
          <CardHead title="项目操作" badge={projectStatus(progress?.status || project.status).label} />
          <div className="config-operation-list">
            <button type="button" onClick={onPause}>
              <Pause size={15} />
              <span>
                <strong>暂停采集</strong>
                <small>用于临时停止当前运行流程。</small>
              </span>
            </button>
            <button type="button" className="danger" onClick={onStop}>
              <AlertTriangle size={15} />
              <span>
                <strong>终止当前任务</strong>
                <small>对运行中的任务发出终止请求。</small>
              </span>
            </button>
            <button type="button" onClick={onOpenAi}>
              <FileJson size={15} />
              <span>
                <strong>生成洞察</strong>
                <small>基于现有样本生成下一步建议。</small>
              </span>
            </button>
            <button type="button" className="danger" onClick={onArchive}>
              <Download size={15} />
              <span>
                <strong>归档项目</strong>
                <small>归档入口但保留任务、样本和证据记录。</small>
              </span>
            </button>
          </div>
        </article>
      </div>
    </div>
  );
}

function ProjectHistoryPanel({
  project,
  detail,
  progress,
  onCreateTask,
  onArchive,
  onPause,
  onStop,
  onOpenData,
  onOpenAi,
}: {
  project: GrowthProjectSummary;
  detail: GrowthProjectDetail | null;
  progress: GrowthProjectCollectionProgress | null;
  onCreateTask: () => void;
  onArchive: () => void;
  onPause: () => void;
  onStop: () => void;
  onOpenData: () => void;
  onOpenAi: () => void;
}) {
  const historyRecords = React.useMemo(
    () => sortCollectionRecords(detail?.collection_records || []),
    [detail?.collection_records],
  );
  const hasActiveRun = progress?.status === "running" || progress?.status === "queued";
  const currentJobId =
    (hasActiveRun
      ? progress?.current_job_id || progress?.running_job_id || progress?.progress.job?.id
      : historyRecords[0]?.id || progress?.current_job_id || progress?.progress.job?.id) || null;
  const currentRecord =
    historyRecords.find((record) => record.id === currentJobId) ||
    (progress?.progress.job
      ? {
          id: progress.progress.job.id,
          name: progress.progress.job.name,
          platforms: progress.progress.job.platforms || [],
          collection_mode: progress.progress.job.collection_mode || "search",
          keywords: progress.progress.job.keywords || [],
          status: progress.progress.job.status || progress.status,
          posts: progress.progress.sample_counts.posts || 0,
          comments: progress.progress.sample_counts.comments || 0,
          raw_records: progress.progress.sample_counts.raw_records || 0,
          updated_at: progress.progress.latest_event?.created_at || null,
        }
      : null);
  const currentStatusValue = progress?.status || currentRecord?.status || project.status;
  const currentStatus = projectStatus(currentStatusValue);
  const currentPlatforms = currentRecord?.platforms || [];
  const currentKeywords = currentRecord?.keywords || [];
  const queueEntry = progress?.queued_jobs.find((item) => item.job_id === currentJobId) || null;
  const samplePercent = progress?.progress.sample_percent ?? progress?.progress.percent ?? 0;
  const stepPercent = progress?.progress.step_percent ?? progress?.progress.percent ?? 0;
  const sampleCounts = progress?.progress.sample_counts || {
    posts: currentRecord?.posts || 0,
    comments: currentRecord?.comments || 0,
    raw_records: currentRecord?.raw_records || 0,
    creators: 0,
  };
  const unitCounts = progress?.progress.unit_counts || {
    total: 0,
    running: 0,
    succeeded: 0,
    failed: 0,
  };
  const latestEvent = progress?.progress.latest_event || progress?.progress.events?.[0] || null;
  const recentEvents = progress?.progress.events?.slice(0, 6) || [];
  const crawler = progress?.progress.crawler || null;
  const targetPosts = progress?.progress.target_counts?.posts || 0;
  const automation = progress?.automation || null;
  const automationDaemon = automation?.daemon || null;
  const automationState = automationLiveState(progress);
  const [currentTaskExpanded, setCurrentTaskExpanded] = React.useState(true);

  return (
    <div className="research-config-panel">
      <div className="research-config-main">
        <div className="history-panel-main">
          <article className={`workbench-card config-editor-card task-current-card ${currentTaskExpanded ? "" : "is-collapsed"}`}>
            <CardHead title="当前任务" badge={currentStatus.label} />
            {currentRecord ? (
              <>
                <div className="task-current-head">
                  <div>
                    <strong>{currentRecord.name || `采集任务 #${currentRecord.id}`}</strong>
                    <span>
                      任务 #{currentRecord.id}
                      {queueEntry ? ` · 队列第 ${queueEntry.queue_position} 位` : ""}
                      {currentRecord.updated_at ? ` · ${formatDateTime(currentRecord.updated_at).slice(0, 16)}` : ""}
                    </span>
                  </div>
                  <div className="task-current-head-actions">
                    <button
                      type="button"
                      className="task-collapse-btn"
                      onClick={() => setCurrentTaskExpanded((value) => !value)}
                      aria-expanded={currentTaskExpanded}
                    >
                      {currentTaskExpanded ? "收起" : "展开"}
                    </button>
                    <span className={`task-status-pill status-${currentStatus.dot}`}>
                      {collectionLiveLabel(progress, currentStatusValue)}
                    </span>
                  </div>
                </div>

                <div className="task-current-summary">
                  <span>{`样本 ${samplePercent}%`}</span>
                  <span>{`执行 ${stepPercent}%`}</span>
                  <span>{currentPlatforms.length ? currentPlatforms.map(labelPlatform).join(" / ") : "未配置平台"}</span>
                  <span>{currentKeywords.length ? `${currentKeywords.length} 个关键词` : "未设置关键词"}</span>
                  <span>{crawler?.status || "离线"}</span>
                </div>

                <div className="task-current-metrics">
                  <div className="task-current-metric">
                    <span>样本进度</span>
                    <strong>{samplePercent}%</strong>
                    <small>{targetPosts ? `${formatNumber(sampleCounts.posts)} / ${formatNumber(targetPosts)} 帖` : `已采集 ${formatNumber(sampleCounts.posts)} 帖`}</small>
                  </div>
                  <div className="task-current-metric">
                    <span>执行进度</span>
                    <strong>{stepPercent}%</strong>
                    <small>{`${unitCounts.succeeded || 0} 成功 / ${unitCounts.failed || 0} 失败 / ${unitCounts.total || 0} 总计`}</small>
                  </div>
                  <div className="task-current-metric">
                    <span>评论与原始数据</span>
                    <strong>{formatNumber(sampleCounts.comments)}</strong>
                    <small>{`${formatNumber(sampleCounts.raw_records)} 条原始记录`}</small>
                  </div>
                  <div className="task-current-metric">
                    <span>爬虫状态</span>
                    <strong>{crawler?.status || "离线"}</strong>
                    <small>{crawler?.platform ? `${labelPlatform(crawler.platform)} / ${crawler.crawler_type || "crawler"}` : "等待执行"}</small>
                  </div>
                </div>

                <div className="task-current-meta-grid">
                  <div className="task-current-meta-box">
                    <span>采集平台</span>
                    <strong>{currentPlatforms.length ? currentPlatforms.map(labelPlatform).join(" / ") : "未配置"}</strong>
                  </div>
                  <div className="task-current-meta-box">
                    <span>关键词范围</span>
                    <strong>{currentKeywords.length ? `${currentKeywords.length} 个关键词` : "未设置关键词"}</strong>
                  </div>
                </div>

                {currentKeywords.length > 0 && (
                  <div className="task-chip-list">
                    {currentKeywords.slice(0, 10).map((keyword) => (
                      <span key={keyword}>{keyword}</span>
                    ))}
                    {currentKeywords.length > 10 && <span>+{currentKeywords.length - 10}</span>}
                  </div>
                )}

                <div className="history-live-grid">
                  <div className="history-live-panel">
                    <span>最新任务事件</span>
                    <strong>{collectionEventLabel(latestEvent?.event_type)}</strong>
                    <p>{collectionEventMessage(latestEvent)}</p>
                    <small>
                      {latestEvent?.created_at ? formatDateTime(latestEvent.created_at).slice(0, 16) : "暂无时间"}
                      {latestEvent?.platform ? ` · ${labelPlatform(latestEvent.platform)}` : ""}
                    </small>
                  </div>
                  <div className="history-live-panel">
                    <span>最新爬虫日志</span>
                    <strong>{crawler?.latest_log?.level || "暂无日志"}</strong>
                    <p>{crawler?.latest_log?.message || "任务进入队列后，会在这里显示最近一条爬虫日志。"}</p>
                    <small>
                      {crawler?.latest_log?.timestamp ? formatDateTime(crawler.latest_log.timestamp).slice(0, 16) : "等待日志"}
                      {typeof crawler?.log_count === "number" ? ` · 共 ${crawler.log_count} 条` : ""}
                    </small>
                  </div>
                </div>

                <div className="history-timeline">
                  <div className="history-timeline-head">
                    <strong>最近运行轨迹</strong>
                    <span>{recentEvents.length ? `${recentEvents.length} 条` : "暂无事件"}</span>
                  </div>
                  {recentEvents.length ? (
                    recentEvents.map((event, index) => (
                      <div key={`${event.id || event.created_at || "event"}-${event.event_type || "unknown"}-${index}`} className="history-timeline-item">
                        <div className="history-timeline-copy">
                          <strong>{collectionEventLabel(event.event_type)}</strong>
                          <p>{collectionEventMessage(event)}</p>
                        </div>
                        <span>{event.created_at ? formatDateTime(event.created_at).slice(0, 16) : "刚刚"}</span>
                      </div>
                    ))
                  ) : (
                    <div className="collection-plan-empty-note">任务创建后，这里会展示队列、爬虫与采集单元事件。</div>
                  )}
                </div>
              </>
            ) : (
              <div className="collection-plan-empty-note">当前项目还没有采集任务。点击右侧“新建采集任务”后，这里会展示队列、进度和爬虫日志。</div>
            )}
          </article>

          <article className="workbench-card config-editor-card">
            <CardHead title="历史任务" badge={`${historyRecords.length} 条`} />
            {historyRecords.length ? (
              <div className="task-history-list">
                {historyRecords.map((record, index) => {
                  const status = projectStatus(record.id === currentJobId ? currentStatusValue : record.status);
                  const isCurrent = record.id === currentJobId;
                  return (
                    <div key={record.id} className={`task-history-row ${isCurrent ? "is-current" : ""}`}>
                      <div className="task-history-row-head">
                        <div>
                          <strong>{record.name || `采集任务 #${record.id}`}</strong>
                          <span>{`任务 #${record.id}${record.updated_at ? ` · ${formatDateTime(record.updated_at).slice(0, 16)}` : ""}`}</span>
                        </div>
                        <div className="task-history-row-status">
                          {isCurrent && <em>当前任务</em>}
                          {!isCurrent && index === 0 && <em>最近任务</em>}
                          <span className={`task-status-pill status-${status.dot}`}>{status.label}</span>
                        </div>
                      </div>
                      <div className="task-history-row-meta">
                        <span>{record.platforms.length ? record.platforms.map(labelPlatform).join(" / ") : "未配置平台"}</span>
                        <span>{record.keywords.length ? `${record.keywords.length} 个关键词` : "无关键词"}</span>
                        <span>{`${formatNumber(record.posts)} 帖 / ${formatNumber(record.comments)} 评 / ${formatNumber(record.raw_records)} 原始`}</span>
                        <span>{record.collection_mode || "search"}</span>
                      </div>
                    </div>
                  );
                })}
              </div>
            ) : (
              <div className="collection-plan-empty-note">当前项目还没有历史任务记录。</div>
            )}
          </article>
        </div>

        <aside className="config-impact-column">
          <article className="workbench-card config-editor-card automation-status-card">
            <CardHead title="自动采集" badge={labelAutomationCadence(automation?.enabled, automation?.interval_minutes)} />
            <div className="automation-status-head">
              <span className={`task-status-pill status-${automationState.dot}`}>{automationState.label}</span>
              <small>{automationState.note}</small>
            </div>
            <div className="automation-status-grid">
              <div className="automation-status-item">
                <span>下次执行</span>
                <strong>{automation?.next_run_at ? formatDateTime(automation.next_run_at).slice(0, 16) : "未计划"}</strong>
              </div>
              <div className="automation-status-item">
                <span>上次调度</span>
                <strong>{automation?.last_scheduled_at ? formatDateTime(automation.last_scheduled_at).slice(0, 16) : "暂无"}</strong>
              </div>
              <div className="automation-status-item">
                <span>守护进程</span>
                <strong>{automationDaemon?.running ? "在线" : "离线"}</strong>
              </div>
              <div className="automation-status-item">
                <span>最近心跳</span>
                <strong>{automationDaemon?.last_tick_at ? formatRelativeTime(automationDaemon.last_tick_at) : "暂无"}</strong>
              </div>
            </div>
            {automationDaemon?.last_error ? (
              <div className="automation-status-warning">
                <strong>最近错误</strong>
                <p>{automationDaemon.last_error}</p>
              </div>
            ) : (
              <p className="automation-status-note">自动采集会按计划创建新的采集任务，并在左侧历史任务列表中持续累积。</p>
            )}
          </article>

          <article className="workbench-card config-danger-card">
            <CardHead title="任务操作" />
            <div className="config-operation-list">
              <button type="button" onClick={onCreateTask}>
                <Play size={15} />
                <span>
                  <strong>新建采集任务</strong>
                  <small>按当前项目配置启动一次新的采集任务。</small>
                </span>
              </button>
              <button type="button" onClick={onPause}>
                <Pause size={15} />
                <span>
                  <strong>暂停采集</strong>
                  <small>对运行中的任务发送暂停请求。</small>
                </span>
              </button>
              <button type="button" className="danger" onClick={onStop}>
                <AlertTriangle size={15} />
                <span>
                  <strong>终止当前任务</strong>
                  <small>立即停止当前正在执行的采集任务。</small>
                </span>
              </button>
              <button type="button" onClick={onOpenData}>
                <BarChart3 size={15} />
                <span>
                  <strong>查看实时数据</strong>
                  <small>检查当前任务已经回流的帖子、评论和原始记录。</small>
                </span>
              </button>
              <button type="button" onClick={onOpenAi}>
                <FileJson size={15} />
                <span>
                  <strong>生成洞察</strong>
                  <small>基于当前项目样本生成最新洞察和建议。</small>
                </span>
              </button>
              <button type="button" className="danger" onClick={onArchive}>
                <Download size={15} />
                <span>
                  <strong>归档项目</strong>
                  <small>隐藏项目入口，但保留任务、样本与日志记录。</small>
                </span>
              </button>
            </div>
          </article>
        </aside>
      </div>
    </div>
  );
}

function ResearchConfigPanel({
  project,
  detail,
  saving,
  onSave,
  onOpenPlan,
  onDelete,
}: {
  project: GrowthProjectSummary;
  detail: GrowthProjectDetail | null;
  saving: boolean;
  onSave: (payload: GrowthProjectUpdatePayload) => Promise<void>;
  onOpenPlan: () => void;
  onDelete: () => void;
}) {
  const settings = detail?.settings;
  const [name, setName] = React.useState(project.name);
  const [primaryGoal, setPrimaryGoal] = React.useState<GrowthProjectSummary["primary_goal"]>(project.primary_goal);
  const [platforms, setPlatforms] = React.useState<string[]>(project.platforms);
  const [commentsEnabled, setCommentsEnabled] = React.useState(settings?.comment_collection_enabled ?? true);
  const [refreshCadence, setRefreshCadence] = React.useState<RefreshCadence>(
    (settings?.refresh_cadence as RefreshCadence | undefined) || "daily",
  );
  const [customIntervalValue, setCustomIntervalValue] = React.useState(settings?.custom_interval_value || 1);
  const [refreshTimeUtc8, setRefreshTimeUtc8] = React.useState(settings?.refresh_time_utc8 || "");
  const [dailyCollectionLimit, setDailyCollectionLimit] = React.useState(
    settings?.daily_collection_limit_per_platform || DEFAULT_DAILY_COLLECTION_LIMIT_PER_PLATFORM,
  );
  const [keywords, setKeywords] = React.useState<ConfigKeywordDraft[]>(() => keywordDraftsFromDetail(detail));
  const [selectedKeywordIds, setSelectedKeywordIds] = React.useState<string[]>([]);
  const [newKeyword, setNewKeyword] = React.useState("");
  const [newKeywordType, setNewKeywordType] = React.useState<GrowthProjectKeywordType>("expanded");
  const [projectBulkType, setProjectBulkType] = React.useState<GrowthProjectKeywordType>("expanded");
  const [candidateKeywords, setCandidateKeywords] = React.useState<KeywordCandidateDraft[]>([]);
  const [selectedCandidateIds, setSelectedCandidateIds] = React.useState<string[]>([]);
  const [candidateBulkType, setCandidateBulkType] = React.useState<GrowthProjectKeywordType>("expanded");
  const [candidateDrawerOpen, setCandidateDrawerOpen] = React.useState(false);
  const [aiPrompt, setAiPrompt] = React.useState("");
  const [aiRequestedCount, setAiRequestedCount] = React.useState(24);
  const [aiLoading, setAiLoading] = React.useState(false);
  const [aiProviderHint, setAiProviderHint] = React.useState<string | null>(null);
  const [importText, setImportText] = React.useState("");
  const [importKeywordType, setImportKeywordType] = React.useState<GrowthProjectKeywordType>("expanded");
  const [error, setError] = React.useState<string | null>(null);
  const [candidateError, setCandidateError] = React.useState<string | null>(null);
  const [baseline, setBaseline] = React.useState("");

  React.useEffect(() => {
    const nextKeywords = keywordDraftsFromDetail(detail);
    const nextCadence = ((settings?.refresh_cadence as RefreshCadence | undefined) || "daily");
    const nextState = {
      name: project.name,
      primary_goal: project.primary_goal,
      platforms: project.platforms,
      comment_collection_enabled: settings?.comment_collection_enabled ?? true,
      refresh_cadence: nextCadence,
      custom_interval_value: settings?.custom_interval_value || 1,
      refresh_time_utc8: settings?.refresh_time_utc8 || "",
      daily_collection_limit_per_platform: settings?.daily_collection_limit_per_platform || DEFAULT_DAILY_COLLECTION_LIMIT_PER_PLATFORM,
      keywords: nextKeywords.map(({ id: _id, ...item }) => item),
    };
    setName(nextState.name);
    setPrimaryGoal(nextState.primary_goal);
    setPlatforms(nextState.platforms);
    setCommentsEnabled(nextState.comment_collection_enabled);
    setRefreshCadence(nextState.refresh_cadence);
    setCustomIntervalValue(nextState.custom_interval_value);
    setRefreshTimeUtc8(nextState.refresh_time_utc8);
    setDailyCollectionLimit(nextState.daily_collection_limit_per_platform);
    setKeywords(nextKeywords);
    setSelectedKeywordIds([]);
    setCandidateKeywords([]);
    setSelectedCandidateIds([]);
    setCandidateDrawerOpen(false);
    setAiPrompt("");
    setAiRequestedCount(24);
    setAiProviderHint(null);
    setImportText("");
    setError(null);
    setCandidateError(null);
    setBaseline(JSON.stringify(nextState));
  }, [detail, project.id, project.name, project.platforms, project.primary_goal, settings]);

  const customCadence = refreshCadence === "custom_hours" || refreshCadence === "custom_days";
  const activeKeywordCount = keywords.filter((item) => item.keyword.trim() && item.keyword_type !== "excluded" && item.keyword_type !== "pending").length;
  const excludedKeywordCount = keywords.filter((item) => item.keyword.trim() && item.keyword_type === "excluded").length;
  const pendingKeywordCount = keywords.filter((item) => item.keyword.trim() && item.keyword_type === "pending").length;
  const collectionReadyPlatforms = supportedCollectionPlatforms(platforms);
  const selectedKeywordSet = new Set(selectedKeywordIds);
  const selectedCandidateSet = new Set(selectedCandidateIds);
  const sortedCandidates = sortCandidatesByType(candidateKeywords);
  const candidateCoreCount = candidateKeywords.filter((item) => item.keyword_type === "core").length;
  const candidateExpandedCount = candidateKeywords.filter((item) => item.keyword_type === "expanded").length;
  const candidateExcludedCount = candidateKeywords.filter((item) => item.keyword_type === "excluded").length;

  const currentSignature = JSON.stringify({
    name: name.trim(),
    primary_goal: primaryGoal,
    platforms,
    comment_collection_enabled: commentsEnabled,
    refresh_cadence: refreshCadence,
    custom_interval_value: customCadence ? customIntervalValue : 1,
    refresh_time_utc8: refreshCadence === "daily" ? refreshTimeUtc8.trim() : "",
    daily_collection_limit_per_platform: dailyCollectionLimit,
    keywords: normalizedKeywordPayload(keywords),
  });
  const dirty = currentSignature !== baseline;

  function togglePlatform(platform: string) {
    setPlatforms((current) => (current.includes(platform) ? current.filter((item) => item !== platform) : [...current, platform]));
  }

  function updateKeyword(id: string, patch: Partial<ConfigKeywordDraft>) {
    setKeywords((current) =>
      current.map((item) => {
        if (item.id !== id) return item;
        const next = { ...item, ...patch } as ConfigKeywordDraft;
        if (patch.keyword_type) {
          next.keyword_type = normalizeKeywordType(patch.keyword_type);
          next.status = keywordStatusForType(next.keyword_type);
        }
        return next;
      }),
    );
  }

  function addKeyword() {
    const keyword = newKeyword.trim();
    if (!keyword) return;
    setKeywords((current) =>
      mergeProjectKeywords(current, [
        {
          keyword,
          keyword_type: newKeywordType,
          source: "manual",
        },
      ]),
    );
    setNewKeyword("");
  }

  function updateCandidate(id: string, patch: Partial<KeywordCandidateDraft>) {
    setCandidateKeywords((current) =>
      current.map((item) => {
        if (item.id !== id) return item;
        const next = { ...item, ...patch } as KeywordCandidateDraft;
        if (patch.keyword_type) {
          next.keyword_type = normalizeKeywordType(patch.keyword_type);
          next.status = keywordStatusForType(next.keyword_type);
        }
        return next;
      }),
    );
  }

  async function generateAiCandidates() {
    const inputText = aiPrompt.trim();
    if (!inputText) {
      setCandidateError("请输入种子词、业务描述或明确指令。");
      return;
    }
    setAiLoading(true);
    setCandidateError(null);
    try {
      const response = await api<GrowthProjectKeywordAISuggestResponse>(
        `/api/research/growth-projects/${encodeURIComponent(project.id)}/keywords/ai-suggest`,
        {
          method: "POST",
          body: JSON.stringify({
            input_text: inputText,
            count: Math.max(5, Math.min(80, Math.trunc(aiRequestedCount || 24))),
          }),
        },
      );
      const additions = (response.suggestions || []).map((item) =>
        buildKeywordCandidateDraft(item.keyword, normalizeKeywordType(item.keyword_type), {
          source: item.source || "ai",
          reason: item.reason || null,
          confidence: item.confidence ?? null,
        }),
      );
      if (!additions.length) {
        setCandidateError("AI 没有返回可用关键词，请换一种描述再试。");
        return;
      }
      setCandidateKeywords((current) => mergeCandidateKeywords(current, additions));
      setCandidateDrawerOpen(true);
      setAiProviderHint([response.provider?.name, response.provider?.model].filter(Boolean).join(" / ") || "AI Gateway");
    } catch (cause) {
      setCandidateError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setAiLoading(false);
    }
  }

  function importCandidateKeywords() {
    const parsedKeywords = parseBulkKeywords(importText);
    if (!parsedKeywords.length) {
      setCandidateError("请输入要导入的关键词。");
      return;
    }
    const additions = parsedKeywords.map((keyword) =>
      buildKeywordCandidateDraft(keyword, importKeywordType, {
        source: "ai_imported",
      }),
    );
    setCandidateKeywords((current) => mergeCandidateKeywords(current, additions));
    setCandidateDrawerOpen(true);
    setImportText("");
    setCandidateError(null);
  }

  function addCandidatesToProject(mode: "selected" | "all") {
    const sourceItems = mode === "all" ? candidateKeywords : candidateKeywords.filter((item) => selectedCandidateSet.has(item.id));
    if (!sourceItems.length) {
      setCandidateError(mode === "selected" ? "请先选择候选词。" : "当前没有候选词可加入项目。");
      return;
    }
    setKeywords((current) =>
      mergeProjectKeywords(
        current,
        sourceItems.map((item) => ({
          keyword: item.keyword,
          keyword_type: item.keyword_type,
          source: item.source || "ai",
        })),
      ),
    );
    setCandidateError(null);
  }

  function resetForm() {
    const nextKeywords = keywordDraftsFromDetail(detail);
    setName(project.name);
    setPrimaryGoal(project.primary_goal);
    setPlatforms(project.platforms);
    setCommentsEnabled(settings?.comment_collection_enabled ?? true);
    setRefreshCadence(((settings?.refresh_cadence as RefreshCadence | undefined) || "daily"));
    setCustomIntervalValue(settings?.custom_interval_value || 1);
    setRefreshTimeUtc8(settings?.refresh_time_utc8 || "");
    setDailyCollectionLimit(settings?.daily_collection_limit_per_platform || DEFAULT_DAILY_COLLECTION_LIMIT_PER_PLATFORM);
    setKeywords(nextKeywords);
    setSelectedKeywordIds([]);
    setError(null);
  }

  async function submit() {
    const payloadKeywords = normalizedKeywordPayload(keywords);
    if (!name.trim()) {
      setError("项目名称不能为空。");
      return;
    }
    if (!platforms.length) {
      setError("至少选择一个覆盖平台。");
      return;
    }
    if (!payloadKeywords.some((item) => item.status === "active" && item.keyword_type !== "excluded")) {
      setError("至少保留一个可采集关键词。");
      return;
    }
    if (customCadence && customIntervalValue < 1) {
      setError("自定义刷新间隔必须大于 0。");
      return;
    }
    if (refreshCadence === "daily" && refreshTimeUtc8.trim() && !validUtc8Time(refreshTimeUtc8.trim())) {
      setError("刷新时间必须是 UTC+8 的 HH:mm 格式。");
      return;
    }
    if (dailyCollectionLimit < 1 || dailyCollectionLimit > 500) {
      setError("每日每平台上限必须在 1 到 500 之间。");
      return;
    }
    setError(null);
    await onSave({
      name: name.trim(),
      primary_goal: primaryGoal,
      platforms,
      comment_collection_enabled: commentsEnabled,
      refresh_cadence: refreshCadence,
      custom_interval_value: customCadence ? Math.max(1, Math.trunc(customIntervalValue)) : undefined,
      custom_interval_unit: refreshCadence === "custom_hours" ? "hours" : refreshCadence === "custom_days" ? "days" : undefined,
      refresh_time_utc8: refreshCadence === "daily" ? refreshTimeUtc8.trim() || null : null,
      daily_collection_limit_per_platform: Math.max(1, Math.min(500, Math.trunc(dailyCollectionLimit))),
      keywords: payloadKeywords,
    });
    setBaseline(currentSignature);
  }

  return (
    <section className="research-config-panel">
      <div className="research-config-main">
        <article className="workbench-card config-editor-card">
          <CardHead title="研究配置" badge={dirty ? "未保存" : "已同步"} />

          <div className="config-form-grid">
            <label className="config-field config-field-wide">
              <span>项目名称</span>
              <input value={name} onChange={(event) => setName(event.currentTarget.value)} />
            </label>
            <label className="config-field">
              <span>研究目标</span>
              <select value={primaryGoal} onChange={(event) => setPrimaryGoal(event.currentTarget.value as GrowthProjectSummary["primary_goal"])}>
                {GOAL_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="config-field">
              <span>刷新频率</span>
              <select value={refreshCadence} onChange={(event) => setRefreshCadence(event.currentTarget.value as RefreshCadence)}>
                {REFRESH_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
            {refreshCadence === "daily" && (
              <label className="config-field">
                <span>刷新时间 UTC+8（可选）</span>
                <input
                  type="time"
                  value={refreshTimeUtc8}
                  onChange={(event) => setRefreshTimeUtc8(event.currentTarget.value)}
                />
                <small>不填时按保存时间每 24 小时刷新。</small>
              </label>
            )}
            <label className="config-field">
              <span>每日每平台上限</span>
              <input
                type="number"
                min={1}
                max={500}
                value={dailyCollectionLimit}
                onChange={(event) =>
                  setDailyCollectionLimit(toInteger(Number(event.currentTarget.value), DEFAULT_DAILY_COLLECTION_LIMIT_PER_PLATFORM, 1))
                }
              />
            </label>
            {customCadence && (
              <label className="config-field">
                <span>间隔数值</span>
                <input
                  type="number"
                  min={1}
                  value={customIntervalValue}
                  onChange={(event) => setCustomIntervalValue(toInteger(Number(event.currentTarget.value), 1, 1))}
                />
              </label>
            )}
          </div>

          <div className="config-section-block">
            <div className="config-section-title">
              <Layers size={16} />
              <strong>覆盖平台</strong>
            </div>
            <div className="config-platform-grid">
              {PROJECT_PLATFORM_OPTIONS.map((platform) => {
                const selected = platforms.includes(platform);
                return (
                  <button
                    type="button"
                    key={platform}
                    className={`config-platform-option ${selected ? "selected" : ""}`}
                    onClick={() => togglePlatform(platform)}
                  >
                    <PlatformName platform={platform} />
                    <span>{COLLECTION_PLATFORMS.includes(platform) ? "可直接采集" : "样本分析"}</span>
                  </button>
                );
              })}
            </div>
          </div>

          <div className="config-section-block compact">
            <div className="config-section-title">
              <MessageSquare size={16} />
              <strong>评论采集</strong>
            </div>
            <label className="config-switch-row">
              <input type="checkbox" checked={commentsEnabled} onChange={(event) => setCommentsEnabled(event.currentTarget.checked)} />
              <span>
                <strong>{commentsEnabled ? "采集帖子与评论" : "仅采集帖子"}</strong>
                <small>{commentsEnabled ? "新任务会回带评论样本，用于补充情绪和痛点分析。" : "采集速度更快，但评论层洞察会减少。"}</small>
              </span>
            </label>
          </div>

          <div className="config-section-block">
            <div className="config-section-title">
              <Target size={16} />
              <strong>项目关键词</strong>
            </div>
            <div className="config-keyword-toolbar">
              <div className="config-keyword-toolbar-copy">
                <strong>当前配置</strong>
                <span>保存后会进入项目正式配置，直接影响采集任务。</span>
              </div>
              <div className="config-keyword-bulk">
                <button type="button" className="config-mini-action" onClick={() => setSelectedKeywordIds(selectedKeywordIds.length === keywords.length ? [] : keywords.map((item) => item.id))}>
                  {selectedKeywordIds.length === keywords.length && keywords.length ? "取消全选" : "全选"}
                </button>
                <select value={projectBulkType} onChange={(event) => setProjectBulkType(event.currentTarget.value as GrowthProjectKeywordType)}>
                  {Object.entries(KEYWORD_TYPE_LABELS).map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </select>
                <button
                  type="button"
                  className="config-mini-action"
                  onClick={() =>
                    setKeywords((current) =>
                      current.map((item) =>
                        selectedKeywordSet.has(item.id)
                          ? { ...item, keyword_type: projectBulkType, status: keywordStatusForType(projectBulkType) }
                          : item,
                      ),
                    )}
                >
                  批量改类型
                </button>
                <button
                  type="button"
                  className="config-mini-action danger"
                  onClick={() => {
                    setKeywords((current) => current.filter((item) => !selectedKeywordSet.has(item.id)));
                    setSelectedKeywordIds([]);
                  }}
                >
                  删除选中
                </button>
              </div>
            </div>

            <div className="config-keyword-list">
              {keywords.length ? (
                keywords.map((item) => (
                  <div className="config-keyword-row" key={item.id}>
                    <label className="config-keyword-checkbox">
                      <input
                        type="checkbox"
                        checked={selectedKeywordSet.has(item.id)}
                        onChange={() =>
                          setSelectedKeywordIds((current) =>
                            current.includes(item.id) ? current.filter((id) => id !== item.id) : [...current, item.id],
                          )
                        }
                      />
                    </label>
                    <input value={item.keyword} onChange={(event) => updateKeyword(item.id, { keyword: event.currentTarget.value })} />
                    <select value={item.keyword_type} onChange={(event) => updateKeyword(item.id, { keyword_type: event.currentTarget.value as GrowthProjectKeywordType })}>
                      {Object.entries(KEYWORD_TYPE_LABELS).map(([value, label]) => (
                        <option key={value} value={value}>
                          {label}
                        </option>
                      ))}
                    </select>
                    <button type="button" onClick={() => setKeywords((current) => current.filter((keyword) => keyword.id !== item.id))} aria-label="移除关键词">
                      <X size={14} />
                    </button>
                  </div>
                ))
              ) : (
                <div className="config-empty-keywords">暂无关键词</div>
              )}
            </div>

            <div className="config-keyword-add-row">
              <input value={newKeyword} onChange={(event) => setNewKeyword(event.currentTarget.value)} placeholder="手动补充一个关键词" />
              <select value={newKeywordType} onChange={(event) => setNewKeywordType(event.currentTarget.value as GrowthProjectKeywordType)}>
                {Object.entries(KEYWORD_TYPE_LABELS).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
              <Button variant="ghost" size="sm" onClick={addKeyword}>
                <Plus size={14} /> 添加
              </Button>
            </div>
            <div className="config-helper-text">
              当前项目词：可采集 {activeKeywordCount} 个，排除词 {excludedKeywordCount} 个，待确认 {pendingKeywordCount} 个。
            </div>
          </div>

          <div className="config-section-block">
            <div className="config-section-title">
              <Sparkles size={16} />
              <strong>AI 生成与候选词池</strong>
            </div>
            <div className="config-ai-panel">
              <div className="config-ai-grid">
                <label className="config-field config-field-wide">
                  <span>输入种子词或指令</span>
                  <textarea
                    className="config-ai-textarea"
                    value={aiPrompt}
                    onChange={(event) => setAiPrompt(event.currentTarget.value)}
                    placeholder="例如：暑期教育项目，面向家长决策，生成适合小红书和抖音采集的核心词、扩展词和排除词。"
                  />
                </label>
                <label className="config-field">
                  <span>生成数量</span>
                  <input
                    type="number"
                    min={5}
                    max={80}
                    value={aiRequestedCount}
                    onChange={(event) => setAiRequestedCount(toInteger(Number(event.currentTarget.value), 24, 5))}
                  />
                </label>
                <div className="config-ai-actions">
                  <Button variant="primary" onClick={() => void generateAiCandidates()} disabled={aiLoading}>
                    {aiLoading ? <RefreshCw size={15} className="spin" /> : <Sparkles size={15} />}
                    生成关键词
                  </Button>
                  {aiProviderHint && <span className="config-ai-provider">{aiProviderHint}</span>}
                </div>
              </div>

              <div className="config-candidate-summary">
                <div className="config-keyword-toolbar-copy">
                  <strong>候选词池</strong>
                  <span>
                    核心词 {candidateCoreCount} / 扩展词 {candidateExpandedCount} / 排除词 {candidateExcludedCount}
                  </span>
                </div>
                <Button variant="ghost" onClick={() => setCandidateDrawerOpen(true)}>
                  <Layers size={15} />
                  管理候选词
                </Button>
              </div>

              <Drawer open={candidateDrawerOpen} onOpenChange={setCandidateDrawerOpen} title="候选词池" description="管理 AI 生成和批量导入的候选关键词。">
                <div className="config-candidate-drawer">
              <div className="config-keyword-toolbar candidate">
                <div className="config-keyword-toolbar-copy">
                  <strong>候选词池</strong>
                  <span>
                    核心词 {candidateKeywords.filter((item) => item.keyword_type === "core").length} / 扩展词{" "}
                    {candidateKeywords.filter((item) => item.keyword_type === "expanded").length} / 排除词{" "}
                    {candidateKeywords.filter((item) => item.keyword_type === "excluded").length}
                  </span>
                </div>
                <div className="config-keyword-bulk">
                  <button type="button" className="config-mini-action" onClick={() => setSelectedCandidateIds(selectedCandidateIds.length === candidateKeywords.length ? [] : candidateKeywords.map((item) => item.id))}>
                    {selectedCandidateIds.length === candidateKeywords.length && candidateKeywords.length ? "取消全选" : "全选"}
                  </button>
                  <select value={candidateBulkType} onChange={(event) => setCandidateBulkType(event.currentTarget.value as GrowthProjectKeywordType)}>
                    {Object.entries(KEYWORD_TYPE_LABELS).map(([value, label]) => (
                      <option key={value} value={value}>
                        {label}
                      </option>
                    ))}
                  </select>
                  <button
                    type="button"
                    className="config-mini-action"
                    onClick={() =>
                      setCandidateKeywords((current) =>
                        current.map((item) =>
                          selectedCandidateSet.has(item.id)
                            ? { ...item, keyword_type: candidateBulkType, status: keywordStatusForType(candidateBulkType) }
                            : item,
                        ),
                      )
                    }
                  >
                    批量改类型
                  </button>
                  <button type="button" className="config-mini-action" onClick={() => addCandidatesToProject("selected")}>
                    加入选中
                  </button>
                  <button type="button" className="config-mini-action" onClick={() => addCandidatesToProject("all")}>
                    全部加入项目
                  </button>
                  <button
                    type="button"
                    className="config-mini-action danger"
                    onClick={() => {
                      setCandidateKeywords((current) => current.filter((item) => !selectedCandidateSet.has(item.id)));
                      setSelectedCandidateIds([]);
                    }}
                  >
                    删除选中
                  </button>
                </div>
              </div>

              <div className="config-import-grid">
                <label className="config-field config-field-wide">
                  <span>批量导入候选词</span>
                  <textarea
                    className="config-ai-textarea compact"
                    value={importText}
                    onChange={(event) => setImportText(event.currentTarget.value)}
                    placeholder="支持换行、逗号或分号分隔。导入后进入候选词池，不会直接保存到项目。"
                  />
                </label>
                <label className="config-field">
                  <span>默认类型</span>
                  <select value={importKeywordType} onChange={(event) => setImportKeywordType(event.currentTarget.value as GrowthProjectKeywordType)}>
                    {Object.entries(KEYWORD_TYPE_LABELS).map(([value, label]) => (
                      <option key={value} value={value}>
                        {label}
                      </option>
                    ))}
                  </select>
                </label>
                <div className="config-ai-actions">
                  <Button variant="ghost" onClick={importCandidateKeywords}>
                    <Download size={15} />
                    导入到候选池
                  </Button>
                </div>
              </div>

              <div className="config-candidate-groups">
                {sortedCandidates.length ? (
                  (["core", "expanded", "excluded", "pending"] as const).map((keywordType) => {
                    const rows = sortedCandidates.filter((item) => item.keyword_type === keywordType);
                    if (!rows.length) return null;
                    return (
                      <div className="config-candidate-group" key={keywordType}>
                        <div className="config-candidate-group-head">
                          <strong>{KEYWORD_TYPE_LABELS[keywordType]}</strong>
                          <span>{rows.length}</span>
                        </div>
                        <div className="config-keyword-list">
                          {rows.map((item) => (
                            <div className="config-keyword-row candidate" key={item.id}>
                              <label className="config-keyword-checkbox">
                                <input
                                  type="checkbox"
                                  checked={selectedCandidateSet.has(item.id)}
                                  onChange={() =>
                                    setSelectedCandidateIds((current) =>
                                      current.includes(item.id) ? current.filter((id) => id !== item.id) : [...current, item.id],
                                    )
                                  }
                                />
                              </label>
                              <div className="config-candidate-cell">
                                <input value={item.keyword} onChange={(event) => updateCandidate(item.id, { keyword: event.currentTarget.value })} />
                                <div className="config-candidate-meta">
                                  <span>{item.reason || "未提供分类原因"}</span>
                                  {typeof item.confidence === "number" && <strong>{Math.round(item.confidence * 100)}%</strong>}
                                </div>
                              </div>
                              <select value={item.keyword_type} onChange={(event) => updateCandidate(item.id, { keyword_type: event.currentTarget.value as GrowthProjectKeywordType })}>
                                {Object.entries(KEYWORD_TYPE_LABELS).map(([value, label]) => (
                                  <option key={value} value={value}>
                                    {label}
                                  </option>
                                ))}
                              </select>
                              <button type="button" onClick={() => setCandidateKeywords((current) => current.filter((candidate) => candidate.id !== item.id))} aria-label="移除候选词">
                                <X size={14} />
                              </button>
                            </div>
                          ))}
                        </div>
                      </div>
                    );
                  })
                ) : (
                  <div className="config-empty-keywords">AI 生成或批量导入后，候选词会显示在这里。</div>
                )}
              </div>
                </div>
              </Drawer>
            </div>
          </div>

          {error && <div className="config-error-banner">{error}</div>}
          {candidateError && <div className="config-error-banner">{candidateError}</div>}

          <div className="config-form-actions">
            <Button variant="ghost" onClick={resetForm} disabled={!dirty || saving}>
              <RotateCcw size={15} /> 重置
            </Button>
            <Button variant="primary" onClick={() => void submit()} disabled={!dirty || saving}>
              {saving ? <RefreshCw size={15} className="spin" /> : <Save size={15} />}
              保存配置
            </Button>
          </div>
        </article>

        <aside className="config-impact-column">
          <article className="workbench-card config-impact-card">
            <CardHead title="配置影响" />
            <div className="config-impact-grid">
              <ConfigImpactItem icon={<Target size={15} />} label="可采集关键词" value={`${activeKeywordCount} 条`} />
              <ConfigImpactItem icon={<ShieldCheck size={15} />} label="排除词" value={`${excludedKeywordCount} 条`} />
              <ConfigImpactItem icon={<Database size={15} />} label="直接采集平台" value={`${collectionReadyPlatforms.length} 个`} />
              <ConfigImpactItem icon={<Clock size={15} />} label="刷新方式" value={labelRefreshCadenceWithTime(refreshCadence, refreshTimeUtc8)} />
              <ConfigImpactItem icon={<Target size={15} />} label="每日每平台上限" value={`${dailyCollectionLimit} 条`} />
              <ConfigImpactItem icon={<Sparkles size={15} />} label="待处理候选词" value={`${candidateKeywords.length} 条`} />
            </div>
            <div className="config-impact-note">
              {collectionReadyPlatforms.length
                ? `下次采集会优先使用 ${collectionReadyPlatforms.map(labelPlatform).join(" / ")}。`
                : "当前平台仅进入研究范围，不会自动创建实时采集任务。"}
            </div>
          </article>

          <article className="workbench-card config-danger-card">
            <CardHead title="项目操作" />
            <div className="config-operation-list">
              <button type="button" onClick={onOpenPlan}>
                <Database size={15} />
                <span>
                  <strong>配置采集计划</strong>
                  <small>调整平台、采集范围和单次规模。</small>
                </span>
              </button>
              <button type="button" className="danger" onClick={onDelete}>
                <AlertTriangle size={15} />
                <span>
                  <strong>删除项目</strong>
                  <small>归档项目入口，已采集样本与任务记录会保留。</small>
                </span>
              </button>
            </div>
          </article>
        </aside>
      </div>
    </section>
  );
}

function CollectionControlsDialog({
  open,
  project,
  detail,
  controls,
  onClose,
  onChange,
  onSubmit,
}: {
  open: boolean;
  project: GrowthProjectSummary;
  detail: GrowthProjectDetail | null;
  controls: GrowthProjectCollectionRunPayload;
  onClose: () => void;
  onChange: (payload: GrowthProjectCollectionRunPayload) => void;
  onSubmit: () => void;
}) {
  if (!open) return null;

  const projectKeywords = (detail?.keywords || []).filter((item) => item.type !== "excluded").map((item) => item.keyword);
  const supportsSelected = controls.keyword_scope === "selected_project" || controls.keyword_scope === "selected_project_plus_extra";
  const supportsExtra =
    controls.keyword_scope === "all_project_plus_extra" ||
    controls.keyword_scope === "selected_project_plus_extra" ||
    controls.keyword_scope === "extra_only";

  function togglePlatform(platform: string) {
    onChange({
      ...controls,
      platforms: controls.platforms.includes(platform)
        ? controls.platforms.filter((item) => item !== platform)
        : [...controls.platforms, platform],
    });
  }

  function toggleKeyword(keyword: string) {
    onChange({
      ...controls,
      selected_keywords: controls.selected_keywords.includes(keyword)
        ? controls.selected_keywords.filter((item) => item !== keyword)
        : [...controls.selected_keywords, keyword],
    });
  }

  return (
    <div className="collection-task-overlay" role="dialog" aria-modal="true">
      <form
        className="collection-task-dialog"
        onSubmit={(event) => {
          event.preventDefault();
          onSubmit();
        }}
      >
        <header className="collection-task-head">
          <div>
            <strong>新建采集任务</strong>
            <span>{project.name}</span>
          </div>
          <button type="button" onClick={onClose} aria-label="关闭">
            <X size={16} />
          </button>
        </header>

        <section className="collection-task-section">
          <h3>采集平台</h3>
          <div className="collection-choice-grid">
            {supportedCollectionPlatforms(project.platforms).map((platform) => (
              <label key={platform} className="collection-choice">
                <input type="checkbox" checked={controls.platforms.includes(platform)} onChange={() => togglePlatform(platform)} />
                <span>{labelPlatform(platform)}</span>
              </label>
            ))}
          </div>
        </section>

        <section className="collection-task-section">
          <h3>关键词范围</h3>
          <label className="collection-field">
            <span>范围</span>
            <select
              value={controls.keyword_scope}
              onChange={(event) =>
                onChange({
                  ...controls,
                  keyword_scope: event.currentTarget.value as GrowthProjectCollectionRunPayload["keyword_scope"],
                })}
            >
              <option value="all_project">全部项目关键词</option>
              <option value="selected_project">仅选中的项目关键词</option>
              <option value="all_project_plus_extra">全部项目关键词 + 额外关键词</option>
              <option value="selected_project_plus_extra">选中项目关键词 + 额外关键词</option>
              <option value="extra_only">仅额外关键词</option>
            </select>
          </label>

          {supportsSelected && (
            <div className="collection-keyword-box">
              {projectKeywords.map((keyword) => (
                <label key={keyword} className="collection-keyword-option">
                  <input type="checkbox" checked={controls.selected_keywords.includes(keyword)} onChange={() => toggleKeyword(keyword)} />
                  <span>{keyword}</span>
                </label>
              ))}
            </div>
          )}

          {supportsExtra && (
            <label className="collection-field">
              <span>额外关键词</span>
              <textarea
                value={controls.extra_keywords.join("\n")}
                onChange={(event) => onChange({ ...controls, extra_keywords: parseBulkKeywords(event.currentTarget.value) })}
                placeholder="支持换行或逗号分隔"
              />
            </label>
          )}
        </section>

        <section className="collection-task-section">
          <h3>采集规模</h3>
          <div className="collection-controls-grid">
            <label>
              每平台目标帖子
              <input
                type="number"
                min={10}
                max={500}
                value={controls.target_posts_per_platform}
                onChange={(event) =>
                  onChange({
                    ...controls,
                    target_posts_per_platform: toInteger(event.currentTarget.valueAsNumber, DEFAULT_DAILY_COLLECTION_LIMIT_PER_PLATFORM, 10),
                  })}
              />
            </label>
            <label>
              每关键词/平台上限
              <input
                type="number"
                min={1}
                max={1000}
                value={controls.max_results_per_keyword_per_platform}
                onChange={(event) =>
                  onChange({
                    ...controls,
                    max_results_per_keyword_per_platform: toInteger(event.currentTarget.valueAsNumber, DEFAULT_DAILY_COLLECTION_LIMIT_PER_PLATFORM, 1),
                  })}
              />
            </label>
          </div>
        </section>

        <footer className="collection-task-foot">
          <Button variant="ghost" onClick={onClose} type="button">
            取消
          </Button>
          <Button variant="primary" type="submit">
            创建任务
          </Button>
        </footer>
      </form>
    </div>
  );
}

function ProjectCreateDialog({
  onClose,
  onCreate,
}: {
  onClose: () => void;
  onCreate: (payload: GrowthProjectCreatePayload) => Promise<void>;
}) {
  const [name, setName] = React.useState(DEFAULT_PROJECT_NAME);
  const [primaryGoal, setPrimaryGoal] = React.useState<GrowthProjectSummary["primary_goal"]>("mixed_research");
  const [platforms, setPlatforms] = React.useState<string[]>(["xhs", "dy"]);
  const [keywordsText, setKeywordsText] = React.useState("教育培训\n升学规划");
  const [refreshCadence, setRefreshCadence] = React.useState<GrowthProjectCreatePayload["refresh_cadence"]>("daily");
  const [dailyCollectionLimit, setDailyCollectionLimit] = React.useState(DEFAULT_DAILY_COLLECTION_LIMIT_PER_PLATFORM);
  const [collectionDepth, setCollectionDepth] = React.useState<GrowthProjectCreatePayload["collection_depth"]>("standard");
  const [submitting, setSubmitting] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  function togglePlatform(platform: string) {
    setPlatforms((current) => (current.includes(platform) ? current.filter((item) => item !== platform) : [...current, platform]));
  }

  async function submit() {
    const keywords = parseBulkKeywords(keywordsText);
    if (!name.trim()) {
      setError("项目名称不能为空。");
      return;
    }
    if (!platforms.length) {
      setError("至少选择一个平台。");
      return;
    }
    if (!keywords.length) {
      setError("至少填写一个关键词。");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await onCreate({
        name: name.trim(),
        primary_goal: primaryGoal,
        platforms,
        keywords,
        collection_depth: collectionDepth,
        refresh_cadence: refreshCadence,
        daily_collection_limit_per_platform: Math.max(1, Math.min(500, Math.trunc(dailyCollectionLimit))),
        auto_ai_analysis: true,
        start_immediately: false,
      });
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="project-create-overlay">
      <div className="project-create-dialog workbench-card">
        <CardHead title="新建项目" />
        <label className="config-field">
          <span>项目名称</span>
          <input value={name} onChange={(event) => setName(event.currentTarget.value)} />
        </label>
        <label className="config-field">
          <span>研究目标</span>
          <select value={primaryGoal} onChange={(event) => setPrimaryGoal(event.currentTarget.value as GrowthProjectSummary["primary_goal"])}>
            {GOAL_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
        <div className="config-section-block">
          <div className="config-section-title">
            <Layers size={16} />
            <strong>覆盖平台</strong>
          </div>
          <div className="config-platform-grid">
            {PROJECT_PLATFORM_OPTIONS.map((platform) => (
              <button
                type="button"
                key={platform}
                className={`config-platform-option ${platforms.includes(platform) ? "selected" : ""}`}
                onClick={() => togglePlatform(platform)}
              >
                <PlatformName platform={platform} />
                <span>{COLLECTION_PLATFORMS.includes(platform) ? "可采集" : "研究范围"}</span>
              </button>
            ))}
          </div>
        </div>
        <label className="config-field">
          <span>初始关键词</span>
          <textarea className="config-ai-textarea compact" value={keywordsText} onChange={(event) => setKeywordsText(event.currentTarget.value)} />
        </label>
        <div className="config-form-grid">
          <label className="config-field">
            <span>刷新频率</span>
            <select value={refreshCadence} onChange={(event) => setRefreshCadence(event.currentTarget.value as GrowthProjectCreatePayload["refresh_cadence"])}>
              {REFRESH_OPTIONS.filter((item) => item.value === "off" || item.value === "daily" || item.value === "three_days" || item.value === "weekly").map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
          <label className="config-field">
            <span>采集深度</span>
            <select value={collectionDepth} onChange={(event) => setCollectionDepth(event.currentTarget.value as GrowthProjectCreatePayload["collection_depth"])}>
              <option value="lightweight">轻量</option>
              <option value="standard">标准</option>
              <option value="deep">深度</option>
            </select>
          </label>
          <label className="config-field">
            <span>每日每平台上限</span>
            <input
              type="number"
              min={1}
              max={500}
              value={dailyCollectionLimit}
              onChange={(event) =>
                setDailyCollectionLimit(toInteger(Number(event.currentTarget.value), DEFAULT_DAILY_COLLECTION_LIMIT_PER_PLATFORM, 1))
              }
            />
          </label>
        </div>
        {error && <div className="config-error-banner">{error}</div>}
        <div className="config-form-actions">
          <Button variant="ghost" onClick={onClose} disabled={submitting}>
            取消
          </Button>
          <Button variant="primary" onClick={() => void submit()} disabled={submitting}>
            {submitting ? <RefreshCw size={15} className="spin" /> : <Save size={15} />}
            创建项目
          </Button>
        </div>
      </div>
    </div>
  );
}

function CardHead({
  title,
  badge,
}: {
  title: string;
  badge?: string;
}) {
  return (
    <div className="workbench-card-head">
      <div className="workbench-card-head-copy">
        <strong>{title}</strong>
      </div>
      {badge && <span className="workbench-card-badge">{badge}</span>}
    </div>
  );
}

function ConfigImpactItem({
  icon,
  label,
  value,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
}) {
  return (
    <div className="config-impact-item">
      <em>{icon}</em>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function PlatformName({ platform }: { platform: string }) {
  const label =
    {
      dy: "抖音",
      xhs: "小红书",
      wb: "微博",
      bili: "B站",
      ks: "快手",
      zhihu: "知乎",
      tieba: "贴吧",
      wechat: "微信",
    }[platform] || platform;

  return <strong className="config-platform-label">{label}</strong>;
}

function PlatformBadge({ platform }: { platform: string }) {
  const meta =
    {
      dy: { label: "抖音", short: "抖", color: "#111827" },
      xhs: { label: "小红书", short: "红", color: "#ff2442" },
      wb: { label: "微博", short: "微", color: "#f59e0b" },
      bili: { label: "B站", short: "B", color: "#00a1d6" },
      ks: { label: "快手", short: "快", color: "#ff7a00" },
      zhihu: { label: "知乎", short: "知", color: "#2563eb" },
      tieba: { label: "贴吧", short: "贴", color: "#3b82f6" },
      wechat: { label: "微信", short: "微", color: "#1aad19" },
    }[platform] || { label: platform, short: platform.slice(0, 1).toUpperCase(), color: "#64748b" };

  return (
    <div className="config-platform-badge">
      <span className="config-platform-badge-dot" style={{ backgroundColor: meta.color }}>
        {meta.short}
      </span>
      <strong>{meta.label}</strong>
    </div>
  );
}
