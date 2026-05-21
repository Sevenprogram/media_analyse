import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
  ZAxis,
} from "recharts";
import type { CommentRecord, DashboardOpportunity, PostRecord, ResearchJob } from "../types";
import { labelPlatform, RISK_LABELS, SCORE_PARTS } from "../utils/format";
import { Card, CardDescription, CardHeader, CardTitle } from "./ui";

const CHART_COLORS = ["#04786f", "#2563eb", "#ff9f1c", "#101820", "#ef4444", "#94a3b8"];
const AXIS_STYLE = { fill: "#64716f", fontSize: 12 };
const GRID_STROKE = "#e3ebe7";
const TOOLTIP_STYLE = {
  border: "1px solid #dce6e2",
  borderRadius: 8,
  boxShadow: "0 14px 34px rgba(16, 24, 32, 0.12)",
  color: "#18231f",
};

export function fallbackScoreBreakdown(item: DashboardOpportunity) {
  return item.score_breakdown || {
    heat_growth: Number(item.score || 0),
    sample_confidence: item.confidence === "high" ? 85 : item.confidence === "medium" ? 65 : 35,
    competition_gap: Number(item.score || 0),
    actionability: Number(item.score || 0),
  };
}

export function opportunityChange24h(item: DashboardOpportunity) {
  return Number(item.trend?.change_24h ?? item.change_24h ?? 0);
}

export function opportunityTrendPoints(
  item: DashboardOpportunity,
  window: "7d" | "14d" | "30d" = "7d",
) {
  const source =
    window === "30d"
      ? item.trend?.points_30d
      : window === "14d"
        ? item.trend?.points_14d
        : item.trend?.points_7d;
  const points = source?.length
    ? source
    : item.detail?.trend_30d?.slice(window === "30d" ? -30 : window === "14d" ? -14 : -7);
  return (points || []).map((point, index) => ({
    label: String(point.date || point.day || point.snapshot_date || index + 1),
    score: Number(point.score || point.value || point.heat_score || point.count || item.score || 0),
  }));
}

export function ChartCard({
  title,
  subtitle,
  children,
  empty,
}: {
  title: string;
  subtitle: string;
  children: React.ReactNode;
  empty?: boolean;
}) {
  return (
    <Card className="chart-card">
      <CardHeader>
        <div>
          <CardTitle>{title}</CardTitle>
          <CardDescription>{subtitle}</CardDescription>
        </div>
      </CardHeader>
      {empty ? <div className="chart-empty">暂无图表数据</div> : children}
    </Card>
  );
}

export function OpportunityScoreBars({ opportunity }: { opportunity: DashboardOpportunity }) {
  const breakdown = fallbackScoreBreakdown(opportunity);
  return (
    <div className="score-bars">
      {SCORE_PARTS.map(([key, label]) => (
        <div className="score-bar" key={key}>
          <span>{label}</span>
          <div>
            <i style={{ width: `${Math.max(0, Math.min(100, breakdown[key]))}%` }} />
          </div>
          <strong>{Math.round(breakdown[key])}</strong>
        </div>
      ))}
    </div>
  );
}

