# Mail & Message 系统设计文档

## 概览

FP (Future Protocol) 的消息系统采用双层架构设计：

- **Mail（信封层）**：负责传输、路由、加密、签名
- **Message（内容层）**：负责应用层业务逻辑

这种设计遵循关注点分离原则，将传输问题与业务逻辑解耦。

---

## 1. Mail（信封层）

### 1.1 核心职责

Mail 是通信的**传输包装**，类似现实世界的信封：

- **路由信息**：`sender`, `recipient` - 明确从哪里来、到哪里去
- **内容封装**：`message` - 可以是明文 (Message) 或密文 (str)
- **安全保障**：`signature` - 确保发送方身份和内容完整性
- **生命周期跟踪**：`status` - 从发送到处理完成的全流程状态

### 1.2 数据结构

```python
# fp/core/base.py
class MailBase(BaseModel, Generic[SenderT, RecipientT, MessageT, SignatureT]):
    sender: SenderT              # 发送方地址
    recipient: RecipientT        # 接收方地址（可以是列表）
    message: MessageT            # 消息内容（Message 或加密字符串）
    signature: SignatureT        # 签名
    status: MailStatus           # 当前状态
    fp: str = "0.1"              # 协议版本

# fp/mail.py
class Mail(MailBase[FPAddress, list[FPAddress], Message | str, str]):
    """具体实现，使用 FPAddress 路由 + Ed25519 签名 + X25519 加密"""
    signer: SignerVerifier       # 签名验证器
    cipher: EncryptorDecryptor   # 加密解密器
```

### 1.3 Mail 生命周期状态

```python
# fp/core/base.py
class MailStatus(str, Enum):
    SENT       = "sent"        # 已发送：entity.send_message 创建 mail 时
    DELIVERING = "delivering"  # 投递中：host.route_mail 开始路由时
    QUEUED     = "queued"      # 队列中：目标 host WebSocket 断开，等待重连
    FAILED     = "failed"      # 失败：找不到目标 entity 或无可用路由
    RECEIVED   = "received"    # 已送达：entity.receive_mail 存入 mailbox
    PROCESSING   = "processing"    # 处理中：handler 开始处理
    DONE    = "done"     # 已处理：handler 处理完成
```

#### 状态流转图

```
Agent 处理流程：
SENT → DELIVERING → RECEIVED → PROCESSING → DONE

Human 处理流程（跳过 PROCESSING）：
SENT → DELIVERING → RECEIVED → DONE

异常分支：
SENT → DELIVERING → QUEUED   (对方离线)
SENT → DELIVERING → FAILED   (找不到目标)
```

**重要说明**：
- **Agent Entity**: 需要调用 LLM 处理，会经历 PROCESSING 状态
- **Human Entity**: 无需处理，直接从 RECEIVED 跳到 DONE（表示已读）

#### 状态更新触发点

| 状态        | 触发位置                     | 代码位置                          |
|-------------|------------------------------|-----------------------------------|
| SENT        | entity.send_message          | fp/entity.py:298                  |
| DELIVERING  | host.route_mail              | fp/host.py:285                    |
| FAILED      | host.route_mail (找不到entity) | fp/host.py:327                    |
| RECEIVED    | entity.receive_mail          | fp/entity.py:440                  |
| PROCESSING  | entity.receive_mail (Agent only) | fp/entity.py:489                  |
| DONE        | entity.receive_mail (处理完成)   | fp/entity.py:506                  |

**注意**：Human Entity 在 receive_mail 中直接跳到 DONE，不经过 PROCESSING。

### 1.4 Mail 核心方法

```python
# 封装 mail（签名 + 可选加密）
Mail.seal(
    sender: FPAddress,
    recipient: FPAddress,
    message: Message,
    sign_private_key: str,
    encrypt_public_key: str | None
) -> Mail

# 拆封 mail（验签 + 可选解密）
mail.unseal(
    verify_public_key: str | None,
    decrypt_private_key: str | None
) -> Mail | None
```

---

## 2. Message（内容层）

### 2.1 核心职责

Message 是通信的**业务内容**，定义了应用层的交互语义：

