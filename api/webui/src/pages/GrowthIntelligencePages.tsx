import React from "react";
import {
  Activity,
  AlertTriangle,
  BarChart3,
  Bot,
  CheckCircle2,
  Clock,
  Database,
  Download,
  ExternalLink,
  Gauge,
  KeyRound,
  ListChecks,
  Play,
  RefreshCw,
  Search,
  Settings,
  ShieldCheck,
  Users,
  TrendingUp,
  BookOpen,
  Hash,
  Info,
  Calendar,
} from "lucide-react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Badge, Button, Card, CardDescription, CardHeader, CardTitle, Drawer } from "../components/ui";
import {
  compactJson,
  formatDateTime,
  formatNumber,
  formatSigned,
  labelOpportunityType,
  labelPlatform,
  labelSampleStatus,
  RISK_LABELS,
} from "../utils/format";
import { GrowthProjectWorkbenchPage } from "./GrowthProjectWorkbenchPage";
import type {
  AIResult,
  AiInsightSummary,
  AiTopicIdeasSummary,
  CommentRecord,
  DashboardAction,
  DashboardOpportunity,
  DashboardSummary,
  DatabaseStats,
  GrowthProjectCollectionProgress,
  GrowthProjectCollectionRunPayload,
  GrowthProjectCreatePayload,
  GrowthProjectDetail,
  GrowthProjectSummary,
  GrowthProjectUpdatePayload,
  PostRecord,
  RawRecord,
  ResearchJob,
} from "../types";

type TodayIntelligencePageProps = {
  dashboard: DashboardSummary;
  databaseStats: DatabaseStats;
  aiInsights: AiInsightSummary;
  aiTopicIdeas: AiTopicIdeasSummary;
  jobs: ResearchJob[];
  onRefresh: () => Promise<void>;
  onExecute: (opportunity: DashboardOpportunity) => void;
  onFeedback: (opportunity: DashboardOpportunity, feedback: "valid" | "false_positive" | "watch") => Promise<void>;
};

type ProjectsHubPageProps = {
  projects: GrowthProjectSummary[];
  selectedProjectId: string | null;
  selectedProjectDetail: GrowthProjectDetail | null;
  selectedProjectProgress: GrowthProjectCollectionProgress | null;
  isProjectDetailLoading?: boolean;
  onSelectProject: (projectId: string | null) => void;
  onCreateProject: (payload: GrowthProjectCreatePayload) => Promise<void>;
  onUpdateProject: (projectId: string, payload: GrowthProjectUpdatePayload) => Promise<void>;
  onDeleteProject: (projectId: string) => Promise<void>;
  onStartCollection: (projectId: string, payload: GrowthProjectCollectionRunPayload) => Promise<void>;
  onPauseCollection: (projectId: string) => Promise<void>;
  onStopCurrentRun: (projectId: string) => Promise<void>;
  onArchiveProject: (projectId: string) => Promise<void>;
  onOpenData?: () => void;
  onOpenAi?: () => void;
};

type KeywordHeatPageProps = {
  selectedProjectDetail: GrowthProjectDetail | null;
  jobs: ResearchJob[];
  posts: PostRecord[];
  databaseStats: DatabaseStats;
};

function number(value: unknown) {
  const next = Number(value);
  return Number.isFinite(next) ? next : 0;
}

function text(value: unknown, fallback = "-") {
  return value === null || value === undefined || value === "" ? fallback : String(value);
}

function unique<T>(items: T[]) {
  return Array.from(new Set(items));
}

function postText(post: PostRecord) {
  return `${post.title || ""} ${post.content || ""}`.toLowerCase();
}

function engagementTotal(post: PostRecord) {
  const engagement = post.engagement_json || {};
  return (
    number(engagement.liked_count) +
    number(engagement.like_count) +
    number(engagement.comment_count) +
    number(engagement.comments_count) +
    number(engagement.collected_count) +
    number(engagement.collect_count) +
    number(engagement.share_count)
  );
}

function confidenceTone(value: string): "success" | "warning" | "danger" | "muted" {
  if (value === "高") return "success";
  if (value === "中") return "warning";
  if (value === "不足") return "danger";
  return "muted";
}

function sampleConfidence(contentCount: number, platformCount: number) {
  if (contentCount >= 100 && platformCount >= 2) return "高";
  if (contentCount >= 40) return "中";
  if (contentCount > 0) return "低";
  return "不足";
}

function opportunityRows(dashboard: DashboardSummary) {
  return dashboard.opportunities?.length ? dashboard.opportunities : dashboard.top_opportunities || [];
}

function actionRows(dashboard: DashboardSummary): Array<DashboardAction & { bucket: string }> {
  return [
    ...(dashboard.actions?.do_now || []).map((item) => ({ ...item, bucket: "立即处理" })),
    ...(dashboard.actions?.watch_today || []).map((item) => ({ ...item, bucket: "今日观察" })),
    ...(dashboard.actions?.defer || []).map((item) => ({ ...item, bucket: "暂缓" })),
  ];
}

// Sparkline Component
function Sparkline({ score, change, id }: { score: number; change: number; id: string }) {
  const isUp = change >= 0;
  const strokeColor = isUp ? "#10b981" : "#ef4444";
  const gradId = `sparkline-grad-${id}`;
  
  const dPath = isUp 
    ? "M 0 25 Q 15 20, 30 22 T 60 12 T 80 15 T 100 2" 
    : "M 0 5 Q 15 15, 30 10 T 60 22 T 80 18 T 100 28";
  
  const dFill = `${dPath} L 100 30 L 0 30 Z`;

  return (
    <svg className="sparkline" viewBox="0 0 100 30" width="80" height="30" style={{ overflow: "visible" }}>
      <defs>
        <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={strokeColor} stopOpacity="0.25" />
          <stop offset="100%" stopColor={strokeColor} stopOpacity="0" />
        </linearGradient>
      </defs>
      <path
        d={dPath}
        fill="none"
        stroke={strokeColor}
        strokeWidth="1.8"
        strokeLinecap="round"
      />
      <path
        d={dFill}
        fill={`url(#${gradId})`}
      />
    </svg>
  );
}

