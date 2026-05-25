# 采集新数据与自动分析 DDL 草案

## 1. 目标

为内容追踪与友商监控增加统一的采集任务持久化结构，支持：

- 手动触发采集
- 采集状态轮询
- 采集摘要记录
- 与分析 run 关联
- 后续扩展定时任务

本草案优先兼容当前项目已存在的 SQLite / PostgreSQL / MySQL 多数据库模式。

---

## 2. 设计原则

### 2.1 P0 优先单表

P0 建议先落一张通用表：

- `collection_runs`

将平台级明细、汇总结果、错误信息优先存入 JSON 字段。

这样可以：

- 降低首期开发复杂度
- 避免过早把平台级结构硬编码进表

### 2.2 P1 再拆子表

如果后续需要高频按平台、按 tracker、按 competitor 聚合查询，再增加：

- `content_tracker_collection_runs`
- `competitor_collection_runs`
- `collection_run_platform_results`

---

## 3. 主表：collection_runs

### 3.1 字段定义

```sql
CREATE TABLE collection_runs (
    id BIGINT PRIMARY KEY,
    run_type VARCHAR(64) NOT NULL,
    target_id BIGINT NOT NULL,
    mode VARCHAR(64) NOT NULL,
    status VARCHAR(32) NOT NULL,
    phase VARCHAR(64) NOT NULL,
    trigger_source VARCHAR(32) NOT NULL,
    request_payload_json TEXT,
    platforms_json TEXT,
    summary_json TEXT,
    error_json TEXT,
    triggered_analysis_run_id BIGINT,
    started_at DATETIME,
    finished_at DATETIME,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL
);
```

### 3.2 字段语义

- `id`
  - 采集任务唯一 ID

- `run_type`
  - `content_tracker`
  - `competitor_monitor`

- `target_id`
  - 对应 tracker_id 或 competitor_id

- `mode`
  - `collect_only`
  - `collect_and_analyze`
  - `collect_and_refresh`

- `status`
  - `queued`
  - `running`
  - `succeeded`
  - `partial_failed`
  - `failed`
  - `cancelled`

- `phase`
  - `collecting`
  - `normalizing`
  - `persisting`
  - `triggering_analysis`
  - `analyzing`
  - `completed`

- `trigger_source`
  - `manual`
  - `scheduled`
  - `followup`

- `request_payload_json`
  - 原始请求参数

- `platforms_json`
  - 本次采集涉及的平台列表

- `summary_json`
  - 采集汇总信息

- `error_json`
  - 错误信息

- `triggered_analysis_run_id`
  - 若本次采集后触发了分析，则关联分析 run id

---

## 4. JSON 字段结构建议

### 4.1 request_payload_json

```json
{
  "lookback_days": 7,
  "limit_per_platform": 50,
  "platforms": ["xhs", "dy"],
  "included_keywords": ["狗粮", "宠物食品"],
  "excluded_keywords": ["广告", "无关词"]
}
```

### 4.2 summary_json

```json
{
  "new_posts_count": 18,
  "updated_posts_count": 12,
  "deduped_posts_count": 4,
  "new_snapshots_count": 9,
  "success_platforms": ["xhs"],
  "failed_platforms": ["dy"],
  "matched_keyword_count": 6,
  "analysis_triggered": true
}
```

### 4.3 error_json

```json
{
  "errors": [
    {
      "platform": "dy",
      "stage": "collecting",
      "code": "RATE_LIMIT",
      "message": "provider returned rate limit",
      "retryable": true
    }
  ]
}
```

---

## 5. 索引建议

```sql
CREATE INDEX idx_collection_runs_type_target_created
ON collection_runs (run_type, target_id, created_at DESC);
```

```sql
CREATE INDEX idx_collection_runs_status_created
ON collection_runs (status, created_at DESC);
```

```sql
CREATE INDEX idx_collection_runs_triggered_analysis
ON collection_runs (triggered_analysis_run_id);
```

作用：

- 按 tracker / competitor 查最近任务
- 查询运行中任务
- 从采集任务反查分析任务

---

## 6. P1 子表：content_tracker_collection_runs

如果后续希望对 tracker 采集做更细聚合，可增加：

```sql
CREATE TABLE content_tracker_collection_runs (
    id BIGINT PRIMARY KEY,
    tracker_id BIGINT NOT NULL,
    collection_run_id BIGINT NOT NULL,
    new_posts_count INT NOT NULL DEFAULT 0,
    updated_posts_count INT NOT NULL DEFAULT 0,
    deduped_posts_count INT NOT NULL DEFAULT 0,
    failed_platform_count INT NOT NULL DEFAULT 0,
    matched_keyword_count INT NOT NULL DEFAULT 0,
    triggered_analysis_run_id BIGINT,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL
);
```

索引：

```sql
CREATE INDEX idx_tracker_collection_runs_tracker_created
ON content_tracker_collection_runs (tracker_id, created_at DESC);
```

---

## 7. P1 子表：competitor_collection_runs

```sql
CREATE TABLE competitor_collection_runs (
    id BIGINT PRIMARY KEY,
    competitor_id BIGINT NOT NULL,
    collection_run_id BIGINT NOT NULL,
    new_posts_count INT NOT NULL DEFAULT 0,
    updated_posts_count INT NOT NULL DEFAULT 0,
    new_snapshots_count INT NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL
);
```

索引：

```sql
CREATE INDEX idx_competitor_collection_runs_competitor_created
ON competitor_collection_runs (competitor_id, created_at DESC);
```

---

## 8. P1 子表：collection_run_platform_results

如果后续要按平台展示明细状态，建议增加：

```sql
CREATE TABLE collection_run_platform_results (
    id BIGINT PRIMARY KEY,
    collection_run_id BIGINT NOT NULL,
    platform VARCHAR(32) NOT NULL,
    status VARCHAR(32) NOT NULL,
    new_posts_count INT NOT NULL DEFAULT 0,
    updated_posts_count INT NOT NULL DEFAULT 0,
    deduped_posts_count INT NOT NULL DEFAULT 0,
    error_code VARCHAR(64),
    error_message TEXT,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL
);
```

索引：

```sql
CREATE INDEX idx_collection_platform_results_run
ON collection_run_platform_results (collection_run_id);
```

---

## 9. 与现有分析表的关联

当前系统已有 analysis run / snapshot 概念。

新增采集表需要做到：

- 采集任务可以触发分析任务
- 分析任务可反查其来源采集任务

P0 最简单做法：

- 在 `collection_runs.triggered_analysis_run_id` 存分析 run id

P1 可选：

- 在分析 run 表增加 `source_collection_run_id`

---

## 10. 数据保留策略

建议：

- `collection_runs` 永久保留最近 90 天
- 90 天前可按业务需要归档或删除

P0 可先不做自动清理，只做设计预留。

---

## 11. P0 推荐落地方案

首期只建：

- `collection_runs`

不立即建子表，原因：

- 先把任务链路跑通
- 减少数据库迁移复杂度
- 后续根据实际查询模式再拆表

---

## 12. 验收标准

- 能记录每次采集任务
- 能按 target_id 查最近任务
- 能查询运行中状态
- 能记录 summary / error / triggered_analysis_run_id
- 能兼容 SQLite / PostgreSQL / MySQL

