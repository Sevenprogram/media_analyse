# 通用增长情报平台设计

Date: 2026-05-20

## 目标

把研究工作台升级为通用增长情报平台。系统不再只服务一个固定关键词或教育赛道，而是支持多个赛道、多个场景包、多个平台、多个账号角色和多种报告口径。

老板提出的四类问题必须能在前端形成可解释答案：

1. 输入关键词或场景，筛选一批匹配达人。
2. 输入文字、视频内容或内容链接，定位关键词，搜索同类内容并持续追踪。
3. 每日监控所选友商账号的全部流量，并拆分内容组成模式。
4. 判断平台当下对某个关键词的热度、推流增强、正常波动、降温或疑似限流。

第一条验证链路继续使用教育赛道的 `K12教育 + 单亲妈妈`，但所有模型、接口和页面都按通用平台版设计，后续可以扩展到美妆、科技、母婴、财经等赛道。

## 设计原则

- 通用配置优先：赛道、场景包、关键词、平台、权重、报告口径都由后台配置驱动。
- 真实数据优先：老板看板只展示真实采集、回填、分析后生成的数据，不使用静态假数据冒充业务结果。
- 人工确认优先：AI 可以生成建议和解释，但正式词库、自动维护建议、达人加入监控池等关键动作默认需要人工确认。
- 异步执行优先：真实平台采集默认异步执行，前端显示任务状态，并提供“等待完成并刷新”按钮用于演示或小批量验证。
- 证据可解释：达人推荐、关键词热度、推流/限流判断、友商分析都必须展示分数、标签和证据。
- 同一账号统一沉淀：达人候选、已监控达人、友商账号共用统一账号画像，通过角色关系区分用途。

## 用户角色

### 研究人员

负责配置赛道、场景包、关键词、平台策略、AI 建议审核，以及检查候选达人和报告证据。

### 运营人员

负责发起达人筛选、创建监控池、追踪内容、添加友商账号、查看每日报告。

### 老板或决策者

主要查看赛道报告和场景包报告，关注机会、风险、友商变化、推荐动作和证据链接。

## 核心业务闭环

### 闭环一：关键词发现达人

1. 用户选择赛道和场景包，例如教育赛道下的 `K12教育 + 单亲妈妈`。
2. 系统读取该场景包的主词、辅助词、排除词、平台适配词和权重。
3. 系统先查本地账号画像、历史内容、候选达人和监控池成员。
4. 如果用户打开实时发现，系统按平台策略触发 TikHub 或平台爬虫搜索。
5. 采集完成后自动回填到 `research_posts`、`research_authors`、`raw_records`。
6. 系统从内容作者中抽取或更新统一账号画像。
7. 系统按场景包规则和 AI 补充分析计算达人匹配分。
8. 前端展示候选达人：标签、分数、证据解释、最近内容、互动表现、是否已监控。
9. 用户勾选达人加入监控池。
10. 用户可选择“加入并立即爬取”，立即执行同一个长期监控任务一次。

### 闭环二：内容追踪

1. 用户输入文字内容、视频标题、视频 OCR 文本、链接或采集到的内容样本。
2. 系统根据当前赛道和场景包抽取关键词、场景标签和内容类型。
3. 系统搜索本地相似内容。
4. 如果用户打开实时搜索，系统触发平台搜索采集。
5. 系统生成相似内容候选列表，展示相似度、命中词、证据上下文和互动数据。
6. 用户创建内容追踪器。
7. 系统按配置定期采集同类内容，生成追踪快照。
8. 前端展示内容趋势、相似内容簇、关键词位置、爆款率和代表案例。

### 闭环三：友商每日监控

1. 用户添加友商账号，账号进入统一账号画像，并增加 `competitor` 角色。
2. 系统按账号平台和监控频率创建或更新 creator-mode 研究任务。
3. 每日采集友商主页内容。
4. 系统自动回填、打标签、计算互动指标和内容组成。
5. 系统生成友商组成快照。
6. 前端展示关键词分布、标签分布、内容类型、发布时间、爆款率和互动结构。
7. 赛道报告汇总多个友商的变化，场景包报告展示相关友商的细分表现。

### 闭环四：关键词热度和推流/限流判断

