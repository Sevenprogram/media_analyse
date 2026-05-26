# 今日情报默认 AI 分析设计

## 1. 目标

今日情报页默认使用 AI 生成分析结果，但 AI 只能基于真实采集数据、任务状态、规则指标和证据摘要做归纳。页面要回答三个问题：

- 今天优先处理什么。
- 哪些机会值得投入。
- 当前数据和结论是否可信。

这不是单纯的数据看板，也不是纯 AI 聊天页。它是跨模块信号聚合后的每日行动面板。

## 2. 核心原则

- 真实数据优先：采集量、任务状态、样本质量、机会基础分和风险等级由后端规则计算。
- AI 默认参与：今日摘要、行动解释、机会理由、风险说明和补采建议默认由 AI 生成。
- 可追溯：每条 AI 结论必须带证据来源，不能只有自然语言建议。
- 可降级：AI 失败时仍展示规则版结果，并明确标记为规则降级。
- 不让 AI 判定事实：AI 不直接决定任务是否失败、样本数是多少、风险是否存在、机会基础分是多少。

## 3. 当前状态判断

现有页面已经接入部分真实接口：

- `/api/reports/dashboard-summary`
- `/api/research/database/stats`
- `/api/research/jobs`
- `/api/reports/ai-insights/latest`
- `/api/reports/ai-topic-ideas`

但今日情报页仍存在演示兜底：

- `mockActions`
- 默认机会卡片
- 固定风险文案
- 固定样本质量比例
- 固定平台证据量默认值
- 固定最后更新时间

正式制作时，这些只能作为空状态或开发兜底，不能作为默认业务展示。

## 4. AI Provider

默认使用环境变量中的中转站配置：

```env
AI_GATEWAY_API_KEY
AI_GATEWAY_BASE_URL
AI_GATEWAY_MODEL
AI_GATEWAY_TIMEOUT
AI_GATEWAY_MAX_CONCURRENCY
AI_GATEWAY_MAX_TOKENS
AI_GATEWAY_NAME
```

前端不读取 API key。所有 AI 调用走后端 `OpenAICompatibleProvider`。

后端已经存在可复用能力：

- `research/ai_provider.py`
- `/api/research/ai/providers/gateway/bootstrap`
- 内容追踪和内容策略中的 AI Provider 解析逻辑

今日情报应复用这套能力，不新建前端直连 AI。

## 5. 总流程

```text
页面打开
-> 请求最新今日情报
-> 如果结果存在且未过期，直接展示
-> 如果不存在或已过期，后端触发默认 AI 分析
-> 规则聚合真实数据
-> AI 生成今日摘要、行动解释、机会解释、风险说明
-> 保存 AI run 和结构化输出
-> 前端展示 AI 结果、生成时间、模型和证据链
```

刷新按钮分两类：

- 刷新数据：重新读取接口和最新 AI 结果。
- 重新生成：基于当前真实数据重新运行 AI 今日情报。

## 6. 输入数据包

后端给 AI 的输入应是压缩后的结构化数据包，避免直接塞全量原文。

### 6.1 任务与采集

- 运行中任务数
- 失败任务数
- 待处理任务数
- 最近失败原因
- 平台维度采集状态
- 最近更新时间

### 6.2 样本质量

- 总样本数
- 有效样本数
- 低质样本数
- 无效样本数
- 平台覆盖
- 时间新鲜度
- 重复率或噪音率
- 样本质量等级

### 6.3 机会候选

来自已有模块：

- 内容追踪机会
- 达人发现机会
- 友商异常机会
- 关键词热度机会
- 内容策略机会

每个候选必须包含：

- 类型
- 平台
- 基础机会值
- 增长信号
- 样本质量
- 风险标签
- 证据摘要
- 推荐动作

### 6.4 风险候选

- API key 缺失或无效
- 平台限流
- 代理异常
- 入库失败
- 后处理失败
- AI 分析失败
- 样本不足
- 单平台偏样本

## 7. AI 输出结构

AI 必须返回 JSON，不返回 Markdown 长文。

```json
{
  "status": "completed",
  "executive_summary": "string",
  "generated_at": "ISO datetime",
  "provider": {
    "name": "AI Gateway",
    "model": "model name"
  },
  "actions": [
    {
      "id": "string",
      "title": "string",
      "reason": "string",
      "priority_explanation": "string",
      "target_type": "collection|content|creator|competitor|keyword|system",
      "action": "retry_task|collect_more|open_opportunity|contact_creator|create_tracker|review_risk",
      "payload": {},
      "evidence_refs": [],
      "risk_notes": []
    }
  ],
  "opportunity_explanations": [
    {
      "opportunity_id": "string",
      "why_now": "string",
      "suggested_angle": "string",
      "execution_advice": "string",
      "risk_notes": [],
      "evidence_refs": []
    }
  ],
  "risk_explanations": [
    {
      "risk_id": "string",
      "business_impact": "string",
      "recommended_action": "string",
      "evidence_refs": []
    }
  ],
  "sample_quality_explanation": {
    "summary": "string",
    "coverage_gap": "string",
    "collection_advice": "string"
  },
  "data_bias_notes": [],
  "assumptions": []
}
```

## 8. 模块分析口径

### 8.1 顶部上下文

顶部展示当前项目、时间窗口、最后更新时间和 AI 状态。

