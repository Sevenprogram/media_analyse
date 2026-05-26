import React from "react";
import { CalendarDays, Loader2, RefreshCw } from "lucide-react";
import { useEndpoint } from "../lib/useEndpoint";
import { api } from "../utils/api";
import { AccountSidebar } from "./AccountSidebar";
import { AccountDetailPanel } from "./AccountDetailPanel";
import { InsightSidebar } from "./InsightSidebar";
import { AddCompetitorDrawer } from "./AddCompetitorDrawer";
import { mockAccounts, mockCreatorAccounts, mockOverview } from "./mock";
import type { MonitorType, TodaySummary, WorkbenchAccount } from "./types";

type CollectionRun = {
  id: number;
  status?: string | null;
  phase?: string | null;
  summary?: Record<string, unknown> | null;
  error?: { message?: string | null } | null;
};

type CollectionRunResponse = {
  run: CollectionRun;
};

function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

function dateRangeLabel(date: string) {
  const end = new Date(date);
  if (Number.isNaN(end.getTime())) return `${date} ~ ${date}`;
  const start = new Date(end);
  start.setDate(end.getDate() - 7);
  const format = (value: Date) =>
    `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, "0")}-${String(value.getDate()).padStart(2, "0")}`;
  return `${format(start)} ~ ${format(end)}`;
}

