# 内容追踪分析页 PRD

- 日期：2026-05-23
- 页面：内容追踪分析页（`content_tracking` / `tracker_detail`）
- 目标：将当前“内容追踪”从相似内容检索页升级为围绕单个追踪器的趋势判断、模式拆解、风险校验与动作建议页面
- 关联文档：
  - `docs/superpowers/specs/2026-05-23-content-tracking-analysis-data-model.md`
  - `docs/superpowers/specs/2026-05-23-content-tracking-backend-api-and-aggregation.md`

## 1. 产品定位

内容追踪分析页用于围绕一个 `Content Tracker` 持续回答以下问题：

1. 当前追踪器处于什么状态
2. 这类内容是否正在形成趋势
3. 当前追踪器配置是否有效
4. 这些内容为什么会被认为属于同一模式
5. 是否正在向更多创作者或更多平台扩散
6. 当前判断是否可信
7. 现在应采取什么动作

它不是：

- 原始内容列表页
- 单纯关键词命中页
- 通用 BI 仪表盘
- 任务运行页

它应完成的业务闭环：

```text
内容种子 / 关键词
-> 相似样本召回
-> 模式识别
-> 趋势判断
-> 风险校验
-> 动作建议
```

## 2. 用户与使用场景

### 2.1 目标用户

- 内容运营：判断一个方向是否值得跟进、复用、测试
- 增长负责人：判断一个方向是否值得投入资源
- 研究分析员：校验结论可信度，调整关键词、排除词、窗口期
- 管理者：快速浏览当前状态、机会与风险

### 2.2 高频场景

#### 场景一：从单条内容创建追踪器后复盘

用户从内容解析页创建追踪器，第二天查看：

- 同类内容有没有变多
- 哪个平台最活跃
- 新出现了哪些高价值变体
- 当前词包是否过宽或过窄

#### 场景二：从关键词热度页跳入内容追踪

用户在关键词热度页看到某词升温，进入内容追踪页判断：

- 是真实趋势还是噪声
- 是否值得新建达人发现任务
- 是否要拆分为多个追踪器

#### 场景三：日常监控

用户每天打开内容追踪页，希望在 10 秒内知道：

- 哪些追踪器值得继续看
- 哪些追踪器需要补采
- 哪些追踪器出现异常

## 3. 页面成功标准

页面上线后应能满足：

- 用户在 10 秒内得出“继续跟 / 补采 / 调词 / 降级”的初步判断
- 用户能理解状态结论的原因，而不是只看到黑盒总分
- 页面能区分“无数据”和“负趋势”
- 每个动作建议都能追溯到证据样本或公式指标
- 后端分析结果可独立于前端复用

## 4. 页面核心原则

### 4.1 每个区块只回答一个问题

页面不做“所有信息混在一起”的大屏，而是分块回答问题。

### 4.2 每个结论必须有证据

任何状态、标签、结论、建议动作都必须能追溯到：

- 指标
- 规则
- 代表样本
- 风险说明

### 4.3 风险会降低结论强度

风险不是附属展示，而是要直接影响：

- 状态判定
- 置信度
- 推荐动作

### 4.4 优先回答动作问题

页面最终目标不是让用户“看懂图”，而是让用户知道下一步做什么。

## 5. 页面结构

页面分为 8 个区块：

1. 追踪器头部区
2. 追踪总览区
3. 趋势分析区
4. 关键词效果区
5. 内容模式拆解区
6. 创作者参与区
7. 代表样本与证据区
8. 结论与动作区

---

## 6. 追踪器头部区

### 6.1 产品目标

明确这页正在分析什么，避免用户误把不同 Tracker 的结果混淆。

### 6.2 展示字段

- `tracker_name`
- `tracker_status`
- `platforms`
- `included_keywords`
- `excluded_keywords`
- `time_window_days`
- `created_from`
  - manual
  - source_content
  - keyword_hotspot
  - ai_suggestion
- `last_refresh_time`
- `last_analysis_time`
- `last_collection_status`

### 6.3 操作

- `立即刷新`
- `编辑追踪器`
- `一键补采`
- `暂停 / 恢复`
- `导出分析`
- `查看任务日志`

### 6.4 设计要求

- 头部要固定分析边界，不承载深度解释
- 风险提示可出现在头部，但不替代后文风险区

### 6.5 空态与异常态

空态：

- 未配置主关键词
- 未配置平台
- Tracker 刚创建但尚未采集

异常态：

- 最近采集失败
- 最近分析结果过旧
- 追踪器被暂停

---

## 7. 追踪总览区

### 7.1 产品目标

让用户在最短时间内知道：

- 当前状态
- 当前结论是否可信
- 是否值得继续看

### 7.2 展示模块

#### 7.2.1 状态总卡

字段：

