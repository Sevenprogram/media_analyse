# 内容追踪后端接口与聚合任务设计

- 日期：2026-05-23
- 范围：内容追踪分析页所需 API、分析快照、聚合任务、重算策略、数据表建议、开发顺序
- 关联文档：
  - `docs/superpowers/specs/2026-05-23-content-tracking-analysis-prd.md`
  - `docs/superpowers/specs/2026-05-23-content-tracking-analysis-data-model.md`

## 1. 设计目标

本设计文档回答以下问题：

1. 后端需要提供哪些接口
2. 这些接口返回什么结构
3. 聚合任务如何组织
4. 何时全量重算、何时增量更新
5. 需要哪些分析快照表或派生表
6. 开发应该如何拆阶段

目标不是一次性做完所有智能能力，而是先建立一个可解释、可扩展、可重算的分析流水线。

## 2. 总体架构

建议将内容追踪分析拆为三条链路：

```text
A. 采集链路
Tracker 配置
-> 内容抓取
-> 快照写入

B. 分析链路
Tracker 配置 + 内容样本 + 快照
-> candidate_set
-> 指标聚合
-> decision snapshot

C. 查询链路
分析快照
-> API
-> 页面
```

这三条链路解耦的原因：

- 查询接口不直接压原始表
- 前端不会因实时计算而变慢
- 后续可复算历史快照
- 可支持“上一次分析结果”和“当前最新结果”共存

## 3. 建议数据产物

建议引入 6 类持久化分析产物：

1. `tracker_analysis_run`
2. `tracker_candidate_sample`
3. `tracker_keyword_metric_snapshot`
4. `tracker_pattern_metric_snapshot`
5. `tracker_creator_metric_snapshot`
6. `tracker_analysis_snapshot`

---

## 4. 表设计建议

### 4.1 tracker_analysis_run

用途：

- 记录一次分析任务的运行信息

字段建议：

- `id`
- `tracker_id`
- `run_type`
  - scheduled
  - manual
  - backfill
  - config_change
- `status`
  - pending
  - running
  - completed
  - failed
- `analysis_window_start`
- `analysis_window_end`
- `started_at`
- `finished_at`
- `input_post_count`
- `input_snapshot_count`
- `error_message`

### 4.2 tracker_candidate_sample

用途：

- 保存一次分析对每条样本的归因结果

字段建议：

- `analysis_run_id`
- `tracker_id`
- `platform`
- `platform_post_id`
- `author_id`
- `publish_time`
- `similarity_score`
- `candidate_level`
  - L1
  - L2
  - L3
- `sample_bucket`
  - viral_representative
  - early_signal
  - new_variant
  - cross_platform_repeat
  - risk_false_positive
- `matched_keywords_json`
- `keyword_hits_detail_json`
- `fingerprint_json`
- `pattern_cluster_id`
- `engagement_total`
- `snapshot_delta_json`

### 4.3 tracker_keyword_metric_snapshot

用途：

- 保存每次分析中各关键词指标

字段建议：

- `analysis_run_id`
- `tracker_id`
- `keyword`
- `keyword_type`
- `hit_content_count`
- `hit_creator_count`
- `avg_similarity`
- `avg_engagement`
- `viral_rate`
- `growth_rate`
- `noise_rate`
- `keyword_value_score`
- `recommended_action`

### 4.4 tracker_pattern_metric_snapshot

用途：

- 保存模式簇和模式结构指标

字段建议：

- `analysis_run_id`
- `tracker_id`
- `pattern_cluster_id`
- `cluster_name`
- `cluster_size`
- `cluster_share`
- `cluster_growth`
- `cluster_creator_count`
- `cluster_value_score`
- `top_content_type`
- `top_audience`
- `top_pain_point`
- `top_conversion_intent`

### 4.5 tracker_creator_metric_snapshot

用途：

- 保存创作者扩散指标与创作者线索

字段建议：

- `analysis_run_id`
- `tracker_id`
- `creator_id`
- `platform`
- `role`
- `post_count_in_tracker`
- `avg_similarity`
- `avg_engagement`
- `is_brand_like`
- `recommended_action`

### 4.6 tracker_analysis_snapshot

用途：

- 保存页面主查询对象

字段建议：

- `analysis_run_id`
- `tracker_id`
- `status`
- `decision_confidence`
- `summary_json`
- `overview_json`
- `trends_json`
- `keywords_json`
- `patterns_json`
- `creators_json`
- `samples_json`
- `risks_json`
- `decisions_json`
- `meta_json`
- `created_at`

说明：

- 页面主接口优先从该表读
- 大对象字段可先用 JSON，后续再拆表优化

---

## 5. API 设计

建议将 API 分为 3 组：

1. Tracker 配置与操作接口
2. Tracker 分析查询接口
3. Tracker 分析执行接口

---

## 6. Tracker 配置与操作接口

### 6.1 创建追踪器

`POST /api/content-tracking/trackers`

请求：

