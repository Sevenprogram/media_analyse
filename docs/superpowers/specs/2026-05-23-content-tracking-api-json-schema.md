# 内容追踪分析接口 JSON Schema 与字段规范

- 日期：2026-05-23
- 范围：内容追踪分析相关接口的请求/响应字段规范、JSON Schema 草案、字段语义说明
- 关联文档：
  - `docs/superpowers/specs/2026-05-23-content-tracking-analysis-prd.md`
  - `docs/superpowers/specs/2026-05-23-content-tracking-analysis-data-model.md`
  - `docs/superpowers/specs/2026-05-23-content-tracking-backend-api-and-aggregation.md`

## 1. 设计原则

- 主分析接口按分析语义返回，不按底层表返回
- 所有指标字段命名统一使用英文 snake_case
- 所有百分比型字段若无特殊说明，范围统一为 `0.0 ~ 1.0`
- 所有得分字段若无特殊说明，范围统一为 `0 ~ 100`
- 所有时间字段统一使用 ISO 8601 UTC 字符串
- 所有数组字段在无数据时返回 `[]`，不返回 `null`
- 所有对象字段在无数据时返回空对象或带 `status` 的结果，不返回结构缺失

## 2. 状态枚举

### 2.1 Tracker 状态

```json
["active", "paused", "archived"]
```

### 2.2 分析页状态

```json
["rising", "stable", "declining", "noise_high", "sample_insufficient", "watching"]
```

### 2.3 分析运行状态

```json
["pending", "running", "completed", "failed"]
```

### 2.4 候选样本层级

```json
["L1", "L2", "L3"]
```

### 2.5 样本桶

```json
[
  "viral_representative",
  "early_signal",
  "new_variant",
  "cross_platform_repeat",
  "risk_false_positive"
]
```

### 2.6 推荐动作

```json
[
  "keep_tracking",
  "backfill",
  "expand_keywords",
  "add_negative_keywords",
  "split_tracker",
  "create_creator_discovery",
  "create_competitor_monitor",
  "downgrade_to_watch"
]
```

## 3. 通用 Schema 片段

### 3.1 MetricValue

```json
{
  "type": "object",
  "required": ["value"],
  "properties": {
    "value": { "type": ["number", "integer", "string"] },
    "label": { "type": "string" },
    "unit": { "type": "string" },
    "delta": { "type": "number" },
    "note": { "type": "string" }
  },
  "additionalProperties": false
}
```

### 3.2 EvidenceRef

```json
{
  "type": "object",
  "required": ["ref_type", "ref_id"],
  "properties": {
    "ref_type": {
      "type": "string",
      "enum": ["post", "keyword", "cluster", "creator", "snapshot", "job"]
    },
    "ref_id": { "type": "string" },
    "reason": { "type": "string" }
  },
  "additionalProperties": false
}
```

### 3.3 RiskItem

```json
{
  "type": "object",
  "required": ["risk_code", "level", "message"],
  "properties": {
    "risk_code": { "type": "string" },
    "level": {
      "type": "string",
      "enum": ["low", "medium", "high"]
    },
    "message": { "type": "string" },
    "blocking": { "type": "boolean" },
    "evidence_refs": {
      "type": "array",
      "items": { "$ref": "#/$defs/evidenceRef" }
    }
  },
  "additionalProperties": false
}
```

## 4. Tracker 对象 Schema

