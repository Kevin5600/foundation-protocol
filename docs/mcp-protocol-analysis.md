# MCP 协议与 Python SDK 代码架构校验（基于本机源码快照）

## 1. 校验范围与结论

本文件基于以下代码快照做逐项核验：

- 本地下载快照：`~/Downloads/mcp-python-sdk-main`
- 远端最新 `main` 校验快照（2026-03-01 拉取）：`/tmp/mcp-python-sdk-latest`
- 关键源码：
  - `src/mcp/types/_types.py`
  - `src/mcp/shared/version.py`
  - `src/mcp/shared/session.py`
  - `src/mcp/client/session.py`
  - `src/mcp/client/client.py`
  - `src/mcp/server/lowlevel/server.py`
  - `src/mcp/server/mcpserver/server.py`
  - `src/mcp/server/streamable_http.py`
  - `src/mcp/server/streamable_http_manager.py`

校验结论：

- 当前文档按代码实现已对齐。
- MCP 在该 SDK 中是双向 JSON-RPC 会话协议（Client->Server 和 Server->Client 请求都存在）。
- `tasks/*` 能力在此 SDK 内明确是实验性实现。

## 2. 协议版本与协商事实（代码实锤）

来自 `src/mcp/types/_types.py` 与 `src/mcp/shared/version.py`：

- `LATEST_PROTOCOL_VERSION = "2025-11-25"`
- `DEFAULT_NEGOTIATED_VERSION = "2025-03-26"`
- `SUPPORTED_PROTOCOL_VERSIONS = ["2024-11-05", "2025-03-26", "2025-06-18", "2025-11-25"]`

这意味着：

- 传输层（尤其 Streamable HTTP）在协议头缺失时会回退默认协商版本。
- 初始化 (`initialize`) 的版本协商由会话层与 server session 联合处理。

## 3. MCP 方法面（按类型定义）

来自 `src/mcp/types/_types.py` 中 `method: Literal[...]` 定义，可分为：

核心请求：

- `initialize`
- `ping`
- `resources/list`
- `resources/templates/list`
- `resources/read`
- `resources/subscribe`
- `resources/unsubscribe`
- `prompts/list`
- `prompts/get`
- `tools/list`
- `tools/call`
- `logging/setLevel`
- `completion/complete`

Server->Client 请求（MCP 双向特性）：

- `sampling/createMessage`
- `roots/list`
- `elicitation/create`

实验性任务请求：

- `tasks/get`
- `tasks/result`
- `tasks/cancel`
- `tasks/list`

通知类：

- `notifications/initialized`
- `notifications/progress`
- `notifications/resources/list_changed`
- `notifications/resources/updated`
- `notifications/prompts/list_changed`
- `notifications/tools/list_changed`
- `notifications/message`
- `notifications/roots/list_changed`
- `notifications/cancelled`
- `notifications/elicitation/complete`
- `notifications/tasks/status`

## 4. 数据模型与能力协商（按代码）

### 4.1 基础模型

- 所有协议对象统一继承 `MCPModel`（Pydantic v2，自动 snake_case <-> camelCase）。
- 典型内容类型：`TextContent`、`ImageContent`、`AudioContent`、`EmbeddedResource`、`ResourceLink`。
- Task 状态字面量：`working | input_required | completed | failed | cancelled`（实验性）。

### 4.2 能力模型

客户端能力（`ClientCapabilities`）可包含：

- `roots`
- `sampling`
- `elicitation`
- `experimental`
- `tasks`

服务端能力（`ServerCapabilities`）可包含：

- `prompts`
- `resources`
- `tools`
- `logging`
- `completions`
- `experimental`
- `tasks`

能力由初始化阶段交换，server 侧可基于 handler 注册自动推断大部分 capability（见 lowlevel `Server.get_capabilities`）。

## 5. SDK 分层架构

## 5.1 类型层（`src/mcp/types`）