1. 用户选择赛道、场景包、平台和关键词。
2. 系统聚合 24 小时、7 天、30 天真实内容和互动数据。
3. 规则引擎计算热度分、增长分、供给分、竞争分、推流信号分、降温风险分。
4. AI 根据规则证据生成自然语言解释。
5. 前端双轨展示规则判断和 AI 判断。
6. 如果规则和 AI 结论冲突，系统标记为“需要人工复核”。

## 配置模型

### 全局默认平台

全局设置维护默认采集平台。场景包可以覆盖或追加平台。

字段：

- `default_platforms`: 默认平台列表，例如 `["xhs", "dy"]`
- `fallback_to_default_platforms`: 场景包未配置平台时是否使用默认平台
- `realtime_discovery_default`: 实时发现默认开关，默认关闭
- `async_execution_default`: 默认异步执行，固定为开启
- `wait_refresh_timeout_seconds`: 等待完成并刷新超时时间

规则：

- 用户任务有显式平台时，优先使用任务平台。
- 场景包有平台覆盖时，使用场景包平台。
- 两者都没有时，使用全局默认平台。
- 全部为空时，前端阻止执行并提示配置平台。

### 赛道

字段：

- `id`
- `code`
- `name`
- `description`
- `default_platforms`
- `keyword_review_mode`: 默认 `manual_review`
- `enabled`
- `created_at`
- `updated_at`

示例：

- `education`: 教育赛道
- `beauty`: 美妆护肤
- `technology`: 科技数码

### 场景包

场景包代表一个可监控的人群、需求、内容场景或业务目标。

字段：

- `id`
- `vertical_id`
- `name`
- `description`
- `audience`
- `scenario`
- `business_goal`
- `platforms`
- `match_mode`: `single` 或 `multi`
- `primary_required`: 默认 true
- `enabled`

示例：

- 教育赛道：`K12教育 + 单亲妈妈`
- 教育赛道：`初中升学焦虑`
- 美妆赛道：`敏感肌修复`
- 科技赛道：`AI办公自动化`

### 场景包关键词

字段：

- `id`
- `scene_pack_id`
- `keyword`
- `keyword_type`: `primary`、`secondary`、`negative`、`platform_adapted`、`synonym`
- `platform`
- `weight`
- `reason`
- `usage_flags`: `creator_discovery`、`content_tracking`、`keyword_heat`、`competitor_analysis`
- `enabled`

规则：

- 主关键词必须命中。
- 辅助关键词加分。
- 平台适配词只在对应平台或平台为空时使用。
- 排除词扣分或排除。
- 多场景包模式下，候选只需满足任一场景包主词规则，但跨多个场景包命中会额外加分。

### AI 关键词建议

AI 建议不直接写入正式词库，而是进入待审核队列。

字段：

- `id`
- `vertical_id`
- `scene_pack_id`
- `input_text`
- `suggestion_type`: `new_keyword`、`weight_change`、`negative_keyword`、`platform_adaptation`
- `suggested_payload`
- `confidence`
- `reason`
- `status`: `pending`、`approved`、`rejected`
- `created_by_ai_provider_id`
- `reviewed_by`
- `reviewed_at`

规则：

- 默认全部进入待审核队列。
- 审核通过后才写入正式词库。
- 被拒绝的建议保留记录，避免重复推荐。
- AI 自动维护能力可以定期生成建议，但不能绕过审核。

## 统一账号画像

达人和友商账号使用同一套账号画像。

### 账号画像

字段：

- `platform`
- `account_id`
- `sec_account_id`
- `display_name`
- `avatar_url`
- `profile_url`
- `bio`
- `verified`
- `region`
- `follower_count`
- `following_count`
- `post_count`
- `avg_engagement_rate`
- `hot_post_rate`
- `recent_post_count_30d`
- `latest_post_time`
- `contact_clues`
- `tag_summary_json`
- `last_crawled_at`
- `updated_at`

### 账号角色

同一个账号可以有多个角色。

字段：

- `account_profile_id`
- `role`: `candidate_creator`、`monitored_creator`、`competitor`
- `vertical_id`
- `scene_pack_id`
- `monitor_pool_id`
- `source`
- `status`
- `created_at`

规则：

- 候选达人来自搜索发现。
- 已监控达人来自用户加入监控池。
- 友商账号来自用户添加或导入。
- 账号重复时更新画像，不重复创建实体。

## 采集和自动处理流水线

### 真实采集

第一版优先支持 TikHub 小红书和抖音。

要求：