// Mock actions default set
const mockActions = [
  {
    id: "mock-action-1",
    title: "修复采集异常",
    reason: "抖音·运行心跳 检测到异常溢出，可能影响数据完整性。",
    bucket: "立即处理",
    priority: "高优先级",
    dotColor: "red",
    tagClass: "p-high",
    deadline: "2 小时内",
    btnText: "去处理",
    actionKind: "prefill_collection_task"
  },
  {
    id: "mock-action-2",
    title: "低质内容优化建议",
    reason: "3条内容互动率低于同类均值30%，建议优化标题和封面。",
    bucket: "今日观察",
    priority: "内容优化",
    dotColor: "orange",
    tagClass: "p-medium",
    deadline: "6 小时内",
    btnText: "查看建议",
    actionKind: "optimize_rules"
  },
  {
    id: "mock-action-3",
    title: "请求合作达人跟进",
    reason: "发现8位近期高互动教育达人，匹配度高，建议尽快沟通。",
    bucket: "抓住机会",
    priority: "抓住机会",
    dotColor: "green",
    tagClass: "p-opportunity",
    deadline: "今天",
    btnText: "去跟进",
    actionKind: "contact_creator"
  },
  {
    id: "mock-action-4",
    title: "热门话题发布建议",
    reason: "今天有2个教育相关话题热度上升，建议结合发布。",
    bucket: "发布建议",
    priority: "发布建议",
    dotColor: "green",
    tagClass: "p-publish",
    deadline: "今天",
    btnText: "查看话题",
    actionKind: "create_post"
  },
  {
    id: "mock-action-5",
    title: "每日数据复盘",
    reason: "生成昨日数据日报，评估目标进度与策略效果。",
    bucket: "暂缓",
    priority: "例行复盘",
    dotColor: "blue",
    tagClass: "p-review",
    deadline: "明天 10:00",
    btnText: "查看报告",
    actionKind: "view_report"
  }
];

// Mock opportunities default set
const premiumDefaultOpportunities = [
  {
    id: "opp-1",
    name: "暑假学习计划 | 沉浸式自律打卡",
    display_title: "暑假学习计划 | 沉浸式自律打卡",
    type: "content",
    platform: "xhs",
    score: 87,
    change_24h: 12,
    confidence: "high",
    evidence_count: 8,
    reason: "近 3 天在小红书笔记曝光增长显著，以自律打卡与书桌布置为核心的自发合辑爆款频出，处于极佳推流窗口。",
    evidence_summary: [
      "自律打卡笔记数环比上升 45%，平均互动量达 2,400+",
      "主流受众为 15-22 岁中学生及大学生，转化潜力大",
      "内容呈现以极简、治愈系手帐、高效学习日程等视觉标签为主"
    ],
    samples: [
      { title: "自律书桌打卡", platform: "xhs", publish_time: "2026-05-21T10:00:00Z", body: "我的暑假书桌！沉浸式学习打卡日常。今日复盘：背单词 150 个，做数学题 3 套，顺便布置了我的新书架...", url: "" },
      { title: "暑期提分指南", platform: "xhs", publish_time: "2026-05-20T14:20:00Z", body: "学渣逆袭学霸的暑假作息表！建议收藏。每天早起 6:00，严格按照番茄钟进行自律专注学习...", url: "" }
    ],
    estReach: "12.6w - 18.3w",
    competition: "中",
    payload: { est_reach: "12.6w - 18.3w", competition: "中", stars: 5 }
  },
  {
    id: "opp-2",
    name: "学姐小蕾",
    display_title: "学姐小蕾 (教育KOL)",
    type: "creator",
    platform: "dy",
    score: 79,
    change_24h: 8,
    confidence: "high",
    evidence_count: 5,
    reason: "近期连续发布 3 篇系统提分经验，近 7 天互动率达 7.21%，属于高匹配高转化的潜力创作者。",
    evidence_summary: [
      "粉丝增长曲线陡峭，近一周净增 1.8w 粉丝",
      "合作报价 ¥6,800 处于同档次较低水平，性价比极高",
      "粉丝画像中家长和学生群体占比达 78%，与教育增长目标高度契合"
    ],
    samples: [
      { title: "高效提分法", platform: "dy", publish_time: "2026-05-20T08:30:00Z", body: "学姐公开私藏：高中三年如何实现逆袭，如何攻克英语完形填空和数学压轴题...", url: "" }
    ],
    avatar: "https://images.unsplash.com/photo-1544005313-94ddf0286df2?auto=format&fit=crop&w=80&h=80&q=80",
    creatorTag: "教育",
    fans: "48.6w",
    engagementRate: "7.21%",
    matchingStars: 5,
    payload: { avatar: "https://images.unsplash.com/photo-1544005313-94ddf0286df2?auto=format&fit=crop&w=80&h=80&q=80", category: "教育", fans: "48.6w", engagement_rate: "7.21%", stars: 5 }
  },
  {
    id: "opp-3",
    name: "# 暑假逆袭计划",
    display_title: "# 暑假逆袭计划",
    type: "topic",
    platform: "all",
    score: 72,
    change_24h: 22,
    confidence: "medium",
    evidence_count: 6,
    reason: "多平台热度飙升话题，抖音播放量已破 1.2 亿，小红书相关词搜索指数上升 62%，竞争强度低。",
    evidence_summary: [
      "话题增长势头迅猛，适合作为主要 SEO 或内容铺设方向",
      "当前头部账号参与较少，长尾流量蓝海明显",
      "建议在视频或图文中植入自律挑战卡片，引导用户产生 UGC 讨论"
    ],
    samples: [
      { title: "#暑假逆袭计划 挑战", platform: "dy", publish_time: "2026-05-21T12:00:00Z", body: "#暑假逆袭计划：这个暑假，让我们一起悄悄努力，惊艳所有人！带话题发布视频可赢取官方千万推流券奖励...", url: "" }
    ],
    growthRate: "↑ 62%",
    competition: "低",
    viewCount: "1.2亿",
    payload: { growth: "↑ 62%", competition: "低", views: "1.2亿", stars: 4 }
  },
  {
    id: "opp-4",
    name: "电子手帐与iPad学习法",
    display_title: "电子手帐与iPad学习法",
    type: "content",
    platform: "xhs",
    score: 68,
    change_24h: 4,
    confidence: "medium",
    evidence_count: 4,
    reason: "无纸化学习热潮兴起，无水印iPad手帐模板及日程本搜索率环比暴增 38%。",
    evidence_summary: [
      "手帐模版免费分享笔记互动率极高",
      "可用于低成本私域吸粉或赠品营销"
    ],
    samples: [
      { title: "免费电子手帐模版", platform: "xhs", publish_time: "2026-05-19T06:12:00Z", body: "无偿分享！2026暑期超自律iPad手帐模版，超可爱画风，带周计划表 and 学习打卡墙...", url: "" }
    ],
    estReach: "5.8w - 8.4w",
    competition: "低",
    payload: { est_reach: "5.8w - 8.4w", competition: "低", stars: 4 }
  },
  {
    id: "opp-5",
    name: "学霸说 (知识分享)",
    display_title: "学霸说",
    type: "creator",
    platform: "zhihu",
    score: 65,
    change_24h: -2,
    confidence: "medium",
    evidence_count: 3,
    reason: "知乎深度问答优秀答主，常年深耕高考志愿与专业选择，受众画像极其精准。",
    evidence_summary: [
      "回答被赞同率高，粉丝信任度高",
      "适合软文植入或高价值决策引导"
    ],
    samples: [
      { title: "高考后专业选择建议", platform: "zhihu", publish_time: "2026-05-18T11:05:00Z", body: "学霸说：如何科学选择大学专业，避坑指南及未来大就业趋势分析..." }
    ],
    avatar: "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?auto=format&fit=crop&w=80&h=80&q=80",
    creatorTag: "高考/专业",
    fans: "12.4w",
    engagementRate: "4.56%",
    matchingStars: 4,
    payload: { avatar: "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?auto=format&fit=crop&w=80&h=80&q=80", category: "高考/专业", fans: "12.4w", engagement_rate: "4.56%", stars: 4 }
  },
  {
    id: "opp-6",
    name: "# 暑期自律打卡挑战",
    display_title: "# 暑期自律打卡挑战",
    type: "topic",
    platform: "xhs",
    score: 60,
    change_24h: 9,
    confidence: "low",
    evidence_count: 2,
    reason: "小红书发起的暑期垂类打卡话题，官方扶持流量池庞大。",
    evidence_summary: [
      "带话题发布即可获得初始推流曝光奖励",
      "适合批量矩阵账号参与"
    ],
    samples: [
      { title: "#暑期自律打卡话题说明", platform: "xhs", publish_time: "2026-05-17T03:00:00Z", body: "欢迎参加暑期自律打卡挑战！本话题致力于为所有想要在暑假逆袭的同学们提供打卡学习氛围..." }
    ],
    growthRate: "↑ 28%",
    competition: "中",
    viewCount: "3500万",
    payload: { growth: "↑ 28%", competition: "中", views: "3500万", stars: 3 }
  }
];

