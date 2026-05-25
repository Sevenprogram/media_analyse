import React from "react";
import {
  AlertTriangle,
  ArrowDown,
  ArrowUp,
  CheckCircle2,
  Database,
  Layers3,
  Loader2,
  RefreshCw,
  RotateCcw,
  Save,
  ShieldCheck,
  SlidersHorizontal,
  Tags,
  UsersRound,
} from "lucide-react";
import {
  CONFIGURABLE_SIDE_NAV_ITEMS,
  defaultSideNavConfig,
  normalizeSideNavConfig,
} from "../navigation";
import { api, ApiError } from "../utils/api";
import type { AuthSession } from "../utils/authSession";
import type { SideNavConfigResponse, SideNavConfigValue } from "../types";
import "./admin.css";

interface AdminConsolePageProps {
  session: AuthSession;
}

interface PlatformCapability {
  platform: string;
  enabled?: boolean;
  crawl_search_enabled?: boolean;
  crawl_creator_enabled?: boolean;
  crawl_detail_enabled?: boolean;
  comments_enabled?: boolean;
  analysis_enabled?: boolean;
  keyword_heat_enabled?: boolean;
  rate_limit_per_minute?: number;
  max_daily_jobs?: number | null;
  notes?: string | null;
}

interface Vertical {
  id: number;
  code: string;
  name: string;
  enabled?: boolean;
}

interface TagGroup {
  id: number;
  vertical_id: number;
  name: string;
  enabled?: boolean;
  sort_order?: number;
}

interface TagDefinition {
  id: number;
  vertical_id: number;
  group_id: number;
  tag_name: string;
  keywords?: string[];
  synonyms?: string[];
  negative_keywords?: string[];
  weight?: number;
  enabled?: boolean;
}

interface TaggingStatus {
  entity_tag_count: number;
  by_entity_type: Record<string, number>;
  by_source: Record<string, number>;
}

interface RebuildJob {
  job_id: string;
  status: string;
  total?: number;
  processed?: number;
  rebuilt_count?: number;
  percent?: number;
  error?: string | null;
}

const platformLabels: Record<string, string> = {
  xhs: "小红书",
  dy: "抖音",
  ks: "快手",
  bili: "Bilibili",
  wb: "微博",
  tieba: "贴吧",
  zhihu: "知乎",
};