- 小红书使用 TikHub `xhs` 搜索通道。
- 抖音使用 TikHub 当前推荐搜索端点：`POST /api/v1/douyin/search/fetch_general_search_v1`。
- TikHub Key 只从环境变量或后台 Provider/凭证配置读取，不写入前端代码。
- 采集日志不得输出完整 API Key。

### 自动处理流水线

采集完成后必须自动执行：

1. 平台原始表落库。
2. 回填到研究聚合表。
3. 建立 raw record。
4. 抽取或更新统一账号画像。
5. 规则标签匹配。
6. AI 补充标签和解释。
7. 刷新达人候选、关键词热度、内容追踪或友商快照。
8. 前端收到状态完成后刷新图表。

如果某一步失败：

- 不影响已完成的前置数据保存。
- 写入任务事件。
- 前端显示失败阶段、错误原因和重试按钮。

## 达人评分

候选达人评分由规则分和 AI 解释组成。

### 规则分

分数区间 0-100。

建议权重：

- 主词命中：最高 30 分。
- 辅助词命中：最高 20 分。
- 平台适配词命中：最高 10 分。
- 近 30 天发帖数：最高 10 分。
- 互动表现：最高 15 分。
- 标签匹配：最高 10 分。
- 负向关键词：最高扣 30 分。
- 已监控重复：默认不推荐，可由用户选择是否显示。

### 证据

每个候选达人必须展示：

- 命中的主词和辅助词。
- 命中的内容标题或摘要。
- 对应平台和内容链接。
- 最近发布时间。
- 互动数据。
- 负向命中原因。
- AI 补充解释。

## 监控池

监控池代表一个长期业务目标。

字段：

- `id`
- `vertical_id`
- `scene_pack_ids`
- `name`
- `description`
- `platforms`
- `frequency_minutes`
- `comment_policy`: `none`、`level1`、`level1_and_replies`
- `automation_enabled`
- `automation_mode`: `review_queue`、`direct_add`
- `min_match_score`
- `top_n`
- `min_recent_posts_30d`
- `exclude_existing_monitored`
- `enabled`

规则：

- 默认每 12 小时一次，也就是每天 2 次。
- 用户可以自定义频率。
- 监控池内可包含多个平台、多个账号。
- 系统为监控池维护一个 creator-mode 研究任务。
- “立即爬取”复用同一个长期任务，不创建一次性任务。

## 内容追踪

内容追踪器字段：

- `vertical_id`
- `scene_pack_ids`
- `name`
- `platforms`
- `seed_content_refs`
- `included_keywords`
- `excluded_keywords`
- `similarity_threshold`
- `frequency_minutes`
- `enabled`

快照字段：

- `tracker_id`
- `snapshot_date`
- `matched_posts`
- `new_posts`
- `hot_posts`
- `keyword_distribution`
- `tag_distribution`
- `content_type_distribution`
- `top_posts`
- `evidence`

前端展示：

- 输入内容和自动抽词。
- 同类内容列表。
- 相似度和证据上下文。
- 创建追踪器。
- 追踪快照趋势。

## 友商监控

友商账号使用统一账号画像的 `competitor` 角色。

组成快照字段：

- `competitor_account_id`
- `snapshot_date`
- `new_post_count`
- `total_interaction`
- `keyword_distribution`
- `tag_distribution`
- `content_type_distribution`
- `publish_time_distribution`
- `hot_post_rate`
- `interaction_structure`
- `top_posts`
- `evidence`

前端展示：

- 友商账号列表。
- 今日新增内容。
- 内容组成拆分。
- 爆款内容。
- 与前一日或 7 日均值的变化。
- 进入赛道报告和场景包报告的引用。

## 关键词热度和推流/限流

采用规则 + AI 双轨展示。

### 规则指标

- `volume_24h`: 24 小时新增内容数。
- `volume_7d_avg`: 7 日日均新增内容数。
- `volume_30d_avg`: 30 日日均新增内容数。
- `engagement_24h`: 24 小时互动总量。
- `hot_post_rate`: 高互动内容占比。
- `creator_participation`: 参与账号数量。
- `platform_coverage`: 平台覆盖数量。
- `competition_density`: 同关键词内容供给密度。
- `cooldown_risk`: 降温风险。

### 标签

- `boosting`: 疑似推流增强。
- `normal`: 正常波动。
- `cooling`: 热度下降。
- `limited`: 疑似限流。
- `insufficient_data`: 样本不足。

### 规则