- `status`
  - 升温
  - 稳定
  - 衰减
  - 噪音高
  - 样本不足
  - 观察中
- `decision_confidence`
- `summary_sentence`
- `primary_reason`
- `top_risk`

#### 7.2.2 样本规模卡

字段：

- `content_count_24h`
- `content_count_7d`
- `creator_count_7d`
- `platform_count`
- `snapshot_count`

#### 7.2.3 增长卡

字段：

- `content_growth_rate_24h`
- `content_growth_rate_7d`
- `engagement_growth_rate_24h`
- `viral_ratio_change`
- `new_creator_ratio`

#### 7.2.4 数据质量卡

字段：

- `sample_quality_score`
- `collection_success_rate`
- `time_continuity`
- `snapshot_coverage`
- `history_baseline_ready`

### 7.3 产品规则

总览区状态来自多个信号综合，而不是单一指标：

- 内容量变化
- 互动变化
- 新增创作者变化
- 噪音率
- 样本质量

### 7.4 展示原则

- 状态必须带原因
- 置信度必须带来源
- “无数据”必须显式提示，而不是显示为 0 趋势

---

## 8. 趋势分析区

### 8.1 产品目标

回答“这类内容是否正在形成趋势，以及趋势来自哪里”。

### 8.2 展示模块

#### 8.2.1 时间趋势图

图表：

- 按时间的内容数
- 按时间的互动总量
- 按时间的新增创作者数

切换维度：

- 24h
- 7d
- 30d

#### 8.2.2 平台分布卡

字段：

- `platform_share`
- `platform_growth_rate`
- `platform_engagement_share`
- `dominant_platform`

#### 8.2.3 新内容 vs 老内容贡献卡

字段：

- `new_content_engagement_share`
- `old_content_engagement_share`
- `new_content_viral_ratio`
- `old_content_reactivation_ratio`

#### 8.2.4 异常波动卡

字段：

- `anomaly_time`
- `anomaly_type`
- `affected_platforms`
- `possible_reasons`
- `impact_level`

### 8.3 异常类型定义

- 内容量突增
- 互动量突增
- 单平台断崖
- 采集中断
- 快照缺失
- 历史基线不足
- 老内容回流造成假升温

### 8.4 产品要求

- 需要支持只看高相似样本
- 需要支持平台筛选
- 需要支持按关键词子集筛选
- 趋势图中异常点应可点击看解释

---

## 9. 关键词效果区

### 9.1 产品目标

回答“当前追踪器关键词配置是否有效、是否需要调词”。

### 9.2 展示模块

#### 9.2.1 关键词效果表

字段：

- `keyword`
- `keyword_type`
  - primary
  - secondary
  - synonym
  - negative
- `hit_content_count`
- `hit_creator_count`
- `avg_similarity`
- `avg_engagement`
- `viral_rate`
- `growth_rate`
- `noise_rate`
- `keyword_value_score`
- `recommended_action`

#### 9.2.2 高价值词榜

展示：

- 高频词
- 高互动词
- 爆款共现词

#### 9.2.3 新增词榜

展示最近窗口新出现或显著增长的词。

#### 9.2.4 噪音词榜

展示高命中但低相似、低质量或跨场景误伤的词。

#### 9.2.5 扩词与排除词建议

输出：

- 推荐加入词
- 推荐排除词
- 平台特有表达

### 9.3 推荐动作定义

- 保留
- 提升优先级
- 观察
- 加入扩展词
- 加入排除词
- 拆分为独立追踪器

### 9.4 产品要求

- 表格每行要能展开看“为什么”
- 建议动作必须能追溯到命中样本与分数

---

## 10. 内容模式拆解区

### 10.1 产品目标

回答“这些内容为什么属于同一类，以及它们内部有哪些子模式”。

### 10.2 展示模块

#### 10.2.1 结构类型分布

结构建议：

- 教程型
- 避坑型
- 清单型
- 对比型
- 经验分享型
- 情绪表达型
- 热点借势型

字段：

- `content_type`
- `content_type_share`
- `content_type_growth`
- `content_type_avg_engagement`

#### 10.2.2 Hook 模式卡

展示：

- 高频开头句式
- 高频痛点句式
- 高频反差句式
- 高频承诺句式

#### 10.2.3 受众与痛点分布卡

字段：

- `audience_distribution`
- `pain_point_distribution`
- `scene_distribution`

#### 10.2.4 转化意图卡

字段：

- `conversion_intent_distribution`
  - 种草
  - 留资
  - 引流
  - 成交
  - 纯流量

#### 10.2.5 模式簇卡

每个模式簇展示：

- `cluster_id`
- `cluster_name`
- `cluster_size`
- `cluster_share`
- `cluster_growth`
- `cluster_creator_count`
- `cluster_value_score`
- `top_representative_sample`
- `top_representative_creator`
- `cluster_reason_summary`