```json
{
  "$id": "tracker",
  "type": "object",
  "required": [
    "tracker_id",
    "name",
    "platforms",
    "included_keywords",
    "excluded_keywords",
    "time_window_days",
    "status",
    "created_at",
    "updated_at"
  ],
  "properties": {
    "tracker_id": { "type": "integer" },
    "name": { "type": "string" },
    "platforms": {
      "type": "array",
      "items": { "type": "string" }
    },
    "included_keywords": {
      "type": "array",
      "items": { "type": "string" }
    },
    "excluded_keywords": {
      "type": "array",
      "items": { "type": "string" }
    },
    "time_window_days": { "type": "integer", "minimum": 1, "maximum": 90 },
    "status": { "type": "string", "enum": ["active", "paused", "archived"] },
    "created_from": { "type": "string" },
    "last_refresh_time": { "type": ["string", "null"], "format": "date-time" },
    "last_analysis_time": { "type": ["string", "null"], "format": "date-time" },
    "last_collection_status": { "type": ["string", "null"] },
    "created_at": { "type": "string", "format": "date-time" },
    "updated_at": { "type": "string", "format": "date-time" }
  },
  "additionalProperties": false
}
```

## 5. 主分析页响应 Schema

### 5.1 顶层结构

```json
{
  "$id": "tracker_analysis_response",
  "type": "object",
  "required": [
    "tracker",
    "overview",
    "trends",
    "keywords",
    "patterns",
    "creators",
    "samples",
    "risks",
    "decisions",
    "meta"
  ],
  "properties": {
    "tracker": { "$ref": "#/$defs/tracker" },
    "overview": { "$ref": "#/$defs/overview" },
    "trends": { "$ref": "#/$defs/trends" },
    "keywords": { "$ref": "#/$defs/keywords" },
    "patterns": { "$ref": "#/$defs/patterns" },
    "creators": { "$ref": "#/$defs/creators" },
    "samples": { "$ref": "#/$defs/samples" },
    "risks": { "$ref": "#/$defs/risks" },
    "decisions": { "$ref": "#/$defs/decisions" },
    "meta": { "$ref": "#/$defs/meta" }
  },
  "$defs": {}
}
```

### 5.2 Overview

```json
{
  "$id": "overview",
  "type": "object",
  "required": [
    "status",
    "decision_confidence",
    "summary_sentence",
    "sample_quality_score",
    "metrics"
  ],
  "properties": {
    "status": {
      "type": "string",
      "enum": ["rising", "stable", "declining", "noise_high", "sample_insufficient", "watching"]
    },
    "decision_confidence": { "type": "number", "minimum": 0, "maximum": 100 },
    "summary_sentence": { "type": "string" },
    "primary_reason": { "type": "string" },
    "top_risk": { "type": ["string", "null"] },
    "sample_quality_score": { "type": "number", "minimum": 0, "maximum": 100 },
    "metrics": {
      "type": "object",
      "required": [
        "content_count_24h",
        "content_count_7d",
        "creator_count_7d",
        "platform_count",
        "snapshot_count",
        "content_growth_rate_24h",
        "content_growth_rate_7d",
        "engagement_growth_rate_24h",
        "viral_ratio_change",
        "new_creator_ratio"
      ],
      "properties": {
        "content_count_24h": { "type": "integer" },
        "content_count_7d": { "type": "integer" },
        "creator_count_7d": { "type": "integer" },
        "platform_count": { "type": "integer" },
        "snapshot_count": { "type": "integer" },
        "content_growth_rate_24h": { "type": "number" },
        "content_growth_rate_7d": { "type": "number" },
        "engagement_growth_rate_24h": { "type": "number" },
        "viral_ratio_change": { "type": "number" },
        "new_creator_ratio": { "type": "number" }
      },
      "additionalProperties": false
    },
    "evidence_refs": {
      "type": "array",
      "items": { "$ref": "#/$defs/evidenceRef" }
    }
  },
  "additionalProperties": false
}
```

### 5.3 Trends

