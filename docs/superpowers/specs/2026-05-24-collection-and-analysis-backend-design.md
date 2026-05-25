# 采集新数据与自动分析后端设计

## 1. 目标

为内容追踪与友商监控增加一层可复用的`采集任务编排能力`，并与现有分析快照逻辑衔接。

核心要求：

- 支持手动触发采集
- 支持采集后自动分析
- 任务可轮询
- 失败可诊断
- 与现有数据库分析链路兼容

---

## 2. 设计原则

### 2.1 采集与分析拆分

两个任务对象：

- `collection_run`
- `analysis_run`

采集任务可以不触发分析任务。

### 2.2 异步执行

接口不等待爬虫执行完毕。

推荐模式：

1. 接口创建 run 记录
2. 返回 `run_id`
3. 后台执行
4. 前端轮询

### 2.3 结果持久化

每次任务都需要有：

- 输入参数
- 状态
- 汇总结果
- 错误信息
- 关联分析 run

---

## 3. 任务对象模型

### 3.1 collection_runs

建议新增表：

`collection_runs`

字段：

- `id`
- `run_type`
  - `content_tracker`
  - `competitor_monitor`
- `target_id`
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
- `platforms_json`
- `request_payload_json`
- `summary_json`
- `error_json`
- `started_at`
- `finished_at`
- `created_at`
- `updated_at`

### 3.2 content_tracker_collection_runs

如需要更强查询能力，可加子表：

- `id`
- `tracker_id`
- `collection_run_id`
- `new_posts_count`
- `updated_posts_count`
- `deduped_posts_count`
- `failed_platform_count`
- `matched_keyword_count`
- `triggered_analysis_run_id`

### 3.3 competitor_collection_runs

- `id`
- `competitor_id`
- `collection_run_id`
- `new_posts_count`
- `updated_posts_count`
- `new_snapshots_count`
- `triggered_refresh_at`

如果 P0 想更快落地，可先只建 `collection_runs`，将细节都放 `summary_json`。

---

## 4. 内容追踪采集任务设计

### 4.1 输入

- `tracker_id`
- `mode`
- `lookback_days`
- `limit_per_platform`
- `platforms[]` 可选，默认 tracker 配置

### 4.2 读取配置

从 tracker 读取：

- 平台
- 包含关键词
- 排除关键词
- 回溯时间窗口

### 4.3 执行流程

1. 创建 `collection_run`
2. 更新状态为 `running`
3. 逐平台执行采集
4. 标准化内容
5. 去重
6. 写入数据库
7. 汇总采集统计
8. 若 `mode=collect_and_analyze`，创建分析任务
9. 更新 run 状态

### 4.4 标准化字段

建议统一产出：

- `platform`
- `platform_post_id`
- `author_id`
- `title`
- `content`
- `publish_time`
- `url`
- `engagement_json`
- `matched_keywords`
- `raw_payload_json`

### 4.5 去重策略

优先键：

- `(platform, platform_post_id)`

回退键：

- `(platform, normalized_url)`

更新策略：

- 内容已存在：更新互动快照、更新时间、raw payload
- 内容不存在：插入新记录

---

## 5. 友商监控采集任务设计

### 5.1 输入

- `competitor_id`
- `mode`
- `lookback_days`
- `latest_limit`

### 5.2 读取配置

从 competitor 读取：

- 平台
- creator_id
- profile_url
- 监控状态

### 5.3 执行流程

1. 创建 `collection_run`
2. 更新状态为 `running`
3. 采集当前账号最近内容
4. 更新内容与互动快照
5. 写入数据库
6. 若 `mode=collect_and_refresh`，刷新 summary/ranking/composition/anomalies
7. 更新 run 状态

### 5.4 刷新范围

P0 建议仅刷新：

- `today_summary`
- `contribution_ranking`
- `composition`
- `anomaly_feed`

`monitor_settings` 不需要每次同步时重新生成。

---

## 6. 接口设计

### 6.1 内容追踪

#### POST `/api/content-tracking/trackers/{tracker_id}/collect`

作用：

- 创建 tracker 采集任务

请求体：

```json
{
  "lookback_days": 7,
  "limit_per_platform": 50,
  "platforms": ["xhs", "dy"]
}
```

响应：

