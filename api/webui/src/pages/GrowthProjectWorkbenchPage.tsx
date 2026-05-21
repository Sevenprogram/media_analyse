import React from "react";
import {
  Activity,
  AlertTriangle,
  Archive,
  Bot,
  Copy,
  Database,
  ExternalLink,
  FileJson,
  Pause,
  Pencil,
  Play,
  Plus,
  RefreshCw,
  Search,
  Settings,
  Square,
  Trash2,
} from "lucide-react";
import { Badge, Button, Card, CardDescription, CardHeader, CardTitle, ConfirmDialog, Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui";
import { api } from "../utils/api";
import { formatDateTime, formatNumber, labelPlatform } from "../utils/format";
import type { GrowthProjectCollectionProgress, GrowthProjectCreatePayload, GrowthProjectDetail, GrowthProjectSummary, GrowthProjectUpdatePayload, ScenePackOption } from "../types";

const GOAL_LABELS: Record<GrowthProjectSummary["primary_goal"], string> = {
  topic_discovery: "找选题",
  creator_discovery: "找达人",
  keyword_expansion: "扩关键词",
  competitor_monitoring: "盯竞品",
  mixed_research: "综合研究",
};

const ACTION_LABELS: Record<string, string> = {
  backfill_comments: "补抓评论",
  backfill_posts: "补抓帖子",
  generate_insight: "生成洞察",
  start_collection: "开始采集",
  view_failed_jobs: "查看失败任务",
  wait_for_collection: "等待采集完成",
};

const SAMPLE_STATUS_LABELS: Record<string, string> = {
  collection_issue: "采集异常，需要处理",
  collecting: "采集中",
  sample_insufficient: "帖子样本不足",
  comment_insufficient: "帖子够用，评论不足",
  ready_for_insight: "样本够用，可生成洞察",
};

const PROJECT_STATE_LABELS: Record<string, string> = {
  collection_issue: "采集异常",
  collecting: "采集中",
  sample_insufficient: "样本不足",
  preliminarily_analyzable: "可初判",
  deeply_analyzable: "可分析",
};

const KEYWORD_TYPE_LABELS: Record<string, string> = {
  core: "核心词",
  expanded: "扩展词",
  pending: "待确认词",
  excluded: "排除词",
  primary: "核心词",
  secondary: "扩展词",
  synonym: "扩展词",
  platform_adapted: "扩展词",
  ai_suggested: "待确认词",
  negative: "排除词",
};

const PLATFORM_OPTIONS = [
  { value: "xhs", label: "小红书" },
  { value: "dy", label: "抖音" },
  { value: "wb", label: "微博" },
  { value: "bili", label: "B站" },
  { value: "ks", label: "快手" },
  { value: "zhihu", label: "知乎" },
  { value: "tieba", label: "贴吧" },
];

type ProjectActionNotice = {
  tone: "info" | "success" | "error";
  message: string;
};

const COLLECTION_WINDOW_OPTIONS = [
  { value: 1, label: "近 1 天" },
  { value: 3, label: "近 3 天" },
  { value: 7, label: "近 7 天" },
  { value: 30, label: "近 30 天" },
];

type UnknownRecord = Record<string, unknown>;

type ProjectPostsDialogSource =
  | { kind: "project"; projectId: string }
  | { kind: "job"; jobId: number };

type ProjectPostsPage = {
  posts: UnknownRecord[];
  total: number;
  limit: number;
  offset: number;
  has_more: boolean;
};

type ProjectPostsDialogState = {
  source: ProjectPostsDialogSource;
  title: string;
  description: string;
  posts: UnknownRecord[];
  total: number;
  limit: number;
  offset: number;
  hasMore: boolean;
  loading: boolean;
  error: string | null;
};

const POST_DIALOG_PAGE_SIZE = 20;

export function GrowthProjectWorkbenchPage({
  projects,
  selectedProjectId,
  selectedProjectDetail,
  selectedProjectProgress,
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
  onSelectProject: (projectId: string) => void;
  onCreateProject: (payload: GrowthProjectCreatePayload) => Promise<void>;
  onUpdateProject: (projectId: string, payload: GrowthProjectUpdatePayload) => Promise<void>;
  onDeleteProject: (projectId: string) => Promise<void>;
  onStartCollection: (projectId: string, targetPostsPerPlatform?: number, collectionWindowDays?: number) => Promise<void>;
  onPauseCollection: (projectId: string) => Promise<void>;
  onStopCurrentRun: (projectId: string) => Promise<void>;
  onArchiveProject: (projectId: string) => Promise<void>;
  onOpenData: () => void;
  onOpenAi: () => void;
}) {
  const [showCreate, setShowCreate] = React.useState(false);
  const [postsDialog, setPostsDialog] = React.useState<ProjectPostsDialogState | null>(null);
  const selected = projects.find((project) => project.id === selectedProjectId) || projects[0] || null;

  async function loadPostsPage(source: ProjectPostsDialogSource, title: string, offset = 0) {
    const current = postsDialog?.source.kind === source.kind ? postsDialog : null;
    setPostsDialog({
      source,
      title,
      description: "正在读取采集内容...",
      posts: current?.posts || [],
      total: current?.total || 0,
      limit: POST_DIALOG_PAGE_SIZE,
      offset,
      hasMore: current?.hasMore || false,
      loading: true,
      error: null,
    });
    try {
      const endpoint = source.kind === "project"
        ? `/api/research/growth-projects/${encodeURIComponent(source.projectId)}/posts?limit=${POST_DIALOG_PAGE_SIZE}&offset=${offset}`
        : `/api/research/jobs/${source.jobId}/posts?limit=${POST_DIALOG_PAGE_SIZE}&offset=${offset}`;
      const page = await api<ProjectPostsPage>(endpoint);
      setPostsDialog({
        source,
        title,
        description: postPageDescription(page.total, page.offset, page.posts.length),
        posts: page.posts || [],
        total: page.total || 0,
        limit: page.limit || POST_DIALOG_PAGE_SIZE,
        offset: page.offset || 0,
        hasMore: Boolean(page.has_more),
        loading: false,
        error: null,
      });
    } catch (err) {
      setPostsDialog({
        source,
        title,
        description: "采集内容读取失败。",
        posts: [],
        total: 0,
        limit: POST_DIALOG_PAGE_SIZE,
        offset,
        hasMore: false,
        loading: false,
        error: err instanceof Error ? err.message : String(err),
      });
    }
  }

  function openProjectPosts(title: string, projectId: string) {
    void loadPostsPage({ kind: "project", projectId }, title, 0);
  }

  function openJobPosts(title: string, jobId: number) {
    void loadPostsPage({ kind: "job", jobId }, title, 0);
  }

  return (
    <section className="module-page growth-workbench">
      <div className="module-hero">
        <div className="module-hero-icon"><Activity size={30} /></div>
        <div>
          <span>Research Console</span>
          <h1>增长项目</h1>
          <p>按项目聚合关键词团、样本、洞察和采集记录；先判断有没有机会，再下钻到采集细节。</p>
        </div>
        <Button variant="primary" onClick={() => setShowCreate(true)}><Plus size={16} />新建增长项目</Button>
      </div>

      {showCreate && <GrowthProjectCreateForm onCreate={onCreateProject} onClose={() => setShowCreate(false)} />}

      <div className="growth-project-layout">
        <div className="growth-project-list">
          {projects.length ? (
            projects.map((project) => (
              <GrowthProjectCard
                key={project.id}
                project={project}
                active={project.id === selected?.id}
                onClick={() => onSelectProject(project.id)}
                onOpenPosts={() => openProjectPosts(`${project.name} · 采集内容`, project.id)}
              />
            ))
          ) : (
            <EmptyState title="暂无增长项目" body="创建项目后，采集任务、样本和洞察会聚合到这里。" />
          )}
        </div>
        <ProjectDetailPanel
          detail={selectedProjectDetail}
          selected={selected}
          progress={selectedProjectProgress}
          onUpdateProject={onUpdateProject}
          onDeleteProject={onDeleteProject}
          onStartCollection={onStartCollection}
          onPauseCollection={onPauseCollection}
          onStopCurrentRun={onStopCurrentRun}
          onArchiveProject={onArchiveProject}
          onOpenData={onOpenData}
          onOpenAi={onOpenAi}
          onOpenProjectPosts={(title, projectId) => openProjectPosts(title, projectId)}
          onOpenJobPosts={(title, jobId) => openJobPosts(title, jobId)}
        />
      </div>
      <ProjectPostsDialog
        state={postsDialog}
        onClose={() => setPostsDialog(null)}
        onPageChange={(offset) => postsDialog && void loadPostsPage(postsDialog.source, postsDialog.title, offset)}
      />
    </section>
  );
}

function GrowthProjectCard({ project, active, onClick, onOpenPosts }: { project: GrowthProjectSummary; active: boolean; onClick: () => void; onOpenPosts: () => void }) {
  const metrics = project.metrics;
  const action = ACTION_LABELS[project.recommended_action.kind] || project.recommended_action.label;

  return (
    <Card className={`growth-project-card ${active ? "active" : ""}`} role="button" tabIndex={0} onClick={onClick} onKeyDown={(event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        onClick();
      }
    }}>
      <div className="growth-project-card-head">
        <div>
          <h2>{project.name}</h2>
          <p>{GOAL_LABELS[project.primary_goal] || project.primary_goal} / {project.platforms.map(labelPlatform).join(" / ") || "未设置平台"}</p>
        </div>
        <Badge tone={badgeTone(project.sample_status.kind)}>{PROJECT_STATE_LABELS[project.status] || project.status}</Badge>
      </div>
      <div className="growth-project-action">
        <span>建议动作</span>
        <strong>{action}</strong>
        <span className="growth-project-sample">{sampleStatusLabel(project.sample_status)}</span>
      </div>
      <div className="growth-project-metrics">
        <span>{formatNumber(metrics.jobs)} 任务</span>
        <button
          type="button"
          className="growth-project-metric-button"
          disabled={!metrics.posts}
          onClick={(event) => {
            event.stopPropagation();
            onOpenPosts();
          }}
        >
          {formatNumber(metrics.posts)} 帖子
        </button>
        <span>{formatNumber(metrics.comments)} 评论</span>
        <span>{formatNumber(metrics.raw_records)} raw</span>
        {metrics.failed_jobs > 0 && <span className="danger">{formatNumber(metrics.failed_jobs)} 失败</span>}
      </div>
      <p>机会评分：{project.opportunity_score ?? "待分析"} / 最近采集：{formatDateTime(project.last_collected_at)}</p>
    </Card>
  );
}