```json
{
  "$id": "trends",
  "type": "object",
  "required": ["series", "platforms", "anomalies", "metrics"],
  "properties": {
    "series": {
      "type": "array",
      "items": {
        "type": "object",
        "required": [
          "bucket_start",
          "content_count",
          "engagement_total",
          "new_creator_count",
          "viral_count",
          "platform_count"
        ],
        "properties": {
          "bucket_start": { "type": "string", "format": "date-time" },
          "content_count": { "type": "integer" },
          "engagement_total": { "type": "integer" },
          "new_creator_count": { "type": "integer" },
          "viral_count": { "type": "integer" },
          "platform_count": { "type": "integer" }
        },
        "additionalProperties": false
      }
    },
    "platforms": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["platform", "sample_share", "engagement_share", "growth_rate"],
        "properties": {
          "platform": { "type": "string" },
          "sample_share": { "type": "number" },
          "engagement_share": { "type": "number" },
          "growth_rate": { "type": "number" }
        },
        "additionalProperties": false
      }
    },
    "anomalies": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["anomaly_time", "anomaly_type", "impact_level", "message"],
        "properties": {
          "anomaly_time": { "type": "string", "format": "date-time" },
          "anomaly_type": { "type": "string" },
          "impact_level": { "type": "string", "enum": ["low", "medium", "high"] },
          "message": { "type": "string" },
          "possible_reasons": {
            "type": "array",
            "items": { "type": "string" }
          }
        },
        "additionalProperties": false
      }
    },
    "metrics": {
      "type": "object",
      "required": [
        "trend_strength_score",
        "platform_concentration",
        "new_content_engagement_share",
        "old_content_reactivation_ratio",
        "viral_ratio"
      ],
      "properties": {
        "trend_strength_score": { "type": "number" },
        "platform_concentration": { "type": "number" },
        "new_content_engagement_share": { "type": "number" },
        "old_content_reactivation_ratio": { "type": "number" },
        "viral_ratio": { "type": "number" }
      },
      "additionalProperties": false
    }
  },
  "additionalProperties": false
}
```

### 5.4 Keywords

```json
{
  "$id": "keywords",
  "type": "object",
  "required": ["rows", "top_keywords", "new_keywords", "noise_keywords", "suggestions"],
  "properties": {
    "rows": {
      "type": "array",
      "items": {
        "type": "object",
        "required": [
          "keyword",
          "keyword_type",
          "hit_content_count",
          "hit_creator_count",
          "avg_similarity",
          "avg_engagement",
          "viral_rate",
          "growth_rate",
          "noise_rate",
          "keyword_value_score",
          "recommended_action"
        ],
        "properties": {
          "keyword": { "type": "string" },
          "keyword_type": { "type": "string" },
          "hit_content_count": { "type": "integer" },
          "hit_creator_count": { "type": "integer" },
          "avg_similarity": { "type": "number" },
          "avg_engagement": { "type": "number" },
          "viral_rate": { "type": "number" },
          "growth_rate": { "type": "number" },
          "noise_rate": { "type": "number" },
          "keyword_value_score": { "type": "number" },
          "recommended_action": { "type": "string" }
        },
        "additionalProperties": false
      }
    },
    "top_keywords": {
      "type": "array",
      "items": { "type": "string" }
    },
    "new_keywords": {
      "type": "array",
      "items": { "type": "string" }
    },
    "noise_keywords": {
      "type": "array",
      "items": { "type": "string" }
    },
    "suggestions": {
      "type": "object",
      "required": ["recommended_include", "recommended_exclude"],
      "properties": {
        "recommended_include": {
          "type": "array",
          "items": { "type": "string" }
        },
        "recommended_exclude": {
          "type": "array",
          "items": { "type": "string" }
        }
      },
      "additionalProperties": false
    }
  },
  "additionalProperties": false
}
```

### 5.5 Patterns

