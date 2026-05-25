# 内容追踪分析数据库 DDL 草案

- 日期：2026-05-23
- 范围：内容追踪分析所需新增表、索引建议、字段类型建议、约束建议
- 关联文档：
  - `docs/superpowers/specs/2026-05-23-content-tracking-analysis-data-model.md`
  - `docs/superpowers/specs/2026-05-23-content-tracking-backend-api-and-aggregation.md`

## 1. 说明

本文件提供的是 DDL 草案，不绑定特定数据库方言。字段类型以 PostgreSQL 风格为主，若后续项目使用 SQLite 或其他数据库，可做轻量映射。

设计原则：

- 原始事实与分析快照分离
- 分析快照可重算
- 尽量保留分析运行历史
- 大对象先使用 JSONB，等字段稳定后再垂直拆表

## 2. tracker_analysis_run

```sql
CREATE TABLE tracker_analysis_run (
    id BIGSERIAL PRIMARY KEY,
    tracker_id BIGINT NOT NULL,
    run_type VARCHAR(32) NOT NULL,
    status VARCHAR(32) NOT NULL,
    analysis_window_start TIMESTAMPTZ NOT NULL,
    analysis_window_end TIMESTAMPTZ NOT NULL,
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    input_post_count INTEGER NOT NULL DEFAULT 0,
    input_snapshot_count INTEGER NOT NULL DEFAULT 0,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

索引建议：

```sql
CREATE INDEX idx_tracker_analysis_run_tracker_id ON tracker_analysis_run(tracker_id);
CREATE INDEX idx_tracker_analysis_run_status ON tracker_analysis_run(status);
CREATE INDEX idx_tracker_analysis_run_created_at ON tracker_analysis_run(created_at DESC);
```

## 3. tracker_candidate_sample

```sql
CREATE TABLE tracker_candidate_sample (
    id BIGSERIAL PRIMARY KEY,
    analysis_run_id BIGINT NOT NULL,
    tracker_id BIGINT NOT NULL,
    platform VARCHAR(32) NOT NULL,
    platform_post_id VARCHAR(255) NOT NULL,
    author_id VARCHAR(255),
    publish_time TIMESTAMPTZ,
    similarity_score NUMERIC(6,2) NOT NULL,
    candidate_level VARCHAR(8) NOT NULL,
    sample_bucket VARCHAR(64),
    matched_keywords_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    keyword_hits_detail_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    fingerprint_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    pattern_cluster_id VARCHAR(128),
    engagement_total BIGINT NOT NULL DEFAULT 0,
    snapshot_delta_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (analysis_run_id, platform, platform_post_id)
);
```

索引建议：

```sql
CREATE INDEX idx_tracker_candidate_sample_tracker_id ON tracker_candidate_sample(tracker_id);
CREATE INDEX idx_tracker_candidate_sample_analysis_run_id ON tracker_candidate_sample(analysis_run_id);
CREATE INDEX idx_tracker_candidate_sample_similarity_score ON tracker_candidate_sample(similarity_score DESC);
CREATE INDEX idx_tracker_candidate_sample_candidate_level ON tracker_candidate_sample(candidate_level);
CREATE INDEX idx_tracker_candidate_sample_pattern_cluster_id ON tracker_candidate_sample(pattern_cluster_id);
CREATE INDEX idx_tracker_candidate_sample_publish_time ON tracker_candidate_sample(publish_time DESC);
```

## 4. tracker_keyword_metric_snapshot

```sql
CREATE TABLE tracker_keyword_metric_snapshot (
    id BIGSERIAL PRIMARY KEY,
    analysis_run_id BIGINT NOT NULL,
    tracker_id BIGINT NOT NULL,
    keyword VARCHAR(255) NOT NULL,
    keyword_type VARCHAR(32) NOT NULL,
    hit_content_count INTEGER NOT NULL DEFAULT 0,
    hit_creator_count INTEGER NOT NULL DEFAULT 0,
    avg_similarity NUMERIC(6,2) NOT NULL DEFAULT 0,
    avg_engagement NUMERIC(12,2) NOT NULL DEFAULT 0,
    viral_rate NUMERIC(8,6) NOT NULL DEFAULT 0,
    growth_rate NUMERIC(10,6) NOT NULL DEFAULT 0,
    noise_rate NUMERIC(8,6) NOT NULL DEFAULT 0,
    keyword_value_score NUMERIC(6,2) NOT NULL DEFAULT 0,
    recommended_action VARCHAR(64),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (analysis_run_id, keyword)
);
```

索引建议：

```sql
CREATE INDEX idx_tracker_keyword_metric_snapshot_tracker_id ON tracker_keyword_metric_snapshot(tracker_id);
CREATE INDEX idx_tracker_keyword_metric_snapshot_analysis_run_id ON tracker_keyword_metric_snapshot(analysis_run_id);
CREATE INDEX idx_tracker_keyword_metric_snapshot_value_score ON tracker_keyword_metric_snapshot(keyword_value_score DESC);
CREATE INDEX idx_tracker_keyword_metric_snapshot_growth_rate ON tracker_keyword_metric_snapshot(growth_rate DESC);
```

## 5. tracker_pattern_metric_snapshot

```sql
CREATE TABLE tracker_pattern_metric_snapshot (
    id BIGSERIAL PRIMARY KEY,
    analysis_run_id BIGINT NOT NULL,
    tracker_id BIGINT NOT NULL,
    pattern_cluster_id VARCHAR(128) NOT NULL,
    cluster_name VARCHAR(255) NOT NULL,
    cluster_size INTEGER NOT NULL DEFAULT 0,
    cluster_share NUMERIC(8,6) NOT NULL DEFAULT 0,
    cluster_growth NUMERIC(10,6) NOT NULL DEFAULT 0,
    cluster_creator_count INTEGER NOT NULL DEFAULT 0,
    cluster_value_score NUMERIC(6,2) NOT NULL DEFAULT 0,
    top_content_type VARCHAR(64),
    top_audience VARCHAR(128),
    top_pain_point VARCHAR(128),
    top_conversion_intent VARCHAR(64),
    cluster_reason_summary TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (analysis_run_id, pattern_cluster_id)
);
```

索引建议：

```sql
CREATE INDEX idx_tracker_pattern_metric_snapshot_tracker_id ON tracker_pattern_metric_snapshot(tracker_id);
CREATE INDEX idx_tracker_pattern_metric_snapshot_analysis_run_id ON tracker_pattern_metric_snapshot(analysis_run_id);
CREATE INDEX idx_tracker_pattern_metric_snapshot_cluster_value_score ON tracker_pattern_metric_snapshot(cluster_value_score DESC);
```

## 6. tracker_creator_metric_snapshot

```sql
CREATE TABLE tracker_creator_metric_snapshot (
    id BIGSERIAL PRIMARY KEY,
    analysis_run_id BIGINT NOT NULL,
    tracker_id BIGINT NOT NULL,
    creator_id VARCHAR(255) NOT NULL,
    platform VARCHAR(32) NOT NULL,
    role VARCHAR(64),
    post_count_in_tracker INTEGER NOT NULL DEFAULT 0,
    avg_similarity NUMERIC(6,2) NOT NULL DEFAULT 0,
    avg_engagement NUMERIC(12,2) NOT NULL DEFAULT 0,
    is_brand_like BOOLEAN NOT NULL DEFAULT FALSE,
    recommended_action VARCHAR(64),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (analysis_run_id, platform, creator_id)
);
```

索引建议：

```sql
CREATE INDEX idx_tracker_creator_metric_snapshot_tracker_id ON tracker_creator_metric_snapshot(tracker_id);
CREATE INDEX idx_tracker_creator_metric_snapshot_analysis_run_id ON tracker_creator_metric_snapshot(analysis_run_id);
CREATE INDEX idx_tracker_creator_metric_snapshot_role ON tracker_creator_metric_snapshot(role);
CREATE INDEX idx_tracker_creator_metric_snapshot_is_brand_like ON tracker_creator_metric_snapshot(is_brand_like);
```

## 7. tracker_analysis_snapshot

```sql
CREATE TABLE tracker_analysis_snapshot (
    id BIGSERIAL PRIMARY KEY,
    analysis_run_id BIGINT NOT NULL UNIQUE,
    tracker_id BIGINT NOT NULL,
    status VARCHAR(64) NOT NULL,
    decision_confidence NUMERIC(6,2) NOT NULL DEFAULT 0,
    summary_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    overview_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    trends_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    keywords_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    patterns_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    creators_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    samples_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    risks_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    decisions_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    meta_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

索引建议：

```sql
CREATE INDEX idx_tracker_analysis_snapshot_tracker_id ON tracker_analysis_snapshot(tracker_id);
CREATE INDEX idx_tracker_analysis_snapshot_status ON tracker_analysis_snapshot(status);
CREATE INDEX idx_tracker_analysis_snapshot_created_at ON tracker_analysis_snapshot(created_at DESC);
```

## 8. 可选增强表

### 8.1 tracker_trend_bucket_snapshot

若后续趋势图查询频繁，可将时间序列单独拆表：

```sql
CREATE TABLE tracker_trend_bucket_snapshot (
    id BIGSERIAL PRIMARY KEY,
    analysis_run_id BIGINT NOT NULL,
    tracker_id BIGINT NOT NULL,
    bucket_start TIMESTAMPTZ NOT NULL,
    bucket_granularity VARCHAR(16) NOT NULL,
    content_count INTEGER NOT NULL DEFAULT 0,
    engagement_total BIGINT NOT NULL DEFAULT 0,
    new_creator_count INTEGER NOT NULL DEFAULT 0,
    viral_count INTEGER NOT NULL DEFAULT 0,
    platform_count INTEGER NOT NULL DEFAULT 0,
    UNIQUE (analysis_run_id, bucket_start, bucket_granularity)
);
```

### 8.2 tracker_analysis_anomaly

若后续异常解释需要独立查询：

```sql
CREATE TABLE tracker_analysis_anomaly (
    id BIGSERIAL PRIMARY KEY,
    analysis_run_id BIGINT NOT NULL,
    tracker_id BIGINT NOT NULL,
    anomaly_time TIMESTAMPTZ NOT NULL,
    anomaly_type VARCHAR(64) NOT NULL,
    impact_level VARCHAR(16) NOT NULL,
    message TEXT NOT NULL,
    possible_reasons_json JSONB NOT NULL DEFAULT '[]'::jsonb
);
```

## 9. 外键与约束建议

若当前仓库已有稳定的 `content_tracker` 主表，可增加外键：

```sql
ALTER TABLE tracker_analysis_run
ADD CONSTRAINT fk_tracker_analysis_run_tracker
FOREIGN KEY (tracker_id) REFERENCES content_tracker(id);
```

其余快照表可全部指向 `tracker_analysis_run.id` 和 `tracker_id`。

如果当前仓库仍在快速迭代阶段，也可以暂时不加外键，只保留业务层校验，减少迁移成本。

## 10. 清理与保留策略

建议保留：

- `tracker_analysis_snapshot`：长期保留
- `tracker_analysis_run`：长期保留
- `tracker_candidate_sample`：保留最近 N 次或最近 N 天
- 其他 metric snapshot：视存储成本保留最近 N 次

建议策略：

- 保留最近 30 次运行的全量中间结果
- 更老的运行只保留主快照与运行记录

## 11. 迁移顺序建议

1. `tracker_analysis_run`
2. `tracker_candidate_sample`
3. `tracker_keyword_metric_snapshot`
4. `tracker_pattern_metric_snapshot`
5. `tracker_creator_metric_snapshot`
6. `tracker_analysis_snapshot`
7. 可选增强表

## 12. 开发注意事项

- JSONB 字段先满足页面开发，字段稳定后再做拆分
- 所有得分字段统一保留两位小数
- 所有比率字段建议保留六位小数，避免累积误差
- 为避免重复分析写入冲突，建议使用 `(analysis_run_id, business_key)` 唯一约束
