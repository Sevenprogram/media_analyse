import React from "react";
import { ChevronDown, ExternalLink, FileOutput, Loader2, MoreHorizontal, RefreshCw, Share2 } from "lucide-react";
import type { MonitorType, WorkbenchAccount } from "./types";
import { labelPlatform } from "../utils/format";
import { api } from "../utils/api";
import { useInView } from "../lib/useInView";
import { getMockMonitorSettings } from "./mock";
import { DailyLedger } from "./DailyLedger";
import { ContentContributionTable } from "./ContentContributionTable";
import { MonitoringPulse } from "./MonitoringPulse";

export interface AccountDetailPanelProps {
  account: WorkbenchAccount;
  date: string;
  onDateChange: (date: string) => void;
  onRefresh: () => void;
  refreshing?: boolean;
  useMock?: boolean;
}

type MonitorSettings = {
  competitor_id: number;
  job_id: number | null;
  schedule_enabled: boolean;
  interval_minutes: number;
  cadence_label: string;
  next_run_at: string | null;
  last_scheduled_at: string | null;
  last_refresh_at: string | null;
  last_refresh_status: string | null;
};

const CADENCE_OPTIONS = [
  { value: "manual", label: "手动", schedule_enabled: false, interval_minutes: null },
  { value: "8h", label: "每 8 小时", schedule_enabled: true, interval_minutes: 8 * 60 },
  { value: "daily", label: "每天一次", schedule_enabled: true, interval_minutes: 24 * 60 },
  { value: "weekly", label: "每周一次", schedule_enabled: true, interval_minutes: 7 * 24 * 60 },
];