```json
{
  "$id": "patterns",
  "type": "object",
  "required": ["content_type_distribution", "clusters", "hook_patterns", "audience_distribution", "conversion_intent_distribution"],
  "properties": {
    "content_type_distribution": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["content_type", "share", "growth_rate", "avg_engagement"],
        "properties": {
          "content_type": { "type": "string" },
          "share": { "type": "number" },
          "growth_rate": { "type": "number" },
          "avg_engagement": { "type": "number" }
        },
        "additionalProperties": false
      }
    },
    "clusters": {
      "type": "array",
      "items": {
        "type": "object",
        "required": [
          "cluster_id",
          "cluster_name",
          "cluster_size",
          "cluster_share",
          "cluster_growth",
          "cluster_creator_count",
          "cluster_value_score"
        ],
        "properties": {
          "cluster_id": { "type": "string" },
          "cluster_name": { "type": "string" },
          "cluster_size": { "type": "integer" },
          "cluster_share": { "type": "number" },
          "cluster_growth": { "type": "number" },
          "cluster_creator_count": { "type": "integer" },
          "cluster_value_score": { "type": "number" },
          "cluster_reason_summary": { "type": "string" }
        },
        "additionalProperties": false
      }
    },
    "hook_patterns": {
      "type": "array",
      "items": { "type": "string" }
    },
    "audience_distribution": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["name", "share"],
        "properties": {
          "name": { "type": "string" },
          "share": { "type": "number" }
        },
        "additionalProperties": false
      }
    },
    "conversion_intent_distribution": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["name", "share"],
        "properties": {
          "name": { "type": "string" },
          "share": { "type": "number" }
        },
        "additionalProperties": false
      }
    }
  },
  "additionalProperties": false
}
```

### 5.6 Creators

```json
{
  "$id": "creators",
  "type": "object",
  "required": ["metrics", "top_creators"],
  "properties": {
    "metrics": {
      "type": "object",
      "required": [
        "creator_count_7d",
        "new_creator_count_7d",
        "repeat_creator_count_7d",
        "new_creator_ratio",
        "repeat_creator_ratio",
        "top_creator_dependency",
        "creator_spread_score"
      ],
      "properties": {
        "creator_count_7d": { "type": "integer" },
        "new_creator_count_7d": { "type": "integer" },
        "repeat_creator_count_7d": { "type": "integer" },
        "new_creator_ratio": { "type": "number" },
        "repeat_creator_ratio": { "type": "number" },
        "top_creator_dependency": { "type": "number" },
        "creator_spread_score": { "type": "number" }
      },
      "additionalProperties": false
    },
    "top_creators": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["creator_id", "platform", "role", "post_count_in_tracker", "avg_similarity", "avg_engagement"],
        "properties": {
          "creator_id": { "type": "string" },
          "platform": { "type": "string" },
          "role": { "type": "string" },
          "post_count_in_tracker": { "type": "integer" },
          "avg_similarity": { "type": "number" },
          "avg_engagement": { "type": "number" },
          "is_brand_like": { "type": "boolean" },
          "recommended_action": { "type": "string" }
        },
        "additionalProperties": false
      }
    }
  },
  "additionalProperties": false
}
```

### 5.7 Samples

```json
{
  "$id": "samples",
  "type": "object",
  "required": ["viral_representative", "early_signal", "new_variant", "cross_platform_repeat", "risk_false_positive"],
  "properties": {
    "viral_representative": { "$ref": "#/$defs/sampleArray" },
    "early_signal": { "$ref": "#/$defs/sampleArray" },
    "new_variant": { "$ref": "#/$defs/sampleArray" },
    "cross_platform_repeat": { "$ref": "#/$defs/sampleArray" },
    "risk_false_positive": { "$ref": "#/$defs/sampleArray" }
  }
}
```

单条样本建议字段：

```json
{
  "platform": "xhs",
  "platform_post_id": "abc",
  "author_id": "creator_1",
  "title": "string",
  "publish_time": "2026-05-23T10:00:00Z",
  "engagement_total": 1234,
  "similarity_score": 88.2,
  "candidate_level": "L1",
  "sample_bucket": "viral_representative",
  "matched_keywords": ["string"],
  "matched_patterns": ["string"],
  "reason_summary": "string",
  "snapshot_delta": {
    "like_delta": 20,
    "comment_delta": 8,
    "collect_delta": 5,
    "share_delta": 2
  }
}
```

