# A2A 协议与 Python SDK 代码架构校验（基于本机源码快照）

## 1. 校验范围与关键纠偏

本文件按以下代码快照核验：

- 本地下载快照：`~/Downloads/a2a-python-main`
- 远端最新 `main` 校验快照（2026-03-01 拉取）：`/tmp/a2a-python-latest`
- 关键源码：
  - `README.md`
  - `src/a2a/types.py`
  - `src/a2a/client/*`
  - `src/a2a/server/*`
  - `src/a2a/grpc/a2a_pb2.py`

关键纠偏结论（最重要）：

- 截至 **2026-03-01**，该 SDK 最新代码实现基线仍是 **A2A v0.3.0**，不是 v1.0。
  - 证据：`README.md` 的 compatibility 章节明确写 `v0.3.0`。
  - 证据：`CHANGELOG.md` 顶部最新版本为 `0.3.24 (2026-02-20)`，仍属 `0.3.x` 线。
  - `types.py` 中 `AgentCard.protocol_version` 默认值也是 `"0.3.0"`。

## 2. 当前 SDK 的协议事实（按代码）

## 2.1 版本与打包形态

- 包名：`a2a-sdk`
- Python：`>=3.10`
- 类型层：`src/a2a/types.py` 为 datamodel-codegen 生成文件（文件头直接标注 generated）。
- gRPC 层：`src/a2a/grpc/a2a_pb2.py`、`a2a_pb2_grpc.py` 由 proto 生成。

## 2.2 当前方法面（JSON-RPC）

来自 `src/a2a/types.py` 的 `method: Literal[...]`：

- `message/send`
- `message/stream`
- `tasks/get`
- `tasks/cancel`
- `tasks/resubscribe`
- `tasks/pushNotificationConfig/set`
- `tasks/pushNotificationConfig/get`
- `tasks/pushNotificationConfig/list`
- `tasks/pushNotificationConfig/delete`
- `agent/getAuthenticatedExtendedCard`

注意：

- 此快照下没有 `tasks/list` JSON-RPC 方法。

## 2.3 任务状态机（SDK 可见枚举）

`TaskState`（`src/a2a/types.py`）包含：

- `submitted`
- `working`
- `input-required`
- `completed`
- `canceled`
- `failed`
- `rejected`
- `auth-required`
- `unknown`

终态在默认 handler 中按代码判定为：

- `completed`
- `canceled`
- `failed`
- `rejected`

## 2.4 AgentCard 结构（v0.3.x 风格）

当前字段体系重点是：

- `url`
- `preferred_transport`
- `additional_interfaces`
- `capabilities`（`streaming` / `push_notifications` / `extensions`）
- `security_schemes`
- `security`
- `skills`
- `supports_authenticated_extended_card`
- `signatures`

这与 v1.0 常见叙述里的 `supportedInterfaces/protocolBinding` 等字段命名并不相同。

## 3. A2A Python SDK 分层架构

## 3.1 类型与协议绑定层

- `a2a.types`：Pydantic 模型（由 JSON Schema 生成）。
- `a2a.grpc`：protobuf/gRPC 生成代码。
- `a2a_pb2.py` 内嵌 HTTP 注解，映射 REST 路径。

## 3.2 Client 层

核心组件：

- `BaseClient`（统一 transport 无关逻辑）
- `ClientFactory`（按 AgentCard + ClientConfig 选择 transport）
- `ClientConfig`（streaming/polling/accepted_output_modes/extensions 等）

支持传输：

- JSON-RPC（`client/transports/jsonrpc.py`）
- REST（`client/transports/rest.py`）
- gRPC（`client/transports/grpc.py`，需可选依赖）

协商逻辑要点：

- 默认优先 server 偏好 transport（可通过 `use_client_preference` 切换）。
- 若双方无交集 transport，会直接报错。

## 3.3 Server 层

应用适配层：

