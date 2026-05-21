# Scene Pack Driven Growth Project Workflow Product And Development Design

## 1. 背景

当前任务工作台已经从“采集任务队列”转向“增长项目”视角。这个方向解决了主页面信息混乱的问题：用户先看到业务项目，再下钻到采集记录。

下一步需要把增长项目和关键词库打通。增长项目不应该每次从零配置关键词、平台、采集深度和 AI 模板，而应该可以从关键词库中的“场景包”快速创建。

场景包是可复用的业务研究模板。它沉淀关键词资产、适用目标、推荐平台、默认采集深度和默认 AI 分析模板。增长项目引用场景包后，生成项目关键词快照和采集计划，再由用户决定是否开始采集。

## 2. 产品目标

建立一条完整工作流：

```text
关键词库配置场景包
  -> 用场景包创建增长项目
  -> 项目生成关键词快照和采集计划
  -> 用户开始采集
  -> 系统产生采集记录和样本数据
  -> 规则判断样本状态
  -> AI 生成洞察
  -> 用户确认关键词、选题、达人或竞品动作
  -> 关键词和经验沉淀回场景包，或进入周期监控
```

第一版重点不是完整自动化 SOP，而是把“业务研究模板”做清楚：

- 场景包在关键词库配置。
- 增长项目可以选择场景包。
- 项目保存关键词快照，不直接污染原始场景包。
- 用户可以开始、暂停、停止本轮采集。
- 采集计划和采集记录分离。
- AI 洞察后的好关键词可以沉淀回场景包。

## 3. 用户角色

### 运营/内容团队

关注：

- 哪个项目现在该做什么。
- 哪些关键词可以采。
- 哪些待确认词值得加入。
- 采集后能不能生成选题和内容方向。

### 负责人/老板

关注：

- 当前项目是否有机会。
- 样本是否足够支撑判断。
- 哪些项目需要继续投入。
- 哪些项目可以归档或进入监控。

### 数据/采集团队

关注：

- 采集计划是否开启。
- 当前本轮采集是否运行中。
- 哪些采集任务失败。
- 是否需要重跑、停止或排查日志。

## 4. 核心概念

### 4.1 场景包

场景包是关键词库中的业务研究模板。

字段：

- 场景包名称
- 说明
- 适用主目标
- 推荐平台
- 默认采集深度
- 默认 AI 分析模板
- 来源：系统内置、自定义、项目沉淀
- 状态：启用、归档

第一版支持：

- 系统内置场景包
- 用户自定义场景包
- 从项目沉淀为新场景包

后续支持：

- AI 生成场景包
- 场景包版本
- 场景包效果评分
- 团队共享和权限

### 4.2 场景包关键词

关键词分四类：

```text
核心词 / 扩展词 / 待确认词 / 排除词
```

定义：

- 核心词：一定参与默认采集，代表业务认知中的主线词。
- 扩展词：默认参与采集，用于扩大样本和发现机会。
- 待确认词：不默认参与采集，需要人工确认。
- 排除词：不参与采集，用于过滤噪音、AI 扩词和搜索结果。

规则：

- 从场景包创建项目时，核心词和扩展词进入项目采集关键词。
- 待确认词进入项目待确认列表，不参与采集。
- 排除词进入项目排除列表，参与过滤。
- 项目内修改关键词不直接修改原始场景包。
- 项目内确认出的好词可以手动保存回场景包。

### 4.3 增长项目

增长项目是业务执行对象。

字段：

- 项目名
- 主目标
- 关联场景包
- 平台
- 项目状态
- 采集状态
- 样本状态
- 建议动作
- 机会评分
- 最近采集时间

项目状态：

```text
活跃 / 暂停 / 已归档
```

采集状态：

```text
未开始 / 等待中 / 采集中 / 本轮完成 / 失败
```

### 4.4 项目关键词快照

项目从场景包创建时复制一份关键词快照。

目的：

- 项目可以独立实验关键词。
- 场景包可以保持稳定。
- 场景包更新后，项目可以选择同步新增词。
- 项目产生的新词可以选择沉淀回场景包。

### 4.5 采集计划

采集计划是项目级执行策略，不等于具体采集任务。

示例：

```text
抖音关键词搜索：核心词 + 扩展词
小红书关键词搜索：核心词 + 扩展词
评论补抓：标准采集开启
AI 洞察：采集完成后可生成
```

### 4.6 采集记录

采集记录是底层执行审计，承接现有 `research_jobs`。

包括：

