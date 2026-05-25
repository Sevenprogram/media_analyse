# 采集新数据与自动分析 API Schema

## 1. 目标

定义内容追踪与友商监控的采集任务接口，支持：

- 手动触发采集
- 采集并分析
- 状态轮询
- 页面局部刷新

---

## 2. 通用状态枚举

### 2.1 run_status

- `queued`
- `running`
- `succeeded`
- `partial_failed`
- `failed`
- `cancelled`

### 2.2 run_phase

- `collecting`
- `normalizing`
- `persisting`
- `triggering_analysis`
- `analyzing`
- `completed`

---

## 3. 内容追踪接口

### 3.1 POST `/api/content-tracking/trackers/{tracker_id}/collect`

作用：

- 创建采集任务，不自动分析

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
  "tracker_id": 1,
  "run_type": "content_tracker",
  "mode": "collect_only",
  "status": "queued",
  "phase": "collecting",
  "created_at": "2026-05-24T10:00:00Z"
}
```

### 3.2 POST `/api/content-tracking/trackers/{tracker_id}/collect-and-analyze`

作用：

- 创建采集任务，采集完成后自动分析

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
  "run_id": 102,
  "tracker_id": 1,
  "run_type": "content_tracker",
  "mode": "collect_and_analyze",
  "status": "queued",
  "phase": "collecting",
  "created_at": "2026-05-24T10:01:00Z"
}
```

### 3.3 GET `/api/content-tracking/collection-runs/{run_id}`

作用：

- 查询内容追踪采集任务状态

响应：

```json
{
  "run_id": 102,
  "tracker_id": 1,
  "run_type": "content_tracker",
  "mode": "collect_and_analyze",
  "status": "running",
  "phase": "persisting",
  "trigger_source": "manual",
  "started_at": "2026-05-24T10:01:01Z",
  "finished_at": null,
  "summary": {
    "new_posts_count": 12,
    "updated_posts_count": 7,
    "deduped_posts_count": 2,
    "success_platforms": ["xhs"],
    "failed_platforms": []
  },
  "errors": [],
  "triggered_analysis_run_id": null
}
```

---

## 4. 友商监控接口

### 4.1 POST `/api/competitors/{competitor_id}/collect`

作用：

- 同步当前账号最新内容

请求体：

```json
{
  "lookback_days": 7,
  "latest_limit": 50
}
```

响应：

```json
{
  "run_id": 201,
  "competitor_id": 1,
  "run_type": "competitor_monitor",
  "mode": "collect_only",
  "status": "queued",
  "phase": "collecting",
  "created_at": "2026-05-24T10:03:00Z"
}
```

### 4.2 POST `/api/competitors/{competitor_id}/collect-and-refresh`

作用：

- 同步内容并刷新竞品分析模块

请求体：

```json
{
  "lookback_days": 7,
  "latest_limit": 50
}
```

响应：

```json
{
  "run_id": 202,
  "competitor_id": 1,
  "run_type": "competitor_monitor",
  "mode": "collect_and_refresh",
  "status": "queued",
  "phase": "collecting",
  "created_at": "2026-05-24T10:04:00Z"
}
```

### 4.3 GET `/api/competitors/collection-runs/{run_id}`

响应：

```json
{
  "run_id": 202,
  "competitor_id": 1,
  "run_type": "competitor_monitor",
  "mode": "collect_and_refresh",
  "status": "succeeded",
  "phase": "completed",
  "trigger_source": "manual",
  "started_at": "2026-05-24T10:04:02Z",
  "finished_at": "2026-05-24T10:04:25Z",
  "summary": {
    "new_posts_count": 8,
    "updated_posts_count": 12,
    "new_snapshots_count": 9,
    "analysis_triggered": true
  },
  "errors": [],
  "triggered_analysis_run_id": null
}
```

---

## 5. 通用错误结构

建议所有 GET run 接口统一返回：

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

## 6. 前端轮询建议

### 6.1 轮询频率

- `queued` / `running`：每 2 秒
- `succeeded` / `failed` / `partial_failed`：停止轮询

### 6.2 刷新动作

#### 内容追踪

当 run 完成且 `mode=collect_and_analyze` 时：

- 刷新 tracker latest analysis
- 刷新 tracker history

#### 友商监控

当 run 完成且 `mode=collect_and_refresh` 时：

- 刷新当前 competitor 相关模块数据

---

## 7. 验收标准

- 接口能返回统一 run 结构
- 页面可基于 run status 做状态反馈
- 失败时能返回 platform/stage/code/message
- 成功时能返回 summary

