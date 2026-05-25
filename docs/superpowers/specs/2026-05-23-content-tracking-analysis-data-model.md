# 内容追踪分析数据模型设计

- 日期：2026-05-23
- 范围：内容追踪分析页的分析输入、中间层、公式、状态判定、风险约束、输出结构
- 关联文档：
  - `docs/superpowers/specs/2026-05-23-content-tracking-analysis-prd.md`
  - `docs/superpowers/specs/2026-05-23-content-tracking-backend-api-and-aggregation.md`

## 1. 设计目标

本设计文档解决以下问题：

1. 内容追踪页依赖哪些原始数据
2. 什么内容算 Tracker 的候选样本
3. 相似度、趋势、样本质量、噪音率、扩散度怎么计算
4. 最终状态与结论如何从中间指标得到
5. 后端应该输出什么结构给前端和其他消费方

本设计优先使用：

- 可解释规则
- 可复现公式
- 分层中间结果
- 不把复杂逻辑直接塞进前端

## 2. 数据分层

建议分析链路分 4 层：

```text
L0 原始层
-> L1 规范化层
-> L2 分析中间层
-> L3 决策输出层
```

### 2.1 L0 原始层

- 追踪器配置
- 内容样本
- 内容快照
- 创作者资料
- 任务执行记录

### 2.2 L1 规范化层

- 标准化关键词命中
- 标准化互动指标
- 标准化结构标签
- 标准化创作者角色

### 2.3 L2 分析中间层

- candidate_set
- keyword_metrics
- trend_metrics
- pattern_metrics
- creator_metrics
- quality_metrics
- noise_metrics

### 2.4 L3 决策输出层

- tracker_status
- decision_confidence
- recommended_actions
- evidence_refs

## 3. 核心实体定义

### 3.1 Tracker

字段：

- `tracker_id`
- `name`
- `platforms[]`
- `included_keywords[]`
- `excluded_keywords[]`
- `time_window_days`
- `status`
- `created_from`
- `created_at`
- `updated_at`

### 3.2 PostRecord

字段：

- `platform`
- `platform_post_id`
- `author_id`
- `title`
- `content`
- `publish_time`
- `url`
- `engagement_json`
- `source_keyword`
- `tags`
- `job_id`

### 3.3 PostSnapshot

字段：

- `platform`
- `platform_post_id`
- `snapshot_time`
- `like_count`
- `comment_count`
- `collect_count`
- `share_count`
- `total_engagement`

### 3.4 CreatorProfile

字段：

- `platform`
- `author_id`
- `follower_count`
- `recent_post_count`
- `avg_engagement`
- `creator_type`
- `is_brand_like`

### 3.5 AnalysisArtifact

字段：

- `similarity_score`
- `matched_keywords`
- `keyword_hits_detail`
- `fingerprint`
- `pattern_cluster_id`
- `sample_quality_flags`

## 4. 分析中间层结构

建议所有分析先拆成 7 个中间层对象：

1. `candidate_set`
2. `keyword_metrics`
3. `trend_metrics`
4. `pattern_metrics`
5. `creator_metrics`
6. `quality_metrics`
7. `decision_metrics`

这样做的原因：

- 便于调试公式
- 便于部分重算
- 便于后续 A/B 调整权重
- 便于其他页面复用

---

## 5. candidate_set：候选样本模型

### 5.1 目标

定义“什么内容算这个 Tracker 的样本”。

### 5.2 基础得分组成

令：

- `K` = 关键词匹配得分
- `P` = 模式相似得分
- `E` = 互动质量修正
- `N` = 噪音惩罚

则：

```text
similarity_score_raw = 0.45 * K + 0.40 * P + 0.15 * E - N
similarity_score = clamp(similarity_score_raw, 0, 100)
```

### 5.3 关键词匹配得分 K

令：

- `w_i` 为第 i 个命中词的权重
- `W` 为 Tracker 所有可匹配词权重总和

则：

```text
K = 100 * sum(w_i) / max(W, 1)
```

权重建议：

- primary: 1.0
- secondary: 0.7
- synonym: 0.5
- negative: 不参与正分，参与惩罚

### 5.4 模式相似得分 P

将相似拆成 5 维：

- `topic_sim`
- `audience_sim`
- `pain_point_sim`
- `structure_sim`
- `conversion_intent_sim`

则：