- 24 小时新增明显高于 7 日均值，且高互动内容占比提升，倾向 `boosting`。
- 24 小时新增接近 7 日均值，互动稳定，倾向 `normal`。
- 24 小时新增低于 7 日均值且互动下降，倾向 `cooling`。
- 内容供给增加但曝光互动异常下降，或同类账号集中低互动，倾向 `limited`。
- 样本量不足时输出 `insufficient_data`，不做强判断。

### 双轨展示

前端同时展示：

- 规则标签。
- 规则分数。
- AI 标签。
- AI 解释。
- 证据列表。
- 是否冲突。

如果规则标签和 AI 标签不同，显示“需要人工复核”。

## 老板报告

报告同时支持赛道汇总和场景包细分。

### 赛道报告

面向老板默认入口。

模块：

- 今日机会摘要。
- 热门关键词 Top N。
- 推荐达人 Top N。
- 友商变化摘要。
- 平台推流/限流信号。
- 风险提醒。
- 建议动作。
- 证据链接。

### 场景包报告

面向运营和研究人员。

模块：

- 场景包关键词表现。
- 候选达人详情。
- 已监控达人动态。
- 同类内容追踪。
- 友商相关内容。
- 关键词热度双轨判断。
- 可执行动作。

### 报告生成规则

- 报告只引用真实数据、规则结果和 AI 分析结果。
- 每条结论必须能追溯到内容、账号或快照证据。
- 数据不足时明确显示样本不足，不生成强结论。

## 前端页面

### 配置中心

- 全局默认平台。
- 平台能力开关。
- TikHub 凭证状态。
- 4Router Provider 状态。
- 赛道列表。
- 场景包列表。
- AI 自动维护待审核队列。

### 赛道词库

- 赛道管理。
- 场景包管理。
- 主词、辅助词、排除词、平台适配词。
- AI 扩词。
- 审核后入库。
- 导入导出。

### 人群筛选

- 选择赛道和场景包。
- 实时发现开关。
- 候选达人表格。
- 分数、标签、证据。
- 加入监控池。
- 加入并立即爬取。

### 监控池

- 监控池列表。
- 成员管理。
- 频率配置。
- 评论策略。
- 自动化规则。
- 立即执行。

### 内容追踪

- 输入内容。
- 抽取关键词。
- 搜索同类内容。
- 创建追踪器。
- 快照趋势。

### 友商监控

- 友商账号管理。
- 每日采集状态。
- 内容组成拆分。
- 爆款率和互动结构。

### 关键词热度

- 选择赛道、场景包、平台和关键词。
- 规则分数。
- AI 判断。
- 证据解释。
- 冲突复核。

### 报告中心

- 赛道报告。
- 场景包报告。
- 导出 Markdown、CSV、Excel。

## API 设计

### 配置

- `GET /api/research/global-defaults`
- `PUT /api/research/global-defaults`
- `GET /api/keyword-library/verticals`
- `POST /api/keyword-library/verticals`
- `GET /api/keyword-library/scene-packs`
- `POST /api/keyword-library/scene-packs`
- `GET /api/keyword-library/keywords`
- `POST /api/keyword-library/keywords`

### AI 建议审核

- `POST /api/keyword-library/ai/expand`
- `GET /api/keyword-library/ai/suggestions`
- `POST /api/keyword-library/ai/suggestions/{id}/approve`
- `POST /api/keyword-library/ai/suggestions/{id}/reject`

### 采集和处理

- `POST /api/research/jobs/{id}/execute`
- `POST /api/research/jobs/{id}/wait-refresh`
- `POST /api/research/jobs/{id}/backfill/{platform}`
- `POST /api/research/jobs/{id}/postprocess`

### 账号画像

- `GET /api/accounts/profiles`
- `GET /api/accounts/profiles/{id}`
- `POST /api/accounts/profiles/{id}/roles`
- `DELETE /api/accounts/profiles/{id}/roles/{role_id}`

### 达人筛选

- `POST /api/creator-search/discover`
- `POST /api/creator-search/discover/realtime`
- `POST /api/creator-search/discover/{job_id}/wait-refresh`
- `GET /api/creator-search/candidates`
- `POST /api/creator-search/monitor-pools/{pool_id}/creators`

### 内容追踪

- `POST /api/content-tracking/extract-keywords`
- `POST /api/content-tracking/search-similar`
- `POST /api/content-tracking/realtime-discovery`
- `POST /api/content-tracking/trackers`
- `POST /api/content-tracking/trackers/{tracker_id}/analysis`