function ProjectDetailPanel({
  detail,
  selected,
  progress,
  onUpdateProject,
  onDeleteProject,
  onStartCollection,
  onPauseCollection,
  onStopCurrentRun,
  onArchiveProject,
  onOpenData,
  onOpenAi,
  onOpenProjectPosts,
  onOpenJobPosts,
}: {
  detail: GrowthProjectDetail | null;
  selected: GrowthProjectSummary | null;
  progress: GrowthProjectCollectionProgress | null;
  onUpdateProject: (projectId: string, payload: GrowthProjectUpdatePayload) => Promise<void>;
  onDeleteProject: (projectId: string) => Promise<void>;
  onStartCollection: (projectId: string, targetPostsPerPlatform?: number, collectionWindowDays?: number) => Promise<void>;
  onPauseCollection: (projectId: string) => Promise<void>;
  onStopCurrentRun: (projectId: string) => Promise<void>;
  onArchiveProject: (projectId: string) => Promise<void>;
  onOpenData: () => void;
  onOpenAi: () => void;
  onOpenProjectPosts: (title: string, projectId: string) => void;
  onOpenJobPosts: (title: string, jobId: number) => void;
}) {
  const [busy, setBusy] = React.useState<string | null>(null);
  const [editing, setEditing] = React.useState(false);
  const [actionNotice, setActionNotice] = React.useState<ProjectActionNotice | null>(null);
  const [targetPostsPerPlatform, setTargetPostsPerPlatform] = React.useState(50);
  const [collectionWindowDays, setCollectionWindowDays] = React.useState(3);

  React.useEffect(() => {
    setActionNotice(null);
    setEditing(false);
  }, [selected?.id]);

  if (!selected) {
    return (
      <Card className="growth-project-detail">
        <CardTitle>选择一个增长项目</CardTitle>
        <CardDescription>项目详情会展示概览、AI 洞察、样本、关键词团和采集记录。</CardDescription>
      </Card>
    );
  }

  const project = detail?.project || selected;
  const action = ACTION_LABELS[project.recommended_action.kind] || project.recommended_action.label;
  const collectionActive = progress?.status === "queued" || progress?.status === "running";
  const latestMessage = progress?.progress.latest_event?.message || "";
  const collectionFailed = progress?.status === "failed" || isFailureMessage(latestMessage);

  async function runAction(kind: string, fn: (projectId: string) => Promise<void>) {
    setBusy(kind);
    setActionNotice({
      tone: "info",
      message: kind === "start" ? "已收到点击，正在提交采集任务。" : "正在提交操作。",
    });
    try {
      await fn(project.id);
      setActionNotice({
        tone: "success",
        message: actionSuccessMessage(kind),
      });
    } catch (err) {
      setActionNotice({
        tone: "error",
        message: err instanceof Error ? err.message : String(err),
      });
    } finally {
      setBusy(null);
    }
  }

  async function runStartCollection() {
    const target = clampTargetPosts(targetPostsPerPlatform);
    const windowDays = clampCollectionWindowDays(collectionWindowDays);
    setTargetPostsPerPlatform(target);
    setCollectionWindowDays(windowDays);
    setBusy("start");
    setActionNotice({
      tone: "info",
      message: `已收到点击，正在提交采集任务：近 ${windowDays} 天，每个平台目标 ${target} 条。`,
    });
    try {
      await onStartCollection(project.id, target, windowDays);
      setActionNotice({
        tone: "success",
        message: `采集任务已提交：近 ${windowDays} 天，${project.platforms.length || 1} 个平台，每个平台目标 ${target} 条。`,
      });
    } catch (err) {
      setActionNotice({
        tone: "error",
        message: err instanceof Error ? err.message : String(err),
      });
    } finally {
      setBusy(null);
    }
  }

  return (
    <Card className="growth-project-detail">
      <div className="project-status-bar">
        <div><span>建议动作</span><strong>{action}</strong></div>
        <div><span>样本状态</span><strong>{sampleStatusLabel(project.sample_status)}</strong></div>
        <div><span>机会评分</span><strong>{project.opportunity_score ?? "待分析"}</strong></div>
      </div>

      <div className="project-control-bar">
        <label className="collection-target-input">
          <span>每个平台</span>
          <input
            type="number"
            min={10}
            max={500}
            step={10}
            value={targetPostsPerPlatform}
            disabled={!!busy || (collectionActive && !collectionFailed)}
            onChange={(event) => setTargetPostsPerPlatform(Number(event.target.value) || 50)}
            onBlur={() => setTargetPostsPerPlatform((value) => clampTargetPosts(value))}
          />
          <span>条</span>
        </label>
        <label className="collection-target-input">
          <span>时间范围</span>
          <select
            value={collectionWindowDays}
            disabled={!!busy || (collectionActive && !collectionFailed)}
            onChange={(event) => setCollectionWindowDays(clampCollectionWindowDays(Number(event.target.value)))}
          >
            {COLLECTION_WINDOW_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>{option.label}</option>
            ))}
          </select>
        </label>
        <Button
          variant={collectionFailed ? "warning" : "primary"}
          disabled={!!busy || (collectionActive && !collectionFailed)}
          onClick={runStartCollection}
        >
          {busy === "start" ? <RefreshCw size={16} className="spin" /> : <Play size={16} />}
          {startCollectionLabel(busy, collectionActive, collectionFailed)}
        </Button>
        <Button variant="ghost" disabled={!!busy} onClick={() => setEditing((current) => !current)}><Pencil size={16} />编辑项目</Button>
        <Button variant="ghost" disabled={!!busy} onClick={() => runAction("pause", onPauseCollection)}><Pause size={16} />暂停采集</Button>
        <Button variant="ghost" disabled={!!busy} onClick={() => runAction("stop", onStopCurrentRun)}><Square size={16} />停止本轮</Button>
        <Button variant="ghost" disabled={!!busy} onClick={() => runAction("archive", onArchiveProject)}><Archive size={16} />归档项目</Button>
        <Button variant="ghost" disabled={!!busy} onClick={() => runAction("delete", onDeleteProject)}><Trash2 size={16} />删除项目</Button>
      </div>

      {actionNotice && (
        <div className={`project-action-notice ${actionNotice.tone}`}>
          {actionNotice.tone === "error" ? <AlertTriangle size={16} /> : <Activity size={16} />}
          <span>{actionNotice.message}</span>
        </div>
      )}

      {editing && (
        <GrowthProjectEditForm
          project={project}
          settings={detail?.settings}
          onSave={(payload) => onUpdateProject(project.id, payload)}
          onClose={() => setEditing(false)}
        />
      )}

      <CollectionProgressPanel
        progress={progress}
        onOpenPosts={(jobId) => onOpenJobPosts(`${project.name} · 当前任务采集内容`, jobId)}
      />

      <Tabs defaultValue="overview" className="project-tabs">
        <TabsList className="project-tab-list">
          <TabsTrigger value="overview">概览</TabsTrigger>
          <TabsTrigger value="ai">AI 洞察</TabsTrigger>
          <TabsTrigger value="samples">样本数据</TabsTrigger>
          <TabsTrigger value="keywords">关键词&场景</TabsTrigger>
          <TabsTrigger value="records">采集记录</TabsTrigger>
          <TabsTrigger value="settings">设置</TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="project-tab-content">
          <CardHeader>
            <div>
              <CardTitle>{project.name}</CardTitle>
              <CardDescription>{detail?.overview.current_judgment || "正在加载项目判断。"}</CardDescription>
            </div>
          </CardHeader>
          <div className="project-overview-grid">
            <Metric label="帖子" value={project.metrics.posts} icon={<FileJson size={16} />} onClick={() => onOpenProjectPosts(`${project.name} · 采集内容`, project.id)} />
            <Metric label="评论" value={project.metrics.comments} icon={<FileJson size={16} />} />
            <Metric label="达人" value={project.metrics.creators} icon={<Search size={16} />} />
            <Metric label="失败任务" value={project.metrics.failed_jobs} icon={<Activity size={16} />} />
          </div>
          <div className="result-actions">
            <Button variant="primary" onClick={onOpenAi}><Bot size={16} />生成洞察</Button>
            <Button variant="ghost" onClick={onOpenData}><Database size={16} />查看样本</Button>
          </div>
        </TabsContent>

        <TabsContent value="ai" className="project-tab-content">
          <CardTitle>AI 洞察</CardTitle>
          <p>{detail?.ai_insights.summary || "还没有生成聚合项目洞察。"}</p>
          {!!detail?.ai_insights.missing_data.length && <p>缺少数据：{detail.ai_insights.missing_data.join("、")}</p>}
        </TabsContent>

        <TabsContent value="samples" className="project-tab-content">
          <div className="project-overview-grid">
            <Metric label="帖子" value={detail?.sample_data.posts ?? project.metrics.posts} icon={<FileJson size={16} />} onClick={() => onOpenProjectPosts(`${project.name} · 采集内容`, project.id)} />
            <Metric label="评论" value={detail?.sample_data.comments ?? project.metrics.comments} icon={<FileJson size={16} />} />
            <Metric label="达人" value={detail?.sample_data.creators ?? project.metrics.creators} icon={<Search size={16} />} />
            <Metric label="Raw" value={detail?.sample_data.raw_records ?? project.metrics.raw_records} icon={<Database size={16} />} />
          </div>
        </TabsContent>

        <TabsContent value="keywords" className="project-tab-content">
          <KeywordGroups keywords={detail?.keywords || []} />
        </TabsContent>

        <TabsContent value="records" className="project-tab-content">
          <div className="collection-record-list">
            {(detail?.collection_records || []).map((record) => (
              <div className="collection-record-row" key={record.id}>
                <div>
                  <strong>{record.name}</strong>
                  <span>{record.platforms.map(labelPlatform).join(" / ")} / {record.collection_mode}</span>
                </div>
                <span>{record.status}</span>
                <span>{formatNumber(record.posts)} 帖子</span>
                <span>{formatNumber(record.comments)} 评论</span>
                <span>{formatNumber(record.raw_records)} raw</span>
              </div>
            ))}
            {!detail?.collection_records.length && <CardDescription>暂无采集记录。</CardDescription>}
          </div>
        </TabsContent>

        <TabsContent value="settings" className="project-tab-content">
          <p><Settings size={16} /> 主目标：{goalLabel(project.primary_goal)}</p>
          <p>平台：{project.platforms.map(labelPlatform).join(" / ") || "未设置"}</p>
          <p>刷新周期：{detail?.settings.refresh_cadence || "off"}</p>
        </TabsContent>
      </Tabs>
    </Card>
  );
}