```text
P = 0.25 * topic_sim
  + 0.20 * audience_sim
  + 0.20 * pain_point_sim
  + 0.20 * structure_sim
  + 0.15 * conversion_intent_sim
```

各项范围统一在 `[0, 100]`。

### 5.5 互动质量修正 E

令：

- `engagement_total = like + comment + collect + share`
- `engagement_cap` 为平台或项目级上限基准

则：

```text
E = min(100, log(1 + engagement_total) / log(1 + engagement_cap) * 100)
```

说明：

- 使用对数压缩，避免单条超级爆款拉偏全局
- 后续可按平台单独设置 cap

### 5.6 噪音惩罚 N

```text
N = excluded_keyword_penalty
  + cross_scene_penalty
  + weak_structure_penalty
  + low_text_quality_penalty
```

建议：

- 命中排除词：固定高惩罚
- 结构和受众明显偏离：中惩罚
- 文本过短且仅靠单词命中：中惩罚

### 5.7 样本分层

- `L1`: `similarity_score >= 75`
- `L2`: `55 <= similarity_score < 75`
- `L3`: `similarity_score < 55` 且有关键词命中

用途：

- L1：核心分析样本
- L2：边界扩展样本
- L3：噪音分析样本

### 5.8 代表样本分桶

根据额外规则将候选样本放入：

- `viral_representative`
- `early_signal`
- `new_variant`
- `cross_platform_repeat`
- `risk_false_positive`

---

## 6. keyword_metrics：关键词分析模型

### 6.1 目标

衡量每个关键词“带来的是真实价值还是噪音”。

### 6.2 每个关键词的基础字段

对每个关键词 `kw` 计算：

- `hit_content_count(kw)`
- `hit_creator_count(kw)`
- `avg_similarity(kw)`
- `avg_engagement(kw)`
- `viral_rate(kw)`
- `growth_rate(kw)`
- `noise_rate(kw)`
- `co_occurrence_with_primary(kw)`
- `keyword_value_score(kw)`

### 6.3 公式

#### 命中内容数

```text
hit_content_count(kw) = count(distinct content_id where kw matched)
```

#### 命中创作者数

```text
hit_creator_count(kw) = count(distinct author_id where kw matched)
```

#### 平均相似度

```text
avg_similarity(kw) = avg(similarity_score of matched samples)
```

#### 平均互动

```text
avg_engagement(kw) = avg(engagement_total of matched samples)
```

#### 爆款关联率

```text
viral_rate(kw) = viral_sample_count(kw) / max(hit_content_count(kw), 1)
```

#### 增长率

```text
growth_rate(kw) = (current_hits - previous_hits) / max(previous_hits, 1)
```

#### 噪音率

```text
noise_rate(kw) = l3_hits(kw) / max(total_hits(kw), 1)
```

### 6.4 关键词价值分

```text
keyword_value_score(kw)
= 0.20 * normalized(hit_content_count)
+ 0.25 * normalized(avg_similarity)
+ 0.20 * normalized(avg_engagement)
+ 0.20 * normalized(viral_rate)
+ 0.15 * normalized(growth_rate)
- 0.25 * normalized(noise_rate)
```

### 6.5 扩词建议规则

满足以下条件时可进入建议扩词：

- 最近窗口命中量增长明显
- 多数命中出现在 L1 样本
- 平均互动不低于 Tracker 中位数
- 与主词共现率高
- 不是排除词

### 6.6 排除词建议规则

满足以下条件时可进入建议排除词：

- 命中量高
- 噪音率高
- 与高相似样本共现弱
- 常出现在跨场景样本中

---

## 7. trend_metrics：趋势分析模型

### 7.1 目标

判断“正在升温、稳定还是衰减”，并识别是假升温还是真扩散。

### 7.2 时间窗口

建议至少支持：

- 24h
- 7d
- 30d

可按日或按小时聚合。

### 7.3 基础聚合字段

对时间桶 `t` 计算：

- `content_count_t`
- `engagement_total_t`
- `new_creator_count_t`
- `viral_count_t`
- `platform_count_t`

### 7.4 基础增速

```text
content_growth_rate
= (current_content_count - previous_content_count)
 / max(previous_content_count, 1)
```

```text
engagement_growth_rate
= (current_engagement_total - previous_engagement_total)
 / max(previous_engagement_total, 1)
```