```json
{
  "name": "string",
  "platforms": ["xhs", "dy"],
  "included_keywords": ["string"],
  "excluded_keywords": ["string"],
  "time_window_days": 7
}
```

返回：

```json
{
  "tracker": {}
}
```

### 6.2 获取追踪器列表

`GET /api/content-tracking/trackers`

参数：

- `status`
- `enabled_only`
- `project_id` 可选

返回建议包含轻量状态摘要：

- 最近分析时间
- 当前状态
- 样本质量

### 6.3 获取单个追踪器配置

`GET /api/content-tracking/trackers/{tracker_id}`

### 6.4 更新追踪器

`PATCH /api/content-tracking/trackers/{tracker_id}`

支持更新：

- 名称
- 平台
- 关键词
- 排除词
- 时间窗口
- 状态

### 6.5 暂停 / 恢复追踪器

`POST /api/content-tracking/trackers/{tracker_id}/pause`

`POST /api/content-tracking/trackers/{tracker_id}/resume`

---

## 7. Tracker 分析查询接口

### 7.1 获取追踪器主分析页数据

`GET /api/content-tracking/trackers/{tracker_id}/analysis`

参数建议：

- `range=24h|7d|30d`
- `platform=xhs,dy`
- `keyword=...`
- `min_similarity=...`
- `refresh=false|true`

返回结构建议：

```json
{
  "tracker": {},
  "overview": {},
  "trends": {},
  "keywords": {},
  "patterns": {},
  "creators": {},
  "samples": {},
  "risks": {},
  "decisions": {},
  "meta": {
    "analysis_run_id": 123,
    "analysis_time": "2026-05-23T10:00:00Z",
    "range": "7d",
    "data_freshness": "fresh"
  }
}
```

说明：

- 默认返回最新成功分析结果
- `refresh=true` 只触发后台分析，不建议同步阻塞接口太久

### 7.2 获取趋势明细

`GET /api/content-tracking/trackers/{tracker_id}/analysis/trends`

返回：

- 时间序列数组
- 异常点数组
- 平台对比数组

适合后续单独图表重载，不必每次拉全量主分析页。

### 7.3 获取关键词分析明细

`GET /api/content-tracking/trackers/{tracker_id}/analysis/keywords`

参数：

- `sort_by=value_score|growth|noise|hits`
- `keyword_type`
- `limit`

### 7.4 获取模式分析明细

`GET /api/content-tracking/trackers/{tracker_id}/analysis/patterns`

参数：

- `cluster_id`
- `content_type`
- `audience`
- `limit`

### 7.5 获取创作者分析明细

`GET /api/content-tracking/trackers/{tracker_id}/analysis/creators`

参数：

- `role`
- `is_brand_like`
- `limit`

### 7.6 获取代表样本明细

`GET /api/content-tracking/trackers/{tracker_id}/analysis/samples`

参数：

- `bucket=viral_representative|early_signal|new_variant|cross_platform_repeat|risk_false_positive`
- `platform`
- `cluster_id`
- `keyword`
- `limit`

### 7.7 获取分析运行历史

`GET /api/content-tracking/trackers/{tracker_id}/analysis/history`

返回：

- 历次分析运行
- 历次状态变化
- 主要指标变化摘要

用于后续状态变化回溯。

---

## 8. Tracker 分析执行接口

### 8.1 触发分析

`POST /api/content-tracking/trackers/{tracker_id}/analysis:run`

请求：

```json
{
  "run_type": "manual",
  "range": "7d",
  "force_recollect": false
}
```

返回：

```json
{
  "analysis_run_id": 123,
  "status": "pending"
}
```

### 8.2 查询分析运行状态

`GET /api/content-tracking/analysis-runs/{analysis_run_id}`

返回：

- 状态
- 进度
- 输入样本数
- 错误信息

### 8.3 触发补采

`POST /api/content-tracking/trackers/{tracker_id}/backfill`

请求：

```json
{
  "days": 7,
  "platforms": ["xhs", "dy"],
  "keywords_override": ["..."]
}
```

### 8.4 触发重新分析

`POST /api/content-tracking/trackers/{tracker_id}/recompute`

用于：

- 调整公式
- 修复历史任务
- 回算历史状态

---

## 9. 聚合任务设计

建议拆成 5 个后台任务。

### 9.1 任务一：候选样本构建

任务名建议：

- `tracker_candidate_builder`

输入：

- tracker 配置
- 时间窗口内内容样本

处理：

- 计算关键词命中
- 计算相似度
- 打 candidate level
- 生成 fingerprint
- 生成 sample_bucket

输出：

- `tracker_candidate_sample`

### 9.2 任务二：关键词指标聚合

任务名建议：

- `tracker_keyword_aggregator`

输入：

- `tracker_candidate_sample`

处理：

- 聚合命中量
- 聚合平均相似度
- 聚合互动
- 计算噪音率
- 计算关键词价值分
- 生成推荐动作

输出：

- `tracker_keyword_metric_snapshot`

### 9.3 任务三：模式与创作者指标聚合

任务名建议：

- `tracker_pattern_creator_aggregator`

输入：