状态包括：

- AI 分析完成
- AI 分析中
- AI 分析失败，使用规则降级
- 数据已过期，建议重新生成

### 8.2 今日行动清单

规则负责候选生成和基础优先级，AI 负责解释和文案。

排序因素：

- 是否影响数据可信度
- 是否有时间窗口
- 是否能立刻执行
- 是否与当前项目目标相关
- 不处理是否会错过机会

行动类型：

- 修复采集异常
- 补采样本
- 跟进达人
- 加入内容排期
- 查看友商变化
- 调整关键词
- 标记已处理或继续观察

### 8.3 机会队列

机会基础分由规则计算：

```text
机会值 = 增长信号 + 样本质量 + 可执行性 + 项目匹配度 - 风险扣分
```

AI 负责解释：

- 为什么现在值得做。
- 适合什么内容角度。
- 适合哪个平台。
- 有哪些风险。
- 下一步应该跳转到哪个模块。

机会类型：

- 内容机会
- 达人机会
- 话题机会
- 友商变化机会
- 关键词机会

### 8.4 采集与任务风险

规则识别风险，AI 解释业务影响。

必须展示：

- 风险等级
- 影响对象
- 影响范围
- 是否可重试
- 推荐处理动作

风险会反向影响机会排序和行动清单。

### 8.5 样本质量概览

规则计算样本质量，AI 解释可信度。

规则指标：

- 有效样本占比
- 低质样本占比
- 无效样本占比
- 平台覆盖度
- 时间新鲜度
- 样本量是否达到阈值

约束：

- 样本不足时，强行动建议降级为观察建议。
- 单平台样本过高时，标记数据偏向。
- 样本质量低时，机会分上限降低。

### 8.6 数据证据量

数据证据量展示真实统计，不由 AI 生成。

AI 只解释：

- 哪个平台数据更充分。
- 哪个平台需要补采。
- 当前结论是否偏向某平台。

### 8.7 机会详情抽屉

详情抽屉展示完整证据链：

- 规则基础分
- AI 解释
- 样本质量
- 代表性证据
- 风险提示
- 推荐动作
- 人工反馈

人工反馈包括：

- 有效
- 误判
- 继续观察
- 已执行

## 9. 后端设计

建议新增今日情报聚合服务：

- `research/today_intelligence.py`

职责：

- 聚合真实数据
- 生成规则候选 actions、opportunities、risks
- 计算样本质量和证据统计
- 构造 AI 输入包
- 调用 AI Gateway
- 规范化 AI 输出
- 降级为规则版

建议新增接口：

- `GET /api/reports/today-intelligence`
- `POST /api/reports/today-intelligence/run`

`GET` 返回最新结果。没有结果或结果过期时，可以返回 `status=stale|missing`，由前端提示或后端自动触发。

`POST` 强制重新生成 AI 今日情报。

## 10. 数据持久化

P0 可以先用 JSON 状态表或复用现有 AI run 风格。

建议保存：

- 输入摘要
- 规则基础结果
- AI 输出
- provider 信息
- status
- error
- generated_at
- expires_at

这样可以避免页面每次打开都重复消耗 AI。

## 11. 前端设计

`TodayIntelligencePage` 不再默认混入 mock 数据。

前端展示顺序：

1. 规则和 AI 结果加载中。
2. 已有最新 AI 结果。
3. AI 运行中，展示上次结果或骨架屏。
4. AI 失败，展示规则降级结果。
5. 无真实数据，引导创建项目和启动采集。

页面必须显示：

- AI 状态
- 模型
- 生成时间
- 数据窗口
- 是否规则降级

## 12. 错误处理

AI 调用失败时：

- 保存错误信息。
- 页面展示规则版。
- 明确标记 AI 降级。
- 提供重新生成按钮。

数据不足时：

- 不调用或少调用 AI 的强结论生成。
- 让 AI 输出补采建议。
- 页面不展示强机会判断。

Provider 未配置时：

- 页面显示 AI Provider 未配置。
- 提供去设置或 bootstrap 的入口。
- 仍展示规则版结果。

## 13. 测试策略

后端测试：

- Provider 环境变量解析。
- AI 输入包不泄露 API key。
- AI 输出 JSON 规范化。
- AI 失败时规则降级。
- 样本不足时机会降级。
- 真实统计覆盖样本质量和证据量。

前端测试：

- AI 完成状态展示。
- AI 运行中状态展示。
- AI 降级状态展示。
- 空数据状态展示。
- 点击行动和机会跳转正确。

## 14. P0 范围

必须做：

- 默认 AI 今日情报生成。
- 真实数据聚合。
- 规则基础分和风险判断。
- AI 输出结构化解释。
- AI 状态展示。
- 规则降级。
- 去除默认业务 mock 展示。

暂不做：

- 多人协作指派。
- 自动推送。
- 长篇日报编辑器。
- 复杂预测模型。
- 让 AI 自动执行高风险动作。

## 15. 验收标准

- 页面打开默认展示 AI 今日情报或 AI 运行状态。
- 所有行动、机会、风险都有真实数据来源。
- AI 结果显示模型、生成时间和状态。
- AI 失败时页面仍可用，并显示规则降级。
- 机会值、样本质量、风险等级不是 AI 幻觉生成。
- mock 数据不再作为正常业务结果展示。