```text
new_creator_growth_rate
= (current_new_creator_count - previous_new_creator_count)
 / max(previous_new_creator_count, 1)
```

### 7.5 爆款占比

```text
viral_ratio = viral_sample_count / max(total_sample_count, 1)
```

```text
viral_ratio_change = current_viral_ratio - previous_viral_ratio
```

### 7.6 新内容贡献

```text
new_content_engagement_share
= new_content_incremental_engagement
 / max(total_incremental_engagement, 1)
```

### 7.7 老内容回流占比

```text
old_content_reactivation_ratio
= old_content_incremental_engagement
 / max(total_incremental_engagement, 1)
```

### 7.8 平台集中度

```text
platform_concentration
= top1_platform_sample_count
 / max(total_sample_count, 1)
```

说明：

- 值越高，越依赖单平台
- 过高时应降低“全局趋势”结论强度

### 7.9 趋势强度分

```text
trend_strength_score
= 0.35 * normalized(content_growth_rate)
+ 0.35 * normalized(engagement_growth_rate)
+ 0.20 * normalized(new_creator_growth_rate)
+ 0.10 * normalized(viral_ratio_change)
```

### 7.10 趋势状态建议

- `rising`
  - 趋势强度高
  - 样本质量至少中
- `stable`
  - 指标波动低
  - 新旧样本都稳定
- `declining`
  - 内容、互动、创作者至少两项持续下降
- `undetermined`
  - 数据或历史不足

---

## 8. pattern_metrics：模式分析模型

### 8.1 目标

把“相似内容”提升为“相似模式”。

### 8.2 抽取维度

每个候选样本应至少抽取：

- `topic`
- `audience`
- `pain_point`
- `scene`
- `content_type`
- `hook_pattern`
- `conversion_intent`

### 8.3 结构类型占比

```text
content_type_share(type)
= sample_count(type) / max(total_sample_count, 1)
```

### 8.4 结构类型增速

```text
content_type_growth(type)
= (current_count(type) - previous_count(type))
 / max(previous_count(type), 1)
```

### 8.5 模式稳定度

```text
pattern_stability
= top3_cluster_sample_count
 / max(total_sample_count, 1)
```

解释：

- 越高表示模式越集中
- 越低表示 Tracker 内部方向更分散

### 8.6 模式扩散度

```text
pattern_spread(cluster)
= creator_count(cluster)
 / max(total_creator_count, 1)
```

### 8.7 变种率

```text
pattern_variant_rate
= current_new_cluster_count
 / max(current_total_cluster_count, 1)
```

### 8.8 模式簇价值分

```text
cluster_value_score
= 0.30 * normalized(cluster_size)
+ 0.25 * normalized(cluster_engagement_avg)
+ 0.20 * normalized(cluster_growth)
+ 0.15 * normalized(cluster_creator_count)
+ 0.10 * normalized(pattern_spread)
```

---

## 9. creator_metrics：创作者扩散模型

### 9.1 目标

判断“是少数账号带动，还是方向正在扩散”。

### 9.2 基础字段

- `creator_count`
- `new_creator_count`
- `repeat_creator_count`
- `top_creator_content_share`
- `high_similarity_creator_count`

### 9.3 新增创作者占比

```text
new_creator_ratio
= current_new_creator_count
 / max(current_creator_count, 1)
```

### 9.4 复发创作者率

```text
repeat_creator_ratio
= repeat_creator_count
 / max(total_creator_count, 1)
```

### 9.5 头部依赖度

```text
top_creator_dependency
= top10_creator_sample_count
 / max(total_sample_count, 1)
```

### 9.6 创作者扩散分

```text
creator_spread_score
= 0.40 * normalized(new_creator_ratio)
+ 0.35 * normalized(repeat_creator_ratio)
+ 0.25 * (1 - normalized(top_creator_dependency))
```

说明：

- 新增创作者多、复发创作者高、头部依赖低时，说明扩散更真实

---

## 10. quality_metrics：样本质量模型

### 10.1 目标

判断当前结论是否足够可信。

### 10.2 输入字段

- `content_count_7d`
- `creator_count_7d`
- `platform_count`
- `time_continuity`
- `collection_success_rate`
- `snapshot_coverage`
- `history_baseline_ready`

### 10.3 时间连续性

```text
time_continuity
= active_time_buckets
 / max(expected_time_buckets, 1)
```

