import React from "react";
import * as DialogPrimitive from "@radix-ui/react-dialog";
import {
  AlertTriangle,
  Bell,
  ChevronDown,
  Check,
  CheckCircle2,
  Clock3,
  HelpCircle,
  ListChecks,
  Loader2,
  LogOut,
  Menu,
  RefreshCw,
  Search,
  Sparkles,
  X,
} from "lucide-react";

export interface AppHeaderUser {
  email: string;
  displayName?: string | null;
  organizationName?: string;
  role?: string;
  initial?: string;
}

export interface AppHeaderProject {
  id: string;
  name: string;
  status?: string;
  platforms?: string[];
}

export interface AppHeaderNotification {
  id: string;
  title: string;
  body?: string;
  status: string;
  source?: string;
  updatedAt?: string | null;
  progress?: number | null;
}

export interface AppHeaderProps {
  title?: string;
  unreadCount?: number;
  notifications?: AppHeaderNotification[];
  notificationsLoading?: boolean;
  notificationError?: string | null;
  loading?: boolean;
  onRefresh?: () => void;
  currentUser?: AppHeaderUser | null;
  onLogout?: () => void;
  projects?: AppHeaderProject[];
  selectedProjectId?: string | null;
  onSelectProject?: (projectId: string) => void;
}