```json
{
  "run_id": 101,
  "status": "queued",
  "tracker_id": 1,
  "mode": "collect_only"
}
```

#### POST `/api/content-tracking/trackers/{tracker_id}/collect-and-analyze`

作用：

- 创建 tracker 采集任务，并在成功后触发分析

#### GET `/api/content-tracking/collection-runs/{run_id}`

作用：

- 查询采集任务状态

### 6.2 友商监控

#### POST `/api/competitors/{competitor_id}/collect`

#### POST `/api/competitors/{competitor_id}/collect-and-refresh`

#### GET `/api/competitors/collection-runs/{run_id}`

---

## 7. 服务层设计

建议新增服务：

### 7.1 `research/collection_runs.py`

职责：

- 创建 run
- 更新状态
- 记录 summary/error

### 7.2 `research/content_tracker_collection.py`

职责：

- 执行 tracker 采集
- 调用平台 provider
- 入库
- 可选触发分析

### 7.3 `research/competitor_collection.py`

职责：

- 执行 competitor 采集
- 更新账号内容与快照
- 刷新监控分析结果

### 7.4 `research/platform_collectors/*`

职责：

- 对接不同平台采集能力
- 返回统一结构

---

## 8. 平台采集适配层

建议统一接口：

```python
class PlatformCollector(Protocol):
    async def collect_by_keywords(self, *, keywords: list[str], excluded_keywords: list[str], lookback_days: int, limit: int) -> list[CollectedPost]: ...
    async def collect_by_creator(self, *, creator_id: str | None, profile_url: str | None, lookback_days: int, limit: int) -> list[CollectedPost]: ...
```

建议统一输出模型：

```python
class CollectedPost(BaseModel):
    platform: str
    platform_post_id: str
    author_id: str | None
    title: str | None
    content: str | None
    publish_time: datetime | None
    url: str | None
    engagement: dict[str, Any]
    raw_payload: dict[str, Any]
```

---

## 9. 任务状态更新规则

### 9.1 成功

条件：

- 至少一个平台成功
- 写库完成
- 若要求自动分析，则分析完成

### 9.2 部分失败

条件：

- 至少一个平台成功
- 至少一个平台失败

### 9.3 失败

条件：

- 所有平台失败
- 或写库阶段失败
- 或分析阶段失败且要求分析结果为强一致

P0 建议：

- 采集成功、分析失败时，采集 run 记为 `partial_failed`
- 并在 `summary_json` 记录分析 run 失败信息

---

## 10. 前端轮询协议

前端轮询 `GET run` 时，后端建议返回：

```json
{
  "run_id": 101,
  "status": "running",
  "phase": "persisting",
  "started_at": "2026-05-24T10:00:00Z",
  "finished_at": null,
  "summary": {
    "new_posts_count": 12,
    "updated_posts_count": 8,
    "failed_platforms": ["dy"]
  },
  "errors": []
}
```

---

## 11. 与现有分析链路衔接

### 11.1 内容追踪

采集任务完成后，直接调用现有：

- candidate set 构建
- quality/trend/keyword/pattern/creator/risk/decision 计算
- snapshot 落库

### 11.2 友商监控

采集任务完成后，刷新已有账号分析视图的数据来源。

不建议前端自己拼分析。

---

## 12. 错误与重试策略

### 12.1 自动重试

可自动重试场景：

- 网络抖动
- 短时平台不可达

### 12.2 不自动重试

- 配置错误
- creator_id 不存在
- 鉴权失效

### 12.3 错误结构

建议 `error_json` 至少包含：

- `platform`
- `stage`
- `code`
- `message`
- `retryable`

---

## 13. P0 实施顺序

1. 新建 `collection_runs` 表
2. 新增 run repository
3. 新增 tracker collect 接口
4. 新增 competitor collect 接口
5. 接入内容追踪“采集并分析”
6. 接入竞品页“同步并更新分析”
7. 前端按钮与轮询

---

## 14. 验收标准

### 后端

- 可创建内容追踪采集任务
- 可创建友商同步任务
- run 状态可查询
- 采集结果可写库
- 可触发后续分析或刷新

### 前端

- 页面可发起任务
- 页面可轮询状态
- 页面可看到成功、部分失败、失败

### 数据

- 新样本入库可复用现有分析链路
- 不需要页面直接参与爬虫过程