- 任务名
- 平台
- 采集模式
- 关键词或目标
- 状态
- 帖子数
- 评论数
- Raw 数
- 开始/结束时间
- 失败原因
- 重跑、停止、查看日志、查看 Raw

采集记录不是主页面核心，只在项目详情中下钻查看。

## 5. 完整产品工作流

### 5.1 配置场景包

入口：

```text
关键词库 -> 场景包
```

用户可以：

- 查看系统内置场景包
- 创建自定义场景包
- 编辑关键词分类
- 复制场景包
- 归档场景包
- 用场景包创建增长项目

场景包卡片显示：

```text
暑期教育招生
适用目标：找选题 / 扩关键词
推荐平台：抖音、小红书
关键词：核心 8 / 扩展 24 / 待确认 13 / 排除 9
默认采集深度：标准
默认 AI 模板：选题机会分析
最近使用：3 个项目
```

### 5.2 用场景包创建增长项目

入口：

```text
增长项目 -> 新建增长项目
关键词库 -> 场景包 -> 用此创建增长项目
```

新建表单字段：

- 项目名
- 场景包，可选
- 主目标
- 平台
- 核心词
- 扩展词
- 待确认词
- 排除词
- 采集深度
- 是否启用周期刷新
- AI 分析模板

选择场景包后自动填充：

- 主目标
- 推荐平台
- 核心词
- 扩展词
- 待确认词
- 排除词
- 采集深度
- AI 模板

用户可以修改预填内容。提交后创建：

- 增长项目
- 项目关键词快照
- 采集计划
- 初始采集记录，按用户选择决定是否立即运行

### 5.3 项目列表

入口：

```text
任务工作台 / 增长项目
```

左侧显示项目列表。

项目卡片显示：

- 项目名
- 主目标
- 关联场景包
- 样本状态
- 采集状态
- 建议动作
- 机会评分
- 最近采集时间
- 数据摘要：任务、帖子、评论、达人、Raw、失败任务

点击左侧项目后，右侧展示详情。

### 5.4 项目详情

右侧顶部状态条：

```text
建议动作
样本状态
采集状态
机会评分
```

右上角项目级动作：

```text
开始采集
暂停采集
停止本轮
刷新数据
更多
```

更多菜单：

```text
编辑项目
复制项目
归档项目
删除项目
查看采集日志
```

删除规则：

- 默认删除项目配置，不删除已采集样本。
- 彻底删除项目和样本数据是高级危险操作，第一版不做或隐藏在高级设置。
- 推荐优先提供“归档项目”，而不是鼓励删除。

详情 tabs：

```text
概览 / AI洞察 / 样本数据 / 关键词&场景 / 采集计划 / 采集记录 / 设置
```

### 5.5 关键词&场景

展示：

- 当前场景包
- 同步状态：已同步、场景包有更新、项目已自定义
- 核心词
- 扩展词
- 待确认词
- 排除词

动作：

- 从场景包同步新增词
- 保存项目词为新场景包
- AI 扩词
- 确认待确认词
- 移到排除词
- 按选中关键词补抓

待确认词处理：

```text
转为核心词
转为扩展词
加入排除词
忽略
```

### 5.6 采集控制

按钮状态：

```text
未开始 -> 开始采集
等待中 -> 暂停采集
采集中 -> 停止本轮
本轮完成 -> 再采一轮
失败 -> 查看失败任务 / 重试
暂停 -> 继续采集
```

产品语言：

- 使用“采集”
- 不使用“爬虫”
- 停止按钮叫“停止本轮”，避免误解成永久停止项目

### 5.7 AI 洞察和沉淀

样本足够后，用户点击：

```text
生成洞察
```

AI 输出：

- 机会判断
- 选题建议
- 高潜关键词
- 达人建议
- 竞品观察
- 风险与缺口
- 需要补充的数据

AI 或采集发现的新词进入项目待确认词。

用户确认后可以：

- 加入当前项目
- 保存回当前场景包
- 另存为新场景包
- 按选中词补抓

### 5.8 项目结束

项目可以：

- 导出报告
- 加入周期监控
- 保存为新场景包
- 归档项目

## 6. 页面设计

### 6.1 关键词库页面

新增 tab：

```text
关键词 / 词簇 / 场景包 / 待确认建议 / 排除词
```

第一版可只实现：

```text
关键词 / 场景包
```

场景包列表：

- 左侧列表或卡片
- 右侧详情

详情包含：

- 基础信息
- 推荐平台
- 默认采集深度
- 默认 AI 模板
- 四类关键词
- 使用记录

