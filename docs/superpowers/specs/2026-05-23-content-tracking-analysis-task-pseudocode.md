# 内容追踪分析任务伪代码与流程设计

- 日期：2026-05-23
- 范围：分析任务编排、伪代码、关键函数拆分、重算与失败恢复策略
- 关联文档：
  - `docs/superpowers/specs/2026-05-23-content-tracking-analysis-data-model.md`
  - `docs/superpowers/specs/2026-05-23-content-tracking-backend-api-and-aggregation.md`

## 1. 总体流程

```text
加载 tracker 配置
-> 拉取时间窗口内候选原始内容
-> 构建 candidate_set
-> 聚合 keyword_metrics
-> 聚合 trend_metrics / quality_metrics / noise_metrics
-> 聚合 pattern_metrics / creator_metrics
-> 生成 decision_metrics
-> 组装 tracker_analysis_snapshot
-> 持久化
```

## 2. 主流程伪代码

```text
function run_tracker_analysis(tracker_id, run_type, range):
    run = create_analysis_run(tracker_id, run_type, range)
    mark_run_running(run)

    try:
        tracker = load_tracker(tracker_id)
        inputs = load_analysis_inputs(tracker, range)

        candidate_set = build_candidate_set(tracker, inputs.posts, inputs.snapshots)
        persist_candidate_set(run.id, tracker.id, candidate_set)

        keyword_metrics = aggregate_keyword_metrics(tracker, candidate_set)
        persist_keyword_metrics(run.id, tracker.id, keyword_metrics)

        trend_metrics = aggregate_trend_metrics(tracker, candidate_set, inputs.snapshots)
        quality_metrics = aggregate_quality_metrics(tracker, candidate_set, inputs.jobs, inputs.snapshots)
        noise_metrics = aggregate_noise_metrics(tracker, candidate_set)

        pattern_metrics = aggregate_pattern_metrics(tracker, candidate_set)
        persist_pattern_metrics(run.id, tracker.id, pattern_metrics)

        creator_metrics = aggregate_creator_metrics(tracker, candidate_set, inputs.creators)
        persist_creator_metrics(run.id, tracker.id, creator_metrics)

        decision_metrics = build_decision_metrics(
            tracker=tracker,
            candidate_set=candidate_set,
            keyword_metrics=keyword_metrics,
            trend_metrics=trend_metrics,
            quality_metrics=quality_metrics,
            noise_metrics=noise_metrics,
            pattern_metrics=pattern_metrics,
            creator_metrics=creator_metrics
        )

        snapshot = build_analysis_snapshot(
            tracker=tracker,
            candidate_set=candidate_set,
            keyword_metrics=keyword_metrics,
            trend_metrics=trend_metrics,
            quality_metrics=quality_metrics,
            noise_metrics=noise_metrics,
            pattern_metrics=pattern_metrics,
            creator_metrics=creator_metrics,
            decision_metrics=decision_metrics
        )

        persist_analysis_snapshot(run.id, tracker.id, snapshot)
        mark_run_completed(run, snapshot_meta)
    except Exception as exc:
        mark_run_failed(run, exc)
        raise
```

## 3. 输入加载伪代码

```text
function load_analysis_inputs(tracker, range):
    window = resolve_window(range, tracker.time_window_days)
    posts = list_posts(platforms=tracker.platforms, start=window.start, end=window.end)
    snapshots = list_post_snapshots(platforms=tracker.platforms, start=window.start, end=window.end)
    creators = list_creator_profiles(platforms=tracker.platforms)
    jobs = list_related_jobs(tracker.id, window)

    return {
        posts: posts,
        snapshots: snapshots,
        creators: creators,
        jobs: jobs,
        window: window
    }
```

注意：

- P0 阶段创作者资料允许缺失
- 若快照不足，不阻断分析，只在 quality / risks 中降级

## 4. candidate_set 构建伪代码

```text
function build_candidate_set(tracker, posts, snapshots):
    result = []

    for post in posts:
        keyword_score = compute_keyword_match_score(tracker, post)
        fingerprint = build_or_load_fingerprint(post)
        pattern_score = compute_pattern_similarity(tracker, post, fingerprint)
        engagement_score = compute_engagement_score(post)
        noise_penalty = compute_noise_penalty(tracker, post, fingerprint)

        similarity_score = clamp(
            0.45 * keyword_score +
            0.40 * pattern_score +
            0.15 * engagement_score -
            noise_penalty,
            0,
            100
        )

        candidate_level = classify_candidate_level(similarity_score)
        sample_bucket = classify_sample_bucket(post, similarity_score, snapshots, fingerprint)

        result.append({
            post_id: post.platform_post_id,
            platform: post.platform,
            author_id: post.author_id,
            similarity_score: similarity_score,
            candidate_level: candidate_level,
            sample_bucket: sample_bucket,
            matched_keywords: extract_matched_keywords(tracker, post),
            fingerprint: fingerprint,
            engagement_total: extract_engagement_total(post),
            snapshot_delta: calculate_snapshot_delta(post, snapshots)
        })

    return result
```