### 5.8 Risks

```json
{
  "$id": "risks",
  "type": "object",
  "required": ["items"],
  "properties": {
    "items": {
      "type": "array",
      "items": { "$ref": "#/$defs/riskItem" }
    }
  },
  "additionalProperties": false
}
```

### 5.9 Decisions

```json
{
  "$id": "decisions",
  "type": "object",
  "required": ["decision_type", "decision_confidence", "decision_reason_summary", "recommended_actions"],
  "properties": {
    "decision_type": { "type": "string" },
    "decision_confidence": { "type": "number", "minimum": 0, "maximum": 100 },
    "decision_reason_summary": { "type": "string" },
    "supporting_evidence_count": { "type": "integer" },
    "recommended_actions": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["action", "reason"],
        "properties": {
          "action": { "type": "string" },
          "reason": { "type": "string" },
          "priority": { "type": "string", "enum": ["low", "medium", "high"] }
        },
        "additionalProperties": false
      }
    }
  },
  "additionalProperties": false
}
```

### 5.10 Meta

```json
{
  "$id": "meta",
  "type": "object",
  "required": ["analysis_run_id", "analysis_time", "range", "data_freshness"],
  "properties": {
    "analysis_run_id": { "type": "integer" },
    "analysis_time": { "type": "string", "format": "date-time" },
    "range": { "type": "string" },
    "data_freshness": { "type": "string", "enum": ["fresh", "stale", "partial"] },
    "formula_version": { "type": "string" }
  },
  "additionalProperties": false
}
```

## 6. 请求 Schema 草案

### 6.1 创建 Tracker

```json
{
  "type": "object",
  "required": ["name", "platforms", "included_keywords", "time_window_days"],
  "properties": {
    "name": { "type": "string", "minLength": 1, "maxLength": 120 },
    "platforms": {
      "type": "array",
      "minItems": 1,
      "items": { "type": "string" }
    },
    "included_keywords": {
      "type": "array",
      "minItems": 1,
      "items": { "type": "string" }
    },
    "excluded_keywords": {
      "type": "array",
      "items": { "type": "string" }
    },
    "time_window_days": {
      "type": "integer",
      "minimum": 1,
      "maximum": 90
    }
  },
  "additionalProperties": false
}
```

### 6.2 触发分析

```json
{
  "type": "object",
  "required": ["run_type", "range"],
  "properties": {
    "run_type": {
      "type": "string",
      "enum": ["manual", "scheduled", "backfill", "config_change"]
    },
    "range": {
      "type": "string",
      "enum": ["24h", "7d", "30d"]
    },
    "force_recollect": { "type": "boolean" }
  },
  "additionalProperties": false
}
```

### 6.3 触发补采

```json
{
  "type": "object",
  "required": ["days"],
  "properties": {
    "days": { "type": "integer", "minimum": 1, "maximum": 30 },
    "platforms": {
      "type": "array",
      "items": { "type": "string" }
    },
    "keywords_override": {
      "type": "array",
      "items": { "type": "string" }
    }
  },
  "additionalProperties": false
}
```

## 7. 字段语义与单位约定

- `*_ratio`：默认 `0.0 ~ 1.0`
- `*_share`：默认 `0.0 ~ 1.0`
- `*_score`：默认 `0 ~ 100`
- `*_growth_rate`：可为负值，例如 `-0.23`
- `engagement_total`：默认 `like + comment + collect + share`
- `decision_confidence`：表示结论可信度，不表示业务机会大小
- `keyword_value_score`：表示词对 Tracker 的价值，不表示热度本身

## 8. 兼容性建议

- P0 阶段允许部分字段为空，但结构必须稳定
- 所有新增字段应优先向后兼容
- 公式版本建议通过 `meta.formula_version` 返回，便于重算与前后端校验
