import React from "react";
import {
  Bell,
  Bot,
  ChevronDown,
  HelpCircle,
  Loader2,
  Radar,
  RefreshCw,
  Search,
  Settings,
} from "lucide-react";
import type { ResearchTab } from "../types";

type TabItem = {
  id: ResearchTab;
  label: string;
};

const TOP_TABS: TabItem[] = [
  { id: "today", label: "工作台" },
  { id: "keyword_heat", label: "数据洞察" },
  { id: "content_library", label: "内容策略" },
  { id: "competitors", label: "友商监控" },
  { id: "creators", label: "KOL 发现" },
  { id: "data_board", label: "营销分析" },
  { id: "reports_center", label: "品牌报告" },
];

export interface TopTabBarProps {
  tab: ResearchTab;
  onChange: (tab: ResearchTab) => void;
  loading?: boolean;
  onRefresh?: () => void;
  unreadCount?: number;
}

export function TopTabBar({ tab, onChange, loading, onRefresh, unreadCount = 12 }: TopTabBarProps) {
  const [searchQuery, setSearchQuery] = React.useState("");
  const [scope, setScope] = React.useState<"all" | "responsible" | "participated">("all");

  return (
    <header className="top-tab-bar">
      <div className="top-tab-bar__brand">
        <span className="top-tab-bar__brand-mark">
          <Radar size={20} />
        </span>
        <div className="top-tab-bar__brand-text">
          <strong>增长雷达</strong>
          <span>社媒增长智能系统</span>
        </div>
      </div>

      <nav className="top-tab-bar__tabs" aria-label="主导航">
        {TOP_TABS.map((item) => (
          <button
            key={item.id}
            type="button"
            className={"top-tab" + (tab === item.id ? " is-active" : "")}
            onClick={() => onChange(item.id)}
          >
            {item.label}
          </button>
        ))}
      </nav>

      <div className="top-tab-bar__right">
        <div className="top-tab-bar__scope">
          <select value={scope} onChange={(e) => setScope(e.target.value as typeof scope)}>
            <option value="all">全局</option>
            <option value="responsible">我负责的</option>
            <option value="participated">我参与的</option>
          </select>
          <ChevronDown size={14} />
        </div>
        <div className="top-tab-bar__search">
          <Search size={14} />
          <input
            type="text"
            placeholder="搜索内容 / 账号 / 话题"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        </div>
        <button className="top-tab-bar__icon" type="button" title="AI 助手">
          <Bot size={16} />
        </button>
        <button className="top-tab-bar__icon" type="button" title="消息">
          <Bell size={16} />
          {unreadCount > 0 && <span className="top-tab-bar__badge">{unreadCount}</span>}
        </button>
        {onRefresh && (
          <button className="top-tab-bar__icon" type="button" onClick={onRefresh} title="刷新">
            {loading ? <Loader2 className="spin" size={16} /> : <RefreshCw size={16} />}
          </button>
        )}
        <button className="top-tab-bar__icon" type="button" title="帮助">
          <HelpCircle size={16} />
        </button>
        <button
          className={"top-tab-bar__icon" + (tab === "settings" ? " is-active" : "")}
          type="button"
          title="设置"
          onClick={() => onChange("settings")}
        >
          <Settings size={16} />
        </button>
        <div className="top-tab-bar__user">
          <span className="top-tab-bar__avatar">A</span>
          <span className="top-tab-bar__username">Alice</span>
        </div>
      </div>
    </header>
  );
}