export function OpportunityTrendChart({
  opportunity,
  window,
  compact,
}: {
  opportunity: DashboardOpportunity;
  window?: "7d" | "14d" | "30d";
  compact?: boolean;
}) {
  const rows = opportunityTrendPoints(opportunity, window || "7d");
  const data = rows.length ? rows : [{ label: "当前", score: opportunity.score }];
  return (
    <ResponsiveContainer width="100%" height={compact ? 150 : 210}>
      <AreaChart data={data} margin={{ top: 10, right: 12, left: compact ? -26 : -8, bottom: 0 }}>
        <defs>
          <linearGradient id="opportunityTrendFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor="#04786f" stopOpacity={0.28} />
            <stop offset="95%" stopColor="#04786f" stopOpacity={0.03} />
          </linearGradient>
        </defs>
        <CartesianGrid stroke={GRID_STROKE} strokeDasharray="4 6" vertical={false} />
        <XAxis dataKey="label" tick={AXIS_STYLE} tickLine={false} axisLine={{ stroke: "#d7e1dd" }} minTickGap={18} />
        <YAxis domain={[0, 100]} tick={AXIS_STYLE} tickLine={false} axisLine={false} hide={compact} />
        <Tooltip contentStyle={TOOLTIP_STYLE} cursor={{ stroke: "#04786f", strokeOpacity: 0.18, strokeWidth: 2 }} />
        <Area
          type="monotone"
          dataKey="score"
          fill="url(#opportunityTrendFill)"
          stroke="#04786f"
          strokeWidth={3}
          activeDot={{ r: 5, stroke: "#ffffff", strokeWidth: 2 }}
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}

export function PlatformSignalChart({ opportunities }: { opportunities: DashboardOpportunity[] }) {
  const counts = new Map<string, number>();
  opportunities.forEach((item) =>
    counts.set(item.platform || "unknown", (counts.get(item.platform || "unknown") || 0) + 1),
  );
  const rows = [...counts.entries()].map(([platform, score]) => ({ platform, score }));
  return (
    <ResponsiveContainer width="100%" height={210}>
      <BarChart data={rows} margin={{ top: 12, right: 12, left: -12, bottom: 0 }}>
        <defs>
          <linearGradient id="platformSignalFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#2563eb" stopOpacity={0.95} />
            <stop offset="100%" stopColor="#04786f" stopOpacity={0.88} />
          </linearGradient>
        </defs>
        <CartesianGrid stroke={GRID_STROKE} strokeDasharray="4 6" vertical={false} />
        <XAxis dataKey="platform" tickFormatter={labelPlatform} tick={AXIS_STYLE} tickLine={false} axisLine={{ stroke: "#d7e1dd" }} />
        <YAxis allowDecimals={false} tick={AXIS_STYLE} tickLine={false} axisLine={false} />
        <Tooltip contentStyle={TOOLTIP_STYLE} cursor={{ fill: "rgba(4, 120, 111, 0.06)" }} />
        <Bar dataKey="score" fill="url(#platformSignalFill)" radius={[8, 8, 0, 0]} maxBarSize={54} />
      </BarChart>
    </ResponsiveContainer>
  );
}

export function RiskDistributionChart({ opportunities }: { opportunities: DashboardOpportunity[] }) {
  const counts = new Map<string, number>();
  opportunities.forEach((item) =>
    (item.risk_tags?.length ? item.risk_tags : ["none"]).forEach((risk) =>
      counts.set(risk, (counts.get(risk) || 0) + 1),
    ),
  );
  const rows = [...counts.entries()].map(([name, value]) => ({
    name: name === "none" ? "无风险标签" : RISK_LABELS[name as keyof typeof RISK_LABELS] || name,
    value,
  }));
  return (
    <ResponsiveContainer width="100%" height={210}>
      <PieChart>
        <Pie data={rows} dataKey="value" nameKey="name" innerRadius={46} outerRadius={78} paddingAngle={3}>
          {rows.map((_, index) => (
            <Cell key={index} fill={CHART_COLORS[index % CHART_COLORS.length]} />
          ))}
        </Pie>
        <Tooltip contentStyle={TOOLTIP_STYLE} />
      </PieChart>
    </ResponsiveContainer>
  );
}

export function OpportunityMatrixChart({ opportunities }: { opportunities: DashboardOpportunity[] }) {
  const rows = opportunities.map((item) => ({
    name: item.name,
    heat: fallbackScoreBreakdown(item).heat_growth,
    gap: fallbackScoreBreakdown(item).competition_gap,
    size: Math.max(30, item.sample_scope?.sample_count || item.evidence_count || 20),
  }));
  return (
    <ResponsiveContainer width="100%" height={260}>
      <ScatterChart margin={{ top: 16, right: 18, left: -8, bottom: 4 }}>
        <CartesianGrid stroke={GRID_STROKE} strokeDasharray="4 6" />
        <XAxis dataKey="heat" name="热度" domain={[0, 100]} tick={AXIS_STYLE} tickLine={false} axisLine={{ stroke: "#d7e1dd" }} />
        <YAxis dataKey="gap" name="空档" domain={[0, 100]} tick={AXIS_STYLE} tickLine={false} axisLine={{ stroke: "#d7e1dd" }} />
        <ZAxis dataKey="size" range={[80, 420]} />
        <Tooltip cursor={{ strokeDasharray: "4 4", stroke: "#04786f", strokeOpacity: 0.32 }} contentStyle={TOOLTIP_STYLE} />
        <Scatter data={rows} fill="#04786f" fillOpacity={0.88} stroke="#ffffff" strokeWidth={1.5} />
      </ScatterChart>
    </ResponsiveContainer>
  );
}

export function CompetitionGapRanking({ opportunities }: { opportunities: DashboardOpportunity[] }) {
  const rows = opportunities
    .map((item) => ({ name: item.name, value: fallbackScoreBreakdown(item).competition_gap }))
    .sort((a, b) => b.value - a.value)
    .slice(0, 8);
  return (
    <ResponsiveContainer width="100%" height={240}>
      <BarChart data={rows} layout="vertical" margin={{ top: 8, right: 18, left: 4, bottom: 0 }}>
        <CartesianGrid stroke={GRID_STROKE} strokeDasharray="4 6" horizontal={false} />
        <XAxis type="number" domain={[0, 100]} tick={AXIS_STYLE} tickLine={false} axisLine={{ stroke: "#d7e1dd" }} />
        <YAxis type="category" dataKey="name" width={96} tick={AXIS_STYLE} tickLine={false} axisLine={false} />
        <Tooltip contentStyle={TOOLTIP_STYLE} cursor={{ fill: "rgba(255, 159, 28, 0.08)" }} />
        <Bar dataKey="value" fill="#ff9f1c" radius={[0, 8, 8, 0]} maxBarSize={18} />
      </BarChart>
    </ResponsiveContainer>
  );
}

export function platformRows(posts: PostRecord[], comments: CommentRecord[]) {
  const counts = new Map<string, { platform: string; posts: number; comments: number }>();
  posts.forEach((post) => {
    const row = counts.get(post.platform) || { platform: post.platform, posts: 0, comments: 0 };
    row.posts += 1;
    counts.set(post.platform, row);
  });
  comments.forEach((comment) => {
    const row = counts.get(comment.platform) || { platform: comment.platform, posts: 0, comments: 0 };
    row.comments += 1;
    counts.set(comment.platform, row);
  });
  return [...counts.values()];
}

export function buildPublishDateRows(posts: PostRecord[], comments: CommentRecord[]) {
  const counts = new Map<string, { date: string; posts: number; comments: number }>();
  posts.forEach((item) => {
    const date = (item.publish_time || "").slice(0, 10) || "unknown";
    const row = counts.get(date) || { date, posts: 0, comments: 0 };
    row.posts += 1;
    counts.set(date, row);
  });
  comments.forEach((item) => {
    const date = (item.publish_time || "").slice(0, 10) || "unknown";
    const row = counts.get(date) || { date, posts: 0, comments: 0 };
    row.comments += 1;
    counts.set(date, row);
  });
  return [...counts.values()].sort((a, b) => a.date.localeCompare(b.date)).slice(-14);
}

export function buildKeywordHitRows(posts: PostRecord[], selectedJob: ResearchJob | null) {
  const keywords = selectedJob?.keywords?.length
    ? selectedJob.keywords
    : Array.from(new Set(posts.map((post) => String(post.engagement_json?.source_keyword || "")).filter(Boolean)));
  return keywords
    .map((keyword) => ({
      keyword,
      count: posts.filter((post) =>
        `${post.title || ""} ${post.content || ""} ${String(post.engagement_json?.source_keyword || "")}`
          .toLowerCase()
          .includes(keyword.toLowerCase()),
      ).length,
    }))
    .filter((row) => row.count > 0)
    .sort((a, b) => b.count - a.count)
    .slice(0, 8);
}