function ProjectPostsDialog({
  state,
  onClose,
  onPageChange,
}: {
  state: ProjectPostsDialogState | null;
  onClose: () => void;
  onPageChange: (offset: number) => void;
}) {
  const prevOffset = state ? Math.max(0, state.offset - state.limit) : 0;
  const nextOffset = state ? state.offset + state.limit : 0;
  return (
    <ConfirmDialog
      open={Boolean(state)}
      onOpenChange={(open) => !open && onClose()}
      title={state?.title || "采集内容"}
      description={state?.description || ""}
    >
      <div className="project-post-dialog">
        {state?.loading ? (
          <CardDescription>正在加载采集内容...</CardDescription>
        ) : state?.error ? (
          <EmptyState title="采集内容读取失败" body={state.error} />
        ) : state?.posts.length ? (
          state.posts.map((post, index) => <ProjectPostRow key={`${postText(post.platform_post_id || post.id || post.url, "post")}-${index}`} post={post} index={index} />)
        ) : (
          <EmptyState title="暂无采集内容" body="这个任务还没有可展示的帖子样本。" />
        )}
        {state && state.total > state.limit && (
          <div className="project-post-pagination">
            <span>{postPageDescription(state.total, state.offset, state.posts.length)}</span>
            <div>
              <Button type="button" variant="ghost" disabled={state.loading || state.offset <= 0} onClick={() => onPageChange(prevOffset)}>上一页</Button>
              <Button type="button" variant="ghost" disabled={state.loading || !state.hasMore} onClick={() => onPageChange(nextOffset)}>下一页</Button>
            </div>
          </div>
        )}
        <div className="project-post-dialog-actions">
          <Button type="button" variant="ghost" onClick={onClose}>关闭</Button>
        </div>
      </div>
    </ConfirmDialog>
  );
}

