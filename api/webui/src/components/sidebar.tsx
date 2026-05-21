import {
  Activity,
  BarChart3,
  Bot,
  Database,
  Download,
  FileText,
  Gauge,
  Home,
  KeyRound,
  Layers,
  ListChecks,
  Settings,
  Table2,
  Users,
} from "lucide-react";
import type { ResearchTab } from "../types";

type SidebarItem = { id: ResearchTab; label: string; icon: React.ComponentType<{ size?: number }> };
type SidebarGroup = { label: string; items: SidebarItem[] };

const groups: SidebarGroup[] = [
  {
    label: "Overview",
    items: [
      { id: "overview", label: "总览", icon: Home },
      { id: "tasks", label: "任务工作台", icon: Gauge },
      { id: "background_tasks", label: "后台任务", icon: ListChecks },
      { id: "opportunities", label: "增长机会决策", icon: BarChart3 },
    ],
  },
  {
    label: "Growth Tools",
    items: [
      { id: "creators", label: "达人发现", icon: Users },
      { id: "keyword_library", label: "关键词库", icon: KeyRound },
      { id: "competitors", label: "竞品监控", icon: Activity },
      { id: "content_tracking", label: "内容跟踪", icon: Layers },
    ],
  },
  {
    label: "Data",
    items: [
      { id: "data", label: "数据浏览", icon: Table2 },
      { id: "ai", label: "AI 分析", icon: Bot },
      { id: "export", label: "导出中心", icon: Download },
      { id: "config", label: "配置", icon: Settings },
    ],
  },
];

export function ResearchSidebar({
  active,
  onChange,
}: {
  active: ResearchTab;
  onChange: (tab: ResearchTab) => void;
}) {
  return (
    <aside className="sidebar">
      <div className="brand">
        <Database size={28} />
        <div>
          <strong>MediaCrawler</strong>
          <span>Research Console</span>
        </div>
      </div>
      <nav>
        {groups.map((group) => (
          <div className="nav-group" key={group.label}>
            <div className="nav-group-label">{group.label}</div>
            {group.items.map((item) => {
              const Icon = item.icon;
              return (
                <button
                  key={item.id}
                  className={active === item.id ? "active" : ""}
                  onClick={() => onChange(item.id)}
                  type="button"
                >
                  <Icon size={18} />
                  {item.label}
                </button>
              );
            })}
          </div>
        ))}
      </nav>
      <div className="sidebar-footer">
        <FileText size={16} />
        <span>采集、研判、复盘</span>
      </div>
    </aside>
  );
}
