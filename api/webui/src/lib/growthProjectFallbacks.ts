import { labelPlatform } from "../utils/format";
import type {
  AiInsightSummary,
  DashboardSummary,
  DatabaseStats,
  GrowthProjectCollectionProgress,
  GrowthProjectDetail,
  GrowthProjectSummary,
} from "../types";

export const fallbackDashboard = (): DashboardSummary => ({
  decision: {
    headline: "暂无机会判断",
    confidence: "low",
    sample_status: "insufficient",
    sample_summary: "缺少足够样本，系统不会生成假结论。",
    risk_notes: ["先采集样本后再生成机会判断。"],
    evidence_count: 0,
  },
  actions: { do_now: [], watch_today: [], defer: [] },
  monitoring: {
    running_jobs: 0,
    today_collected: 0,
    errors: 0,
    monitor_pools: 0,
    realtime_jobs: 0,
    last_updated_at: null,
  },
  opportunities: [],
  top_opportunities: [],
  watchlist: [],
  ignored_opportunities: [],
  diagnostics: [
    {
      code: "no_data",
      title: "暂无机会判断",
      body: "缺少样本时，系统只显示诊断，不生成假结论。",
    },
  ],
  scoring_profile: {
    weights: {
      heat_growth: 0.35,
      sample_confidence: 0.25,
      competition_gap: 0.2,
      actionability: 0.2,
    },
    window: "7d_plus_24h",
  },
});

export const fallbackDatabaseStats = (): DatabaseStats => ({
  total_collected: 0,
  research_posts: 0,
  research_comments: 0,
  raw_records: 0,
  creator_profiles: 0,
  entity_tags: 0,
  creator_candidates: 0,
  by_platform: { posts: {}, comments: {}, raw_records: {} },
  raw_platform_tables: {},
  raw_platform_totals: {},
});

export const fallbackAiInsights = (): AiInsightSummary => ({
  run: null,
  hotspots: [],
  topic_ideas: [],
});