function ProjectPostRow({ post, index }: { post: UnknownRecord; index: number }) {
  const engagement = postRecord(post.engagement_json || post.engagement);
  const url = postText(post.url || post.note_url || post.aweme_url, "");
  const title = postText(post.title || post.desc || post.platform_post_id || post.id, `采集内容 ${index + 1}`);
  return (
    <article className="project-post-row">
      <div className="project-post-row-head">
        <div>
          <strong>{title}</strong>
          <span>{labelPlatform(postText(post.platform, ""))} · {postText(post.publish_time || post.created_at, "未知发布时间")} · ID {postText(post.platform_post_id || post.id, "-")}</span>
        </div>
        {url && (
          <Button asChild variant="ghost" size="sm">
            <a href={url} target="_blank" rel="noreferrer"><ExternalLink size={14} />打开链接</a>
          </Button>
        )}
      </div>
      <p>{postText(post.content || post.desc || post.summary, "当前帖子未保存正文，仅展示标题和链接。")}</p>
      <div className="project-post-metrics">
        <span>点赞 {formatNumber(postNumber(engagement.liked_count ?? engagement.like_count))}</span>
        <span>评论 {formatNumber(postNumber(engagement.comment_count ?? engagement.comments_count))}</span>
        <span>收藏 {formatNumber(postNumber(engagement.collected_count ?? engagement.favorite_count))}</span>
        <span>分享 {formatNumber(postNumber(engagement.share_count ?? engagement.shared_count))}</span>
      </div>
    </article>
  );
}

