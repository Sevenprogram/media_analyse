import React from "react";
import {
  Bell,
  ChevronDown,
  Check,
  HelpCircle,
  Loader2,
  LogOut,
  Menu,
  RefreshCw,
  Search,
  Sparkles,
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

export interface AppHeaderProps {
  title?: string;
  unreadCount?: number;
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
  unreadCount = 12,
  loading,
  onRefresh,
  currentUser,
  onLogout,
  projects = [],
  selectedProjectId,
  onSelectProject,
}: AppHeaderProps) {
  const [projectMenuOpen, setProjectMenuOpen] = React.useState(false);
  const projectSwitcherRef = React.useRef<HTMLDivElement | null>(null);
  const userName = currentUser?.displayName?.trim() || currentUser?.email || "未登录用户";
  const userRole = currentUser?.role || currentUser?.organizationName || "Workspace";
  const userInitial = currentUser?.initial || Array.from(userName)[0]?.toUpperCase() || "U";
  const canSwitchProject = Boolean(onSelectProject);
  const selectedProject = projects.find((project) => project.id === selectedProjectId) || null;
  const projectTitle = selectedProject?.name || title;

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

        <button type="button" className="app-header__icon app-header__icon--bell" title="消息">
          <Bell size={16} />
          {unreadCount > 0 && <em>{unreadCount}</em>}
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
    </header>
  );
}