- **身份传递**：`sender_card` - 携带发送方完整身份信息（公钥、地址等）
- **交互类型**：`kind` - 定义消息类型（INVOKE、ERROR、FRIEND_REQUEST 等）
- **业务载荷**：`payload` - 具体的业务数据
- **唯一标识**：`message_id` - 用于去重、追踪、回复关联

### 2.2 数据结构

```python
# fp/message.py
class Message(BaseModel):
    message_id: str                     # 消息唯一 ID（UUID）
    sender_card: EntityCard | None      # 发送方身份卡片（用于验签）
    kind: MessageKind                   # 消息类型
    payload: MessagePayload             # 业务数据
    metadata: dict[str, Any]            # 元数据（如 sender_address, reply_to）
```

### 2.3 MessageKind（消息类型）

```python
class MessageKind(str, Enum):
    INVOKE          = "invoke"           # 普通消息/调用
    ERROR           = "error"            # 错误消息
    FRIEND_REQUEST  = "friend_request"   # 好友请求
    FRIEND_ACCEPT   = "friend_accept"    # 接受好友
    FRIEND_REJECT   = "friend_reject"    # 拒绝好友
```

### 2.4 Payload 类型

根据 `MessageKind` 不同，`payload` 有不同的数据结构：

#### InvokePayload（普通消息）

```python
@dataclass
class InvokePayload:
    text: str                    # 消息文本
    session_id: str | None       # 会话 ID（用于多轮对话）
```

#### ErrorPayload（错误消息）

```python
@dataclass
class ErrorPayload:
    error_code: str              # 错误代码
    error_message: str           # 错误描述
    details: dict[str, Any]      # 详细信息
```

#### FriendRequestPayload（好友请求）

```python
@dataclass
class FriendRequestPayload:
    sender_card: EntityCard      # 发送方完整身份信息
    message: str                 # 附加消息
```

---

## 3. Mail & Message 的关系

```
┌─────────────────────────────────────────┐
│              Mail (信封)                │
│  ┌───────────────────────────────────┐  │
│  │ sender:   alice@host1:entity1     │  │
│  │ recipient: [bob@host2:entity2]    │  │
│  │ signature: "0x1a2b3c..."          │  │
│  │ status: RECEIVED                  │  │
│  │ ┌─────────────────────────────┐   │  │
│  │ │    Message (内容)            │   │  │
│  │ │  message_id: "uuid-123"     │   │  │
│  │ │  kind: INVOKE               │   │  │
│  │ │  payload:                   │   │  │
│  │ │    text: "Hello, Bob!"      │   │  │
│  │ │    session_id: "session-1"  │   │  │
│  │ └─────────────────────────────┘   │  │
│  └───────────────────────────────────┘  │
└─────────────────────────────────────────┘
```

### 关键设计原则

1. **Mail 不关心内容语义**
   - Mail 只负责把 Message 从 A 送到 B
   - 不解析 Message 内部的 kind/payload

2. **Message 不关心传输细节**
   - Message 不知道自己会被加密、签名、路由
   - 只定义业务层的交互协议

3. **解耦的好处**
   - 可以独立升级传输层（如更换加密算法）
   - 可以独立扩展消息类型（如添加新的 MessageKind）

---

## 4. 完整消息流程

### 4.1 发送流程（Alice → Bob）

```python
# 1. Alice 创建 Message
message = Message(
    message_id=uuid4().hex,
    sender_card=alice.get_card(),
    kind=MessageKind.INVOKE,
    payload=InvokePayload(text="Hello", session_id="session-1"),
    metadata={}
)

# 2. Alice 将 Message 封装成 Mail
mail = Mail.seal(
    sender=alice.address,
    recipient=bob.address,
    message=message,
    sign_private_key=alice.sign_private_key,
    encrypt_public_key=bob.encrypt_public_key  # 可选加密
)
# 此时 mail.status = SENT

# 3. Alice 发送 Mail（通过 entity.send_message）
await alice.send_message(to=bob.address, message=message)
# → 保存到 Alice 的 outbound mailbox
# → 调用 host.route_mail

# 4. Host 路由 Mail
# mail.status = DELIVERING
await alice_host.route_mail(mail)
# → 如果 Bob 在本地：直接投递
# → 如果 Bob 在 child/parent：转发
# → 如果找不到：mail.status = FAILED

# 5. Bob 收到 Mail（entity.receive_mail）
# mail.status = RECEIVED
await bob.receive_mail(mail)
# → 保存到 Bob 的 inbound mailbox
# → 通知发送方状态更新（WebSocket）

# 6. Bob 的 Handler 处理 Message
# mail.status = PROCESSING
await bob.handler.handle(message)
# → 执行业务逻辑
# → 生成回复（如果需要）

# 7. Handler 完成处理
# mail.status = DONE
# → 标记 mailbox 为已处理
# → 通知发送方状态更新
```