- JSON-RPC app：`server/apps/jsonrpc/*`
- REST app：`server/apps/rest/*`

协议处理层：

- `JSONRPCHandler`
- `RESTHandler`
- `GrpcHandler`

这三类 handler 最终都委托到统一抽象接口 `RequestHandler`。

## 3.4 执行与状态编排层（SDK 核心价值）

默认实现：`DefaultRequestHandler`

编排对象：

- `AgentExecutor`（用户必须实现核心业务执行/cancel）
- `TaskStore`（InMemory 或 Database）
- `QueueManager`（InMemoryQueueManager 默认）
- `EventQueue` + `EventConsumer`
- `TaskManager`
- `ResultAggregator`
- `TaskUpdater`（给 Agent 的高层发布工具）

架构特征：

- 事件驱动（Producer-Consumer）
- 流式与非流式共用同一事件管线
- 支持 client 断流后后台继续消费并持久化任务状态

## 4. 传输与接口映射（按代码）

## 4.1 JSON-RPC HTTP 入口

- 默认 RPC 路径：`/`（`DEFAULT_RPC_URL`）
- Agent Card：`/.well-known/agent-card.json`
- 旧兼容路径：`/.well-known/agent.json`
- 扩展卡旧 HTTP 端点：`/agent/authenticatedExtendedCard`（存在弃用提示）

## 4.2 REST 映射（SDK 当前实现）

`RESTAdapter.routes()` 提供：

- `POST /v1/message:send`
- `POST /v1/message:stream`（SSE）
- `GET /v1/tasks/{id}`
- `POST /v1/tasks/{id}:cancel`
- `GET /v1/tasks/{id}:subscribe`（SSE）
- `POST /v1/tasks/{id}/pushNotificationConfigs`
- `GET /v1/tasks/{id}/pushNotificationConfigs/{push_id}`

同时还注册了：

- `GET /v1/tasks/{id}/pushNotificationConfigs`
- `GET /v1/tasks`

但当前 `RESTHandler` 对这两个接口是 `NotImplementedError`，不能表述为“已完整可用”。

## 4.3 gRPC 服务面

`a2a_pb2.py` 可见服务 `A2AService` 方法：

- `SendMessage`
- `SendStreamingMessage`
- `GetTask`
- `CancelTask`
- `TaskSubscription`
- `CreateTaskPushNotificationConfig`
- `GetTaskPushNotificationConfig`
- `ListTaskPushNotificationConfig`
- `DeleteTaskPushNotificationConfig`
- `GetAgentCard`

## 5. 安全、扩展与签名（代码口径）

### 5.1 扩展协商头

SDK 使用的扩展头是：

- `X-A2A-Extensions`

不是 `A2A-Extensions`。

### 5.2 安全模型

`SecurityScheme` 联合类型包含：

- API Key
- HTTP Auth
- OAuth2
- OpenID Connect
- mTLS

### 5.3 签名能力

`a2a/utils/signing.py` 提供：

- AgentCard 签名创建
- AgentCard 签名验证（可选依赖 `PyJWT`）

## 6. 与 MCP 的边界（按当前 SDK 实际）

- A2A：关注 Agent 与 Agent 的任务协作、流式状态更新、订阅/重连、push 配置。
- MCP：关注 Agent/LLM 与工具、资源、提示模板的互通。
- 在工程落地中，常见模式仍是：A2A 做跨 Agent，MCP 做 Agent 内工具接入。

## 7. 本文档的“准确性边界”

本文是对本机 `~/Downloads/a2a-python-main` 快照的实现级描述，不是所有 A2A 版本的通用文档。

如果你后续升级到新的 A2A 规范（例如 v1.x）或不同 SDK 分支，至少需要重新核验：

- `README.md` compatibility 声明
- `src/a2a/types.py` 的字段和方法枚举
- `server/apps/*` 与 `request_handlers/*` 的可用操作面