- `src/mcp/types/_types.py`：核心协议模型（手写维护，不是 codegen 产物）。
- `src/mcp/types/jsonrpc.py`：JSON-RPC 消息壳模型。

## 5.2 会话层（`src/mcp/shared/session.py`）

核心类：`BaseSession`

职责：

- 请求 ID 分配与响应路由。
- `send_request` / `send_notification`。
- `_receive_loop` 分发请求、响应、通知。
- 通过 `RequestResponder` 管理单请求生命周期和取消。

关键点：

- 这是 MCP 双向 RPC 的核心：同一 session 同时能发请求、也能接请求。

## 5.3 Client 侧

- `ClientSession`（`src/mcp/client/session.py`）：
  - 负责 `initialize`、能力缓存、各类 API 调用。
  - 处理 Server->Client 请求（sampling / elicitation / roots/list）。
- `Client`（`src/mcp/client/client.py`）：高层包装。
  - 入参可为 `Server`/`MCPServer`（in-memory 直连）、`Transport` 或 URL（Streamable HTTP）。

## 5.4 Server 侧

低层：`src/mcp/server/lowlevel/server.py` 的 `Server`

- 构造时注册 `on_*` handler。
- 根据 handler 推导能力。
- 提供 stdio / SSE / Streamable HTTP 的运行与 ASGI 挂载入口。

高层：`src/mcp/server/mcpserver/server.py` 的 `MCPServer`

- 通过 `@tool()` / `@resource()` / `@prompt()` 装饰器暴露能力。
- 用 `ToolManager/ResourceManager/PromptManager` 管理注册对象。
- 通过 `func_metadata` 自动从函数签名生成输入 schema，并做参数校验与同步/异步执行桥接。

## 5.5 传输层

客户端已实现传输：

- stdio
- SSE
- Streamable HTTP
- websocket（独立模块）
- in-memory（测试/本地嵌入）

服务端主路径：

- stdio
- SSE
- Streamable HTTP

说明：

- server 侧存在 `server/websocket.py` 底层实现文件，但高层 `MCPServer.run()` 当前仅暴露 `stdio | sse | streamable-http`。

## 6. Streamable HTTP 代码结构要点

来自 `src/mcp/server/streamable_http.py` 与 `streamable_http_manager.py`：

- 关键头：
  - `mcp-session-id`
  - `mcp-protocol-version`
  - `last-event-id`
- `EventStore` 抽象提供流恢复能力（按事件 ID 回放）。
- `StreamableHTTPSessionManager` 负责：
  - stateful/stateless 模式
  - 会话生命周期和 idle timeout
  - 每会话 transport 实例管理

## 7. 认证与安全组件

- server 侧包含 OAuth 相关模块：`src/mcp/server/auth/*`。
- 传输安全中间件：`src/mcp/server/transport_security.py`。
- client 侧认证扩展位于 `src/mcp/client/auth/*`。

## 8. 任务（Tasks）能力的准确定位

该 SDK 已包含完整 `tasks/*` 类型、通知和 client/server 侧实验模块（`src/mcp/*/experimental`、`src/mcp/shared/experimental/tasks/*`）。

准确表述应为：

- 任务能力在该仓库中有系统实现，但仍被标注为实验性能力，不应当作稳定必选面向所有部署默认开启。

## 9. 与 A2A 的边界（精炼）

- MCP：标准化 Agent/LLM 与工具、资源、提示模板之间的交互。
- A2A：标准化 Agent 与 Agent 之间任务协作。
- 在工程上常见组合是：A2A 负责跨 Agent 协作，Agent 内部再用 MCP 接工具生态。

## 10. 本文档的使用约束

为避免版本漂移，使用本文件时应同时满足：

- 目标代码快照仍为 `~/Downloads/mcp-python-sdk-main` 同一代实现。
- 若升级到新协议版本或 SDK 大版本，需重新校验第 2、3、5 节（版本常量、方法面、分层结构）。
