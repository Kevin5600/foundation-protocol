# CallOwner Checkpoint 设计

## 核心概念

**CallOwner 是 Checkpoint 的通用能力**：当 Entity 收到需要人类决策的消息时，自动转发给 Owner 请求操作或授权。

## 已有架构

FP 已有完整的 Checkpoint pipeline，每个 Entity 持有有序的 `checkpoints: list[CheckPoint]`：

```
收到 Mail → unseal → 存 mailbox → _points_checking (checkpoint pipeline)
  100-199  Session 验证
  200-299  权限 (FriendCheckPoint, FriendRequestCheckPoint)
  300-399  频率/内容
  400-499  业务验证
  500-599  用户自定义
  800-899  副作用 (CarbonCopyCheckpoint)
  900-999  执行 (ArbiterCheckPoint)
```

## CallOwner 策略（三级）

每个 CheckPoint 支持三种 call_owner 策略，前提是 Entity 有 owner：

| 策略 | 说明 |
|------|------|
| `always_pass` | 全通过，不 call owner，agent 自主决策 |
| `conditional` | 按条件决定是否 call（如金额 > 阈值才 call），条件规则各 checkpoint 自定义，先预留 |
| `always_call` | 全需要 call owner，无 owner 则 fallback 到 always_pass |

**本次实现 `always_call` 策略。**

## 所有 Call Owner 场景

### 1. 好友请求

| 字段 | 值 |
|------|---|
| 触发 | 收到 `friend_request` |
| 现状 | `FriendRequestCheckPoint` 硬编码 `approved = True` |
| action_type | `require_approval` |
| 描述 | "{name} 想加你为好友" |
| 操作 | [同意] → friend_accept / [拒绝] → friend_reject |
| auto_reply | "好友请求已收到，等待确认" |

### 2. 收到合同邀请

| 字段 | 值 |
|------|---|
| 触发 | 收到 `contract_status` 且 status=draft（对方创建了合同，等你 approve） |
| 现状 | `ContractApprovalCheckPoint` 硬编码 `auto_approve = True` |
| action_type | `require_approval` |
| 描述 | "收到合同邀请: {title}, 金额 ¥{amount}" |
| 操作 | [签约] → contract_approve / [拒绝] → contract_reject |
| auto_reply | "合同邀请已收到，等待 Owner 审核" |

### 3. 交付验收

| 字段 | 值 |
|------|---|
| 触发 | Party A 收到 `contract_status` 且 status=completing |
| 现状 | 无处理，需要人工去 Trade 页操作 |
| action_type | `require_approval` |
| 描述 | "合同 {title} 已提交交付，请验收" |
| 操作 | [验收通过] → contract_accept / [要求返工] → contract_rework |
| auto_reply | "已收到交付，等待 Owner 验收" |

### 4. ESCROW 付款授权

| 字段 | 值 |
|------|---|
| 触发 | 合同 approve 后 Arbiter 要冻结资金 |
| 现状 | 直接扣款，余额不足则 cancel |
| action_type | `require_approval` |
| 描述 | "合同 {title} 需冻结 ¥{amount}，是否授权？" |
| 操作 | [授权] → 允许 Arbiter 扣款 / [拒绝] → contract_cancel |
| auto_reply | "付款授权请求已收到，等待 Owner 确认" |

### 5. DIRECT 收款方提供收款链接

| 字段 | 值 |
|------|---|
| 触发 | Agent 作为收款方需要发起收款 |
| 现状 | 无此流程 |
| action_type | `require_input` |
| 描述 | "合同 {title} 进入付款阶段，请提供收款链接/二维码" |
| 输入 | URL 或图片（base64） |
| auto_reply | 无 |

### 6. DIRECT 付款方执行付款

| 字段 | 值 |
|------|---|
| 触发 | 收到 `pay_request` |
| 现状 | `PaymentApprovalCheckPoint` 有 policy 但直接放行 |
| action_type | `require_input` |
| 描述 | "收到付款请求 ¥{amount}" |
| 展示 | 收款链接/二维码 + [我已付款] 按钮 |
| auto_reply | "收款请求已收到，已转发给 Owner" |

### 7. DIRECT 收款方确认到账

| 字段 | 值 |
|------|---|
| 触发 | 收到 `pay_claim_completed` |
| 现状 | 无 checkpoint |
| action_type | `require_approval` |
| 描述 | "对方已标记付款 ¥{amount}，请确认到账" |
| 操作 | [确认收到] → pay_confirm_receipt / [有争议] → pay_dispute |
| auto_reply | "已收到付款通知，等待确认" |

### 8. 合同评分

| 字段 | 值 |
|------|---|
| 触发 | 合同进入 settling |
| 现状 | 需要人工去 Trade 页操作 |
| action_type | `require_input` |
| 描述 | "合同 {title} 已完成，请评分" |
| 输入 | 评分 1-5 + 评价文字 |
| auto_reply | 无 |

## 消息协议

### 新增 MessageKind

- `APPROVAL_REQUEST` — Entity → Owner
- `APPROVAL_RESPONSE` — Owner → Entity

### ApprovalRequestPayload

```python
class ApprovalRequestPayload(BaseModel):
    request_id: str
    source_entity_uid: str
    source_entity_name: str
    action_type: str              # "require_approval" | "require_input"
    description: str
    original_kind: str
    original_payload: dict
    available_actions: list[str]  # ["approve", "reject"] 等
```

### ApprovalResponsePayload

```python
class ApprovalResponsePayload(BaseModel):
    request_id: str
    action: str                   # "approve" | "reject" | "submit_input"
    input_data: str | None = None
    method: str | None = None
```

## 等待机制

```
call_owner 发出 approval_request 后：
  ├── 同步等待 10s
  │   ├── 10s 内 owner 响应 → 立即返回 OwnerResponse
  │   └── 超时 → 消息挂起，存入 pending_approvals
  │
  └── 超时后 owner 异步响应 →
      ApprovalResponseCheckPoint 收到 →
      从 pending_approvals 取回原始消息 →
      恢复处理
```

Agent 侧提示: "已发送至邮箱，等待确认。你可以继续其他操作，对方回复后会自动通知你。"

## 实现方案

### CallOwnerMixin

```python
class CallOwnerMixin:
    call_owner_policy: str = "always_call"  # "always_pass" | "conditional" | "always_call"

    async def call_owner(self, entity, message, mail, action_type, description, ...):
        if self.call_owner_policy == "always_pass" or not entity.owner:
            return OwnerResponse(action="approve")
        # ... 发消息、等待、超时挂起
```

给现有 checkpoint 加 mixin，不创建新 checkpoint 类型。复用一套 call_owner 逻辑覆盖全部 8 个场景。

### 前端 — 通用 ApprovalCard

一个组件根据 `action_type` + `original_kind` 动态渲染，覆盖所有 8 种场景。不为每种场景写单独的卡片。

## 实现步骤

1. 消息协议: MessageKind + Payload 定义
2. CallOwnerMixin: call_owner 方法 + 等待/超时/挂起机制
3. ApprovalResponseCheckPoint: 处理 owner 响应
4. 改造现有 CheckPoint: 集成 CallOwnerMixin
5. 前端: ApprovalCard + approval_response 发送
6. CLI: aln set checkpoint 参数
7. Arbiter 改造: DIRECT 模式 settling 触发付款
8. 全量单测