function postPageDescription(total: number, offset: number, count: number) {
  if (!total) return "共 0 条帖子";
  const start = offset + 1;
  const end = offset + count;
  return `共 ${formatNumber(total)} 条，当前 ${formatNumber(start)}-${formatNumber(end)}`;
}

function postRecord(value: unknown): UnknownRecord {
  return value && typeof value === "object" && !Array.isArray(value) ? value as UnknownRecord : {};
}

function postText(value: unknown, fallback = "-") {
  return value === null || value === undefined || value === "" ? fallback : String(value);
}

function postNumber(value: unknown) {
  const next = Number(value);
  return Number.isFinite(next) ? next : 0;
}

function KeywordGroups({ keywords }: { keywords: Array<{ keyword: string; type: string; source: string }> }) {
  const groups = ["core", "expanded", "pending", "excluded"];
  const crawlKeywords = keywords.filter((item) => ["core", "expanded"].includes(normalizeKeywordType(item.type)));
  const copyKeywords = () => {
    const text = crawlKeywords.map((item) => item.keyword).join("\n");
    if (navigator.clipboard && text) {
      void navigator.clipboard.writeText(text);
    }
  };
  return (
    <div className="keyword-assets-panel">
      <div className="crawl-keyword-summary">
        <div>
          <span>参与采集关键词</span>
          <strong>{crawlKeywords.length} 个</strong>
        </div>
        <Button type="button" variant="ghost" onClick={copyKeywords} disabled={!crawlKeywords.length}><Copy size={16} />复制关键词</Button>
      </div>
      <div className="keyword-chip-list prominent">
        {crawlKeywords.map((item) => <Badge key={`crawl-${item.keyword}`} tone="default">{item.keyword}</Badge>)}
        {!crawlKeywords.length && <CardDescription>当前项目还没有可参与采集的核心词或扩展词。</CardDescription>}
      </div>
      <div className="keyword-group-grid">
        {groups.map((group) => {
          const items = keywords.filter((item) => normalizeKeywordType(item.type) === group);
          return (
            <div className="keyword-group" key={group}>
              <strong>{KEYWORD_TYPE_LABELS[group]}</strong>
              <div className="keyword-chip-list">
                {items.map((item) => <Badge key={`${group}-${item.keyword}`} tone={group === "excluded" ? "danger" : "muted"}>{item.keyword} · {sourceLabel(item.source)}</Badge>)}
                {!items.length && <span>暂无</span>}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function GrowthProjectEditForm({
  project,
  settings,
  onSave,
  onClose,
}: {
  project: GrowthProjectSummary;
  settings?: GrowthProjectDetail["settings"];
  onSave: (payload: GrowthProjectUpdatePayload) => Promise<void>;
  onClose: () => void;
}) {
  const [scenePacks, setScenePacks] = React.useState<ScenePackOption[]>([]);
  const [name, setName] = React.useState(project.name);
  const [primaryGoal, setPrimaryGoal] = React.useState(project.primary_goal);
  const [platforms, setPlatforms] = React.useState<string[]>(project.platforms);
  const [scenePackId, setScenePackId] = React.useState(settings?.scene_pack_id ? String(settings.scene_pack_id) : "");
  const [keywordMode, setKeywordMode] = React.useState<NonNullable<GrowthProjectUpdatePayload["scene_pack_keyword_mode"]>>("link_only");
  const [commentCollectionEnabled, setCommentCollectionEnabled] = React.useState(settings?.comment_collection_enabled ?? true);
  const [refreshCadence, setRefreshCadence] = React.useState<NonNullable<GrowthProjectUpdatePayload["refresh_cadence"]>>((settings?.refresh_cadence as NonNullable<GrowthProjectUpdatePayload["refresh_cadence"]>) || "off");
  const [customIntervalValue, setCustomIntervalValue] = React.useState(String(settings?.custom_interval_value || 1));
  const [saving, setSaving] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    let active = true;
    api<{ scene_packs: ScenePackOption[] }>("/api/keyword-library/scene-packs?enabled_only=true")
      .then((data) => {
        if (active) setScenePacks(data.scene_packs || []);
      })
      .catch(() => {
        if (active) setScenePacks([]);
      });
    return () => {
      active = false;
    };
  }, []);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setSaving(true);
    setError(null);
    try {
      await onSave({
        name: name.trim(),
        primary_goal: primaryGoal,
        platforms,
        scene_pack_id: scenePackId ? Number(scenePackId) : undefined,
        scene_pack_keyword_mode: scenePackId && Number(scenePackId) !== settings?.scene_pack_id ? keywordMode : undefined,
        comment_collection_enabled: commentCollectionEnabled,
        refresh_cadence: refreshCadence,
        custom_interval_value: refreshCadence.startsWith("custom_") ? Math.max(1, Number(customIntervalValue) || 1) : undefined,
        custom_interval_unit: refreshCadence === "custom_days" ? "days" : refreshCadence === "custom_hours" ? "hours" : undefined,
      });
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <form className="growth-project-edit-form" onSubmit={submit}>
      {error && <div className="notice error"><AlertTriangle size={16} />{error}</div>}
      <label>项目名<input value={name} onChange={(event) => setName(event.target.value)} required /></label>
      <label>主目标<select value={primaryGoal} onChange={(event) => setPrimaryGoal(event.target.value as GrowthProjectSummary["primary_goal"])}>
        <option value="topic_discovery">找选题</option>
        <option value="creator_discovery">找达人</option>
        <option value="keyword_expansion">扩关键词</option>
        <option value="competitor_monitoring">盯竞品</option>
        <option value="mixed_research">综合研究</option>
      </select></label>
      <div className="edit-field full">
        <span>平台</span>
        <div className="platform-checkbox-grid">
          {PLATFORM_OPTIONS.map((platform) => (
            <label key={platform.value} className="inline-check">
              <input
                type="checkbox"
                checked={platforms.includes(platform.value)}
                onChange={(event) => {
                  setPlatforms((current) => event.target.checked
                    ? Array.from(new Set([...current, platform.value]))
                    : current.filter((item) => item !== platform.value));
                }}
              />
              {platform.label}
            </label>
          ))}
        </div>
      </div>
      <label>场景包<select value={scenePackId} onChange={(event) => setScenePackId(event.target.value)}>
        <option value="">不关联场景包</option>
        {scenePacks.map((pack) => <option key={pack.id} value={pack.id}>{pack.name}</option>)}
      </select></label>
      <label>关键词处理<select value={keywordMode} onChange={(event) => setKeywordMode(event.target.value as NonNullable<GrowthProjectUpdatePayload["scene_pack_keyword_mode"]>)}>
        <option value="replace">替换当前关键词</option>
        <option value="append">追加并去重</option>
        <option value="link_only">只改关联，不动关键词</option>
      </select></label>
      <label>爬取频率<select value={refreshCadence} onChange={(event) => setRefreshCadence(event.target.value as NonNullable<GrowthProjectUpdatePayload["refresh_cadence"]>)}>
        <option value="off">不自动爬取</option>
        <option value="daily">每天</option>
        <option value="three_days">每 3 天</option>
        <option value="weekly">每周</option>
        <option value="custom_hours">每 N 小时</option>
        <option value="custom_days">每 N 天</option>
      </select></label>
      {refreshCadence.startsWith("custom_") && (
        <label>自定义间隔<input type="number" min={1} value={customIntervalValue} onChange={(event) => setCustomIntervalValue(event.target.value)} /></label>
      )}
      <label className="inline-check full"><input type="checkbox" checked={commentCollectionEnabled} onChange={(event) => setCommentCollectionEnabled(event.target.checked)} />采集帖子评论</label>
      <div className="result-actions">
        <Button type="button" variant="ghost" onClick={onClose}>取消</Button>
        <Button type="submit" variant="primary" disabled={saving}>{saving ? <RefreshCw size={16} className="spin" /> : <Pencil size={16} />}保存</Button>
      </div>
    </form>
  );
}

function CollectionProgressPanel({ progress, onOpenPosts }: { progress: GrowthProjectCollectionProgress | null; onOpenPosts?: (jobId: number) => void }) {
  if (!progress) {
    return (
      <div className="collection-progress-panel muted">
        <div className="collection-progress-head">
          <div>
            <span>采集进度</span>
            <strong>等待刷新</strong>
          </div>
          <Badge tone="muted">0%</Badge>
        </div>
        <div className="collection-progress-data-strip">
          <div><span>帖子</span><strong>0</strong></div>
          <div><span>评论</span><strong>0</strong></div>
          <div><span>Raw</span><strong>0</strong></div>
          <div><span>达人</span><strong>0</strong></div>
        </div>
      </div>
    );
  }
  const sample = progress.progress.sample_counts;
  const targetPosts = Number(progress.progress.target_counts?.posts || 0);
  const samplePercent = targetPosts
    ? Math.max(0, Math.min(100, Math.round((sample.posts / targetPosts) * 100)))
    : Math.max(0, Math.min(100, Math.round(progress.progress.sample_percent ?? progress.progress.percent ?? 0)));
  const stepPercent = Math.max(0, Math.min(100, Math.round(progress.progress.step_percent ?? progress.progress.percent ?? 0)));
  const activeJobId = progress.current_job_id || progress.running_job_id || progress.progress.job?.id || null;
  const latestMessage = progress.progress.latest_event?.message || "";
  const failed = progress.status === "failed" || isFailureMessage(latestMessage);
  const hasNoSamplesYet = progress.status === "running" && targetPosts > 0 && sample.posts === 0;
  const queueText = progress.status === "queued"
    ? `排队中，第 ${progress.queued_jobs[0]?.queue_position || 1} 位`
    : failed
      ? "采集异常"
      : hasNoSamplesYet
      ? "采集中，等待首批帖子入库"
      : progress.status === "running"
      ? "采集中"
      : progressStatusLabel(progress.status);
  const badgeTone = failed
    ? "danger"
    : progress.status === "completed"
      ? "success"
      : progress.status === "running"
        ? "warning"
        : progress.status === "queued"
          ? "muted"
          : "default";
  return (
    <div className={`collection-progress-panel ${failed ? "failed" : progress.status}`}>
      <div className="collection-progress-head">
        <div>
          <span>采集进度</span>
          <strong>{queueText}</strong>
        </div>
        <Badge tone={badgeTone}>{samplePercent}%</Badge>
      </div>
      <div className="collection-progress-track" aria-label="collection progress">
        <div style={{ width: `${samplePercent}%` }} />
      </div>
      <div className="collection-progress-primary">
        <span>帖子入库进度</span>
        <strong>{targetPosts ? `${formatNumber(sample.posts)} / ${formatNumber(targetPosts)}` : formatNumber(sample.posts)}</strong>
      </div>
      <div className="collection-progress-data-strip" aria-label="collected sample counts">
        <button
          type="button"
          className="collection-progress-count-button"
          disabled={!sample.posts || !activeJobId}
          onClick={() => activeJobId && onOpenPosts?.(activeJobId)}
        >
          <span>帖子</span>
          <strong>{targetPosts ? `${formatNumber(sample.posts)} / ${formatNumber(targetPosts)}` : formatNumber(sample.posts)}</strong>
        </button>
        <div><span>评论</span><strong>{formatNumber(sample.comments)}</strong></div>
        <div><span>Raw</span><strong>{formatNumber(sample.raw_records)}</strong></div>
        <div><span>达人</span><strong>{formatNumber(sample.creators)}</strong></div>
      </div>
      <div className="collection-progress-metrics">
        <span>队列 {formatNumber(progress.queue.queue_length)}</span>
        {progress.current_job_id && <span>任务 #{progress.current_job_id}</span>}
        <span>任务步骤 {formatNumber(stepPercent)}%</span>
      </div>
      {progress.progress.job && (
        <p>当前任务：{progress.progress.job.name || `#${progress.progress.job.id}`}</p>
      )}
      {latestMessage && (
        <p className={failed ? "collection-error-message" : undefined}>最近日志：{latestMessage}</p>
      )}
    </div>
  );
}

function Metric({ label, value, icon, onClick }: { label: string; value: number; icon: React.ReactNode; onClick?: () => void }) {
  if (onClick) {
    return (
      <button type="button" className="project-mini-metric is-clickable" disabled={!value} onClick={onClick}>
        {icon}
        <span>{label}</span>
        <strong>{formatNumber(value)}</strong>
      </button>
    );
  }
  return (
    <div className="project-mini-metric">
      {icon}
      <span>{label}</span>
      <strong>{formatNumber(value)}</strong>
    </div>
  );
}

function GrowthProjectCreateForm({
  onCreate,
  onClose,
}: {
  onCreate: (payload: GrowthProjectCreatePayload) => Promise<void>;
  onClose: () => void;
}) {
  const [scenePacks, setScenePacks] = React.useState<ScenePackOption[]>([]);
  const [name, setName] = React.useState("");
  const [scenePackId, setScenePackId] = React.useState("");
  const [primaryGoal, setPrimaryGoal] = React.useState<GrowthProjectCreatePayload["primary_goal"]>("topic_discovery");
  const [platforms, setPlatforms] = React.useState("dy,xhs");
  const [keywords, setKeywords] = React.useState("");
  const [collectionDepth, setCollectionDepth] = React.useState<GrowthProjectCreatePayload["collection_depth"]>("standard");
  const [refreshCadence, setRefreshCadence] = React.useState<GrowthProjectCreatePayload["refresh_cadence"]>("off");
  const [startImmediately, setStartImmediately] = React.useState(false);
  const [submitting, setSubmitting] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    let active = true;
    api<{ scene_packs: ScenePackOption[] }>("/api/keyword-library/scene-packs?enabled_only=true")
      .then((data) => {
        if (active) setScenePacks(data.scene_packs || []);
      })
      .catch(() => {
        if (active) setScenePacks([]);
      });
    return () => {
      active = false;
    };
  }, []);

  React.useEffect(() => {
    const pack = scenePacks.find((item) => String(item.id) === scenePackId);
    if (!pack) return;
    setName((current) => current || pack.name);
    setPrimaryGoal(pack.primary_goal || "topic_discovery");
    setPlatforms((pack.default_platforms || []).join(",") || platforms);
    setCollectionDepth(pack.default_collection_depth || "standard");
  }, [scenePackId, scenePacks]);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await onCreate({
        name: name.trim(),
        scene_pack_id: scenePackId ? Number(scenePackId) : undefined,
        primary_goal: primaryGoal,
        platforms: splitValues(platforms),
        keywords: splitValues(keywords),
        collection_depth: collectionDepth,
        refresh_cadence: refreshCadence,
        auto_ai_analysis: true,
        start_immediately: startImmediately,
      });
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Card className="growth-project-create">
      <form onSubmit={submit}>
        <CardHeader>
          <div>
            <CardTitle>新建增长项目</CardTitle>
            <CardDescription>选择主目标和场景包，系统会生成第一批采集计划。</CardDescription>
          </div>
        </CardHeader>
        {error && <div className="notice error"><AlertTriangle size={16} />{error}</div>}
        <div className="form-grid">
          <label>项目名<input value={name} onChange={(event) => setName(event.target.value)} required /></label>
          <label>场景包<select value={scenePackId} onChange={(event) => setScenePackId(event.target.value)}>
            <option value="">手动输入关键词</option>
            {scenePacks.map((pack) => <option value={pack.id} key={pack.id}>{pack.name}</option>)}
          </select></label>
          <label>主目标<select value={primaryGoal} onChange={(event) => setPrimaryGoal(event.target.value as GrowthProjectCreatePayload["primary_goal"])}>
            <option value="topic_discovery">找选题</option>
            <option value="creator_discovery">找达人</option>
            <option value="keyword_expansion">扩关键词</option>
            <option value="competitor_monitoring">盯竞品</option>
            <option value="mixed_research">综合研究</option>
          </select></label>
          <label>平台<input value={platforms} onChange={(event) => setPlatforms(event.target.value)} /></label>
          <label>采集深度<select value={collectionDepth} onChange={(event) => setCollectionDepth(event.target.value as GrowthProjectCreatePayload["collection_depth"])}>
            <option value="lightweight">轻量：只抓帖子</option>
            <option value="standard">标准：帖子 + 基础评论</option>
            <option value="deep">深度：帖子 + 评论 + 子评论</option>
          </select></label>
          <label>刷新周期<select value={refreshCadence} onChange={(event) => setRefreshCadence(event.target.value as GrowthProjectCreatePayload["refresh_cadence"])}>
            <option value="off">不开启</option>
            <option value="daily">每天</option>
            <option value="three_days">每 3 天</option>
            <option value="weekly">每周</option>
          </select></label>
          <label className="full">初始关键词<textarea value={keywords} onChange={(event) => setKeywords(event.target.value)} rows={4} required={!scenePackId} placeholder="选择场景包时可留空；手动模式下用逗号、斜杠或换行分隔。" /></label>
          <label className="inline-check"><input type="checkbox" checked={startImmediately} onChange={(event) => setStartImmediately(event.target.checked)} />创建后立即开始采集</label>
        </div>
        <div className="collection-plan-preview">
          <strong>将创建</strong>
          <span>{splitValues(platforms).map(labelPlatform).join(" / ") || "所选平台"} 关键词搜索任务</span>
          <span>{collectionDepth !== "lightweight" ? "启用评论采集" : "仅采集帖子"}</span>
          <span>{scenePackId ? "从场景包复制关键词快照" : "使用手动输入关键词"}</span>
        </div>
        <div className="result-actions">
          <Button type="button" variant="ghost" onClick={onClose}>取消</Button>
          <Button type="submit" variant="primary" disabled={submitting}>{submitting ? <RefreshCw size={16} className="spin" /> : <RefreshCw size={16} />}创建项目</Button>
        </div>
      </form>
    </Card>
  );
}

function splitValues(value: string) {
  return value.split(/[\n,，/]+/).map((item) => item.trim()).filter(Boolean);
}

function normalizeKeywordType(type: string) {
  if (type === "primary") return "core";
  if (["secondary", "synonym", "platform_adapted"].includes(type)) return "expanded";
  if (type === "ai_suggested") return "pending";
  if (type === "negative") return "excluded";
  return type || "expanded";
}

function badgeTone(kind: string) {
  if (kind === "ready_for_insight") return "success";
  if (kind === "collection_issue") return "danger";
  if (kind === "collecting") return "warning";
  return "muted";
}

function goalLabel(goal: string) {
  return GOAL_LABELS[goal as GrowthProjectSummary["primary_goal"]] || goal;
}

function progressStatusLabel(status: string) {
  const labels: Record<string, string> = {
    idle: "未开始",
    queued: "排队中",
    running: "采集中",
    completed: "已完成",
    empty: "未采到样本",
    failed: "失败",
    cancelled: "已取消",
  };
  return labels[status] || status;
}

function isFailureMessage(message: string) {
  const text = message.toLowerCase();
  return text.includes("exited with code: 1")
    || text.includes("crawler exited")
    || text.includes("failed")
    || text.includes("失败")
    || text.includes("异常");
}

function startCollectionLabel(busy: string | null, collectionActive: boolean, collectionFailed: boolean) {
  if (busy === "start") return "提交中...";
  if (collectionFailed) return "重试采集";
  if (collectionActive) return "采集中...";
  return "立即采集";
}

function actionSuccessMessage(kind: string) {
  const labels: Record<string, string> = {
    start: "采集任务已提交，下面会持续刷新已采集数量。",
    pause: "已提交暂停采集操作。",
    stop: "已提交停止本轮操作。",
    archive: "项目已归档。",
    delete: "项目已删除。",
  };
  return labels[kind] || "操作已提交。";
}

function clampTargetPosts(value: number) {
  return Math.max(10, Math.min(500, Math.round(Number(value) || 50)));
}

function clampCollectionWindowDays(value: number) {
  const allowed = COLLECTION_WINDOW_OPTIONS.map((option) => option.value);
  const parsed = Math.round(Number(value) || 3);
  return allowed.includes(parsed) ? parsed : 3;
}

function sourceLabel(source: string) {
  const labels: Record<string, string> = {
    scene_pack: "场景包",
    manual: "手动",
    research_job: "任务",
  };
  return labels[source] || source || "未知";
}

function sampleStatusLabel(status: GrowthProjectSummary["sample_status"]) {
  return SAMPLE_STATUS_LABELS[status.kind] || status.label;
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