- `tracker_candidate_sample`

处理：

- 聚合模式簇
- 聚合结构占比
- 聚合创作者扩散
- 识别高价值创作者

输出：

- `tracker_pattern_metric_snapshot`
- `tracker_creator_metric_snapshot`

### 9.4 任务四：趋势与质量评估

任务名建议：

- `tracker_trend_quality_aggregator`

输入：

- 时间窗口内容样本
- 快照
- 任务日志

处理：

- 计算内容增速
- 计算互动增速
- 计算新增创作者趋势
- 计算样本质量
- 计算噪音率
- 识别异常

输出：

- trend metrics 中间结果
- quality metrics 中间结果

### 9.5 任务五：决策快照生成

任务名建议：

- `tracker_decision_snapshot_builder`

输入：

- keyword metrics
- pattern metrics
- creator metrics
- trend metrics
- quality metrics

处理：

- 计算状态
- 计算置信度
- 生成动作建议
- 组装页面 JSON

输出：

- `tracker_analysis_snapshot`

---

## 10. 增量更新与全量重算策略

### 10.1 增量更新

适用于：

- 新内容进入
- 新快照写入
- 新创作者资料补全

建议：

- 只重算受影响 Tracker
- 只更新最近窗口
- 重用未变化的候选样本

### 10.2 全量重算

适用于：

- 相似度公式变更
- 模式标签规则变更
- fingerprint 逻辑变更
- 历史修复

建议：

- 保留历史 `analysis_run`
- 新结果覆盖“最新快照”
- 支持按 Tracker 或按日期批量重算

### 10.3 配置变更触发策略

当以下字段变化时建议自动触发重新分析：

- `platforms`
- `included_keywords`
- `excluded_keywords`
- `time_window_days`

策略：

- 小变更：直接重算分析
- 大变更：先补采再重算

---

## 11. 状态流转设计

建议主状态：

- `pending`
- `collecting`
- `analyzing`
- `ready`
- `stale`
- `partial_ready`
- `failed`

页面状态建议来自最新 `tracker_analysis_snapshot` 与 `tracker_analysis_run` 组合判断：

- 最新分析成功且新鲜：`ready`
- 最新分析成功但采集过旧：`stale`
- 采集失败但有历史结果：`partial_ready`
- 无可用结果：`failed`

---

## 12. 指标缓存与存储策略

### 12.1 缓存层

建议主分析页按以下 key 缓存：

```text
tracker_analysis:{tracker_id}:{range}:{platform_hash}:{keyword_hash}:{min_similarity}
```

### 12.2 缓存失效时机

- 新分析快照生成
- Tracker 配置更新
- 强制刷新

### 12.3 存储建议

- 原始样本与快照：数据库事实表
- 中间层指标：快照表
- 大对象展示结构：JSON 快照

先保证可用与可解释，再考虑进一步拆分和列式优化。

---

## 13. API 错误处理设计

### 13.1 主接口错误分层

#### 业务可恢复错误

- 无样本
- 历史不足
- 平台数据中断
- 快照不足

应返回：

- HTTP 200
- `risks` 内显式说明
- `status` 降级

#### 分析执行错误

- 当前分析运行失败
- 某个聚合任务失败

应返回：

- HTTP 200 或 202
- 返回最近可用快照
- `meta.data_freshness = stale`

#### 真正不可恢复错误

- tracker 不存在
- 权限错误
- 参数错误

应返回标准 4xx。

---

## 14. 开发阶段建议

### 14.1 Phase 1：基础可用

目标：

- 主分析页有稳定返回
- 能显示状态、趋势、关键词、样本、动作

交付：

- `tracker_analysis_run`
- `tracker_candidate_sample`
- `tracker_analysis_snapshot`
- 主分析页 API
- 手动触发分析 API

### 14.2 Phase 2：解释增强

目标：

- 加入模式簇、创作者扩散、噪音分析

交付：

- `tracker_keyword_metric_snapshot`
- `tracker_pattern_metric_snapshot`
- `tracker_creator_metric_snapshot`
- 分模块查询 API

### 14.3 Phase 3：自动化增强

目标：

- 自动补采、自动重算、状态提醒

交付：

- backfill API
- recompute API
- 定时任务
- 状态变化推送

---

## 15. 推荐开发顺序

按实际依赖顺序：

1. 规范化样本输入
2. 候选样本构建
3. 主分析页快照结构
4. 趋势与样本质量
5. 关键词分析
6. 模式与创作者分析
7. 决策引擎
8. 历史回溯与重算

原因：

- 主页面最先需要稳定的分析骨架
- 趋势与样本质量是所有结论底座
- 模式和创作者是第二层增强

---

## 16. 验收标准

后端方案满足以下条件才可进入页面开发：

- 单个 Tracker 可返回稳定的主分析 JSON
- 所有状态均有来源字段和公式映射
- 最近分析失败时仍可返回最后一次可用结果
- 支持手动触发分析与补采
- 支持按配置变更重新分析
- 可区分采集问题、分析问题和业务无样本