export const MOCK_GROWTH_PROJECTS: GrowthProjectSummary[] = [
  {
    id: "pet-food-growth",
    name: "宠物主粮增长研究",
    primary_goal: "keyword_expansion",
    platforms: ["dy", "xhs", "wb", "bili"],
    status: "running",
    sample_status: { kind: "ready_for_insight", label: "样本够用，可生成洞察", project_state: "deeply_analyzable" },
    recommended_action: { kind: "generate_insight", label: "生成洞察" },
    opportunity_score: 82,
    last_collected_at: "2026-05-22T05:40:00Z",
    metrics: {
      jobs: 4,
      posts: 136842,
      comments: 684210,
      raw_records: 200000,
      creators: 2450,
      failed_jobs: 0,
      running_jobs: 1,
      pending_jobs: 0,
    },
    job_ids: [101, 102, 103, 104],
  },
  {
    id: "sunscreen-monitor",
    name: "防晒品类社媒洞察",
    primary_goal: "keyword_expansion",
    platforms: ["xhs", "dy"],
    status: "running",
    sample_status: { kind: "ready_for_insight", label: "样本够用，可生成洞察", project_state: "deeply_analyzable" },
    recommended_action: { kind: "generate_insight", label: "生成洞察" },
    opportunity_score: 75,
    last_collected_at: "2026-05-22T05:20:00Z",
    metrics: {
      jobs: 2,
      posts: 42000,
      comments: 120000,
      raw_records: 80000,
      creators: 850,
      failed_jobs: 0,
      running_jobs: 0,
      pending_jobs: 0,
    },
    job_ids: [105, 106],
  },
  {
    id: "coffee-brand-voice",
    name: "咖啡品牌声量监控",
    primary_goal: "keyword_expansion",
    platforms: ["xhs", "dy", "wb"],
    status: "paused",
    sample_status: { kind: "collecting", label: "已暂停", project_state: "collecting" },
    recommended_action: { kind: "start_collection", label: "开始采集" },
    opportunity_score: 60,
    last_collected_at: "2026-05-21T23:10:00Z",
    metrics: {
      jobs: 3,
      posts: 15000,
      comments: 45000,
      raw_records: 30000,
      creators: 420,
      failed_jobs: 1,
      running_jobs: 0,
      pending_jobs: 0,
    },
    job_ids: [107],
  },
  {
    id: "baby-care-competitor",
    name: "母婴用品竞品分析",
    primary_goal: "competitor_monitoring",
    platforms: ["xhs", "dy"],
    status: "running",
    sample_status: { kind: "ready_for_insight", label: "样本够用", project_state: "deeply_analyzable" },
    recommended_action: { kind: "generate_insight", label: "生成洞察" },
    opportunity_score: 85,
    last_collected_at: "2026-05-21T18:33:00Z",
    metrics: {
      jobs: 2,
      posts: 73000,
      comments: 219000,
      raw_records: 120000,
      creators: 1100,
      failed_jobs: 0,
      running_jobs: 1,
      pending_jobs: 0,
    },
    job_ids: [108],
  },
  {
    id: "smart-home-needs",
    name: "智能家居用户需求研究",
    primary_goal: "creator_discovery",
    platforms: ["xhs", "bili"],
    status: "running",
    sample_status: { kind: "collecting", label: "采集中", project_state: "collecting" },
    recommended_action: { kind: "start_collection", label: "开始采集" },
    opportunity_score: 72,
    last_collected_at: "2026-05-21T16:05:00Z",
    metrics: {
      jobs: 2,
      posts: 31000,
      comments: 93000,
      raw_records: 50000,
      creators: 680,
      failed_jobs: 0,
      running_jobs: 0,
      pending_jobs: 0,
    },
    job_ids: [109],
  },
  {
    id: "618-campaign-track",
    name: "618大促话题追踪",
    primary_goal: "mixed_research",
    platforms: ["dy", "xhs", "wb"],
    status: "planned",
    sample_status: { kind: "collecting", label: "计划中", project_state: "sample_insufficient" },
    recommended_action: { kind: "start_collection", label: "开始采集" },
    opportunity_score: null,
    last_collected_at: "2026-05-20T14:22:00Z",
    metrics: {
      jobs: 1,
      posts: 0,
      comments: 0,
      raw_records: 0,
      creators: 0,
      failed_jobs: 0,
      running_jobs: 0,
      pending_jobs: 0,
    },
    job_ids: [110],
  },
  {
    id: "sports-nutrition",
    name: "运动营养品内容洞察",
    primary_goal: "topic_discovery",
    platforms: ["dy", "xhs", "bili"],
    status: "running",
    sample_status: { kind: "collecting", label: "采集中", project_state: "collecting" },
    recommended_action: { kind: "start_collection", label: "开始采集" },
    opportunity_score: 68,
    last_collected_at: "2026-05-20T11:47:00Z",
    metrics: {
      jobs: 3,
      posts: 56000,
      comments: 168000,
      raw_records: 90000,
      creators: 890,
      failed_jobs: 0,
      running_jobs: 1,
      pending_jobs: 0,
    },
    job_ids: [111],
  },
  {
    id: "makeup-ingredients",
    name: "美妆成分趋势洞察",
    primary_goal: "topic_discovery",
    platforms: ["xhs", "dy", "wb"],
    status: "completed",
    sample_status: { kind: "ready_for_insight", label: "已完成", project_state: "deeply_analyzable" },
    recommended_action: { kind: "generate_insight", label: "已完成" },
    opportunity_score: 95,
    last_collected_at: "2026-05-19T09:32:00Z",
    metrics: {
      jobs: 3,
      posts: 100000,
      comments: 300000,
      raw_records: 150000,
      creators: 1800,
      failed_jobs: 0,
      running_jobs: 0,
      pending_jobs: 0,
    },
    job_ids: [112],
  },
];