### 10.4 快照覆盖率

```text
snapshot_coverage
= sample_with_2plus_snapshots
 / max(total_sample_count, 1)
```

### 10.5 样本质量分

```text
sample_quality_score
= 0.22 * normalized(content_count_7d)
+ 0.18 * normalized(creator_count_7d)
+ 0.12 * normalized(platform_count)
+ 0.16 * normalized(time_continuity)
+ 0.14 * normalized(collection_success_rate)
+ 0.10 * normalized(snapshot_coverage)
+ 0.08 * normalized(history_baseline_ready)
```

### 10.6 等级建议

- `high`: `score >= 80`
- `medium`: `60 <= score < 80`
- `low`: `40 <= score < 60`
- `insufficient`: `score < 40`

---

## 11. noise_metrics：噪音分析模型

### 11.1 目标

识别“为什么这个 Tracker 会看起来有数据，但其实不可用”。

### 11.2 噪音来源

- 关键词过泛
- 场景误伤
- 平台表达差异
- 文本残缺
- 排除词配置不足

### 11.3 Tracker 噪音率

```text
tracker_noise_rate
= l3_sample_count
 / max(total_matched_sample_count, 1)
```

### 11.4 跨场景误伤率

```text
cross_scene_noise_rate
= cross_scene_false_positive_count
 / max(total_matched_sample_count, 1)
```

### 11.5 噪音高判断建议

以下任一满足：

- `tracker_noise_rate` 高于阈值
- `cross_scene_noise_rate` 高于阈值
- 主词大多命中低相似样本
- 排除词漏拦截明显

则将 Tracker 标记为：

- `noise_high`

---

## 12. decision_metrics：状态与动作决策模型

### 12.1 输入项

- `trend_strength_score`
- `sample_quality_score`
- `tracker_noise_rate`
- `creator_spread_score`
- `pattern_variant_rate`
- `platform_concentration`
- `history_baseline_ready`

### 12.2 状态判定建议

令：

- `T = trend_strength_score`
- `Q = sample_quality_score`
- `N = tracker_noise_rate`
- `C = creator_spread_score`

建议规则：

```text
if Q < 40:
    status = "sample_insufficient"
elif N > noise_threshold:
    status = "noise_high"
elif T is high and C is high:
    status = "rising"
elif T is medium and Q >= 60:
    status = "stable"
elif T is low and downward_signals >= 2:
    status = "declining"
else:
    status = "watching"
```

### 12.3 结论置信度

令：

- `S = signal_consistency`

其中 `signal_consistency` 表示：

- 趋势
- 创作者扩散
- 模式结构

三类信号是否方向一致。

```text
decision_confidence
= 0.45 * normalized(sample_quality_score)
+ 0.20 * normalized(1 - tracker_noise_rate)
+ 0.20 * normalized(history_baseline_ready)
+ 0.15 * normalized(signal_consistency)
```

### 12.4 推荐动作规则

#### 补采

条件：

- `sample_quality_score` 低
- 或历史基线不足

#### 调词 / 加排除词

条件：

- 噪音高
- 高命中词集中在 L3

#### 继续追踪

条件：

- 趋势高
- 样本质量中高
- 风险可控

#### 转达人发现

条件：

- 高相似创作者持续参与
- 创作者扩散高

#### 转竞品监控

条件：

- `is_brand_like` 作者或品牌账户频繁出现

#### 拆分追踪器

条件：

- 模式簇明显分叉
- `pattern_variant_rate` 高
- 多个簇都具备足够样本

---

## 13. 输出结构建议

最终分析结果建议输出为：

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
  "meta": {}
}
```

各部分都应包含：

- `summary`
- `metrics`
- `status`
- `confidence`
- `evidence_refs`

## 14. 模型实现顺序建议

开发顺序建议：

1. `candidate_set`
2. `quality_metrics`
3. `trend_metrics`
4. `keyword_metrics`
5. `pattern_metrics`
6. `creator_metrics`
7. `decision_metrics`

原因：

- candidate_set 是所有分析底座
- quality 与 trend 决定页面最早可用版本
- 其余模块可在此基础上逐步增强

## 15. 关键约束

- 所有公式必须可回放
- 所有状态必须可解释
- 所有推荐动作必须有来源字段
- 前端不负责拼接复杂规则
- API 返回结构按分析语义组织，不按数据库表结构组织
