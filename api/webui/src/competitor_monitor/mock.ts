import type {
  AnomalyFeed,
  CompositionData,
  ContributionRanking,
  RefreshDiagnostics,
  TodaySummary,
  WorkbenchAccount,
} from "./types";

function svgThumb(text: string, bg: string) {
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="120" height="120" viewBox="0 0 120 120">
    <defs>
      <linearGradient id="g" x1="0" x2="1" y1="0" y2="1">
        <stop offset="0%" stop-color="${bg}"/>
        <stop offset="100%" stop-color="#f7faf9"/>
      </linearGradient>
    </defs>
    <rect width="120" height="120" rx="20" fill="url(#g)"/>
    <text x="50%" y="54%" dominant-baseline="middle" text-anchor="middle" font-size="20" font-family="Arial" fill="#17322d">${text}</text>
  </svg>`;
  return `data:image/svg+xml;utf8,${encodeURIComponent(svg)}`;
}

export const mockAccounts: WorkbenchAccount[] = [
  { id: 101, platform: "dy", creator_id: "myfoodie_official", display_name: "麦富迪 Myfoodie", enabled: true, notes: "主打宠物主粮" },
  { id: 102, platform: "dy", creator_id: "royalcanin_cn", display_name: "皇家宠物食品", enabled: true, notes: "高端主粮" },
  { id: 103, platform: "dy", creator_id: "instinct_pet", display_name: "伯纳天纯", enabled: true, notes: "冻干卖点" },
  { id: 104, platform: "xhs", creator_id: "nourse_lab", display_name: "卫仕 NOURSE", enabled: true, notes: "营养品类" },
  { id: 105, platform: "xhs", creator_id: "yiweipet", display_name: "网易严选宠物", enabled: true, notes: "电商内容" },
  { id: 106, platform: "dy", creator_id: "keres_pet", display_name: "凯锐思", enabled: true, notes: "平价口粮" },
  { id: 107, platform: "dy", creator_id: "bridger_pet", display_name: "比瑞吉 Bridger", enabled: false, notes: "暂停监控" },
  { id: 108, platform: "dy", creator_id: "naturesvar", display_name: "帕特诺尔", enabled: true, notes: "天然粮" },
];

export const mockCreatorAccounts: WorkbenchAccount[] = [
  { id: 201, platform: "xhs", creator_id: "creator_campaign_01", monitor_type: "partner_creator", display_name: "学而思合作达人", enabled: true, notes: "618 宣发" },
  { id: 202, platform: "dy", creator_id: "creator_campaign_02", monitor_type: "partner_creator", display_name: "测评类达人A", enabled: true, notes: "待发布" },
  { id: 203, platform: "xhs", creator_id: "creator_campaign_03", monitor_type: "partner_creator", display_name: "母婴教育达人", enabled: false, notes: "暂停合作" },
];

export const mockOverview = {
  new_posts_total: 56,
  interaction_total: 786000,
  new_hot_total: 9,
  anomaly_total: 3,
};

export const mockMonitorSettingsById: Record<number, {
  competitor_id: number;
  job_id: number | null;
  schedule_enabled: boolean;
  interval_minutes: number;
  cadence_label: string;
  next_run_at: string | null;
  last_scheduled_at: string | null;
  last_refresh_at: string | null;
  last_refresh_status: string | null;
}> = {
  101: {
    competitor_id: 101,
    job_id: 9001,
    schedule_enabled: true,
    interval_minutes: 1440,
    cadence_label: "每天一次",
    next_run_at: "2026-05-23T02:00:00Z",
    last_scheduled_at: "2026-05-22T02:00:00Z",
    last_refresh_at: "2026-05-24T08:30:00Z",
    last_refresh_status: "succeeded",
  },
};

export const mockSummaryById: Record<number, TodaySummary> = {
  101: {
    account_id: 101,
    date: "2026-05-22",
    stale: false,
    snapshot_date: "2026-05-22",
    unmatched_post_count: 0,
    metrics: {
      new_post_count: 8,
      interaction_delta: 126000,
      new_hot_post_count: 2,
      anomaly_count: 1,
      new_content_contribution: 68300,
      old_content_contribution: 31700,
      new_content_contribution_pct: 68.3,
      old_content_contribution_pct: 31.7,
      breakdown: {
        like: { value: 87000, delta_pct: 28.4 },
        comment: { value: 16000, delta_pct: 22.1 },
        collect: { value: 24000, delta_pct: 25.7 },
        share: { value: 6842, delta_pct: 31.3 },
      },
      yesterday_diff_pct: { new_posts: 2, interaction: 32.6 },
      deduped_post_count: 8,
    },
  },
};

export const mockRankingById: Record<number, ContributionRanking> = {
  101: {
    account_id: 101,
    date: "2026-05-22",
    stale: false,
    scope: "all",
    total: 8,
    rows: [
      { rank: 1, post_id: "p101", title: "新手养狗必看：狗粮挑选 6 大避坑指南", thumbnail_url: svgThumb("狗粮", "#f2c18f"), duration_sec: 62, publish_time: "2026-05-21T20:15:00", is_new: true, interaction_delta: 32000, delta_pct: 182.6, contribution_share: 24.8, tags: ["狗粮推荐", "新手养宠"], platform_url: "#", content_type: "短视频" },
      { rank: 2, post_id: "p102", title: "猫咪不爱吃饭？试试这款高蛋白冻干主食", thumbnail_url: svgThumb("猫粮", "#d7c4af"), duration_sec: 48, publish_time: "2026-05-21T18:40:00", is_new: true, interaction_delta: 21000, delta_pct: 156.3, contribution_share: 16.2, tags: ["测评", "冻干"], platform_url: "#", content_type: "图文" },
      { rank: 3, post_id: "p103", title: "8 款热门狗粮成分对比，谁才是真正高肉配方", thumbnail_url: svgThumb("成分", "#d8d9dc"), duration_sec: 59, publish_time: "2026-05-20T16:22:00", is_new: false, interaction_delta: 18000, delta_pct: 98.4, contribution_share: 13.9, tags: ["成分对比", "实测"], platform_url: "#", content_type: "短视频" },
      { rank: 4, post_id: "p104", title: "618 囤粮攻略：这些狗粮千万别闭眼入", thumbnail_url: svgThumb("618", "#c8b094"), duration_sec: 55, publish_time: "2026-05-19T12:05:00", is_new: false, interaction_delta: 12000, delta_pct: 72.8, contribution_share: 9.3, tags: ["618攻略", "囤粮"], platform_url: "#", content_type: "短视频" },
      { rank: 5, post_id: "p105", title: "幼犬软便怎么办？营养师教你看配方表", thumbnail_url: svgThumb("幼犬", "#f0d5bb"), duration_sec: 60, publish_time: "2026-05-19T10:12:00", is_new: false, interaction_delta: 8672, delta_pct: 62.2, contribution_share: 6.7, tags: ["幼犬粮", "配方解读"], platform_url: "#", content_type: "图文" },
      { rank: 6, post_id: "p106", title: "猫咪便便软臭？可能是粮里蛋白过高", thumbnail_url: svgThumb("猫咪", "#dac0aa"), duration_sec: 37, publish_time: "2026-05-18T19:30:00", is_new: false, interaction_delta: 6325, delta_pct: 45.1, contribution_share: 4.9, tags: ["猫粮健康", "肠胃"], platform_url: "#", content_type: "短视频" },
    ],
  },
};

export const mockCompositionById: Record<number, CompositionData> = {
  101: {
    account_id: 101,
    date: "2026-05-22",
    stale: false,
    keywords: [
      { word: "狗粮推荐", weight: 96 },
      { word: "营养配比", weight: 54 },
      { word: "幼犬粮", weight: 42 },
      { word: "冻干", weight: 40 },
      { word: "高蛋白", weight: 36 },
      { word: "性价比", weight: 28 },
      { word: "肠胃健康", weight: 32 },
      { word: "618攻略", weight: 27 },
      { word: "配方表", weight: 30 },
      { word: "便便健康", weight: 18 },
      { word: "宠物测评", weight: 24 },
      { word: "主粮", weight: 34 },
    ],
    content_types: [
      { name: "视频", value: 879 },
      { name: "图文", value: 241 },
      { name: "直播切片", value: 107 },
      { name: "图集", value: 40 },
      { name: "其他", value: 19 },
    ],
    publish_heatmap: {
      buckets: ["morning", "afternoon", "night", "late_night"],
      days: ["2026-05-16", "2026-05-17", "2026-05-18", "2026-05-19", "2026-05-20", "2026-05-21", "2026-05-22"],
      values: [
        [1, 0, 2, 0],
        [0, 1, 2, 0],
        [0, 2, 4, 1],
        [1, 3, 5, 2],
        [1, 4, 6, 2],
        [2, 5, 7, 2],
        [1, 4, 8, 3],
      ],
    },
  },
};

export const mockAnomaliesById: Record<number, AnomalyFeed> = {
  101: {
    account_id: 101,
    date: "2026-05-22",
    stale: false,
    items: [
      { id: "a1", type: "interaction_spike", severity: "high", title: "互动突增", reason: "两条狗粮测评内容贡献了今日 67% 的互动增量，评论区集中讨论适口性与营养配比。", timestamp: "2026-05-22T20:10:00", post_ref: { id: "p101", title: "新手养狗必看：狗粮挑选 6 大避坑指南" } },
      { id: "a2", type: "keyword_shift", severity: "medium", title: "主题变化", reason: "关键词从“价格”转向“真实体验”和“肠胃健康”，内容表达更偏实测口碑。", timestamp: "2026-05-22T17:20:00", post_ref: { id: "p103", title: "8 款热门狗粮成分对比" } },
      { id: "a3", type: "new_hot_post", severity: "low", title: "新爆款", reason: "618 囤粮攻略内容在 6 小时内收藏增长 72.8%，具备继续追踪潜力。", timestamp: "2026-05-22T14:42:00", post_ref: { id: "p104", title: "618 囤粮攻略：这些狗粮千万别闭眼入" } },
    ],
  },
};

export const mockRefreshDiagnosticsById: Record<number, RefreshDiagnostics> = {
  101: {
    account_id: 101,
    date: "2026-05-22",
    stale: false,
    timezone: "Asia/Shanghai",
    last_refresh_at: "2026-05-24T08:30:00Z",
    last_refresh_status: "succeeded",
    stats: {
      raw_matched_posts: 8,
      author_verified_posts: 8,
      displayable_posts: 8,
      eligible_posts: 6,
      degraded_link_posts: 2,
      invalid_url_posts: 2,
      missing_token_posts: 2,
      author_mismatch_posts: 0,
    },
    entries: [
      { id: "run-latest", timestamp: "2026-05-24T08:30:00Z", level: "success", message: "最近一次刷新成功，采集窗口：近 7 天，上限 50 条。" },
      { id: "diag-matched", timestamp: "2026-05-24T08:30:00Z", level: "info", message: "当前匹配到 8 条候选帖子，作者归属核验通过 8 条。" },
      { id: "diag-token", timestamp: "2026-05-24T08:30:00Z", level: "warn", message: "2 条帖子缺少 xsec_token，链接暂不可跳转，已在贡献榜降级展示并等待回填。" },
      { id: "diag-eligible", timestamp: "2026-05-24T08:30:00Z", level: "success", message: "可点击链接 6 条，当前贡献榜展示 8 条。" },
    ],
  },
};

export function getMockSummary(accountId: number) {
  return mockSummaryById[accountId] || mockSummaryById[101];
}

export function getMockRanking(accountId: number) {
  return mockRankingById[accountId] || mockRankingById[101];
}

export function getMockComposition(accountId: number) {
  return mockCompositionById[accountId] || mockCompositionById[101];
}

export function getMockAnomalies(accountId: number) {
  return mockAnomaliesById[accountId] || mockAnomaliesById[101];
}

export function getMockMonitorSettings(accountId: number) {
  return mockMonitorSettingsById[accountId] || mockMonitorSettingsById[101];
}

export function getMockRefreshDiagnostics(accountId: number) {
  return mockRefreshDiagnosticsById[accountId] || mockRefreshDiagnosticsById[101];
}