export function AccountDetailPanel({
  account,
  date,
  onDateChange,
  onRefresh,
  refreshing = false,
  useMock = false,
}: AccountDetailPanelProps) {
  const settingsBlock = useInView<HTMLDivElement>();
  const [settings, setSettings] = React.useState<MonitorSettings>(() => getMockMonitorSettings(account.id));
  const [savingCadence, setSavingCadence] = React.useState(false);
  const monitorType: MonitorType = account.monitor_type || "competitor";
  const isCreatorMonitor = monitorType === "partner_creator";

  React.useEffect(() => {
    if (!settingsBlock.inView) return;
    let cancelled = false;

    async function loadSettings() {
      try {
        const result = await api<MonitorSettings>(`/api/competitors/${account.id}/monitor-settings`);
        if (!cancelled) setSettings(result);
      } catch {
        if (!cancelled) setSettings(getMockMonitorSettings(account.id));
      }
    }

    void loadSettings();

    return () => {
      cancelled = true;
    };
  }, [account.id, settingsBlock.inView]);

  const selectedCadenceValue = React.useMemo(() => {
    const matched = CADENCE_OPTIONS.find((item) => {
      if (!settings.schedule_enabled) return item.value === "manual";
      return item.interval_minutes === settings.interval_minutes;
    });
    return matched?.value || "daily";
  }, [settings]);

  async function handleCadenceChange(event: React.ChangeEvent<HTMLSelectElement>) {
    const option = CADENCE_OPTIONS.find((item) => item.value === event.target.value);
    if (!option) return;

    setSavingCadence(true);
    try {
      const result = await api<MonitorSettings>(`/api/competitors/${account.id}/monitor-settings`, {
        method: "PATCH",
        body: JSON.stringify({
          schedule_enabled: option.schedule_enabled,
          interval_minutes: option.interval_minutes,
        }),
      });
      setSettings(result);
    } catch {
      setSettings((current) => ({
        ...current,
        schedule_enabled: option.schedule_enabled,
        interval_minutes: option.interval_minutes || current.interval_minutes,
        cadence_label: option.label,
      }));
    } finally {
      setSavingCadence(false);
    }
  }

  const lastRefreshLabel = React.useMemo(() => {
    if (!settings.last_refresh_at) return "暂无记录";
    return formatRefreshTime(settings.last_refresh_at);
  }, [settings.last_refresh_at]);

  const refreshStatusLabel = React.useMemo(() => {
    if (refreshing) return "刷新中";
    if (!settings.last_refresh_status) return null;
    if (settings.last_refresh_status === "succeeded") return "成功";
    if (settings.last_refresh_status === "failed") return "失败";
    if (settings.last_refresh_status === "running") return "刷新中";
    if (settings.last_refresh_status === "queued") return "排队中";
    return settings.last_refresh_status;
  }, [refreshing, settings.last_refresh_status]);

  return (
    <div className="cmw-detail" ref={settingsBlock.ref}>
      <header className="cmw-header">
        <div className="cmw-header__title">
          <span className="cmw-header__avatar">{(account.display_name || account.creator_id).slice(0, 2)}</span>
          <div className="cmw-header__title-copy">
            <h2>
              {account.display_name || account.creator_id}
              <span className="cmw-header__platform">{labelPlatform(account.platform)}</span>
              <span className={"cmw-header__status " + (account.enabled !== false ? "is-on" : "is-off")}>
                {account.enabled !== false ? "监控中" : "暂停中"}
              </span>
            </h2>
            <div className="cmw-header__meta">
              <span>平台：{labelPlatform(account.platform)}</span>
              <span>{isCreatorMonitor ? "宣发日期" : "监控时间"}：{date}</span>
              <span>监控频率：{settings.cadence_label}</span>
            </div>
          </div>
        </div>

        <div className="cmw-header__actions">
          <button type="button" className="cmw-header__btn cmw-header__btn--refresh" onClick={onRefresh} disabled={refreshing}>
            {refreshing ? <Loader2 size={14} className="spin" /> : <RefreshCw size={14} />}
            刷新数据
          </button>
          {account.profile_url && (
            <a className="cmw-header__btn" href={account.profile_url} target="_blank" rel="noreferrer">
              <ExternalLink size={14} />
              主页
            </a>
          )}
          <button type="button" className="cmw-header__btn">
            <Share2 size={14} />
            分享
          </button>
          <button type="button" className="cmw-header__btn">
            <FileOutput size={14} />
            导出报告
          </button>
          <button type="button" className="cmw-header__btn">
            更多
            <ChevronDown size={14} />
          </button>
          <button type="button" className="cmw-header__icon-btn" aria-label="更多操作">
            <MoreHorizontal size={14} />
          </button>
        </div>

        <div className="cmw-header__controls">
          <input
            type="date"
            className="cmw-header__date"
            value={date}
            onChange={(event) => onDateChange(event.target.value || date)}
          />

          <label className="cmw-header__cadence">
            <span>监控频率</span>
            <select value={selectedCadenceValue} onChange={handleCadenceChange} disabled={savingCadence}>
              {CADENCE_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {savingCadence && selectedCadenceValue === option.value ? `${option.label}…` : option.label}
                </option>
              ))}
            </select>
          </label>
        </div>

        <div className="cmw-header__summary">
          {refreshing ? <Loader2 size={14} className="spin" /> : <RefreshCw size={14} />}
          <span>上次刷新：{lastRefreshLabel}</span>
          {refreshStatusLabel ? (
            <em
              className={
                "cmw-header__summary-status" +
                (refreshing
                  ? " is-running"
                  : settings.last_refresh_status
                    ? ` is-${settings.last_refresh_status}`
                    : "")
              }
            >
              {refreshStatusLabel}
            </em>
          ) : null}
        </div>
      </header>

      <DailyLedger accountId={account.id} date={date} enabled={settingsBlock.inView} useMock={useMock} monitorType={monitorType} />
      <ContentContributionTable accountId={account.id} date={date} enabled={settingsBlock.inView} useMock={useMock} monitorType={monitorType} />
      <MonitoringPulse accountId={account.id} date={date} useMock={useMock} />
    </div>
  );
}

function formatRefreshTime(value: string): string {
  const parsed = parseUtcLikeDate(value);
  if (!parsed) return value;
  const formatter = new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
  const parts = formatter.formatToParts(parsed);
  const byType = new Map(parts.map((part) => [part.type, part.value]));
  const mm = byType.get("month");
  const dd = byType.get("day");
  const hh = byType.get("hour");
  const mi = byType.get("minute");
  if (!mm || !dd || !hh || !mi) return value;
  return `${mm}-${dd} ${hh}:${mi}`;
}

function parseUtcLikeDate(value: string): Date | null {
  let normalized = value.trim();
  if (!normalized) return null;
  if (/^\d{4}-\d{2}-\d{2} \d{2}:/.test(normalized)) {
    normalized = normalized.replace(" ", "T");
  }
  if (!/[zZ]$|[+-]\d{2}:\d{2}$/.test(normalized)) {
    normalized = `${normalized}Z`;
  }
  const parsed = new Date(normalized);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}