### 6.2 新建增长项目

单页表单 + 采集计划预览。

左侧：

- 项目配置
- 场景包选择
- 关键词快照编辑

右侧：

- 将创建的采集计划
- 将创建的采集记录
- 预计产出

### 6.3 增长项目详情

布局：

```text
左侧：项目列表
右侧：项目详情
```

右侧固定顶部状态条。

Tabs：

```text
概览
AI洞察
样本数据
关键词&场景
采集计划
采集记录
设置
```

## 7. 数据模型设计

### 7.1 scene_packs

```text
id
name
description
primary_goal
recommended_platforms
default_collection_depth
default_ai_template
source
archived
created_at
updated_at
```

`source`：

```text
system / custom / project
```

### 7.2 scene_pack_keywords

```text
id
scene_pack_id
keyword
keyword_type
source
weight
note
created_at
updated_at
```

`keyword_type`：

```text
core / expanded / pending / excluded
```

`source`：

```text
manual / ai / project / system
```

### 7.3 growth_projects

第一版如果已有软聚合项目，可以先不强制建表。正式模型建议：

```text
id
name
primary_goal
scene_pack_id
platforms
project_status
collection_status
sample_status
recommended_action
opportunity_score
last_collected_at
archived
created_at
updated_at
```

### 7.4 growth_project_keywords

```text
id
project_id
scene_pack_id
keyword
keyword_type
source
status
created_at
updated_at
```

`status`：

```text
active / pending / excluded / ignored
```

### 7.5 growth_project_collection_plans

```text
id
project_id
platform
collection_mode
keyword_scope
enabled
schedule_mode
schedule_interval_minutes
last_run_at
next_run_at
created_at
updated_at
```

### 7.6 research_jobs

现有 `research_jobs` 保留。

建议后续增加：

```text
growth_project_id
collection_plan_id
scene_pack_id
```

第一版可以继续通过 `topic`、`project_key` 或软聚合方式关联。

## 8. API 设计

### 8.1 场景包

```text
GET    /api/research/scene-packs
POST   /api/research/scene-packs
GET    /api/research/scene-packs/{id}
PATCH  /api/research/scene-packs/{id}
POST   /api/research/scene-packs/{id}/archive
POST   /api/research/scene-packs/{id}/duplicate
```

关键词：

```text
POST   /api/research/scene-packs/{id}/keywords
PATCH  /api/research/scene-pack-keywords/{keyword_id}
DELETE /api/research/scene-pack-keywords/{keyword_id}
```

### 8.2 增长项目

```text
GET    /api/research/growth-projects
POST   /api/research/growth-projects
GET    /api/research/growth-projects/{id}
PATCH  /api/research/growth-projects/{id}
POST   /api/research/growth-projects/{id}/archive
DELETE /api/research/growth-projects/{id}
```

### 8.3 项目关键词

```text
GET    /api/research/growth-projects/{id}/keywords
POST   /api/research/growth-projects/{id}/keywords
PATCH  /api/research/growth-project-keywords/{keyword_id}
DELETE /api/research/growth-project-keywords/{keyword_id}
POST   /api/research/growth-projects/{id}/sync-scene-pack
POST   /api/research/growth-projects/{id}/save-keywords-to-scene-pack
```

### 8.4 采集控制

```text
POST /api/research/growth-projects/{id}/collection/start
POST /api/research/growth-projects/{id}/collection/pause
POST /api/research/growth-projects/{id}/collection/stop-current-run
POST /api/research/growth-projects/{id}/collection/retry-failed
GET  /api/research/growth-projects/{id}/collection-plans
GET  /api/research/growth-projects/{id}/collection-records
```

第一版映射：

- `start` 创建或调度关联 `research_jobs`
- `pause` 暂停项目计划，不杀已完成记录
- `stop-current-run` 取消当前运行中的本轮任务
- `retry-failed` 重跑失败任务

## 9. 规则设计

### 9.1 项目建议动作优先级

```text
采集异常
  -> 查看失败任务
采集中
  -> 等待采集完成 / 停止本轮
帖子样本不足
  -> 补抓帖子
评论不足
  -> 补抓评论
有新样本但 AI 洞察旧
  -> 更新洞察
样本充足但未分析
  -> 生成洞察
洞察已生成
  -> 确认关键词 / 导出报告 / 加入监控
```

### 9.2 场景包同步规则

项目和场景包有三种同步状态：

```text
已同步
场景包有更新
项目已自定义
```

同步行为：