## 5. 关键词聚合伪代码

```text
function aggregate_keyword_metrics(tracker, candidate_set):
    groups = group_samples_by_keyword(candidate_set)
    rows = []

    for keyword, samples in groups:
        hit_content_count = count_distinct(samples.post_id)
        hit_creator_count = count_distinct(samples.author_id)
        avg_similarity = average(samples.similarity_score)
        avg_engagement = average(samples.engagement_total)
        viral_rate = ratio(count(samples where bucket == "viral_representative"), count(samples))
        growth_rate = compute_keyword_growth(keyword, samples)
        noise_rate = ratio(count(samples where candidate_level == "L3"), count(samples))

        keyword_value_score = compute_keyword_value_score(
            hit_content_count,
            avg_similarity,
            avg_engagement,
            viral_rate,
            growth_rate,
            noise_rate
        )

        recommended_action = recommend_keyword_action(
            keyword_value_score,
            growth_rate,
            noise_rate
        )

        rows.append({...})

    return sort_by_score(rows)
```

## 6. 趋势聚合伪代码

```text
function aggregate_trend_metrics(tracker, candidate_set, snapshots):
    buckets = bucket_samples_by_time(candidate_set)
    series = []

    for bucket in buckets:
        series.append({
            bucket_start: bucket.start,
            content_count: count(bucket.samples),
            engagement_total: sum(bucket.samples.engagement_total),
            new_creator_count: count_new_creators(bucket.samples),
            viral_count: count(bucket.samples where sample_bucket == "viral_representative"),
            platform_count: count_distinct(bucket.samples.platform)
        })

    metrics = compute_trend_summary_metrics(series, candidate_set, snapshots)
    anomalies = detect_trend_anomalies(series, snapshots)

    return {
        series: series,
        metrics: metrics,
        anomalies: anomalies
    }
```

## 7. 样本质量与噪音伪代码

```text
function aggregate_quality_metrics(tracker, candidate_set, jobs, snapshots):
    content_count_7d = count(candidate_set where within_7d)
    creator_count_7d = count_distinct(author_id where within_7d)
    platform_count = count_distinct(platform)
    time_continuity = compute_time_continuity(candidate_set)
    collection_success_rate = compute_collection_success_rate(jobs)
    snapshot_coverage = compute_snapshot_coverage(candidate_set, snapshots)
    history_baseline_ready = compute_history_baseline_ready(candidate_set, snapshots)

    sample_quality_score = weighted_sum(...)

    return {...}
```

```text
function aggregate_noise_metrics(tracker, candidate_set):
    l3_count = count(candidate_set where candidate_level == "L3")
    total_count = count(candidate_set)
    tracker_noise_rate = ratio(l3_count, total_count)

    cross_scene_false_positive_count = count_cross_scene_false_positive(candidate_set)
    cross_scene_noise_rate = ratio(cross_scene_false_positive_count, total_count)

    return {
        tracker_noise_rate: tracker_noise_rate,
        cross_scene_noise_rate: cross_scene_noise_rate
    }
```

## 8. 模式聚合伪代码

```text
function aggregate_pattern_metrics(tracker, candidate_set):
    clusters = cluster_samples(candidate_set)
    rows = []

    for cluster in clusters:
        cluster_size = count(cluster.samples)
        cluster_share = ratio(cluster_size, count(candidate_set))
        cluster_growth = compute_cluster_growth(cluster)
        cluster_creator_count = count_distinct(cluster.samples.author_id)
        cluster_value_score = compute_cluster_value_score(cluster)

        rows.append({
            cluster_id: cluster.id,
            cluster_name: cluster.name,
            cluster_size: cluster_size,
            cluster_share: cluster_share,
            cluster_growth: cluster_growth,
            cluster_creator_count: cluster_creator_count,
            cluster_value_score: cluster_value_score,
            top_content_type: mode(cluster.samples.content_type),
            top_audience: mode(cluster.samples.audience),
            top_pain_point: mode(cluster.samples.pain_point),
            top_conversion_intent: mode(cluster.samples.conversion_intent)
        })

    return {
        clusters: rows,
        content_type_distribution: aggregate_content_type_distribution(candidate_set),
        audience_distribution: aggregate_audience_distribution(candidate_set),
        conversion_intent_distribution: aggregate_conversion_distribution(candidate_set),
        hook_patterns: aggregate_hook_patterns(candidate_set)
    }
```

## 9. 创作者聚合伪代码

```text
function aggregate_creator_metrics(tracker, candidate_set, creators):
    grouped = group_samples_by_creator(candidate_set)
    rows = []

    for creator_key, samples in grouped:
        creator = creators.get(creator_key)
        role = classify_creator_role(samples, creator)

        rows.append({
            creator_id: creator_key.id,
            platform: creator_key.platform,
            role: role,
            post_count_in_tracker: count(samples),
            avg_similarity: average(samples.similarity_score),
            avg_engagement: average(samples.engagement_total),
            is_brand_like: creator.is_brand_like if creator else false,
            recommended_action: recommend_creator_action(role, creator)
        })

    metrics = compute_creator_summary_metrics(rows, candidate_set)
    return {
        metrics: metrics,
        rows: rows
    }
```