export function CompetitorMonitorWorkbench({
  selectedProjectId,
  selectedProjectRecordId,
  selectedProjectName,
}: {
  selectedProjectId?: string | null;
  selectedProjectRecordId?: number | null;
  selectedProjectName?: string | null;
}) {
  const [activeMonitorType, setActiveMonitorType] = React.useState<MonitorType>("competitor");
  const projectContextPending = Boolean(selectedProjectId) && !selectedProjectRecordId;
  const projectQuery = selectedProjectRecordId ? `&project_id=${encodeURIComponent(String(selectedProjectRecordId))}` : "";
  const accountsQuery = useEndpoint<{ competitors: WorkbenchAccount[] }>(
    `/api/competitors?enabled_only=true&monitor_type=${activeMonitorType}${projectQuery}`,
    { competitors: [] },
    { enabled: !projectContextPending },
  );
  const [selectedId, setSelectedId] = React.useState<number | null>(null);
  const [date, setDate] = React.useState<string>(todayIso());
  const [addOpen, setAddOpen] = React.useState(false);
  const [selectedRefreshing, setSelectedRefreshing] = React.useState(false);
  const [allRefreshing, setAllRefreshing] = React.useState(false);
  const [collectionRun, setCollectionRun] = React.useState<CollectionRun | null>(null);
  const [refreshError, setRefreshError] = React.useState<string | null>(null);
  const [refreshVersion, setRefreshVersion] = React.useState(0);
  const [overview, setOverview] = React.useState(mockOverview);
  const [overviewLoading, setOverviewLoading] = React.useState(false);

  const fallbackAccounts = activeMonitorType === "partner_creator" ? mockCreatorAccounts : mockAccounts;
  const hasProjectScope = Boolean(selectedProjectRecordId);
  const accounts = projectContextPending
    ? []
    : accountsQuery.data.competitors.length
      ? accountsQuery.data.competitors
      : (hasProjectScope ? [] : fallbackAccounts);
  const usingMock = !projectContextPending && !hasProjectScope && accountsQuery.data.competitors.length === 0;
  const isCreatorMonitor = activeMonitorType === "partner_creator";

  React.useEffect(() => {
    setSelectedId(null);
    setCollectionRun(null);
    setRefreshError(null);
  }, [selectedProjectRecordId]);

  React.useEffect(() => {
    if (accounts.length === 0) {
      setSelectedId(null);
      return;
    }

    if (selectedId !== null && !accounts.some((account) => account.id === selectedId)) {
      setSelectedId(null);
    }
  }, [accounts, selectedId]);

  React.useEffect(() => {
    let cancelled = false;
    async function loadOverview() {
      if (usingMock) {
        setOverview(mockOverview);
        return;
      }
      if (projectContextPending) {
        setOverview({ new_posts_total: 0, interaction_total: 0, new_hot_total: 0, anomaly_total: 0 });
        setOverviewLoading(false);
        return;
      }
      setOverviewLoading(true);
      const results = await Promise.allSettled(
        accounts.map((account) => api<TodaySummary>(`/api/competitors/${account.id}/today-summary?date=${date}`)),
      );
      if (cancelled) return;

      let nextOverview = { new_posts_total: 0, interaction_total: 0, new_hot_total: 0, anomaly_total: 0 };
      for (const result of results) {
        if (result.status === "fulfilled") {
          nextOverview = {
            new_posts_total: nextOverview.new_posts_total + result.value.metrics.deduped_post_count,
            interaction_total: nextOverview.interaction_total + result.value.metrics.interaction_delta,
            new_hot_total: nextOverview.new_hot_total + result.value.metrics.new_hot_post_count,
            anomaly_total: nextOverview.anomaly_total + result.value.metrics.anomaly_count,
          };
        }
      }

      setOverview(nextOverview);
      setOverviewLoading(false);
    }

    void loadOverview();
    return () => {
      cancelled = true;
    };
  }, [accounts, date, projectContextPending, usingMock]);

  const selectedAccount = React.useMemo(
    () => accounts.find((account) => account.id === selectedId) || null,
    [accounts, selectedId],
  );

  async function waitForCollectionRun(runId: number): Promise<CollectionRun> {
    let latest: CollectionRun | null = null;
    for (let attempt = 0; attempt < 80; attempt += 1) {
      const data = await api<CollectionRunResponse>(`/api/competitors/collection-runs/${runId}`);
      latest = data.run;
      setCollectionRun(latest);
      if (latest.status === "succeeded" || latest.status === "failed") {
        return latest;
      }
      await new Promise((resolve) => window.setTimeout(resolve, 1200));
    }
    throw new Error("Collection run timed out");
  }

  async function refreshCompetitor(account: WorkbenchAccount) {
    const created = await api<CollectionRunResponse>(`/api/competitors/${account.id}/collect-and-refresh`, {
      method: "POST",
      body: JSON.stringify({ latest_limit: 50, days_back: 7, trigger_source: "manual", execute_now: true, headless: true }),
    });
    setCollectionRun(created.run);
    const finished = await waitForCollectionRun(created.run.id);
    if (finished.status === "failed") {
      throw new Error(finished.error?.message || `${account.display_name || account.creator_id} refresh failed`);
    }
  }

  async function finishRefresh() {
    await accountsQuery.reload();
    setRefreshVersion((current) => current + 1);
  }

  async function handleRefreshSelected() {
    if (usingMock) {
      setSelectedRefreshing(true);
      window.setTimeout(() => {
        setSelectedRefreshing(false);
        setRefreshVersion((current) => current + 1);
      }, 600);
      return;
    }
    if (!selectedAccount) return;
    setSelectedRefreshing(true);
    setCollectionRun(null);
    setRefreshError(null);
    try {
      await refreshCompetitor(selectedAccount);
      await finishRefresh();
    } catch (error) {
      setRefreshError(error instanceof Error ? error.message : String(error));
    } finally {
      setSelectedRefreshing(false);
    }
  }

  async function handleRefreshAll() {
    if (usingMock) {
      setAllRefreshing(true);
      window.setTimeout(() => {
        setAllRefreshing(false);
        setRefreshVersion((current) => current + 1);
      }, 600);
      return;
    }
    const enabledAccounts = accounts.filter((account) => account.enabled !== false);
    if (enabledAccounts.length === 0) return;
    setAllRefreshing(true);
    setCollectionRun(null);
    setRefreshError(null);
    const failures: string[] = [];
    try {
      for (const account of enabledAccounts) {
        try {
          await refreshCompetitor(account);
        } catch (error) {
          failures.push(`${account.display_name || account.creator_id}: ${error instanceof Error ? error.message : String(error)}`);
        }
      }
      await finishRefresh();
      if (failures.length > 0) {
        setRefreshError(`部分${isCreatorMonitor ? "达人" : "友商"}刷新失败：${failures.join("；")}`);
      }
    } finally {
      setAllRefreshing(false);
    }
  }

  return (
    <section className="cmw-page">
      <header className="cmw-page__hero">
        <div>
          <div className="cmw-page__eyebrow">{isCreatorMonitor ? "Creator Campaign Watch" : "Competitive Watchtower"}</div>
          <h1>{isCreatorMonitor ? "达人监控" : "友商监控"}</h1>
          <p>
            {isCreatorMonitor
              ? `监控${selectedProjectName ? `「${selectedProjectName}」` : "当前项目"}合作达人的宣发内容、互动增量与发布节奏，识别复投机会和商务跟进风险。`
              : `监控${selectedProjectName ? `「${selectedProjectName}」` : "当前项目"}竞争对手的内容表现、互动趋势与策略变化，识别机会与风险，形成可执行的跟进动作。`}
          </p>
        </div>
        <div className="cmw-page__hero-tools">
          <button type="button" className="cmw-page__refresh-all" onClick={handleRefreshAll} disabled={allRefreshing || selectedRefreshing}>
            {allRefreshing ? <Loader2 size={15} className="spin" /> : <RefreshCw size={15} />}
            刷新全部数据
          </button>
          <div className="cmw-page__datebox">
            <CalendarDays size={16} />
            <span>{dateRangeLabel(date)}</span>
            <input
              type="date"
              value={date}
              onChange={(event) => setDate(event.target.value || date)}
              aria-label="选择数据日期"
            />
          </div>
        </div>
      </header>

      <div className="cmw-shell">
        <div className="cmw-col cmw-col--left">
          <AccountSidebar
            accounts={accounts}
            activeMonitorType={activeMonitorType}
            selectedId={selectedId}
            onSelect={setSelectedId}
            onMonitorTypeChange={(type) => {
              setActiveMonitorType(type);
              setSelectedId(null);
              setCollectionRun(null);
              setRefreshError(null);
            }}
            onAddClick={() => setAddOpen(true)}
            onSyncClick={handleRefreshAll}
            syncing={allRefreshing}
            loading={projectContextPending || accountsQuery.loading || overviewLoading}
            overview={overview}
          />
        </div>

        <div className="cmw-col cmw-col--center">
          {selectedAccount ? (
            <AccountDetailPanel
              key={`${selectedAccount.id}-${refreshVersion}`}
              account={selectedAccount}
              date={date}
              onDateChange={setDate}
              onRefresh={handleRefreshSelected}
              refreshing={selectedRefreshing || allRefreshing}
              useMock={usingMock}
            />
          ) : (
            <div className="cmw-empty">
              {projectContextPending || accountsQuery.loading
                ? "加载中…"
                : isCreatorMonitor
                  ? "请先从左侧选择一个合作达人"
                  : "请先从左侧选择一个友商账号"}
            </div>
          )}
        </div>

        <div className="cmw-col cmw-col--right">
          {selectedAccount ? (
            <InsightSidebar
              key={`${selectedAccount.id}-${date}-${refreshVersion}`}
              accountId={selectedAccount.id}
              date={date}
              useMock={usingMock}
            />
          ) : (
            <div className="cmw-empty">
              {isCreatorMonitor
                ? "选择达人后展示宣发节奏、内容表现与推荐动作。"
                : "选择账号后展示组成模式拆解、热力图与推荐动作。"}
            </div>
          )}
        </div>
      </div>

      {refreshError && <div className="cmw-refresh-status is-error">{refreshError}</div>}

      {collectionRun && (
        <div className="cmw-refresh-status">
          Collection {collectionRun.status || "queued"} / {collectionRun.phase || "queued"}
        </div>
      )}

      <AddCompetitorDrawer
        open={addOpen}
        monitorType={activeMonitorType}
        projectId={selectedProjectRecordId}
        onOpenChange={setAddOpen}
        onCreated={() => {
          void accountsQuery.reload();
        }}
      />
    </section>
  );
}