- 只自动提示，不自动覆盖。
- 默认只同步新增关键词。
- 项目内已排除或忽略的词，不因场景包更新重新加入。
- 保存回场景包必须由用户手动确认。

### 9.3 删除规则

删除项目默认只删除项目配置或将项目软删除。

第一版推荐：

- 做归档。
- 删除项目只隐藏项目和关联关系。
- 不删除帖子、评论、Raw、AI 结果。

彻底删除数据后续作为高级功能。

## 10. 开发阶段

### 阶段 1：场景包基础能力

目标：

- 关键词库可以维护场景包。
- 场景包支持四类关键词。
- 增长项目创建时可以选择场景包。

任务：

- 新增 `scene_packs` 模型或 repository 方法。
- 新增 `scene_pack_keywords` 模型或 repository 方法。
- 新增场景包 API。
- 关键词库页面新增“场景包”tab。
- 新建增长项目表单支持选择场景包。
- 创建项目时生成关键词快照。

### 阶段 2：项目关键词&场景

目标：

- 项目详情可以管理关键词快照。
- 用户可以确认待确认词和保存回场景包。

任务：

- 新增项目关键词 API。
- 项目详情新增“关键词&场景”tab。
- 支持核心词、扩展词、待确认词、排除词切换。
- 支持从场景包同步新增词。
- 支持保存项目关键词为新场景包。

### 阶段 3：项目级采集控制

目标：

- 用户可以在项目右侧控制采集。
- 采集计划和采集记录区分清楚。

任务：

- 新增采集计划聚合逻辑。
- 增长项目详情新增“采集计划”tab。
- 支持开始采集、暂停采集、停止本轮、重试失败。
- 将项目级操作映射到现有 scheduler、worker、research job。

### 阶段 4：AI 洞察和沉淀闭环

目标：

- AI 生成待确认词和业务洞察。
- 用户可以把确认后的关键词沉淀回场景包。

任务：

- AI 输出结构中增加关键词建议。
- 待确认词进入项目关键词快照。
- 支持确认、排除、忽略。
- 支持保存回场景包。
- 支持从洞察进入补抓。

## 11. MVP 范围

第一版必须做：

- 关键词库场景包 tab
- 创建和编辑场景包
- 四类关键词
- 新建增长项目时选择场景包
- 项目关键词快照
- 项目详情展示关键词&场景
- 项目级开始采集、暂停采集、停止本轮
- 项目归档

第一版暂缓：

- AI 自动生成场景包
- 场景包版本系统
- 场景包效果评分
- 复杂权限
- 彻底删除样本数据
- 完整自动化增长 SOP

## 12. 验收标准

产品验收：

- 用户能在关键词库创建一个场景包。
- 用户能用场景包创建一个增长项目。
- 项目能自动带出核心词、扩展词、待确认词、排除词。
- 核心词和扩展词参与采集。
- 待确认词不参与默认采集。
- 排除词不参与采集。
- 用户能在项目右侧开始采集、暂停采集、停止本轮。
- 用户能看到采集计划和采集记录的区别。
- 用户能把项目中的好词保存为新场景包或保存回场景包。

技术验收：

- 场景包 API 有单元测试。
- 项目创建 API 覆盖场景包预填逻辑。
- 项目关键词快照 API 有测试。
- 项目级采集控制 API 有测试。
- 前端 build 通过。
- 关键词库场景包页面和增长项目详情页在桌面和移动视口不发生文本重叠。

## 13. 风险和约束

### 删除风险

项目背后有关联样本、Raw、AI 结果和采集记录。第一版应优先做归档，避免误删数据。

### 采集控制风险

停止本轮采集可能涉及正在运行的 worker 或外部进程。第一版可以先实现“暂停后续计划”和“取消未开始任务”，对已运行任务给出明确提示。

### 场景包污染风险

项目实验出的关键词不应自动写回场景包。必须人工确认。

### AI 候选词失控风险

AI 生成的词默认进入待确认词，不自动参与采集。

### 数据模型演进风险

当前系统已有 `research_jobs` 和关键词库相关能力。第一版应尽量复用现有 repository 和 API，先补聚合层，再逐步引入正式表。

## 14. 推荐落地顺序

推荐顺序：

1. 场景包数据模型和 API
2. 关键词库场景包 tab
3. 新建增长项目选择场景包
4. 项目关键词快照
5. 关键词&场景 tab
6. 项目级采集控制
7. AI 洞察关键词沉淀

这个顺序可以先打通“配置 -> 创建项目 -> 采集”的主链路，再补 AI 和沉淀闭环。