export const generateMockDetail = (
  projectId: string,
  existing: GrowthProjectSummary | null,
): GrowthProjectDetail => {
  const project =
    MOCK_GROWTH_PROJECTS.find((p) => p.id === projectId) || existing || MOCK_GROWTH_PROJECTS[0];
  return {
    project,
    status_bar: {
      recommended_action: project.recommended_action.label,
      sample_status: project.sample_status.label,
      opportunity_score: project.opportunity_score,
    },
    overview: {
      current_judgment: `当前项目数据进展${project.status === "completed" ? "正常完成" : "持续采集中"}，有效率稳定。`,
      recommended_actions: [project.recommended_action],
      sample_status: project.sample_status,
      collection_health: project.metrics,
    },
    ai_insights: {
      summary:
        projectId === "pet-food-growth"
          ? "宠物主粮市场正处于功能性升级与天然无谷品类爆发期。猫粮品类中冻干添加与多肉无谷成为主流卖点；狗粮品类中，肠胃调理与低敏配方声量增速显著。建议加强针对“幼猫粮”“无谷粮”的定向追踪。"
          : `基于对 ${project.name} 项目的社媒采集，发现各平台讨论度稳步增长，受众群体表现出明确的细分趋势。`,
      missing_data: [],
    },
    sample_data: {
      posts: project.metrics.posts,
      comments: project.metrics.comments,
      creators: project.metrics.creators,
      raw_records: project.metrics.raw_records,
    },
    keywords:
      projectId === "pet-food-growth"
        ? [
            { keyword: "主粮", type: "core", source: "scene_pack" },
            { keyword: "猫粮", type: "core", source: "scene_pack" },
            { keyword: "狗粮", type: "core", source: "scene_pack" },
            { keyword: "冻干粮", type: "core", source: "scene_pack" },
            { keyword: "天然粮", type: "core", source: "scene_pack" },
            { keyword: "试用装", type: "excluded", source: "manual" },
            { keyword: "免费领", type: "excluded", source: "manual" },
            { keyword: "抽奖", type: "excluded", source: "manual" },
            { keyword: "领养", type: "excluded", source: "manual" },
            { keyword: "公益", type: "excluded", source: "manual" },
            { keyword: "猫咪日常", type: "expanded", source: "scene_pack" },
            { keyword: "狗狗干饭日常", type: "expanded", source: "scene_pack" },
            { keyword: "宠物主粮推荐", type: "expanded", source: "scene_pack" },
            { keyword: "新手养宠", type: "expanded", source: "scene_pack" },
          ]
        : [
            { keyword: "核心讨论词", type: "core", source: "scene_pack" },
            { keyword: "排除广告词", type: "excluded", source: "manual" },
            { keyword: "相关扩展词", type: "expanded", source: "scene_pack" },
          ],
    collection_records: project.platforms.map((plat, idx) => ({
      id: idx + 301,
      name: `${labelPlatform(plat)}抓取记录`,
      platforms: [plat],
      collection_mode: "keyword",
      keywords: ["核心词"],
      status: project.status === "completed" ? "completed" : "running",
      posts: Math.round(project.metrics.posts / project.platforms.length),
      comments: Math.round(project.metrics.comments / project.platforms.length),
      raw_records: Math.round(project.metrics.raw_records / project.platforms.length),
      updated_at: project.last_collected_at || new Date().toISOString(),
    })),
    settings: {
      primary_goal: project.primary_goal,
      platforms: project.platforms,
      scene_pack_id: 1,
      comment_collection_enabled: true,
      refresh_cadence: project.status === "paused" ? "off" : "daily",
      custom_interval_value: null,
      custom_interval_unit: null,
      daily_collection_limit_per_platform: 50,
    },
  };
};

export const generateMockProgress = (
  projectId: string,
): GrowthProjectCollectionProgress => {
  const project =
    MOCK_GROWTH_PROJECTS.find((p) => p.id === projectId) || MOCK_GROWTH_PROJECTS[0];
  const postsCount = project.metrics.posts;
  return {
    project_id: projectId,
    status:
      project.status === "paused"
        ? "idle"
        : project.status === "completed"
          ? "completed"
          : "running",
    current_job_id: 201,
    running_job_id: 201,
    queued_jobs: [],
    queue: {
      running_job_id: null,
      queued_jobs: [],
      queue_length: 0,
    },
    progress: {
      percent: project.status === "completed" ? 100 : 68,
      sample_percent: project.status === "completed" ? 100 : 68,
      step_percent: project.status === "completed" ? 100 : 68,
      unit_counts: {},
      sample_counts: {
        posts: postsCount || 136842,
        comments: (postsCount || 136842) * 5,
        raw_records: Math.round((postsCount || 136842) * 1.5),
        creators: Math.round((postsCount || 136842) * 0.02),
      },
      target_counts: {
        posts: 200000,
      },
      latest_event: {
        id: 999,
        platform: "dy",
        event_type: "collection_info",
        message:
          project.status === "completed"
            ? "数据抓取任务全部圆满完成。"
            : "正在抓取最新社媒帖子和相关评论，运行稳定。",
        created_at: new Date().toISOString(),
      },
      events: [
        {
          id: 999,
          platform: "dy",
          event_type: "collection_info",
          message: "正在抓取最新社媒帖子和相关评论，运行稳定。",
          created_at: new Date().toISOString(),
        },
      ],
    },
  };
};
