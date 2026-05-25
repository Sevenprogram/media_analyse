import React from "react";
import { Loader2, Plus, RefreshCw, Search } from "lucide-react";
import type { MonitorType, WorkbenchAccount } from "./types";
import { labelPlatform } from "../utils/format";

export interface AccountSidebarProps {
  accounts: WorkbenchAccount[];
  activeMonitorType: MonitorType;
  selectedId: number | null;
  onSelect: (id: number) => void;
  onMonitorTypeChange: (type: MonitorType) => void;
  onAddClick: () => void;
  onSyncClick: () => void;
  syncing?: boolean;
  loading?: boolean;
  overview?: {
    new_posts_total: number;
    interaction_total: number;
    new_hot_total: number;
    anomaly_total: number;
  };
}

const PLATFORM_TEXT: Record<string, string> = {
  xhs: "小红",
  dy: "抖音",
  douyin: "抖音",
};

export function AccountSidebar({
  accounts,
  activeMonitorType,
  selectedId,
  onSelect,
  onMonitorTypeChange,
  onAddClick,
  onSyncClick,
  syncing,
  loading,
  overview,
}: AccountSidebarProps) {
  const [query, setQuery] = React.useState("");

  const filtered = React.useMemo(() => {
    const normalized = query.trim().toLowerCase();
    if (!normalized) return accounts;
    return accounts.filter((account) => {
      return (
        (account.display_name || "").toLowerCase().includes(normalized) ||
        (account.creator_id || "").toLowerCase().includes(normalized) ||
        (account.notes || "").toLowerCase().includes(normalized)
      );
    });
  }, [accounts, query]);

  const totalCount = accounts.length;
  const cap = Math.max(30, totalCount);
  const isCreatorMonitor = activeMonitorType === "partner_creator";
  const addLabel = isCreatorMonitor ? "添加达人" : "添加监控";
  const searchPlaceholder = isCreatorMonitor ? "搜索达人 / 备注" : "搜索账号 / 备注";

  return (
    <>
      <aside className="cmw-account-sidebar">
        <header className="cmw-account-sidebar__head">
          <div className="cmw-account-sidebar__title">
            <strong>监控列表</strong>
            <span className="cmw-account-sidebar__count">({totalCount}/{cap})</span>
          </div>
          <button type="button" className="cmw-account-sidebar__add" onClick={onAddClick} title={addLabel}>
            <Plus size={14} />
            {addLabel}
          </button>
        </header>

        <div className="cmw-account-sidebar__switch" role="tablist" aria-label="监控类型">
          <button
            type="button"
            className={activeMonitorType === "competitor" ? "is-active" : ""}
            onClick={() => onMonitorTypeChange("competitor")}
            role="tab"
            aria-selected={activeMonitorType === "competitor"}
          >
            友商
          </button>
          <button
            type="button"
            className={activeMonitorType === "partner_creator" ? "is-active" : ""}
            onClick={() => onMonitorTypeChange("partner_creator")}
            role="tab"
            aria-selected={activeMonitorType === "partner_creator"}
          >
            达人
          </button>
        </div>

        <div className="cmw-account-sidebar__search">
          <Search size={14} />
          <input
            type="text"
            placeholder={searchPlaceholder}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
        </div>

        <div className="cmw-account-sidebar__list">
          {loading && accounts.length === 0 && <div className="cmw-account-sidebar__empty">加载中...</div>}
          {!loading && filtered.length === 0 && (
            <div className="cmw-account-sidebar__empty">
              {isCreatorMonitor ? "暂无匹配达人" : "暂无匹配账号"}
            </div>
          )}
          {filtered.map((account) => {
            const active = account.id === selectedId;
            const enabled = account.enabled !== false;

            return (
              <button
                key={account.id}
                type="button"
                className={"cmw-account-card" + (active ? " is-selected" : "")}
                onClick={() => onSelect(account.id)}
              >
                <span className="cmw-account-card__avatar">
                  {avatarText(account.platform, account.display_name || account.creator_id || "?")}
                </span>
                <span className="cmw-account-card__body">
                  <span className="cmw-account-card__name">{account.display_name || account.creator_id}</span>
                  <span className="cmw-account-card__meta">{labelPlatform(account.platform)}</span>
                </span>
                <span className={"cmw-account-card__badge " + (enabled ? "is-on" : "is-off")}>
                  {enabled ? "监控中" : "暂停中"}
                </span>
              </button>
            );
          })}
        </div>

        {totalCount > 0 && (
          <div className="cmw-account-sidebar__footer-link">
            <button type="button" onClick={() => setQuery("")}>
              查看全部 ({totalCount})
            </button>
          </div>
        )}
      </aside>

      <section className="cmw-overview-box">
        <header>
          <strong>监控概览</strong>
          <span>今日</span>
        </header>
        <div className="cmw-overview-stat-grid">
          <div className="cmw-overview-stat">
            <span>{isCreatorMonitor ? "宣发内容" : "采集帖子"}</span>
            <strong>{overview?.new_posts_total ?? 0}</strong>
          </div>
          <div className="cmw-overview-stat">
            <span>互动增量</span>
            <strong>{formatCount(overview?.interaction_total ?? 0)}</strong>
          </div>
          <div className="cmw-overview-stat">
            <span>{isCreatorMonitor ? "爆文命中" : "热点内容"}</span>
            <strong>{overview?.new_hot_total ?? 0}</strong>
          </div>
          <div className="cmw-overview-stat">
            <span>异常预警</span>
            <strong className="cmw-overview-stat__danger">{overview?.anomaly_total ?? 0}</strong>
          </div>
        </div>
        <button type="button" className="cmw-overview-box__sync" onClick={onSyncClick} disabled={syncing}>
          {syncing ? <Loader2 size={14} className="spin" /> : <RefreshCw size={14} />}
          {isCreatorMonitor ? "同步达人数据" : "同步监控数据"}
        </button>
      </section>
    </>
  );
}

function avatarText(platform: string, fallback: string) {
  return PLATFORM_TEXT[platform] || fallback.slice(0, 2).toUpperCase();
}

function formatCount(value: number): string {
  if (value >= 10000) return `${(value / 10000).toFixed(1).replace(/\.0$/, "")}w`;
  if (value >= 1000) return `${(value / 1000).toFixed(1).replace(/\.0$/, "")}k`;
  return String(value);
}