### 4.2 状态通知机制

每次状态变更时，接收方会通过 WebSocket 推送状态更新给发送方：

```python
# fp/entity.py
async def _send_status_update(
    self,
    message_id: str,
    sender_address: str,
    new_status: MailStatus
) -> None:
    """通知发送方状态变化"""
    await notify_status_update(sender_entity_uid, {
        "message_id": message_id,
        "status": new_status.value,
        "timestamp": datetime.utcnow().isoformat()
    })
```

前端收到后更新 UI：

```typescript
// aln/web/src/stores/app.ts
function handleStatusUpdate(data: any) {
  // 触发 ChatView 更新消息状态
  notifyMessageListeners({ type: 'status_update', data })
}
```

---

## 5. Mailbox（本地存储）

### 5.1 职责

Mailbox 是每个 entity 的**本地消息存储**，采用 JSONL 格式：

- 保存 inbound（收到的）和 outbound（发出的）mail
- 支持按 `is_read`, `is_done`, `direction` 过滤
- 提供状态更新方法（`mark_as_read`, `mark_as_done`）

### 5.2 存储格式

```jsonl
{"mail": {...}, "metadata": {"direction": "inbound", "is_read": false, "is_done": false, "timestamp": "...", "status": "received"}}
{"mail": {...}, "metadata": {"direction": "outbound", "is_read": true, "is_done": true, "timestamp": "...", "status": "done"}}
```

### 5.3 核心方法

```python
# fp/mailbox.py
class Mailbox:
    def save_inbound(self, mail: Mail) -> None
    def save_outbound(self, mail: Mail) -> None
    def list_mails(is_read=None, is_done=None, direction=None) -> list
    def get_mail(mail_id: str) -> dict | None
    def mark_as_read(mail_id: str) -> bool
    def mark_as_done(mail_id: str) -> bool
    def mark_mail_status(mail_id: str, status: MailStatus) -> bool
```

---

## 6. Handler（消息处理器）

### 6.1 Handler 类型

不同 EntityKind 有不同的 Handler：

| EntityKind | Handler        | 功能                          |
|------------|----------------|-------------------------------|
| HUMAN      | HumanHandler   | 简单记录 + 送达确认           |
| AGENT      | AgentHandler   | 调用 AI Provider 处理消息     |
| TOOL       | MCPHandler     | 执行工具调用（MCP 协议）      |
| RESOURCE   | MCPHandler     | 提供资源访问                  |
| SERVICE    | MCPHandler     | 提供服务                      |

### 6.2 AgentHandler 流程

```python
async def handle(self, message: Message) -> None:
    # 1. 异步处理（不阻塞）
    asyncio.create_task(self._process_message(message))

async def _process_message(self, message: Message) -> None:
    # 2. 更新状态为 PROCESSING
    mailbox.mark_mail_status(message.message_id, MailStatus.PROCESSING)

    # 3. 调用 AI Provider（codex、claude 等）
    result = await self.adapter.run_turn(text, config, ...)

    # 4. 发送回复
    await self.entity.send_message(to=sender, message=response)

    # 5. 标记为 DONE
    mailbox.mark_as_done(message.message_id)
```

### 6.3 HumanHandler 流程

```python
async def handle(self, message: Message) -> None:
    # 1. 记录日志
    self._log_message(message, handler_name="HumanHandler")

    # 2. 发送送达确认（避免前端一直显示"处理中"）
    if message.kind == MessageKind.INVOKE:
        delivery_message = Message(
            kind=MessageKind.INVOKE,
            payload={"text": f"{self.entity.name} 已收到你的消息", ...},
            status="completed"
        )
        await self.entity.send_message(to=sender, message=delivery_message)

    # 3. 标记为已读
    mailbox.mark_as_read(message.message_id)
```

