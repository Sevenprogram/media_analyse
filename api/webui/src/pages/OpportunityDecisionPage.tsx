import React from "react";
import { AlertTriangle, Eye, Play, RefreshCw, SquarePen } from "lucide-react";
import {
  Badge,
  Button,
  Card,
  CardDescription,
  CardHeader,
  CardTitle,
  Drawer,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "../components/ui";
import {
  ChartCard,
  CompetitionGapRanking,
  OpportunityMatrixChart,
  OpportunityScoreBars,
  OpportunityTrendChart,
  PlatformSignalChart,
  RiskDistributionChart,
  opportunityChange24h,
} from "../components/charts";
import {
  formatNumber,
  formatSigned,
  labelConfidence,
  labelOpportunityType,
  labelPlatform,
  labelSampleStatus,
  RISK_LABELS,
} from "../utils/format";
import type { DashboardOpportunity, DashboardSummary, OpportunityRiskTag, OpportunitySample } from "../types";

type OpportunityTypeFilter = "all" | DashboardOpportunity["type"];

export function OpportunityDecisionPage({
  dashboard,
  onRefresh,
  onExecute,
  onFeedback,
}: {
  dashboard: DashboardSummary;
  onRefresh: () => Promise<void>;
  onExecute: (item: DashboardOpportunity) => void;
  onFeedback: (item: DashboardOpportunity, feedback: "valid" | "false_positive" | "watch") => Promise<void>;
}) {
  const [type, setType] = React.useState<OpportunityTypeFilter>("all");
  const [trendWindow, setTrendWindow] = React.useState<"7d" | "14d" | "30d">("7d");
  const [selectedId, setSelectedId] = React.useState<string | null>(null);
  const [detail, setDetail] = React.useState<DashboardOpportunity | null>(null);
  const opportunityPool = dashboard.opportunities?.length ? dashboard.opportunities : dashboard.top_opportunities || [];
  const top = filterOpportunities(opportunityPool, type);
  const watchlist = filterOpportunities(dashboard.watchlist || [], type);
  const all = [...top, ...watchlist];
  const selected = all.find((item) => item.id === selectedId) || top[0] || watchlist[0] || null;
  const currentDecision = type === "all" ? dashboard.decision : dashboard.type_decisions?.[type] || dashboard.decision;
  const currentDiagnostics = type === "all" ? dashboard.diagnostics || [] : dashboard.type_diagnostics?.[type] || [];

  return (
    <section className="opportunity-page opportunity-decision-redesign">
      <div className="title-row compact opportunity-title-row">
        <div>
          <p className="eyebrow">GROWTH OPPORTUNITY DECISION</p>
          <h1>增长机会决策中心</h1>
          <p>先给结论，再看证据；把“看数据”变成“决定今天做什么”。</p>
        </div>
        <div className="title-actions">
          <Button variant="ghost" onClick={onRefresh}>
            <RefreshCw size={16} />
            刷新数据
          </Button>
        </div>
      </div>

      <Tabs value={type} onValueChange={(value) => setType(value as OpportunityTypeFilter)} className="opportunity-tabs">
        <TabsList className="tab-list">
          <TabsTrigger value="all">全部</TabsTrigger>
          <TabsTrigger value="keyword">关键词</TabsTrigger>
          <TabsTrigger value="content">内容</TabsTrigger>
          <TabsTrigger value="creator">达人</TabsTrigger>
          <TabsTrigger value="competitor">友商动作</TabsTrigger>
        </TabsList>
        <TabsContent value={type} forceMount>
          <DecisionHero
            dashboard={dashboard}
            decision={currentDecision}
            opportunity={selected}
            onExecute={onExecute}
            onOpenDetail={setDetail}
          />
          <div className="opportunity-workbench-grid">
            <OpportunityDecisionBoard
              top={top}
              watchlist={watchlist}
              selectedId={selected?.id || null}
              onSelect={setSelectedId}
              onOpenDetail={setDetail}
            />
            <OpportunityExplanationPanel
              opportunity={selected}
              onExecute={onExecute}
              onOpenDetail={setDetail}
            />
            <OpportunityEvidencePanel
              opportunity={selected}
              trendWindow={trendWindow}
              setTrendWindow={setTrendWindow}
              onOpenDetail={setDetail}
            />
          </div>
          <section className="opportunity-core-charts">
            <ChartCard title="综合分拆解" subtitle="解释为什么排在当前优先级。" empty={!selected}>
              {selected && <OpportunityScoreBars opportunity={selected} />}
            </ChartCard>
            <ChartCard title="机会矩阵" subtitle="热度增长 x 竞争空档。" empty={!all.length}>
              <OpportunityMatrixChart opportunities={all} />
            </ChartCard>
            <ChartCard title="平台信号" subtitle="判断是否平台单一。" empty={!all.length}>
              <PlatformSignalChart opportunities={all} />
            </ChartCard>
          </section>
          <details className="advanced-analysis">
            <summary>展开分析：竞争空档、风险分布、内容供给缺口</summary>
            <section className="opportunity-analytics">
              <ChartCard title="竞争空档排行" subtitle="供给不足且友商覆盖不足。" empty={!all.length}>
                <CompetitionGapRanking opportunities={all} />
              </ChartCard>
              <ChartCard title="风险分布" subtitle="小样本、过热、成本等标签。" empty={!all.length}>
                <RiskDistributionChart opportunities={all} />
              </ChartCard>
              <ChartCard title="内容供给缺口" subtitle="先用竞争空档分近似展示。" empty={!all.length}>
                <CompetitionGapRanking opportunities={all.slice().reverse()} />
              </ChartCard>
            </section>
          </details>
          <DiagnosticPanel diagnostics={currentDiagnostics} />
        </TabsContent>
      </Tabs>

      <OpportunityDetailDrawer
        opportunity={detail}
        onClose={() => setDetail(null)}
        onExecute={onExecute}
        onFeedback={onFeedback}
      />
    </section>
  );
}

function filterOpportunities(items: DashboardOpportunity[], type: OpportunityTypeFilter) {
  return type === "all" ? items : items.filter((item) => item.type === type);
}

function DecisionHero({
  dashboard,
  decision,
  opportunity,
  onExecute,
  onOpenDetail,
}: {
  dashboard: DashboardSummary;
  decision: DashboardSummary["decision"];
  opportunity: DashboardOpportunity | null;
  onExecute: (item: DashboardOpportunity) => void;
  onOpenDetail: (item: DashboardOpportunity) => void;
}) {
  const risks = opportunity?.risk_tags?.length || 0;
  const sampleCount = opportunity?.sample_scope?.sample_count || opportunity?.evidence_count || 0;
  return (
    <Card className="decision-hero decision-hero-redesign">
      <div className="decision-hero-main">
        <div className="risk-strip decision-chip-row">
          <Badge tone={decision.confidence === "high" ? "success" : decision.confidence === "medium" ? "warning" : "muted"}>
            {labelConfidence(decision.confidence)}可信
          </Badge>
          <Badge tone={decision.sample_status === "enough" ? "success" : "warning"}>
            {labelSampleStatus(decision.sample_status)}
          </Badge>
          <Badge tone={risks ? "warning" : "muted"}>{risks ? `${risks} 个风险` : "暂无高风险"}</Badge>
        </div>
        <span className="section-label">今日结论</span>
        <h2>{decision.headline}</h2>
        <p>{decision.sample_summary}</p>
        <div className="decision-metrics">
          <MiniMetric value={opportunity ? Math.round(opportunity.score) : 0} label="机会分" />
          <MiniMetric value={formatSigned(opportunityChange24h(opportunity || ({ score: 0 } as DashboardOpportunity)))} label="24h 热度" />
          <MiniMetric value={sampleCount} label="证据样本" />
          <MiniMetric value={risks} label="风险标签" tone={risks ? "warning" : "success"} />
        </div>
      </div>
      <div className="decision-next-action">
        <span>Recommended next action</span>
        <h3>{opportunity ? `预填内容测试任务：${opportunity.name}` : "先采集样本，再生成执行动作"}</h3>
        <p>
          {opportunity
            ? "把决策面板里的“为什么值得做”和“缺什么证据”直接转成执行动作，避免运营再从图表里手动推导。"
            : "缺少可判断机会时，系统只显示诊断，不生成假结论。"}
        </p>
        <div className="button-row">
          <Button disabled={!opportunity} variant="default" onClick={() => opportunity && onExecute(opportunity)}>
            <SquarePen size={16} />
            预填执行单
          </Button>
          <Button disabled={!opportunity} variant="ghost" onClick={() => opportunity && onOpenDetail(opportunity)}>
            <Eye size={16} />
            查看证据详情
          </Button>
        </div>
      </div>
    </Card>
  );
}

function MiniMetric({
  value,
  label,
  tone,
}: {
  value: number | string;
  label: string;
  tone?: "success" | "warning";
}) {
  return (
    <div className={`decision-metric ${tone || ""}`}>
      <strong>{typeof value === "number" ? formatNumber(value) : value}</strong>
      <span>{label}</span>
    </div>
  );
}

function OpportunityDecisionBoard({
  top,
  watchlist,
  selectedId,
  onSelect,
  onOpenDetail,
}: {
  top: DashboardOpportunity[];
  watchlist: DashboardOpportunity[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  onOpenDetail: (item: DashboardOpportunity) => void;
}) {
  return (
    <Card className="opportunity-decision-board">
      <CardHeader>
        <div>
          <CardTitle>机会队列</CardTitle>
          <CardDescription>Top 机会和观察池合并展示，但用状态区分。</CardDescription>
        </div>
        <Badge>
          {top.length} / {watchlist.length}
        </Badge>
      </CardHeader>
      <div className="opportunity-queue-scroll">
        <OpportunityList title="Top 5" items={top} selectedId={selectedId} onSelect={onSelect} onOpenDetail={onOpenDetail} />
        <OpportunityList
          title="观察池"
          items={watchlist}
          selectedId={selectedId}
          onSelect={onSelect}
          onOpenDetail={onOpenDetail}
          watch
        />
      </div>
    </Card>
  );
}

function OpportunityList({
  title,
  items,
  selectedId,
  onSelect,
  onOpenDetail,
  watch,
}: {
  title: string;
  items: DashboardOpportunity[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  onOpenDetail: (item: DashboardOpportunity) => void;
  watch?: boolean;
}) {
  return (
    <div className="opportunity-list">
      <div className="list-title">{title}</div>
      {items.map((item) => (
        <button
          className={`opportunity-card ${item.id === selectedId ? "active" : ""} ${watch ? "watch" : ""}`}
          key={item.id}
          type="button"
          onClick={() => onSelect(item.id)}
        >
          <div className="opportunity-card-head">
            <Badge tone={watch ? "warning" : "success"}>{watch ? "观察" : labelOpportunityType(item.type)}</Badge>
            <strong>{watch ? "观察" : Math.round(item.score)}</strong>
          </div>
          <h3>{item.name}</h3>
          <div className="opportunity-meta">
            <span>{labelPlatform(item.platform)}</span>
            <span>24h {formatSigned(opportunityChange24h(item))}</span>
            <span>{formatNumber(item.sample_scope?.sample_count || item.evidence_count || 0)} 样本</span>
          </div>
          <RiskStrip risks={item.risk_tags || []} />
          <span
            className="text-link"
            onClick={(event) => {
              event.stopPropagation();
              onOpenDetail(item);
            }}
          >
            查看证据
          </span>
        </button>
      ))}
      {!items.length && <EmptyState title={`暂无${title}`} body="采集或回填后，这里会显示可判断的机会。" />}
    </div>
  );
}

function OpportunityExplanationPanel({
  opportunity,
  onExecute,
  onOpenDetail,
}: {
  opportunity: DashboardOpportunity | null;
  onExecute: (item: DashboardOpportunity) => void;
  onOpenDetail: (item: DashboardOpportunity) => void;
}) {
  if (!opportunity) {
    return (
      <Card className="opportunity-explanation">
        <EmptyState title="暂无可解释机会" body="缺少样本时，系统只显示诊断，不生成假结论。" />
      </Card>
    );
  }
  const summaries = opportunity.evidence_summary?.length
    ? opportunity.evidence_summary
    : opportunity.detail?.summary || [opportunity.reason || "暂无摘要"];
  return (
    <Card className="opportunity-explanation">
      <CardHeader>
        <div>
          <span className="section-label">Selected Opportunity</span>
          <CardTitle>{opportunity.name}</CardTitle>
          <CardDescription>
            {labelOpportunityType(opportunity.type)} / {labelPlatform(opportunity.platform)} / 综合机会分 {Math.round(opportunity.score)}
          </CardDescription>
        </div>
        <strong className="score-badge">{Math.round(opportunity.score)}</strong>
      </CardHeader>
      <OpportunityScoreBars opportunity={opportunity} />
      <div className="evidence-summary decision-summary-list">
        {summaries.slice(0, 3).map((item, index) => (
          <p key={item}>
            <strong>{index === 0 ? "为什么值得做：" : index === 1 ? "怎么做：" : "先补什么："}</strong>
            {item}
          </p>
        ))}
      </div>
      <div className="button-row">
        <Button variant="ghost" onClick={() => onOpenDetail(opportunity)}>
          <Eye size={16} />
          查看证据详情
        </Button>
        <Button variant="primary" onClick={() => onExecute(opportunity)}>
          <SquarePen size={16} />
          预填/确认动作
        </Button>
      </div>
    </Card>
  );
}

function OpportunityEvidencePanel({
  opportunity,
  trendWindow,
  setTrendWindow,
  onOpenDetail,
}: {
  opportunity: DashboardOpportunity | null;
  trendWindow: "7d" | "14d" | "30d";
  setTrendWindow: (value: "7d" | "14d" | "30d") => void;
  onOpenDetail: (item: DashboardOpportunity) => void;
}) {
  if (!opportunity) {
    return (
      <Card className="opportunity-evidence-panel">
        <EmptyState title="暂无证据与风险" body="选中机会后，这里会显示风险、趋势和证据摘要。" />
      </Card>
    );
  }
  const summaries = opportunity.evidence_summary?.length
    ? opportunity.evidence_summary
    : opportunity.detail?.summary || [opportunity.reason || "暂无证据摘要"];
  return (
    <Card className="opportunity-evidence-panel">
      <CardHeader>
        <div>
          <CardTitle>证据与风险</CardTitle>
          <CardDescription>只放影响决策的证据，完整样本进抽屉。</CardDescription>
        </div>
      </CardHeader>
      <div className="evidence-risk-box">
        <strong>{opportunity.risk_tags?.length ? "风险提醒" : "风险提醒：暂无高风险"}</strong>
        <RiskStrip risks={opportunity.risk_tags || []} />
      </div>
      <div className="segmented compact trend-window-control">
        {(["7d", "14d", "30d"] as const).map((value) => (
          <Button key={value} size="sm" variant={trendWindow === value ? "primary" : "ghost"} onClick={() => setTrendWindow(value)}>
            {value}
          </Button>
        ))}
      </div>
      <OpportunityTrendChart opportunity={opportunity} window={trendWindow} compact />
      <div className="evidence-source-list">
        {summaries.slice(0, 3).map((item, index) => (
          <article className="evidence-source-card" key={item}>
            <strong>证据 {index + 1}</strong>
            <span>{item}</span>
          </article>
        ))}
      </div>
      <Button variant="ghost" onClick={() => onOpenDetail(opportunity)}>
        <Eye size={16} />
        打开完整证据
      </Button>
    </Card>
  );
}

function OpportunityDetailDrawer({
  opportunity,
  onClose,
  onExecute,
  onFeedback,
}: {
  opportunity: DashboardOpportunity | null;
  onClose: () => void;
  onExecute: (item: DashboardOpportunity) => void;
  onFeedback: (item: DashboardOpportunity, feedback: "valid" | "false_positive" | "watch") => Promise<void>;
}) {
  const [busy, setBusy] = React.useState<"valid" | "false_positive" | "watch" | null>(null);
  async function send(feedback: "valid" | "false_positive" | "watch") {
    if (!opportunity) return;
    setBusy(feedback);
    try {
      await onFeedback(opportunity, feedback);
      if (feedback !== "valid") onClose();
    } finally {
      setBusy(null);
    }
  }
  return (
    <Drawer
      open={!!opportunity}
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
      title="机会详情"
    >
      {opportunity && (
        <div className="drawer-body">
          <div className="drawer-title-block">
            <Badge>{labelOpportunityType(opportunity.type)}</Badge>
            <h2>{opportunity.name}</h2>
            <p>
              {labelPlatform(opportunity.platform)} / 综合分 {Math.round(opportunity.score)}
            </p>
          </div>
          <section className="drawer-section">
            <h3>评分拆解</h3>
            <OpportunityScoreBars opportunity={opportunity} />
          </section>
          <section className="drawer-section">
            <h3>趋势与平台贡献</h3>
            <OpportunityTrendChart opportunity={opportunity} />
            <PlatformSignalChart opportunities={[opportunity]} />
          </section>
          <section className="drawer-section">
            <h3>风险</h3>
            <RiskStrip risks={opportunity.risk_tags || []} />
          </section>
          <section className="drawer-section">
            <h3>样本范围</h3>
            <div className="drawer-metrics">
              <MiniMetric value={opportunity.sample_scope?.window || "-"} label="窗口" />
              <MiniMetric value={opportunity.sample_scope?.sample_count || opportunity.evidence_count || 0} label="样本数" />
              <MiniMetric
                value={(opportunity.sample_scope?.platforms || [opportunity.platform || "-"]).map(labelPlatform).join(" / ")}
                label="平台"
              />
            </div>
          </section>
          <section className="drawer-section">
            <h3>证据摘要</h3>
            {(opportunity.evidence_summary?.length ? opportunity.evidence_summary : opportunity.detail?.summary || []).map((item) => (
              <p key={item}>{item}</p>
            ))}
          </section>
          <section className="drawer-section">
            <h3>证据样本</h3>
            <EvidenceSamplePanel samples={opportunity.samples || []} />
          </section>
          <section className="drawer-section">
            <h3>反馈</h3>
            <div className="feedback-row">
              <Button disabled={!!busy} variant={opportunity.feedback_state === "valid" ? "primary" : "ghost"} onClick={() => send("valid")}>
                有效
              </Button>
              <Button disabled={!!busy} variant="ghost" onClick={() => send("false_positive")}>
                误判
              </Button>
              <Button disabled={!!busy} variant="ghost" onClick={() => send("watch")}>
                先观察
              </Button>
            </div>
          </section>
          <div className="drawer-actions">
            <Button variant="primary" onClick={() => onExecute(opportunity)}>
              <Play size={16} />
              预填/确认执行
            </Button>
          </div>
        </div>
      )}
    </Drawer>
  );
}

function EvidenceSamplePanel({ samples }: { samples: OpportunitySample[] }) {
  const visible = samples.slice(0, 10);
  if (!visible.length) return <p className="muted">暂无 typed evidence samples。</p>;
  return <div className="evidence-samples">{visible.map((sample, index) => <EvidenceSampleCard key={index} sample={sample} />)}</div>;
}

function EvidenceSampleCard({ sample }: { sample: OpportunitySample }) {
  return (
    <article className="evidence-sample">
      <div className="evidence-sample-head">
        <Badge>{sample.type}</Badge>
        <span>
          {labelPlatform(sample.platform)} / {sample.publish_time || "-"}
        </span>
      </div>
      <strong>{sample.title || sample.body?.slice(0, 60) || "未命名样本"}</strong>
      {sample.body && <p>{sample.body}</p>}
      {!!sample.matched_terms?.length && (
        <div className="risk-strip">
          {sample.matched_terms.map((term) => (
            <Badge tone="muted" key={term}>
              {term}
            </Badge>
          ))}
        </div>
      )}
      {sample.url && (
        <a href={sample.url} target="_blank" rel="noreferrer">
          打开原文
        </a>
      )}
    </article>
  );
}

function RiskStrip({ risks }: { risks: OpportunityRiskTag[] }) {
  return (
    <div className="risk-strip">
      {risks.length ? (
        risks.map((risk) => (
          <Badge tone="warning" key={risk}>
            {RISK_LABELS[risk] || risk}
          </Badge>
        ))
      ) : (
        <Badge tone="muted">暂无高风险</Badge>
      )}
    </div>
  );
}

function DiagnosticPanel({ diagnostics }: { diagnostics: Array<{ code: string; title: string; body: string; action?: string }> }) {
  if (!diagnostics.length) return null;
  return (
    <section className="diagnostic-panel">
      {diagnostics.map((item) => (
        <div className="diagnostic-card" key={item.code}>
          <AlertTriangle size={16} />
          <div>
            <strong>{item.title}</strong>
            <p>{item.body}</p>
            {item.action && <small>{item.action}</small>}
          </div>
        </div>
      ))}
    </section>
  );
}

function EmptyState({ title, body }: { title: string; body: string }) {
  return (
    <div className="empty-state">
      <strong>{title}</strong>
      <p>{body}</p>
    </div>
  );
}