## 10. 决策引擎伪代码

```text
function build_decision_metrics(
    tracker,
    candidate_set,
    keyword_metrics,
    trend_metrics,
    quality_metrics,
    noise_metrics,
    pattern_metrics,
    creator_metrics
):
    status = classify_tracker_status(
        trend_strength_score=trend_metrics.metrics.trend_strength_score,
        sample_quality_score=quality_metrics.sample_quality_score,
        tracker_noise_rate=noise_metrics.tracker_noise_rate,
        creator_spread_score=creator_metrics.metrics.creator_spread_score
    )

    decision_confidence = compute_decision_confidence(
        sample_quality_score=quality_metrics.sample_quality_score,
        tracker_noise_rate=noise_metrics.tracker_noise_rate,
        history_baseline_ready=quality_metrics.history_baseline_ready,
        signal_consistency=compute_signal_consistency(...)
    )

    recommended_actions = recommend_actions(
        status=status,
        keyword_metrics=keyword_metrics,
        trend_metrics=trend_metrics,
        quality_metrics=quality_metrics,
        noise_metrics=noise_metrics,
        pattern_metrics=pattern_metrics,
        creator_metrics=creator_metrics
    )

    return {
        status: status,
        decision_confidence: decision_confidence,
        recommended_actions: recommended_actions
    }
```

## 11. 组装主分析快照伪代码

```text
function build_analysis_snapshot(...):
    return {
        tracker: build_tracker_section(tracker),
        overview: build_overview_section(...),
        trends: build_trends_section(...),
        keywords: build_keywords_section(...),
        patterns: build_patterns_section(...),
        creators: build_creators_section(...),
        samples: build_samples_section(candidate_set),
        risks: build_risks_section(...),
        decisions: build_decisions_section(...),
        meta: build_meta_section(...)
    }
```

## 12. 异常检测伪代码

```text
function detect_trend_anomalies(series, snapshots):
    anomalies = []

    for point in series:
        if is_content_spike(point):
            anomalies.append(make_anomaly(point, "content_spike"))
        if is_engagement_spike(point):
            anomalies.append(make_anomaly(point, "engagement_spike"))
        if is_platform_drop(point):
            anomalies.append(make_anomaly(point, "platform_drop"))
        if is_snapshot_gap(point, snapshots):
            anomalies.append(make_anomaly(point, "snapshot_gap"))

    return anomalies
```

P0 建议先用规则法：

- 当期值高于过去 N 桶均值的固定倍数
- 或低于过去 N 桶均值的固定比例

后续再升级为更稳定的统计异常检测。

## 13. 重算策略伪代码

```text
function recompute_tracker(tracker_id, reason):
    if reason in ["formula_change", "fingerprint_change", "cluster_rule_change"]:
        run_full_recompute(tracker_id)
    else:
        run_incremental_recompute(tracker_id)
```

```text
function run_incremental_recompute(tracker_id):
    latest_window = resolve_latest_window(tracker_id)
    run_tracker_analysis(tracker_id, "config_change", latest_window.range)
```

```text
function run_full_recompute(tracker_id):
    for range in ["24h", "7d", "30d"]:
        run_tracker_analysis(tracker_id, "backfill", range)
```

## 14. 失败恢复策略

### 14.1 候选样本构建失败

- 标记本次 run failed
- 不覆盖旧快照
- 主接口继续返回最新成功快照

### 14.2 某个聚合模块失败

例如 pattern 失败但 trend 成功：

- 可标记为 `partial_ready`
- 返回已有模块结果
- 在 `risks` 中说明某模块不可用

### 14.3 快照数据不足

- 不阻断整体分析
- 降低质量分
- 降低结论置信度

## 15. 建议代码模块拆分

建议后端实现按模块拆文件，而不是做一个大函数：

- `tracker_analysis_runner.py`
- `candidate_builder.py`
- `keyword_metrics.py`
- `trend_metrics.py`
- `quality_metrics.py`
- `noise_metrics.py`
- `pattern_metrics.py`
- `creator_metrics.py`
- `decision_engine.py`
- `snapshot_serializer.py`

## 16. P0 先做什么

P0 最小链路建议：

1. `run_tracker_analysis`
2. `build_candidate_set`
3. `aggregate_trend_metrics`
4. `aggregate_quality_metrics`
5. `aggregate_keyword_metrics`
6. `build_decision_metrics`
7. `build_analysis_snapshot`

先不做：

- 复杂聚类
- 多模态 OCR / 字幕
- 高级异常检测
- 自动扩词 AI 代理

## 17. 测试建议

至少要覆盖：

- 低样本场景
- 高噪音场景
- 单平台激增场景
- 老内容回流场景
- 创作者扩散场景
- 分析失败回退场景

核心测试点：

- 状态判定是否符合规则
- 公式输出是否稳定
- 无数据不应误判为衰减
- 有旧快照时失败不应清空主接口