### 友商

- `POST /api/competitors`
- `GET /api/competitors`
- `POST /api/competitors/{id}/composition/rebuild`

### 关键词热度

- `POST /api/keyword-opportunities/heat/rebuild`
- `POST /api/keyword-opportunities/heat/signal`

### 报告

- `GET /api/reports/vertical/{vertical_id}`
- `GET /api/reports/scene-pack/{scene_pack_id}`
- `POST /api/reports/export`

## 错误处理

- 未配置 TikHub Key：提示用户进入配置中心，不显示敏感字段。
- 未配置平台：阻止实时发现，提示设置全局默认平台或场景包平台。
- 平台接口失败：保存失败事件，允许重试。
- AI Provider 未配置：AI 相关按钮显示不可用原因，规则流程仍可运行。
- 样本不足：报告和热度判断显示 `insufficient_data`。
- 自动维护建议冲突：进入待审核队列，不自动覆盖正式词库。

## 测试计划

### 后端测试

- TikHub 小红书采集后自动回填研究表。
- TikHub 抖音使用当前 POST 搜索端点。
- 采集完成后自动触发 postprocess。
- 赛道、场景包、关键词 CRUD。
- AI 建议进入待审核队列。
- 审核通过后写入正式词库。
- 统一账号画像去重。
- 达人评分输出标签、分数、证据。
- 监控池加入达人后复用 creator-mode 长期任务。
- `crawl_now=true` 执行同一个长期任务。
- 关键词热度规则输出标签、分数、证据。
- 规则和 AI 冲突时输出复核标记。
- 友商组成快照生成关键词、标签、内容类型、发布时间、爆款率和互动结构。

### 前端测试

- 配置中心能设置全局默认平台。
- 赛道词库能创建赛道和场景包。
- AI 关键词建议必须审核后才入库。
- 人群筛选能触发异步实时发现。
- 等待完成并刷新后能看到候选达人。
- 监控池能加入达人并立即爬取。
- 内容追踪能从文本抽词并搜索相似内容。
- 关键词热度页能展示规则和 AI 双轨结果。
- 友商页能展示组成快照。
- 报告中心能展示赛道报告和场景包报告。
- 桌面和移动宽度下不出现文字溢出、卡片重叠和按钮挤压。

### 真实数据验证

- 使用测试 TikHub Key 在本地临时环境变量中运行，不写入代码。
- 用 `K12教育` 验证小红书和抖音搜索。
- 采集后自动回填研究表。
- 前端图表显示平台分布、采集趋势和关键词排行。
- AI 分析后显示情绪、立场或主题标签分布。
- 报告页引用真实内容证据。

## 实施阶段

### 阶段一：真实采集到前端图表闭环

- 修复 TikHub 抖音新搜索端点。
- 采集完成后自动回填研究表。
- 前端任务页和总览页自动刷新。
- 确保真实数据能展示平台分布、趋势、关键词排行。

### 阶段二：通用配置底座

- 完善全局默认平台。
- 完善赛道和场景包管理。
- 增加 AI 建议审核队列。
- 前端支持建议确认后入库。

### 阶段三：统一账号画像和达人筛选

- 从采集内容抽取账号。
- 建立统一账号画像。
- 建立账号角色关系。
- 生成候选达人评分和证据。
- 加入监控池和立即爬取。

### 阶段四：内容追踪和关键词热度

- 内容抽词。
- 相似内容搜索。
- 追踪器快照。
- 关键词热度规则。
- 规则 + AI 双轨展示。

### 阶段五：友商监控和老板报告

- 友商账号角色。
- 每日组成快照。
- 赛道报告。
- 场景包报告。
- 导出能力。

## 验收标准

通用平台版完成后，用户可以：

1. 新增一个赛道和多个场景包。
2. 用 AI 生成关键词建议，并人工确认入库。
3. 设置全局默认平台，并让场景包覆盖平台。
4. 用真实平台数据发现达人。
5. 查看候选达人分数、标签和证据。
6. 把达人加入监控池，并立即爬取。
7. 输入内容并创建内容追踪器。
8. 添加友商账号并查看每日组成快照。
9. 查看关键词热度和推流/限流双轨判断。
10. 打开老板报告，看到赛道汇总和场景包细分结论。

如果某个结论样本不足，系统必须明确展示样本不足，而不是输出确定性判断。

