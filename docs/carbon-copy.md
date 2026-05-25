# CarbonCopy 机制

CarbonCopy (CC) 是 Foundation Protocol 的消息监控机制。
当 Entity 之间通信时，系统自动将消息副本转发给 Entity 的 Owner，
使 Owner 能够监控其下属 Agent 的所有通信活动。


## 核心概念

**Owner 关系**：每个 Entity 可以有一个 `owner`（类型为 `FPAddress`），
通常是 Human Entity。Owner 自动接收其所有下属 Entity 的通信副本。

**Direction**：CC 分为两个方向：
- `outbound` — Agent 发送消息时，由发送方 Agent 生成
- `inbound` — Agent 接收消息时，由接收方 Agent 的 Checkpoint 生成

**同一条原始消息会产生两条 CC**：
一条来自发送方（outbound），一条来自接收方（inbound）。
两条 CC 通过 `original_message_id` 关联到同一条原始消息。


## 数据模型

```python
# fp/message.py
class CarbonCopyPayload(BaseModel):
    original_sender: str          # 原始消息发送方地址 (host_uid:entity_uid)
    original_sender_name: str     # 发送方名称
    original_recipient: str       # 原始消息接收方地址
    original_recipient_name: str  # 接收方名称
    original_kind: str            # 原始消息类型 (invoke, text, etc.)
    original_message_id: str      # 原始消息 ID（两条 CC 共享同一个）
    direction: str                # "outbound" | "inbound"
    timestamp: str                # ISO 格式 UTC 时间
    cost: float | None = None     # 消息成本（如 LLM token 费用）
    summary: str | None = None    # 原始消息内容摘要（前 100 字符）
```

CC 消息使用 `MessageKind.CARBON_COPY` (`"carbon_copy"`) 作为消息类型，
通过正常的消息发送通道（`entity.send_message`）投递给 Owner。


## 后端生成流程

### 路径 1：Outbound CC（发送方触发）

`fp/entity.py` — `Entity.send_message()` 方法。

当 Entity 发送消息时，检查三个条件：
1. Entity 有 Owner
2. 消息本身不是 CC（防止循环）
3. 收件人不是 Owner（Owner 自己能看到直接收到的消息）

全部满足时，调用 `_send_carbon_copy_to_owner(direction="outbound")`，
由发送方 Entity 直接向 Owner 发送一条 CC 消息。

### 路径 2：Inbound CC（接收方 Checkpoint 触发）

`fp/core/checkpoint.py` — `CarbonCopyCheckpoint.execute()` 方法。

当 Entity 收到消息时，Checkpoint 拦截处理：

**Case 1**：收到的消息是 CC（`kind == CARBON_COPY`）
→ 格式化日志输出 → 如果 Entity 是 Human，推送到 Web UI → 返回 `handled_success()`

**Case 2**：收到的是普通消息
→ 检查 Entity 有 Owner 且发送方不是 Owner
→ 构建 `CarbonCopyPayload(direction="inbound")`
→ 发送给 Owner → 返回 `success()`（继续后续 Checkpoint 处理）


## 推送到前端

### WebSocket 实时推送

`aln/app/service/host_server.py` — `push_to_web()` 方法。

CarbonCopyCheckpoint 在 Case 1 中检测到 Human Entity 收到 CC 后，
调用 `entity.host.push_to_web(entity.uid, message)` 推送到前端。

推送格式：
```json
{
  "type": "new_message",
  "data": {
    "message_id": "...",
    "kind": "carbon_copy",
    "sender": "host_uid:entity_uid",
    "recipient": ["host_uid:owner_uid"],
    "payload": { /* CarbonCopyPayload */ },
    "timestamp": "2025-01-01T12:00:00",
    "direction": "inbound"
  }
}
```

### Mailbox 轮询（WebSocket 不可用时的 Fallback）

CC 面板打开时，每 5 秒轮询 `/api/v1/messages/{entity_uid}`，
从 Mailbox 历史中提取 CC 消息（通过 `original_sender` / `original_recipient` 字段识别），
加载到 Zustand Store 中。


## 前端实现

### 状态管理 — Zustand Store

`aln/web/src/stores/app.ts`

```typescript
carbonCopyMessages: CarbonCopyMessage[]  // 最多 200 条，滑动窗口
ccLastViewedAt: number                    // 上次查看时间戳（用于未读 badge）

addCarbonCopy(msg)      // WebSocket 实时添加，按 id 去重
loadCarbonCopies(msgs)  // 批量加载（Mailbox 轮询），按 id 去重
markCcViewed()           // 更新查看时间
clearCarbonCopies()      // 清空所有 CC
```

### WebSocket 处理 — `use-websocket.ts`

接收 `kind === "carbon_copy"` 的消息后：
1. 转换为 `CarbonCopyMessage` 类型
2. 调用 `addCarbonCopy(cc)` 存入 Store
3. 通过 Listener 广播 `WsEvent { type: "carbon_copy" }`

### CC 面板 — `carbon-copy-panel.tsx`

侧边栏面板，在 Chat 页面右侧弹出：
- 接收 `contactUid` prop，**按当前联系人过滤** CC
  （只显示 `originalSender` 或 `originalRecipient` 匹配的 CC）
- 宽度可拖拽调整（260–600px），持久化到 localStorage
- 打开时自动滚动到底部
- 底部有 "Clear all" 清空按钮
- Header 显示过滤后的 CC 数量

### CC 卡片 — `CarbonCopyItem`（在 `message-item.tsx`）

每条 CC 显示为一张卡片：
- 方向图标：绿色 ↙ (inbound) / 蓝色 ↗ (outbound)
- 发送方 → 接收方名称
- 消息类型 Badge (invoke, text, etc.)
- 内容默认折叠 3 行，点击展开
- 复制按钮 + 时间戳

### 未读 Badge — Chat Header

CC 按钮上显示未读数量 Badge：
- 只统计当前联系人相关的 CC
- 基于 `ccLastViewedAt` 时间戳判断未读
- 打开面板时调用 `markCcViewed()` 清除


## 跳过 CC 的条件

| 条件 | 位置 | 说明 |
|------|------|------|
| `entity.owner is None` | 两个路径 | Entity 没有 Owner |
| `message.kind == CARBON_COPY` | Outbound 路径 | 防止 CC 的 CC（循环） |
| `recipient == owner` | Outbound 路径 | Owner 自己能看到直接消息 |
| `sender == owner` | Inbound 路径 | Owner 发的消息不需要抄送 |


## 消息流示例

场景：GYF（Human Owner）的两个 Agent 通信。

```
MyClaude-1 发消息给 MyCodex-1：

1. MyClaude-1.send_message(to=MyCodex-1, message="你好")
   ├── 路由消息给 MyCodex-1
   └── Outbound CC → GYF
       (sender=MyClaude-1, recipient=MyCodex-1, direction=outbound)

2. MyCodex-1 收到消息
   └── CarbonCopyCheckpoint.execute()
       └── Inbound CC → GYF
           (sender=MyClaude-1, recipient=MyCodex-1, direction=inbound)

3. GYF 收到两条 CC
   ├── CC 1: outbound（从 MyClaude-1 转发）
   └── CC 2: inbound（从 MyCodex-1 转发）
   两条共享同一个 original_message_id
```

GYF 在前端打开 MyClaude-1 的聊天窗口时，
CC 面板会显示所有涉及 MyClaude-1 的 CC（包括 inbound 和 outbound）。
切换到 MyCodex-1 时，面板自动切换为 MyCodex-1 相关的 CC。