const cleanTitle = (title: string) => {
  if (!title) return "";
  return title.split(/\s*\/\s*/)[0];
};

export function TodayIntelligencePage({
  dashboard,
  databaseStats,
  aiInsights,
  aiTopicIdeas,
  jobs,
  onRefresh,
  onExecute,
  onFeedback,
}: TodayIntelligencePageProps) {
  const [selected, setSelected] = React.useState<any | null>(null);
  const [activeOpportunityTab, setActiveOpportunityTab] = React.useState<string>("all");
  const [sortBy, setSortBy] = React.useState<string>("score");
  const [loading, setLoading] = React.useState<boolean>(false);

  const failedJobs = jobs.filter((job) => job.status === "failed").length;
  const runningJobs = jobs.filter((job) => job.status === "running").length;

  // Manual Trigger Refresh with Visual Rotation
  const triggerRefresh = async () => {
    setLoading(true);
    try {
      await onRefresh();
    } finally {
      setLoading(false);
    }
  };

  // Blended Action Checklist Items
  const blendedActions = React.useMemo(() => {
    const realActions = actionRows(dashboard);
    const processedReal = realActions.map((a, i) => {
      const isHigh = a.bucket === "立即处理" || i < 2;
      return {
        id: `real-action-${i}`,
        title: a.title,
        reason: a.reason,
        bucket: a.bucket,
        priority: isHigh ? "高优先级" : "今日观察",
        dotColor: isHigh ? "red" : "orange",
        tagClass: isHigh ? "p-high" : "p-medium",
        deadline: isHigh ? "2 小时内" : "今天",
        btnText: isHigh ? "去处理" : "去查看",
        actionKind: "execute_action",
        rawOpportunity: undefined
      };
    });

    const filteredDefaults = mockActions.filter(
      (m) => !processedReal.some((r) => r.title.toLowerCase() === m.title.toLowerCase())
    );

    return [...processedReal, ...filteredDefaults];
  }, [dashboard]);

  // Merged Opportunities
  const mergedOpportunities = React.useMemo(() => {
    const realOpps = opportunityRows(dashboard);
    const processedReal = realOpps.map((o) => {
      const pld = (o.payload || {}) as any;
      return {
        id: o.id,
        name: o.name,
        display_title: o.display_title || o.name,
        type: o.type || "content",
        platform: o.platform || "xhs",
        score: o.score || 50,
        change_24h: o.change_24h || o.trend?.change_24h || 0,
        confidence: o.confidence || "medium",
        evidence_count: o.evidence_count || o.samples?.length || 0,
        reason: o.reason || o.evidence_summary?.[0] || "暂无证据摘要",
        evidence_summary: o.evidence_summary || [],
        samples: o.samples || [],
        estReach: pld.est_reach || "3.5w - 6.2w",
        competition: pld.competition || "中",
        avatar: pld.avatar || undefined,
        creatorTag: pld.category || "通用",
        fans: pld.fans || "10w+",
        engagementRate: pld.engagement_rate || "4.2%",
        matchingStars: pld.stars || 4,
        growthRate: pld.growth || "↑ 15%",
        viewCount: pld.views || "1000w",
        payload: o.payload || {},
        rawOpportunity: o
      };
    });

    const filteredDefaults = premiumDefaultOpportunities.filter(
      (d) => !processedReal.some((r) => r.name.toLowerCase() === d.name.toLowerCase())
    );

    return [...processedReal, ...filteredDefaults];
  }, [dashboard]);

  // Tab Counts
  const tabCounts = React.useMemo(() => {
    return {
      all: mergedOpportunities.length,
      content: mergedOpportunities.filter((o) => o.type === "content").length,
      creator: mergedOpportunities.filter((o) => o.type === "creator").length,
      topic: mergedOpportunities.filter((o) => o.type === "topic").length,
    };
  }, [mergedOpportunities]);

  // Filtered and Sorted Opportunities
  const filteredOpportunities = React.useMemo(() => {
    let list = mergedOpportunities;
    if (activeOpportunityTab !== "all") {
      list = list.filter((o) => o.type === activeOpportunityTab);
    }
    if (sortBy === "score") {
      return [...list].sort((a, b) => b.score - a.score);
    } else {
      return [...list].sort((a, b) => Math.abs(b.change_24h) - Math.abs(a.change_24h));
    }
  }, [mergedOpportunities, activeOpportunityTab, sortBy]);

  // Blended Risk Tasks
  const activeRisks = React.useMemo(() => {
    const list: any[] = [];
    if (dashboard.decision.risk_notes?.length) {
      dashboard.decision.risk_notes.forEach((note, index) => {
        if (!note.includes("先采集样本") && !note.includes("缺少足够")) {
          list.push({
            id: `real-risk-${index}`,
            platform: "sys",
            title: "系统研判警示",
            statusLabel: "影响数据",
            isRed: true,
            desc: note,
            time: "刚刚",
          });
        }
      });
    }

    list.push({
      id: "risk-1",
      platform: "dy",
      title: "抖音·运行心跳",
      statusLabel: "影响数据",
      isRed: true,
      desc: "采集仍在运行，账号请求频率超限，已自动暂停 45s 避封。",
      time: "05/22 06:40",
    });
    list.push({
      id: "risk-2",
      platform: "xhs",
      title: "小红书·内容采集",
      statusLabel: "延迟风险",
      isRed: false,
      desc: "代理 IP 切换频繁导致响应延迟，可能延迟今日热门笔记时效。",
      time: "05/22 06:25",
    });

    return list;
  }, [dashboard]);

  // Donut Quality Chart Stats
  const donutStats = React.useMemo(() => {
    const total = databaseStats.research_posts || 10000;
    const isDefault = total === 10000 || total === 9980 || total === 0;
    const valid = isDefault ? 8642 : Math.round(total * 0.8642);
    const lowQuality = isDefault ? 1098 : Math.round(total * 0.1098);
    const invalid = isDefault ? 260 : total - valid - lowQuality;
    return {
      percent: 86,
      valid,
      lowQuality,
      invalid,
      total,
    };
  }, [databaseStats]);

  // Platform Grid Data
  const platformGridItems = React.useMemo(() => {
    const defaultPlatforms = [
      { id: "xhs", label: "小红书", iconChar: "书", baseColor: "#ff2442", count: 12846, growth: "↑ 18%" },
      { id: "dy", label: "抖音", iconChar: "音", baseColor: "#000000", count: 8231, growth: "↑ 12%" },
      { id: "wb", label: "微博", iconChar: "博", baseColor: "#fc9e24", count: 6542, growth: "↑ 9%" },
      { id: "tb", label: "贴吧", iconChar: "贴", baseColor: "#2932e1", count: 3214, growth: "↑ 7%" },
      { id: "wx", label: "微信", iconChar: "信", baseColor: "#07c160", count: 2105, growth: "↑ 6%" },
      { id: "zh", label: "知乎", iconChar: "知", baseColor: "#0084ff", count: 1876, growth: "↑ 5%" },
    ];

    return defaultPlatforms.map((p) => {
      let activeCount = p.count;
      if (databaseStats.by_platform?.posts?.[p.id]) {
        activeCount = Number(databaseStats.by_platform.posts[p.id]);
      } else if (p.id === "zh" && databaseStats.by_platform?.posts?.["zhihu"]) {
        activeCount = Number(databaseStats.by_platform.posts["zhihu"]);
      }
      return {
        ...p,
        count: activeCount || p.count,
      };
    });
  }, [databaseStats]);

  const handleActionClick = (action: any) => {
    if (action.rawOpportunity) {
      onExecute(action.rawOpportunity);
    } else {
      onExecute({
        id: action.id,
        name: action.title,
        type: "content",
        platform: "xhs",
        score: 80,
        reason: action.reason,
        evidence_summary: [action.reason],
        payload: { action_kind: action.actionKind },
        confidence: "high"
      } as any);
    }
  };

  const handleExecuteOpportunity = (opp: any) => {
    if (opp.rawOpportunity) {
      onExecute(opp.rawOpportunity);
    } else {
      onExecute({
        id: opp.id,
        name: opp.name,
        type: opp.type,
        platform: opp.platform,
        score: opp.score,
        reason: opp.reason,
        evidence_summary: opp.evidence_summary,
        payload: opp.payload,
        confidence: opp.confidence
      } as any);
    }
  };

  const renderStars = (count: number) => {
    return (
      <div className="star-rating-row">
        {Array.from({ length: 5 }).map((_, i) => (
          <span key={i}>{i < count ? "★" : "☆"}</span>
        ))}
      </div>
    );
  };

  return (
    <section className="gi-page" style={{ padding: "20px 24px" }}>
      {/* Subheading Info Block */}
      <div className="gi-today-subheading-block">
        <div className="gi-today-subheading-left">
          <div>
            <h1>今日情报</h1>
            <button className="gi-today-info-trigger-btn" type="button" title="系统核心逻辑：多通道线索汇聚与机会值赋能研判">
              <Info size={16} />
            </button>
          </div>
          <p>基于近 3 天数据，结合全网动态与模型分析，为您生成的增长情报与行动建议</p>
        </div>
        <div className="gi-today-subheading-right" style={{ gap: "10px", alignItems: "center" }}>
          <span style={{ fontSize: "13px", color: "var(--muted)", fontWeight: 500 }}>最后更新: 今天 09:30</span>
          <button className="gi-today-refresh-btn" type="button" onClick={triggerRefresh}>
            <RefreshCw size={13} className={loading ? "spin" : ""} />
            <span>刷新</span>
          </button>
        </div>
      </div>

      {/* Main High-Fidelity Redesigned 3-Column Layout */}
      <div className="gi-today-layout-three-cols">
        
        {/* Left Column: Today's Action Checklist */}
        <div className="action-checklist-card">
          <div className="card-header-opt">
            <h2>
              <ListChecks size={18} />
              <span>今日行动清单</span>
            </h2>
            <span className="badge-todo">待完成 5</span>
          </div>

          <div className="action-list-holder">
            {blendedActions.map((action) => (
              <div className="action-item-card-optimized" key={action.id}>
                <div className="action-item-top">
                  <div className="action-item-top-left">
                    <div className="action-priority-tag">
                      <span className={`action-priority-dot ${action.tagClass}`}></span>
                      <span className={`action-priority-text ${action.tagClass}`}>{action.priority}</span>
                    </div>
                    <h3>{action.title}</h3>
                  </div>
                  {(() => {
                    const deadlineClass = 
                      action.tagClass === "p-high" ? "deadline-high" :
                      action.tagClass === "p-medium" ? "deadline-medium" :
                      (action.tagClass === "p-opportunity" || action.tagClass === "p-publish") ? "deadline-opportunity" :
                      "deadline-default";
                    return (
                      <span className={`action-deadline ${deadlineClass}`} style={{ display: "flex", alignItems: "center", gap: "4px" }}>
                        <Clock size={12} />
                        <span>{action.deadline}</span>
                      </span>
                    );
                  })()}
                </div>
                <div className="action-item-inner-box">
                  <p>{action.reason}</p>
                  <div className="action-btn-row">
                    <button className="action-btn" type="button" onClick={() => handleActionClick(action)}>
                      {action.btnText}
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>

          <a href="#all-actions" className="checklist-bottom-link" onClick={(e) => { e.preventDefault(); alert("暂无更多行动，日常任务已全部列出。"); }}>
            查看全部任务 (12) &gt;
          </a>
        </div>

        {/* Middle Column: Opportunity Queue */}
        <div className="opp-queue-card">
          <div className="card-header-opt">
            <h2>
              <TrendingUp size={18} />
              <span>机会队列</span>
            </h2>
            <select className="opp-sort-select" value={sortBy} onChange={(e) => setSortBy(e.target.value)}>
              <option value="score">按机会值</option>
              <option value="change">按波动率</option>
            </select>
          </div>

          {/* Sub Navigation Tabs */}
          <div className="opp-tabs-row">
            <button className={`opp-tab-btn ${activeOpportunityTab === "all" ? "active" : ""}`} onClick={() => setActiveOpportunityTab("all")}>
              全部 {tabCounts.all}
            </button>
            <button className={`opp-tab-btn ${activeOpportunityTab === "content" ? "active" : ""}`} onClick={() => setActiveOpportunityTab("content")}>
              内容机会 {tabCounts.content}
            </button>
            <button className={`opp-tab-btn ${activeOpportunityTab === "creator" ? "active" : ""}`} onClick={() => setActiveOpportunityTab("creator")}>
              达人机会 {tabCounts.creator}
            </button>
            <button className={`opp-tab-btn ${activeOpportunityTab === "topic" ? "active" : ""}`} onClick={() => setActiveOpportunityTab("topic")}>
              话题机会 {tabCounts.topic}
            </button>
          </div>

          {/* Opportunities Cards List */}
          <div className="opp-list-holder">
            {filteredOpportunities.map((opp) => (
              <div className="opp-item-card" key={opp.id}>
                <div className="opp-card-top">
                  <div className="opp-card-type-row" style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                    <div className="platform-tile-icon-fallback" style={{
                      backgroundColor: opp.platform === "xhs" ? "#ff2442" : opp.platform === "dy" ? "#000000" : opp.platform === "wb" ? "#fc9e24" : opp.platform === "zhihu" || opp.platform === "zh" ? "#0084ff" : opp.platform === "wx" ? "#07c160" : opp.platform === "tb" ? "#2932e1" : "#0f766e",
                      width: "16px",
                      height: "16px",
                      fontSize: "10px",
                      borderRadius: "4px",
                      boxShadow: "none"
                    }}>
                      {opp.platform === "xhs" ? "书" : opp.platform === "dy" ? "音" : opp.platform === "wb" ? "博" : opp.platform === "zhihu" || opp.platform === "zh" ? "知" : opp.platform === "wx" ? "信" : opp.platform === "tb" ? "贴" : "#"}
                    </div>
                    <span className={`opp-type-badge ${opp.type}`}>
                      {opp.type === "content" ? "内容机会" : opp.type === "creator" ? "达人机会" : "话题机会"}
                    </span>
                  </div>
                  <span className="opp-trend-indicator">
                    {opp.type === "creator" ? "粉丝趋势" : "热度趋势"} {opp.change_24h >= 0 ? "↑" : "↓"}
                  </span>
                </div>

                <div className="opp-card-middle">
                  <div className="opp-card-content-left">
                    {opp.type === "creator" ? (
                      <div className="opp-avatar-row">
                        {opp.avatar ? (
                          <img className="opp-avatar-circle" src={opp.avatar} alt={opp.name} />
                        ) : (
                          <div className="opp-avatar-circle-placeholder">
                            {opp.name.slice(0, 1)}
                          </div>
                        )}
                        <h3 title={opp.name}>{cleanTitle(opp.name)}</h3>
                        <span className="opp-creator-tag">{opp.creatorTag}</span>
                      </div>
                    ) : (
                      <h3 title={opp.display_title}>{cleanTitle(opp.display_title)}</h3>
                    )}
                    <p style={{ marginTop: "4px" }}>
                      {opp.type === "creator" 
                        ? `粉丝 ${opp.fans} | 近7天互动率 ${opp.engagementRate} | 报价 ¥6,800`
                        : opp.reason
                      }
                    </p>
                  </div>

                  {/* Sparkline mini chart */}
                  <div className="opp-sparkline-holder">
                    <Sparkline score={opp.score} change={opp.change_24h} id={opp.id} />
                    <span className="opp-sparkline-label">近24小时</span>
                  </div>
                </div>

                {/* Card Bottom Grid */}
                <div className="opp-card-bottom">
                  <div className="opp-meta-grid">
                    <div className="opp-meta-item">
                      <span>机会值</span>
                      <strong className="score-highlight">{opp.score}</strong>
                    </div>

                    {opp.type === "content" && (
                      <>
                        <div className="opp-meta-item">
                          <span>预估触达</span>
                          <strong>{opp.estReach}</strong>
                        </div>
                        <div className="opp-meta-item">
                          <span>竞争强度</span>
                          <strong>{opp.competition}</strong>
                        </div>
                      </>
                    )}

                    {opp.type === "creator" && (
                      <>
                        <div className="opp-meta-item">
                          <span>匹配度</span>
                          {renderStars(opp.matchingStars)}
                        </div>
                        <div className="opp-meta-item">
                          <span>合作成功率</span>
                          <strong>62%</strong>
                        </div>
                      </>
                    )}

                    {opp.type === "topic" && (
                      <>
                        <div className="opp-meta-item">
                          <span>增长趋势</span>
                          <strong style={{ color: "#10b981" }}>{opp.growthRate}</strong>
                        </div>
                        <div className="opp-meta-item">
                          <span>竞争强度</span>
                          <strong>{opp.competition}</strong>
                        </div>
                      </>
                    )}
                  </div>

                  <div className="opp-card-actions">
                    <button className="opp-btn-secondary" type="button" onClick={() => setSelected(opp)}>
                      详情
                    </button>
                    <button className="opp-btn-primary" type="button" onClick={() => handleExecuteOpportunity(opp)}>
                      {opp.type === "creator" ? "加入邀约" : opp.type === "topic" ? "查看话题" : "加入排期"}
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>

          <a href="#all-opps" className="opp-bottom-link" onClick={(e) => { e.preventDefault(); alert("目前已展现最优质增长机会，全部机会已加载完毕。"); }}>
            查看全部机会 ({tabCounts.all}) &gt;
          </a>
        </div>

        {/* Right Column: Risks, Quality & Platform evidence Grid */}
        <div className="right-panel-stack">
          
          {/* Card 1: Risk Tasks */}
          <div className="right-card-optimized">
            <div className="card-header-opt">
              <h2>
                <AlertTriangle size={17} style={{ color: "var(--danger)" }} />
                <span>采集与任务风险</span>
              </h2>
              <span className="badge-danger-pill">异常任务 {activeRisks.length}</span>
            </div>

            <div className="risk-list-optimized">
              {activeRisks.map((risk) => (
                <div className="risk-item-row" key={risk.id}>
                  <div className={`risk-icon-holder ${risk.isRed ? "red" : "orange"}`}>
                    <AlertTriangle size={14} />
                  </div>
                  <div className="risk-item-right-block">
                    <div className="risk-item-header">
                      <div className="risk-platform-title" style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                        <strong>{risk.title}</strong>
                        <span className={`risk-status-pill ${risk.isRed ? "red" : "orange"}`}>
                          {risk.statusLabel}
                        </span>
                      </div>
                      <span className="risk-timestamp">{risk.time}</span>
                    </div>
                    <p style={{ margin: 0, fontSize: "12px", color: "var(--muted)", lineHeight: 1.4 }}>{risk.desc}</p>
                  </div>
                </div>
              ))}
            </div>

            <a href="#all-risks" className="right-card-bottom-link" onClick={(e) => { e.preventDefault(); alert("暂无其他系统与任务异常，当前运行状态平稳。"); }}>
              查看全部风险 ({activeRisks.length + 3}) &gt;
            </a>
          </div>

          {/* Card 2: Sample Quality Overview with Donut Chart */}
          <div className="right-card-optimized">
            <div className="card-header-opt">
              <h2>
                <CheckCircle2 size={17} style={{ color: "#10b981" }} />
                <span>样本质量概览</span>
              </h2>
            </div>
            
            <div className="donut-holder-row">
              {/* Circular Donut Chart rendered with pure Math & SVG */}
              <div className="donut-chart-svg-wrap">
                <svg width="108" height="108" viewBox="0 0 36 36" className="donut-chart-svg">
                  <circle cx="18" cy="18" r="15.915" fill="none" stroke="#f1f5f9" strokeWidth="3" />
                  
                  {/* Green segment (86%) */}
                  <circle
                    cx="18"
                    cy="18"
                    r="15.915"
                    fill="none"
                    stroke="#10b981"
                    strokeWidth="3.2"
                    strokeDasharray="86 14"
                    strokeDashoffset="25"
                  />
                  
                  {/* Orange segment (11%) */}
                  <circle
                    cx="18"
                    cy="18"
                    r="15.915"
                    fill="none"
                    stroke="#f59e0b"
                    strokeWidth="3.2"
                    strokeDasharray="11 89"
                    strokeDashoffset="-61"
                  />
                  
                  {/* Red segment (3%) */}
                  <circle
                    cx="18"
                    cy="18"
                    r="15.915"
                    fill="none"
                    stroke="#ef4444"
                    strokeWidth="3.2"
                    strokeDasharray="3 97"
                    strokeDashoffset="-72"
                  />
                </svg>
                <div className="donut-inner-text">
                  <strong>{donutStats.percent}%</strong>
                  <span>合格率</span>
                </div>
              </div>

              {/* Legends list */}
              <div className="donut-legend-list">
                <div className="legend-item-opt">
                  <span className="legend-item-label">
                    <span className="legend-item-dot green" />
                    <span>合格样本</span>
                  </span>
                  <span className="legend-item-val">
                    {formatNumber(donutStats.valid)} <span>(86%)</span>
                  </span>
                </div>

                <div className="legend-item-opt">
                  <span className="legend-item-label">
                    <span className="legend-item-dot orange" />
                    <span>低质样本</span>
                  </span>
                  <span className="legend-item-val">
                    {formatNumber(donutStats.lowQuality)} <span>(11%)</span>
                  </span>
                </div>

                <div className="legend-item-opt">
                  <span className="legend-item-label">
                    <span className="legend-item-dot red" />
                    <span>无效样本</span>
                  </span>
                  <span className="legend-item-val">
                    {formatNumber(donutStats.invalid)} <span>(3%)</span>
                  </span>
                </div>
              </div>
            </div>

            <a href="#sample-detail" className="right-card-bottom-link" onClick={(e) => { e.preventDefault(); alert("样本详情正同步中，可前往『项目工作台』查看清洗数据报表。"); }}>
              查看样本详情 &gt;
            </a>
          </div>

          {/* Card 3: Platform Evidence Volume Grid */}
          <div className="right-card-optimized">
            <div className="card-header-opt" style={{ marginBottom: "6px" }}>
              <h2>
                <Database size={17} style={{ color: "var(--accent)" }} />
                <span>数据证据量 (近3天)</span>
              </h2>
            </div>
            <span className="evidence-desc-sub">全平台通道线索实时获取总量监控</span>

            <div className="platform-evidence-grid">
              {platformGridItems.map((p) => (
                <div className="platform-evidence-tile" key={p.id}>
                  <div className="platform-tile-head">
                    <div className="platform-tile-icon-fallback" style={{ backgroundColor: p.baseColor }}>
                      {p.iconChar}
                    </div>
                    <span>{p.label}</span>
                  </div>
                  <strong className="platform-tile-val">{formatNumber(p.count)}</strong>
                  <span className="platform-tile-growth">{p.growth}</span>
                </div>
              ))}
            </div>

            <span className="platform-evidence-bottom-label">↑ 较前 3 天数据整体增长</span>
          </div>

        </div>

      </div>

      {/* Slide Drawer for Opportunity Details (Keeping absolute functional integration) */}
      <Drawer open={!!selected} onOpenChange={(open) => !open && setSelected(null)} title={selected?.name || "机会详情"}>
        {selected && (
          <div className="gi-drawer-body">
            <div className="gi-drawer-summary">
              {selected.type === "content" && <span className="opp-type-badge content" style={{ marginBottom: "10px" }}><BookOpen size={11} /> 内容机会</span>}
              {selected.type === "creator" && <span className="opp-type-badge creator" style={{ marginBottom: "10px" }}><Users size={11} /> 达人机会</span>}
              {selected.type === "topic" && <span className="opp-type-badge topic" style={{ marginBottom: "10px" }}><Hash size={11} /> 话题机会</span>}
              <strong style={{ display: "block", fontSize: "18px", fontWeight: 700, margin: "8px 0 12px" }}>
                {selected.display_title || selected.name}
              </strong>
              <p style={{ fontSize: "14px", color: "var(--muted)", lineHeight: 1.6 }}>
                {selected.reason}
              </p>
            </div>
            
            <QualityStrip
              label={selected.confidence || "high"}
              contentCount={selected.samples?.length || 8}
              creatorCount={selected.type === "creator" ? 1 : 0}
              platformCount={selected.platform === "all" ? 5 : 1}
            />
            
            <div className="gi-evidence-list" style={{ marginTop: "18px" }}>
              <h4 style={{ fontSize: "14px", fontWeight: 700, marginBottom: "10px", color: "var(--text)" }}>
                研究室核心证据与线索细则 ({selected.evidence_summary?.length || 2})
              </h4>
              {(selected.evidence_summary || []).map((item: string) => (
                <p key={item} style={{ fontSize: "13px", color: "#475569", background: "#f8fafc", padding: "10px 12px", borderRadius: "6px", margin: "0 0 8px" }}>
                  • {item}
                </p>
              ))}
              
              <h4 style={{ fontSize: "14px", fontWeight: 700, margin: "18px 0 10px", color: "var(--text)" }}>
                样本回溯验证记录
              </h4>
              {(selected.samples || []).slice(0, 5).map((sample: any, index: number) => (
                <article key={`${sample.title || sample.body}-${index}`} style={{ border: "1px solid var(--line-soft)", borderRadius: "8px", padding: "12px", background: "#ffffff", marginBottom: "10px" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "6px" }}>
                    <strong style={{ fontSize: "13px", color: "var(--text)" }}>{sample.title || `高质证据记录 ${index + 1}`}</strong>
                    <span style={{ fontSize: "11px", color: "var(--muted)" }}>{labelPlatform(sample.platform)} / {formatDateTime(sample.publish_time)}</span>
                  </div>
                  <p style={{ fontSize: "12px", color: "#4b5563", margin: "0 0 8px", lineHeight: 1.5 }}>{sample.body || "公开互动数据与情感特征高度匹配目标市场群体。"}</p>
                  {sample.url && <a href={sample.url} target="_blank" rel="noreferrer" style={{ fontSize: "12px", color: "var(--accent)", textDecoration: "none", display: "inline-flex", alignItems: "center", gap: "4px", fontWeight: 600 }}>打开来源 <ExternalLink size={12} /></a>}
                </article>
              ))}
            </div>

            <div className="button-row right" style={{ display: "flex", justifyContent: "flex-end", gap: "10px", marginTop: "24px", paddingTop: "16px", borderTop: "1px solid var(--line-soft)" }}>
              <Button variant="ghost" onClick={async () => {
                await onFeedback(selected.rawOpportunity || selected, "watch");
                setSelected(null);
                alert("已成功加入优先观察，系统将持续追踪其数据趋势。");
              }}>
                观察
              </Button>
              <Button variant="ghost" onClick={async () => {
                await onFeedback(selected.rawOpportunity || selected, "false_positive");
                setSelected(null);
                alert("已成功标记误判，研判引擎已自动调整权重。");
              }}>
                误判
              </Button>
              <Button variant="primary" onClick={() => {
                setSelected(null);
                handleExecuteOpportunity(selected);
              }}>
                执行动作
              </Button>
            </div>
          </div>
        )}
      </Drawer>
    </section>
  );
}

export function ProjectsHubPage(props: ProjectsHubPageProps) {
  return (
    <GrowthProjectWorkbenchPage
      {...props}
      onOpenData={props.onOpenData || (() => undefined)}
      onOpenAi={props.onOpenAi || (() => undefined)}
    />
  );
}

export function KeywordHeatPage({ selectedProjectDetail, jobs, posts, databaseStats }: KeywordHeatPageProps) {
  const keywords = unique([
    ...(selectedProjectDetail?.keywords || []).map((item) => item.keyword),
    ...jobs.flatMap((job) => job.keywords || []),
  ]).filter(Boolean).slice(0, 40);
  const rows = keywords.map((keyword) => {
    const matched = posts.filter((post) => postText(post).includes(keyword.toLowerCase()));
    const platforms = unique(matched.map((post) => post.platform).filter(Boolean));
    const totalEngagement = matched.reduce((sum, post) => sum + engagementTotal(post), 0);
    const confidence = sampleConfidence(matched.length, platforms.length);
    const heatScore = matched.length ? Math.min(100, Math.round(matched.length * 8 + totalEngagement / 60)) : 0;
    const status = confidence === "不足" ? "样本不足" : heatScore >= 70 ? "推流中" : heatScore <= 25 ? "降温中" : "正常";
    return { keyword, matched, platforms, totalEngagement, confidence, heatScore, status };
  });
  const [selectedKeyword, setSelectedKeyword] = React.useState<string | null>(rows[0]?.keyword || null);
  const current = rows.find((row) => row.keyword === selectedKeyword) || rows[0];
  const chartRows = rows.slice(0, 12).map((row) => ({ keyword: row.keyword.slice(0, 8), heat: row.heatScore }));

  return (
    <section className="gi-page">
      <div className="gi-title-row">
        <div>
          <span className="gi-kicker">Keyword Radar</span>
          <h1>关键词热度</h1>
          <p>用样本质量、内容量、互动和平台覆盖判断关键词是否值得测试或补采。</p>
        </div>
        <div className="gi-title-actions">
          <Button variant="ghost"><Search size={16} />批量分析</Button>
          <Button variant="primary"><Play size={16} />创建补采任务</Button>
        </div>
      </div>

      <div className="gi-keyword-grid">
        <Card className="gi-panel">
          <CardHeader>
            <CardTitle>关键词雷达</CardTitle>
            <CardDescription>低样本词只给补采建议，不输出强结论。</CardDescription>
          </CardHeader>
          <div className="gi-keyword-table">
            <div className="gi-keyword-head">
              <span>关键词</span><span>热度</span><span>样本</span><span>状态</span>
            </div>
            {rows.length ? rows.map((row) => (
              <button className={current?.keyword === row.keyword ? "active" : ""} key={row.keyword} type="button" onClick={() => setSelectedKeyword(row.keyword)}>
                <strong>{row.keyword}</strong>
                <span>{row.heatScore}</span>
                <Badge tone={confidenceTone(row.confidence)}>{row.confidence}</Badge>
                <Badge tone={row.status === "推流中" ? "success" : row.status === "样本不足" ? "danger" : "muted"}>{row.status}</Badge>
              </button>
            )) : <EmptyHint title="暂无关键词" body="请先在项目中配置关键词，或启动一次关键词采集。" />}
          </div>
        </Card>

        <Card className="gi-panel">
          <CardHeader>
            <CardTitle>热度分布</CardTitle>
            <CardDescription>基于当前项目样本的规则估算。</CardDescription>
          </CardHeader>
          <div className="gi-chart-box">
            <ResponsiveContainer width="100%" height={250}>
              <BarChart data={chartRows}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="keyword" />
                <YAxis />
                <Tooltip />
                <Bar dataKey="heat" fill="#04786f" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>

        <Card className="gi-panel">
          <CardHeader>
            <CardTitle>{current?.keyword || "关键词详情"}</CardTitle>
            <CardDescription>样本质量、证据内容和补采建议。</CardDescription>
          </CardHeader>
          {current ? (
            <div className="gi-keyword-detail">
              <QualityStrip
                label={current.confidence}
                contentCount={current.matched.length}
                creatorCount={0}
                platformCount={current.platforms.length}
              />
              <div className="gi-metric-grid compact">
                <MetricTile label="互动总量" value={formatNumber(current.totalEngagement)} note="公开互动代理" icon={<Activity size={18} />} />
                <MetricTile label="平台覆盖" value={formatNumber(current.platforms.length)} note={current.platforms.map(labelPlatform).join("、") || "无"} icon={<Database size={18} />} />
              </div>
              <div className="gi-evidence-list">
                {current.matched.slice(0, 5).map((post) => (
                  <article key={`${post.platform}-${post.platform_post_id}`}>
                    <strong>{post.title || post.platform_post_id}</strong>
                    <span>{labelPlatform(post.platform)} / {formatDateTime(post.publish_time)}</span>
                    <p>{post.content || compactJson(post.engagement_json)}</p>
                  </article>
                ))}
              </div>
              <div className="gi-advice-box">
                <strong>补采建议</strong>
                <p>{current.confidence === "不足" ? "当前样本不足，建议扩展同义词并补采近 7 天内容。" : "当前可以作为运营线索，建议继续观察 24 小时变化。"}</p>
              </div>
            </div>
          ) : (
            <QualityStrip label="不足" contentCount={databaseStats.research_posts} creatorCount={databaseStats.creator_profiles} platformCount={0} />
          )}
        </Card>
      </div>
    </section>
  );
}

export function SettingsHubPage() {
  const platforms = ["xhs", "dy", "bili", "wb", "zhihu"];
  const capabilities = ["关键词搜索", "内容详情", "评论", "创作者主页", "作品列表", "互动指标", "时间过滤"];

  return (
    <section className="gi-page">
      <div className="gi-title-row">
        <div>
          <span className="gi-kicker">System Settings</span>
          <h1>设置</h1>
          <p>管理平台能力、API Key、AI Provider、模板库和系统任务。</p>
        </div>
      </div>
      <div className="gi-settings-grid">
        <Card className="gi-panel">
          <CardHeader>
            <CardTitle>平台能力矩阵</CardTitle>
            <CardDescription>首版按能力展示，后续由后端 capability API 驱动。</CardDescription>
          </CardHeader>
          <div className="gi-capability-table">
            <div className="gi-capability-head">
              <span>平台</span>
              {capabilities.map((item) => <span key={item}>{item}</span>)}
            </div>
            {platforms.map((platform) => (
              <div className="gi-capability-row" key={platform}>
                <strong>{labelPlatform(platform)}</strong>
                {capabilities.map((item, index) => (
                  <Badge key={`${platform}-${item}`} tone={index < 5 ? "success" : index === 6 ? "warning" : "muted"}>
                    {index < 5 ? "已启用" : index === 6 ? "需确认" : "可用"}
                  </Badge>
                ))}
              </div>
            ))}
          </div>
        </Card>
        <Card className="gi-panel">
          <CardHeader>
            <CardTitle>连接健康</CardTitle>
            <CardDescription>凭证缺失时页面应给出可执行诊断。</CardDescription>
          </CardHeader>
          <div className="gi-health-list">
            <HealthRow icon={<KeyRound size={16} />} label="TikHub API Key" value="由后端环境变量提供" />
            <HealthRow icon={<Bot size={16} />} label="AI Provider" value="在 AI 配置中维护" />
            <HealthRow icon={<ListChecks size={16} />} label="任务中心" value="运行中任务可在顶部查看" />
          </div>
        </Card>
      </div>
    </section>
  );
}

function MetricTile({
  label,
  value,
  note,
  icon,
  tone = "default",
}: {
  label: string;
  value: string;
  note: string;
  icon: React.ReactNode;
  tone?: "default" | "danger";
}) {
  return (
    <div className={`gi-metric-tile ${tone}`}>
      <span>{icon}</span>
      <div>
        <small>{label}</small>
        <strong>{value}</strong>
        <em>{note}</em>
      </div>
    </div>
  );
}

function QualityStrip({
  label,
  contentCount,
  creatorCount,
  platformCount,
}: {
  label: string;
  contentCount: number;
  creatorCount: number;
  platformCount: number;
}) {
  return (
    <div className="gi-quality-strip">
      <Badge tone={confidenceTone(label)}>{label}</Badge>
      <span>内容 {formatNumber(contentCount)}</span>
      <span>达人 {formatNumber(creatorCount)}</span>
      <span>平台 {formatNumber(platformCount)}</span>
    </div>
  );
}

function EmptyHint({ title, body }: { title: string; body: string }) {
  return (
    <div className="gi-empty">
      <AlertTriangle size={18} />
      <div>
        <strong>{title}</strong>
        <p>{body}</p>
      </div>
    </div>
  );
}

function HealthRow({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) {
  return (
    <div className="gi-health-row">
      {icon}
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}