export function AdminConsolePage({ session }: AdminConsolePageProps) {
  const [capabilities, setCapabilities] = React.useState<PlatformCapability[]>([]);
  const [verticals, setVerticals] = React.useState<Vertical[]>([]);
  const [tagGroups, setTagGroups] = React.useState<TagGroup[]>([]);
  const [tagDefinitions, setTagDefinitions] = React.useState<TagDefinition[]>([]);
  const [taggingStatus, setTaggingStatus] = React.useState<TaggingStatus | null>(null);
  const [sideNavConfig, setSideNavConfig] = React.useState<SideNavConfigValue>(() => defaultSideNavConfig());
  const [newVertical, setNewVertical] = React.useState({ code: "", name: "", enabled: true });
  const [rebuildJob, setRebuildJob] = React.useState<RebuildJob | null>(null);
  const [loading, setLoading] = React.useState(false);
  const [actionLoading, setActionLoading] = React.useState<string | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [message, setMessage] = React.useState<string | null>(null);

  const loadAdminData = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    const [capabilityResult, verticalResult, groupResult, tagResult, statusResult, sideNavResult] = await Promise.allSettled([
      api<{ capabilities: PlatformCapability[] }>("/api/admin/platform-capabilities"),
      api<{ verticals: Vertical[] }>("/api/admin/verticals"),
      api<{ tag_groups: TagGroup[] }>("/api/admin/tag-groups"),
      api<{ tag_definitions: TagDefinition[] }>("/api/admin/tag-definitions"),
      api<TaggingStatus>("/api/admin/tagging/status"),
      api<SideNavConfigResponse>("/api/admin/ui/side-nav-config"),
    ]);

    if (capabilityResult.status === "fulfilled") setCapabilities(capabilityResult.value.capabilities || []);
    if (verticalResult.status === "fulfilled") setVerticals(verticalResult.value.verticals || []);
    if (groupResult.status === "fulfilled") setTagGroups(groupResult.value.tag_groups || []);
    if (tagResult.status === "fulfilled") setTagDefinitions(tagResult.value.tag_definitions || []);
    if (statusResult.status === "fulfilled") setTaggingStatus(statusResult.value);
    if (sideNavResult.status === "fulfilled") setSideNavConfig(normalizeSideNavConfig(sideNavResult.value.value));

    const failed = [capabilityResult, verticalResult, groupResult, tagResult, statusResult, sideNavResult].find(
      (result) => result.status === "rejected",
    ) as PromiseRejectedResult | undefined;
    if (failed) {
      setError(adminErrorMessage(failed.reason));
    }
    setLoading(false);
  }, []);

  React.useEffect(() => {
    void loadAdminData();
  }, [loadAdminData]);

  async function runAction(action: string, task: () => Promise<void>) {
    setActionLoading(action);
    setMessage(null);
    setError(null);
    try {
      await task();
    } catch (requestError) {
      setError(adminErrorMessage(requestError));
    } finally {
      setActionLoading(null);
    }
  }

  async function bootstrapDefaults() {
    await runAction("bootstrap", async () => {
      await api<Record<string, unknown>>("/api/admin/bootstrap/defaults", { method: "POST" });
      setMessage("默认赛道、平台能力和标签配置已初始化。");
      await loadAdminData();
    });
  }

  async function createVertical(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await runAction("vertical", async () => {
      const created = await api<Vertical>("/api/admin/verticals", {
        method: "POST",
        body: JSON.stringify(newVertical),
      });
      setVerticals((current) => [created, ...current.filter((item) => item.id !== created.id)]);
      setNewVertical({ code: "", name: "", enabled: true });
      setMessage(`赛道 ${created.name} 已创建。`);
    });
  }

  async function startCreatorProfileRebuild() {
    await runAction("profiles", async () => {
      const job = await api<RebuildJob>("/api/admin/creator-profiles/rebuild/start", {
        method: "POST",
        body: JSON.stringify({ analysis_version: "v1" }),
      });
      setRebuildJob(job);
      setMessage("达人画像重建任务已进入队列。");
    });
  }

  function updateSideNavConfig(updater: (current: SideNavConfigValue) => SideNavConfigValue) {
    setSideNavConfig((current) => normalizeSideNavConfig(updater(normalizeSideNavConfig(current))));
  }

  function toggleSideNavTab(tab: string) {
    updateSideNavConfig((current) => {
      const visibleCount = current.items.filter((item) => item.visible).length;
      return {
        items: current.items.map((item) =>
          item.tab === tab
            ? {
                ...item,
                visible: item.visible ? visibleCount <= 1 : true,
              }
            : item,
        ),
      };
    });
  }

  function moveSideNavTab(tab: string, direction: -1 | 1) {
    updateSideNavConfig((current) => {
      const items = [...current.items];
      const index = items.findIndex((item) => item.tab === tab);
      const nextIndex = index + direction;
      if (index < 0 || nextIndex < 0 || nextIndex >= items.length) {
        return current;
      }
      const next = [...items];
      [next[index], next[nextIndex]] = [next[nextIndex], next[index]];
      return {
        items: next.map((item, itemIndex) => ({ ...item, sort_order: itemIndex * 10 })),
      };
    });
  }

  async function saveSideNavConfig() {
    await runAction("side-nav", async () => {
      const response = await api<SideNavConfigResponse>("/api/admin/ui/side-nav-config", {
        method: "PUT",
        body: JSON.stringify(normalizeSideNavConfig(sideNavConfig)),
      });
      const normalized = normalizeSideNavConfig(response.value);
      setSideNavConfig(normalized);
      window.dispatchEvent(new CustomEvent("side-nav-config:updated", { detail: normalized }));
      setMessage("侧边栏配置已保存，用户刷新页面后生效。");
    });
  }

  function resetSideNavConfig() {
    setSideNavConfig(defaultSideNavConfig());
  }

  const enabledPlatforms = capabilities.filter((item) => item.enabled !== false).length;
  const enabledVerticals = verticals.filter((item) => item.enabled !== false).length;
  const enabledTags = tagDefinitions.filter((item) => item.enabled !== false).length;
  const tagCoverage = taggingStatus?.entity_tag_count || 0;
  const recentTags = tagDefinitions.slice(0, 12);
  const recentGroups = tagGroups.slice(0, 8);
  const sideNavItemByTab = new Map(CONFIGURABLE_SIDE_NAV_ITEMS.map((item) => [item.tab, item]));
  const sideNavRows = sideNavConfig.items
    .map((item) => ({ ...item, definition: sideNavItemByTab.get(item.tab) }))
    .filter((item) => item.definition);
  const visibleSideNavCount = sideNavRows.filter((item) => item.visible).length;

  return (
    <div className="admin-console">
      <header className="admin-hero">
        <div>
          <span className="admin-kicker">Admin Console</span>
          <h1>管理后台</h1>
          <p>{session.organization.name} · {session.user.email}</p>
        </div>
        <div className="admin-hero__actions">
          <button type="button" onClick={loadAdminData} disabled={loading}>
            {loading ? <Loader2 size={16} className="spin" /> : <RefreshCw size={16} />}
            刷新
          </button>
          <button type="button" className="primary" onClick={bootstrapDefaults} disabled={actionLoading === "bootstrap"}>
            {actionLoading === "bootstrap" ? <Loader2 size={16} className="spin" /> : <Database size={16} />}
            初始化默认配置
          </button>
        </div>
      </header>

      {error && <div className="admin-notice error"><AlertTriangle size={16} />{error}</div>}
      {message && <div className="admin-notice success"><CheckCircle2 size={16} />{message}</div>}

      <section className="admin-metrics" aria-label="管理概览">
        <Metric icon={ShieldCheck} label="启用平台" value={`${enabledPlatforms}/${capabilities.length || 0}`} detail="采集与分析能力" />
        <Metric icon={Layers3} label="启用赛道" value={`${enabledVerticals}/${verticals.length || 0}`} detail="业务 vertical" />
        <Metric icon={Tags} label="启用标签" value={`${enabledTags}/${tagDefinitions.length || 0}`} detail="标签定义" />
        <Metric icon={UsersRound} label="已打标实体" value={String(tagCoverage)} detail="内容/达人/关键词" />
      </section>

      <section className="admin-grid">
        <div className="admin-panel admin-panel--wide">
          <div className="admin-panel__head">
            <div>
              <span>Navigation</span>
              <h2>全用户侧边栏</h2>
            </div>
            <div className="admin-nav-actions">
              <button type="button" onClick={resetSideNavConfig} disabled={actionLoading === "side-nav"}>
                <RotateCcw size={15} />
                恢复默认
              </button>
              <button type="button" className="primary" onClick={saveSideNavConfig} disabled={actionLoading === "side-nav"}>
                {actionLoading === "side-nav" ? <Loader2 size={15} className="spin" /> : <Save size={15} />}
                保存配置
              </button>
            </div>
          </div>
          <p className="admin-panel__note">
            这里控制普通用户左侧业务模块的展示和顺序。管理后台和设置固定在底部，不参与全局排序。
          </p>
          <div className="admin-nav-config-list">
            {sideNavRows.map((item, index) => {
              const Icon = item.definition!.icon;
              const cannotHideLast = item.visible && visibleSideNavCount <= 1;
              return (
                <div className={`admin-nav-row ${item.visible ? "" : "is-hidden"}`} key={item.tab}>
                  <span className="admin-nav-row__handle">{String(index + 1).padStart(2, "0")}</span>
                  <span className="admin-nav-row__icon"><Icon size={16} /></span>
                  <div className="admin-nav-row__body">
                    <strong>{item.definition!.label}</strong>
                    <span>{item.tab}</span>
                  </div>
                  <button
                    type="button"
                    className={`admin-switch ${item.visible ? "is-on" : "is-off"}`}
                    onClick={() => toggleSideNavTab(item.tab)}
                    disabled={cannotHideLast}
                    title={cannotHideLast ? "至少保留一个可见模块" : undefined}
                  >
                    {item.visible ? "展示" : "隐藏"}
                  </button>
                  <div className="admin-nav-row__moves">
                    <button type="button" onClick={() => moveSideNavTab(item.tab, -1)} disabled={index === 0} aria-label="上移">
                      <ArrowUp size={14} />
                    </button>
                    <button type="button" onClick={() => moveSideNavTab(item.tab, 1)} disabled={index === sideNavRows.length - 1} aria-label="下移">
                      <ArrowDown size={14} />
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        <div className="admin-panel admin-panel--wide">
          <div className="admin-panel__head">
            <div>
              <span>Platform Matrix</span>
              <h2>平台采集能力</h2>
            </div>
          </div>
          <div className="admin-table-wrap">
            <table className="admin-table">
              <thead>
                <tr>
                  <th>平台</th>
                  <th>搜索</th>
                  <th>达人</th>
                  <th>详情</th>
                  <th>评论</th>
                  <th>分析</th>
                  <th>热度</th>
                  <th>限速</th>
                </tr>
              </thead>
              <tbody>
                {capabilities.map((item) => (
                  <tr key={item.platform}>
                    <td>
                      <strong>{platformLabels[item.platform] || item.platform}</strong>
                      <span>{item.platform}</span>
                    </td>
                    <td><StatusDot enabled={item.crawl_search_enabled !== false} /></td>
                    <td><StatusDot enabled={item.crawl_creator_enabled !== false} /></td>
                    <td><StatusDot enabled={item.crawl_detail_enabled !== false} /></td>
                    <td><StatusDot enabled={item.comments_enabled !== false} /></td>
                    <td><StatusDot enabled={item.analysis_enabled !== false} /></td>
                    <td><StatusDot enabled={item.keyword_heat_enabled !== false} /></td>
                    <td>{item.rate_limit_per_minute || "-"} / min</td>
                  </tr>
                ))}
                {capabilities.length === 0 && <EmptyRow colSpan={8} label="暂无平台能力配置" />}
              </tbody>
            </table>
          </div>
        </div>

        <div className="admin-panel">
          <div className="admin-panel__head">
            <div>
              <span>Verticals</span>
              <h2>赛道配置</h2>
            </div>
          </div>
          <form className="admin-create-form" onSubmit={createVertical}>
            <input
              value={newVertical.code}
              onChange={(event) => setNewVertical((current) => ({ ...current, code: event.target.value }))}
              placeholder="code，如 pet_food"
              required
            />
            <input
              value={newVertical.name}
              onChange={(event) => setNewVertical((current) => ({ ...current, name: event.target.value }))}
              placeholder="赛道名称"
              required
            />
            <label className="admin-checkbox">
              <input
                type="checkbox"
                checked={newVertical.enabled}
                onChange={(event) => setNewVertical((current) => ({ ...current, enabled: event.target.checked }))}
              />
              启用
            </label>
            <button type="submit" disabled={actionLoading === "vertical"}>
              {actionLoading === "vertical" ? <Loader2 size={16} className="spin" /> : <Layers3 size={16} />}
              新增赛道
            </button>
          </form>
          <div className="admin-list">
            {verticals.slice(0, 10).map((vertical) => (
              <div className="admin-list-row" key={vertical.id}>
                <div>
                  <strong>{vertical.name}</strong>
                  <span>{vertical.code}</span>
                </div>
                <StatusPill enabled={vertical.enabled !== false} />
              </div>
            ))}
            {verticals.length === 0 && <div className="admin-empty">暂无赛道配置</div>}
          </div>
        </div>

        <div className="admin-panel admin-panel--wide">
          <div className="admin-panel__head">
            <div>
              <span>Taxonomy</span>
              <h2>标签体系</h2>
            </div>
          </div>
          <div className="admin-taxonomy">
            <div>
              <h3>标签组</h3>
              <div className="admin-list compact">
                {recentGroups.map((group) => (
                  <div className="admin-list-row" key={group.id}>
                    <div>
                      <strong>{group.name}</strong>
                      <span>vertical #{group.vertical_id} · sort {group.sort_order ?? "-"}</span>
                    </div>
                    <StatusPill enabled={group.enabled !== false} />
                  </div>
                ))}
                {recentGroups.length === 0 && <div className="admin-empty">暂无标签组</div>}
              </div>
            </div>
            <div>
              <h3>标签定义</h3>
              <div className="admin-tag-cloud">
                {recentTags.map((tag) => (
                  <span key={tag.id} className={tag.enabled === false ? "is-disabled" : ""}>
                    {tag.tag_name}
                    <em>{tag.weight || 1}</em>
                  </span>
                ))}
                {recentTags.length === 0 && <div className="admin-empty">暂无标签定义</div>}
              </div>
            </div>
          </div>
        </div>

        <div className="admin-panel">
          <div className="admin-panel__head">
            <div>
              <span>Operations</span>
              <h2>系统维护</h2>
            </div>
          </div>
          <div className="admin-ops">
            <button type="button" onClick={startCreatorProfileRebuild} disabled={actionLoading === "profiles"}>
              {actionLoading === "profiles" ? <Loader2 size={16} className="spin" /> : <UsersRound size={16} />}
              重建达人画像
            </button>
            <button type="button" onClick={loadAdminData} disabled={loading}>
              <SlidersHorizontal size={16} />
              重新读取配置
            </button>
          </div>
          <div className="admin-status-box">
            <span>打标状态</span>
            <strong>{taggingStatus ? `${taggingStatus.entity_tag_count} entities` : "未加载"}</strong>
            <p>{formatCounts(taggingStatus?.by_source)}</p>
          </div>
          {rebuildJob && (
            <div className="admin-status-box">
              <span>画像重建任务</span>
              <strong>{rebuildJob.status}</strong>
              <p>{rebuildJob.job_id} · {rebuildJob.percent ?? 0}%</p>
            </div>
          )}
        </div>
      </section>
    </div>
  );
}

function Metric({
  icon: Icon,
  label,
  value,
  detail,
}: {
  icon: React.ComponentType<{ size?: number }>;
  label: string;
  value: string;
  detail: string;
}) {
  return (
    <div className="admin-metric">
      <span><Icon size={18} /></span>
      <div>
        <strong>{value}</strong>
        <p>{label}</p>
        <em>{detail}</em>
      </div>
    </div>
  );
}

function StatusDot({ enabled }: { enabled: boolean }) {
  return <span className={`admin-dot ${enabled ? "is-on" : "is-off"}`} title={enabled ? "启用" : "停用"} />;
}

function StatusPill({ enabled }: { enabled: boolean }) {
  return <span className={`admin-pill ${enabled ? "is-on" : "is-off"}`}>{enabled ? "启用" : "停用"}</span>;
}

function EmptyRow({ colSpan, label }: { colSpan: number; label: string }) {
  return (
    <tr>
      <td colSpan={colSpan} className="admin-table-empty">{label}</td>
    </tr>
  );
}

function formatCounts(counts?: Record<string, number>) {
  if (!counts || Object.keys(counts).length === 0) return "暂无来源统计";
  return Object.entries(counts)
    .map(([key, value]) => `${key || "unknown"} ${value}`)
    .join(" · ");
}

function adminErrorMessage(error: unknown) {
  if (error instanceof ApiError) {
    if (error.status === 403) return "当前账号没有管理后台权限。";
    if (error.status === 401) return "登录已失效，请重新登录。";
    return error.message;
  }
  return error instanceof Error ? error.message : "管理后台请求失败。";
}
