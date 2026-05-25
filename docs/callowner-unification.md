# Callowner 统一改造 TODO

当前目标：把 Callowner 统一成协议层审批机制，不再把审批逻辑散落在
checkpoint、handler、CLI 文案三个位置。

## 统一语义

### outbound_intercept

A 发送时被拦截。A 立即得到一条本地或接口状态：

> 消息需要 owner 审核；通过后自动继续发送；驳回则终止；结果会通知你。

这类消息在 owner 审核通过前，不进入对方 mailbox。

### inbound_intercept

A 发出后，只要到达 B mailbox，A 的视角就算发送成功。

之后若 B 侧要 owner 审核，由 B 收到一条通知：

> 你收到一条 xxx；当前由 owner 处理或审核中；结果会通知你；你可以提醒 owner。

owner 处理完后，再通知 B：

> 审核结果 + 你可以继续执行 xxx。

### notify_only

纯通知，不进入 owner 审批，不复用 Callowner 状态文案。

## 消息矩阵

### friend

- `friend_request`: `inbound_intercept`
- `friend_accept`: `notify_only`
- `friend_reject`: `notify_only`

### contract

- `contract_create`: `outbound_intercept`
- `contract_approve`: `outbound_intercept`
- `contract_reject`: `outbound_intercept`
- `contract_complete`: `outbound_intercept`
- `contract_accept`: `outbound_intercept`
- `contract_rework`: `outbound_intercept`
- `contract_amend`: `outbound_intercept`
- `contract_rate`: `outbound_intercept`
- `contract_cancel`: `outbound_intercept`
- `contract_dispute`: `outbound_intercept`
- `contract_status`: `inbound_intercept`

### pay

- `pay_collect`: 发送时 `outbound_intercept`，收信时 `inbound_intercept`
- `pay_claim_completed`: `inbound_intercept`
- `pay_confirm_receipt`: `inbound_intercept`
- `pay_completed`: `notify_only`

## 改造原则

1. 审批决策只允许发生在 checkpoint。
2. handler 不再直接 `call_owner` 做审批分流。
3. 所有审批流都必须补齐三类通知：
   - pending
   - approved
   - rejected
4. 所有 outbound reject 都必须通知 A。
5. 所有 inbound 审批完成都必须通知 B。

## 代码任务

### Phase 1

- [x] 扩展 `ApprovalStatusPayload`，补结构化字段
- [x] 在 `fp/core/checkpoint.py` 抽统一审批状态 helper
- [x] 给 `PendingApproval` 保存原始预览文本
- [x] 修复 outbound contract create reject 未通知 A
- [x] 修复 outbound contract action reject 未通知 A
- [x] 统一 outbound pay_collect approve/reject 文案
- [x] 统一 inbound friend pending/result 文案
- [x] 统一 inbound contract pending/result 文案
- [x] 统一 inbound pay pending/result 文案

### Phase 2

- [x] 去掉 `AgentHandler` 中审批相关 `call_owner`
- [x] `PAY_CONFIRM_RECEIPT` 补成独立 checkpoint
- [x] `PAY_COMPLETED` 改为纯通知，不走 Callowner
- [x] 收敛 CLI 返回文案与 mailbox 展示

### Phase 3

- [x] Web 聊天区按结构化审批状态显示
- [x] 完善 CLI mailbox 的审批通知显示
- [x] 补齐协议层和 API 层回归测试

## 本轮先做

1. 文档落地
2. 协议层审批状态 helper
3. outbound 审批完成通知补齐
4. 移除 `AgentHandler` 中已经被 checkpoint 覆盖的审批入口