export function AppHeader({
  title = "宠物主粮增长项目",
  unreadCount,
  notifications,
  notificationsLoading = false,
  notificationError = null,
  loading,
  onRefresh,
  currentUser,
  onLogout,
  projects = [],
  selectedProjectId,
  onSelectProject,
}: AppHeaderProps) {
  const [projectMenuOpen, setProjectMenuOpen] = React.useState(false);
  const [notificationDialogOpen, setNotificationDialogOpen] = React.useState(false);
  const projectSwitcherRef = React.useRef<HTMLDivElement | null>(null);
  const userName = currentUser?.displayName?.trim() || currentUser?.email || "未登录用户";
  const userRole = currentUser?.role || currentUser?.organizationName || "Workspace";
  const userInitial = currentUser?.initial || Array.from(userName)[0]?.toUpperCase() || "U";
  const canSwitchProject = Boolean(onSelectProject);
  const selectedProject = projects.find((project) => project.id === selectedProjectId) || null;
  const projectTitle = selectedProject?.name || title;
  const visibleNotifications = notifications ?? [];
  const notificationCount = notifications ? visibleNotifications.length : Math.max(0, unreadCount || 0);
  const notificationCountLabel = notificationCount > 99 ? "99+" : String(notificationCount);

  React.useEffect(() => {
    if (!projectMenuOpen) return;

    const handlePointerDown = (event: PointerEvent) => {
      if (!projectSwitcherRef.current?.contains(event.target as Node)) {
        setProjectMenuOpen(false);
      }
    };
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setProjectMenuOpen(false);
      }
    };

    document.addEventListener("pointerdown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("pointerdown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [projectMenuOpen]);

  React.useEffect(() => {
    setProjectMenuOpen(false);
  }, [selectedProjectId]);

  function selectProject(projectId: string) {
    onSelectProject?.(projectId);
    setProjectMenuOpen(false);
  }

  return (
    <header className="app-header">
      <div className="app-header__left">
        <button type="button" className="app-header__menu" aria-label="展开菜单">
          <Menu size={18} />
        </button>
        <div className="app-header__project-switcher" ref={projectSwitcherRef}>
          <button
            type="button"
            className="app-header__project-pill"
            aria-haspopup="menu"
            aria-expanded={projectMenuOpen}
            onClick={() => {
              if (canSwitchProject) {
                setProjectMenuOpen((open) => !open);
              }
            }}
          >
            <span>{projectTitle}</span>
            <ChevronDown size={15} />
          </button>
          {canSwitchProject && projectMenuOpen && (
            <div className="app-header__project-menu" role="menu" aria-label="切换项目">
              {projects.length > 0 ? (
                projects.map((project) => {
                  const active = project.id === selectedProjectId;
                  return (
                    <button
                      key={project.id}
                      type="button"
                      role="menuitemradio"
                      aria-checked={active}
                      className={`app-header__project-option ${active ? "is-active" : ""}`}
                      onClick={() => selectProject(project.id)}
                    >
                      <span>
                        <strong>{project.name}</strong>
                        <small>{project.platforms?.length ? project.platforms.join(" / ") : project.status || "未配置平台"}</small>
                      </span>
                      {active && <Check size={16} />}
                    </button>
                  );
                })
              ) : (
                <div className="app-header__project-empty">暂无可切换项目</div>
              )}
            </div>
          )}
        </div>
        <label className="app-header__search">
          <Search size={16} />
          <input placeholder="搜索内容 / 账号 / 话题 / 关键词" />
        </label>
      </div>

      <div className="app-header__right">
        <button type="button" className="app-header__pill app-header__pill--assistant" title="AI 助手">
          <Sparkles size={14} />
          <span>AI 助手</span>
        </button>

        {onRefresh && (
          <button type="button" className="app-header__icon" onClick={onRefresh} title="刷新页面">
            {loading ? <Loader2 size={16} className="spin" /> : <RefreshCw size={16} />}
          </button>
        )}

        <button
          type="button"
          className="app-header__icon app-header__icon--bell"
          title="消息"
          aria-label={notificationCount > 0 ? `消息，${notificationCount} 条通知` : "消息"}
          onClick={() => setNotificationDialogOpen(true)}
        >
          <Bell size={16} />
          {notificationCount > 0 && <em>{notificationCountLabel}</em>}
        </button>
        <button type="button" className="app-header__icon" title="帮助">
          <HelpCircle size={16} />
        </button>

        <button type="button" className="app-header__user app-header__user--button" onClick={onLogout} title="退出登录">
          <span className="app-header__avatar">{userInitial}</span>
          <div className="app-header__user-meta">
            <strong>{userName}</strong>
            <span>{userRole}</span>
          </div>
          <LogOut size={14} />
        </button>
      </div>

      <DialogPrimitive.Root open={notificationDialogOpen} onOpenChange={setNotificationDialogOpen}>
        <DialogPrimitive.Portal>
          <DialogPrimitive.Overlay className="ui-dialog-overlay" />
          <DialogPrimitive.Content className="ui-dialog app-notification-dialog">
            <header className="app-notification-dialog__head">
              <div>
                <DialogPrimitive.Title>消息通知</DialogPrimitive.Title>
                <DialogPrimitive.Description>
                  来自后台任务中心的实时状态提醒
                </DialogPrimitive.Description>
              </div>
              <DialogPrimitive.Close asChild>
                <button type="button" className="app-notification-dialog__close" aria-label="关闭">
                  <X size={18} />
                </button>
              </DialogPrimitive.Close>
            </header>

            {notificationError && (
              <div className="app-notification-dialog__error">
                <AlertTriangle size={16} />
                <span>{notificationError}</span>
              </div>
            )}

            <div className="app-notification-dialog__body">
              {notificationsLoading && visibleNotifications.length === 0 ? (
                <div className="app-notification-dialog__empty">
                  <Loader2 size={22} className="spin" />
                  <strong>正在同步后台任务</strong>
                  <span>通知数量会在真实任务返回后更新。</span>
                </div>
              ) : visibleNotifications.length > 0 ? (
                visibleNotifications.map((notification) => (
                  <article
                    className={`app-notification-item ${notificationToneClass(notification.status)}`}
                    key={notification.id}
                  >
                    <div className="app-notification-item__icon">
                      {notificationIcon(notification.status)}
                    </div>
                    <div className="app-notification-item__main">
                      <div className="app-notification-item__title">
                        <strong>{notification.title}</strong>
                        <span>{notificationStatusLabel(notification.status)}</span>
                      </div>
                      {notification.body && <p>{notification.body}</p>}
                      <div className="app-notification-item__meta">
                        {notification.source && <span>{notification.source}</span>}
                        <span>{formatNotificationTime(notification.updatedAt)}</span>
                      </div>
                      {typeof notification.progress === "number" && (
                        <div className="app-notification-item__progress" aria-label={`进度 ${clampNotificationProgress(notification.progress)}%`}>
                          <span style={{ width: `${clampNotificationProgress(notification.progress)}%` }} />
                        </div>
                      )}
                    </div>
                  </article>
                ))
              ) : (
                <div className="app-notification-dialog__empty">
                  <ListChecks size={24} />
                  <strong>暂无通知</strong>
                  <span>有运行、排队或失败的后台任务时，这里会显示真实状态。</span>
                </div>
              )}
            </div>
          </DialogPrimitive.Content>
        </DialogPrimitive.Portal>
      </DialogPrimitive.Root>
    </header>
  );
}

function notificationStatusLabel(status: string) {
  const labels: Record<string, string> = {
    queued: "排队中",
    pending: "排队中",
    running: "运行中",
    stopping: "停止中",
    failed: "失败",
    error: "异常",
  };
  return labels[status] || status;
}

function notificationToneClass(status: string) {
  if (status === "failed" || status === "error") return "is-danger";
  if (status === "queued" || status === "pending" || status === "stopping") return "is-warning";
  if (status === "running") return "is-success";
  return "is-muted";
}

function notificationIcon(status: string) {
  if (status === "failed" || status === "error") return <AlertTriangle size={16} />;
  if (status === "queued" || status === "pending" || status === "stopping") return <Clock3 size={16} />;
  if (status === "running") return <RefreshCw size={16} />;
  return <CheckCircle2 size={16} />;
}

function clampNotificationProgress(value: number) {
  if (!Number.isFinite(value)) return 0;
  return Math.max(0, Math.min(100, Math.round(value)));
}

function formatNotificationTime(value?: string | null) {
  if (!value) return "时间未知";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("zh-CN", {
    timeZone: "Asia/Shanghai",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}
