# Creator Monitor Design

## Goal

在现有“友商监控”工作台中增加“达人监控”能力，用于跟踪合作达人宣发内容的发布和公开互动数据。

## Approved Direction

采用同页双列表切换方案：保留当前三栏工作台结构，在左侧“监控列表”中增加“友商 / 达人”分段切换。切换到达人时，列表、添加按钮、概览文案和空状态切换为达人宣发监控语义。

## Entry Points

1. 监控页通过主页链接添加达人。
2. 达人发现页搜索结果中新增“添加监控”按钮，直接把该达人加入达人监控列表。

## Data Model

复用现有 `research_competitor_accounts` 表和采集链路，因为现有友商监控实际以 `platform + creator_id` 作为账号采集目标。新增 `monitor_type` 字段区分：

- `competitor`: 友商监控账号，作为现有数据的默认值。
- `partner_creator`: 合作达人监控账号。

## API Behavior

- 创建账号接口支持 `monitor_type`。
- 从 URL 创建账号接口支持 `monitor_type`。
- 从达人发现结果创建账号接口复用候选创建接口，并支持 `monitor_type=partner_creator`。
- 列表接口支持按 `monitor_type` 过滤，默认返回 `competitor`，避免现有友商报表混入合作达人。

## Frontend Behavior

- 友商监控工作台维护当前选中的 `monitor_type`。
- 左侧列表按类型请求账号。
- 添加抽屉根据当前类型切换标题和提交字段。
- 达人发现结果操作列增加“添加监控”，成功后按钮显示“已监控”。

## Out Of Scope

- 首期不新增独立达人宣发合同、排期或投放预算模型。
- 首期不做评论情绪和费用 ROI。
- 首期不允许同一 `platform + creator_id` 同时作为友商和合作达人存在。