### 10.3 产品要求

- 模式分析不能只给一个总分
- 必须拆成主题、受众、痛点、结构、转化意图等维度
- 一个 Tracker 内允许存在多个模式簇

---

## 11. 创作者参与区

### 11.1 产品目标

回答“是否有越来越多创作者正在参与，方向是否正在扩散”。

### 11.2 展示模块

#### 11.2.1 创作者概况卡

字段：

- `creator_count_7d`
- `new_creator_count_7d`
- `repeat_creator_count_7d`
- `high_similarity_creator_count`

#### 11.2.2 头腰尾分布卡

字段：

- `head_creator_share`
- `mid_creator_share`
- `tail_creator_share`
- `head_creator_engagement_share`

#### 11.2.3 跟风扩散卡

字段：

- `creator_spread_score`
- `template_reuse_ratio`
- `structure_copy_ratio`
- `new_creator_ratio`

#### 11.2.4 高价值创作者线索卡

字段：

- `creator_id`
- `platform`
- `role`
  - originator
  - repeater
  - high_potential
  - brand_like
- `reason`
- `recommended_action`

### 11.3 产品联动

- 高相似稳定创作者可转达人发现
- 品牌/机构作者可转竞品监控

---

## 12. 代表样本与证据区

### 12.1 产品目标

帮助用户快速人工复核系统结论。

### 12.2 样本桶定义

#### 12.2.1 爆款代表样本

标准：

- 高相似
- 高互动
- 代表典型模式

#### 12.2.2 早期信号样本

标准：

- 发布时间新
- 相似度高
- 初始互动不差

#### 12.2.3 新变种样本

标准：

- 落在新模式簇
- 或结构 / 钩子显著不同

#### 12.2.4 跨平台复现样本

标准：

- 在两个以上平台出现相似模式

#### 12.2.5 风险误伤样本

标准：

- 命中关键词
- 但低相似或明显跨场景

### 12.3 单条样本字段

- `platform`
- `platform_post_id`
- `author_id`
- `title`
- `publish_time`
- `engagement_summary`
- `similarity_score`
- `matched_keywords`
- `matched_patterns`
- `sample_bucket`
- `snapshot_delta`
- `reason_summary`

### 12.4 产品要求

- 每个样本都要能说明为什么在当前分组中
- 要支持从样本跳转到原文、快照、来源任务
- 不能只展示热门样本

---

## 13. 结论与动作区

### 13.1 产品目标

将分析结果转换为具体动作。

### 13.2 展示模块

#### 13.2.1 结论卡

字段：

- `decision_type`
- `decision_confidence`
- `decision_reason_summary`
- `supporting_evidence_count`
- `blocking_risks`

#### 13.2.2 推荐动作卡

动作清单：

- 补采最近 7 天
- 自动扩词
- 加入排除词
- 创建达人发现任务
- 加入竞品监控
- 设置提醒
- 降级观察
- 拆分追踪器

#### 13.2.3 风险说明卡

字段：

- `sample_insufficient`
- `platform_bias`
- `noise_too_high`
- `snapshot_missing`
- `history_not_ready`

### 13.3 产品要求

- 结论必须具体
- 动作必须可执行
- 动作必须有原因
- 样本不足时优先推荐补采

---

## 14. 状态、空态、异常态定义

### 14.1 页面主状态

- `ready`
- `loading`
- `stale`
- `partial_ready`
- `error`

### 14.2 空态类型

- 无 Tracker
- 无关键词
- 无候选样本
- 无历史快照
- 无历史基线

### 14.3 异常态类型

- 采集失败
- 分析失败
- 平台数据中断
- 快照延迟
- 结果过期

### 14.4 边界态

- 单平台极高热但跨平台不扩散
- 单条内容超级爆款拉高均值
- 命中词过泛导致误伤
- 历史窗口不足导致不可判定

---

## 15. P0 / P1 / P2 拆分

### 15.1 P0

- 追踪总览区
- 趋势分析基础版
- 关键词效果区
- 模式拆解基础版
- 创作者参与基础版
- 代表样本矩阵
- 结论与动作区
- 风险与样本质量

### 15.2 P1

- 模式簇聚类
- 快照变化分析
- 平台迁移趋势
- 评论反馈摘要
- 新变种识别

### 15.3 P2

- 自动扩词
- 自动降噪
- 自动拆分追踪器
- 告警与订阅
- 多模态分析

---

## 16. 验收标准

页面满足以下条件才算可用：

- 用户可以在 10 秒内读懂 Tracker 当前状态
- 用户可以通过至少 2 条证据理解状态来源
- 用户可以区分“真实衰减”和“数据异常”
- 用户可以根据页面结果采取明确动作
- 后端分析结果可由规则和字段复现，不依赖前端临时拼装