---

## 7. 前端渲染（UI 层）

### 7.1 消息状态显示

前端在**我发出的消息**下方显示 Mail 状态：

```vue
<!-- aln/web/src/components/chat/MessageItem.vue -->
<div class="text-xs text-gray-400">
  <span>{{ formatTime(message.timestamp) }}</span>

  <!-- 只在我发出的消息上显示状态 -->
  <span v-if="isFromMe && message.status">
    · <span :class="getStatusColor(message.status)">
        {{ formatStatus(message.status) }}
      </span>
  </span>
</div>
```

状态颜色映射：

| 状态       | 中文     | 颜色       | 说明 |
|------------|----------|------------|------|
| sent       | 已发送   | 灰色       | 消息刚发出 |
| delivering | 投递中   | 蓝色       | 正在路由 |
| queued     | 队列中   | 黄色       | 对方离线 |
| failed     | 失败     | 红色       | 路由失败 |
| received   | 已送达   | 绿色       | 对方收到 |
| processing | 处理中   | 蓝色       | Agent 调用 LLM（Human 不显示） |
| done       | 已完成   | 深绿       | 处理完成 |

### 7.2 状态实时更新

通过 WebSocket 接收状态变化：

```typescript
// aln/web/src/views/ChatView.vue
function handleWebSocketMessage(data: any) {
  if (data.type === 'status_update') {
    const { message_id, status } = data.data

    // 找到对应消息并更新状态
    const msgIndex = messages.value.findIndex(m => m.message_id === message_id)
    if (msgIndex !== -1) {
      messages.value[msgIndex].status = status
    }
  }
}
```

---

## 8. 关键设计决策

### 8.1 为什么 Mail 和 Message 分层？

- **传输层变更不影响业务**：可以升级加密算法、路由策略，不改 Message
- **业务层扩展不影响传输**：可以新增 MessageKind，不改 Mail
- **职责清晰**：Mail = "怎么送"，Message = "送什么"

### 8.2 为什么用 JSONL 存储 Mailbox？

- **简单高效**：无需数据库，适合本地存储
- **追加友好**：新消息直接 append，不需要重写整个文件
- **易于备份**：纯文本格式，方便迁移

### 8.3 为什么状态通知用 WebSocket？

- **实时性**：状态变更立即推送给发送方
- **轻量级**：只推送状态更新，不重传整个消息
- **双向通信**：支持 ping/pong 心跳保活

### 8.4 为什么 sender_card 放在 Message 而不是 Mail？

- **Message 需要验签**：接收方拆封 Mail 后，用 `sender_card.sign_public_key` 验证签名
- **Friend 系统依赖 card**：收到好友请求时，需要 `sender_card` 的完整信息
- **Mail 只负责路由**：sender 只需要 FPAddress，不需要完整身份

---

## 9. 未来优化方向

### 9.1 QUEUED 状态实现

当检测到 WebSocket 断开时：

1. Host 将 Mail 状态设为 QUEUED
2. 将 Mail 存入本地队列（持久化）
3. WebSocket 重连后，自动重发队列中的 Mail

### 9.2 批量状态通知

当大量消息状态变更时，合并为一次 WebSocket 推送：

```typescript
{
  type: 'status_batch_update',
  data: [
    { message_id: 'abc', status: 'received' },
    { message_id: 'def', status: 'processing' },
    ...
  ]
}
```

### 9.3 消息去重优化

在 Mailbox 层面实现去重：

- 根据 `message_id` 检测重复
- 避免网络重传导致的重复存储

---

## 10. 总结

FP 的 Mail & Message 系统通过分层设计实现了：

✅ **关注点分离**：传输与业务逻辑解耦
✅ **可扩展性**：独立升级各层
✅ **状态可观测**：完整的生命周期跟踪
✅ **实时性**：WebSocket 推送状态更新
✅ **安全性**：签名 + 可选加密

这套设计为构建可靠的点对点通信系统提供了坚实基础。
