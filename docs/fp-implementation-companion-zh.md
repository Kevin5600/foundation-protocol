# FP 代码实现参考（与 `FP-Hitchhiker-guide.md` 互补）

> 版本基线：基于当前仓库 `main` 分支代码（2026-03-14）。
>
> 这份文档只回答三个问题：
> 1. 代码现在到底实现了什么。
> 2. 这些能力分别在什么文件里。
> 3. 协议边界在哪里（做了什么 / 没做什么）。
>
> 本文件已合并并替代以下旧分析文档（现已移除）：
> - `docs/fp-codebase-guide.md`
> - `docs/fp-protocol-analysis-zh.md`
> - `docs/fp-python-sdk-architecture.md`

---

## 1. 与根目录 Guide 的分工

`FP-Hitchhiker-guide.md` 主要讲 **why + what + 场景**。

本文件主要讲 **how + where（代码真相）**：

- 不重复讲故事和愿景。
- 直接映射到 `src/fp/*` 的真实实现。
- 避免把“设计目标”写成“已经实现”。

---

## 2. 当前实现快照（准确版）

### 2.1 应用入口

- 服务端：`src/fp/app/async_server.py` 的 `AsyncFPServer`
- 客户端：`src/fp/app/async_client.py` 的 `AsyncFPClient`
- 快速接入：`src/fp/quickstart/*`
- 命令行：`src/fp/cli.py`

`src/fp/app/__init__.py` 当前只导出：

- `AsyncFPServer`
- `AsyncFPClient`
- `make_default_entity`

### 2.2 JSON-RPC 方法面

当前 `AsyncJSONRPCDispatcher.from_server(AsyncFPServer())` 方法表数量为 **65**。

方法绑定文件：

- `src/fp/transport/http_jsonrpc.py`
- `src/fp/transport/async_jsonrpc.py`

核心方法族：

- `fp/initialize`, `fp/initialized`, `fp/ping`
- `fp/entities.*`, `fp/orgs.*`, `fp/operations.*`
- `fp/sessions.*`, `fp/activities.*`, `fp/envelopes.deliver`
- `fp/events.*`
- `fp/receipts.*`, `fp/settlements.*`, `fp/disputes.*`
- `fp/provenance.*`
- `fp/federation.*`

### 2.3 实体类型（固定枚举）

定义：`src/fp/protocol/models.py` 中 `EntityKind`

当前内置 8 类：

- `agent`
- `tool`
- `resource`
- `human`
- `organization`
- `institution`
- `service`
- `ui`

---

## 3. 代码架构总览（现状）

```text
src/fp/
  app/            # AsyncFPServer/AsyncFPClient + server ops mixins
  protocol/       # Models / Methods / Envelope / Addressing / Errors
  runtime/        # Async session/activity/event engines + dispatch + idempotency
  graph/          # Entity/Organization/Membership registries + relations
  economy/        # Metering / Receipt / Settlement / Dispute services
  federation/     # ServerCard / Directory / Mesh / Resolver / Replication
  network/        # Host / Router (一等抽象)
  transport/      # JSON-RPC + HTTP publish + SSE/WS/Streamable HTTP bridges
  stores/         # store interfaces + memory/sqlite + async adapters + redis stub
  security/       # auth/authz/jwt/hmac/ed25519/mtls/keyring/revocation
  extensions/     # oauth2 introspection / grpc bridge / provider contracts
  profiles/       # profile descriptors (core/governed/oauth2/grpc/streamable)
  quickstart/     # Agent/Tool/Resource/Service 简化接入
  adapters/       # 框架适配接口与基础类型
  observability/  # trace/metrics/token/cost/audit export
  registry/       # schema/event/pattern registries
```

---

## 4. AsyncFPServer 的真实组织方式

`AsyncFPServer` 是组合门面，不是单文件“巨型流程硬编码”。

### 4.1 组合结构

`src/fp/app/async_server.py` 继承 5 个 mixin：

- `GraphServerOpsMixin`（实体/组织/成员/operation）
- `SessionServerOpsMixin`（会话 + federation forward/ack/replay）
- `ActivityServerOpsMixin`（活动生命周期 + envelope 投递）
- `EventServerOpsMixin`（stream/read/resubscribe/ack + push config）
- `EconomyServerOpsMixin`（receipt/settlement/dispute/provenance/audit）

### 4.2 内部关键组件

- 执行引擎：`AsyncDispatchEngine`（`runtime/dispatch_engine.py`）
- 状态机：
  - `AsyncSessionEngine`（`runtime/async_session_engine.py`）
  - `AsyncActivityEngine`（`runtime/async_activity_engine.py`）
  - `AsyncEventEngine`（`runtime/async_event_engine.py`）
- 治理：`GovernanceModule`（`runtime/modules/governance_module.py`）
- 幂等：`IdempotencyGuard`（`runtime/idempotency.py`）
- 上下文压缩：`ContextCompactor`（`runtime/context_compaction.py`）
- 经济：`MeteringService/ReceiptService/SettlementService/DisputeService`

---

## 5. 协议核心对象与状态机

定义文件：`src/fp/protocol/models.py`

### 5.1 会话状态

`SessionState`：

- `created`
- `active`
- `paused`
- `closing`
- `closed`
- `failed`

### 5.2 活动状态

`ActivityState`：

- `submitted`
- `working`
- `input_required`
- `auth_required`
- `completed`
- `failed`
- `canceled`
- `rejected`

### 5.3 消息族

`MessageFamily`：

- `FP.MSG`
- `FP.SHARE`
- `FP.INVOKE`
- `FP.EVENT`
- `FP.RECEIPT`
- `FP.SETTLE`
- `FP.NEGOTIATE`
- `FP.DISPUTE`

---

## 6. Host / Address / Router / Envelope（已是一等抽象）

### 6.1 Address 与本地/远程判定

文件：`src/fp/protocol/addressing.py`

- `Address(host_id, entity_id)`
- `envelope_to_address(...)`
- `envelope_is_local(...)`
- `coerce_envelope(...)`

### 6.2 Host 与 Router

文件：

- `src/fp/network/host.py`
- `src/fp/network/router.py`

行为：

- `Host.deliver(envelope)`：
  - 本地目标：调用本地 `AsyncFPServer.envelopes_deliver`
  - 远程目标：交给 `Router.forward`
- `Router` 维护远端 host 到 client 的映射，调用远端 `envelopes_deliver`

### 6.3 Envelope 落地路径

`src/fp/app/server_ops_activity.py` 中 `envelopes_deliver`：

1. 校验 envelope 与 family
2. 抽取 `operation + input_payload`
3. 解析或创建 session
4. 调用 `activities_start`
5. 组装成功或错误 envelope 返回

---

## 7. Federation 与发现

### 7.1 对象与模块

- `FPServerCard`：`src/fp/federation/network.py`
- 目录：`DirectoryService`（`directory_service.py`）
- 多目录聚合：`DirectoryMesh`（`directory_mesh.py`）
- 解析连接：`NetworkResolver`（`network.py`）
- HTTP 发布：`FPHTTPPublishedServer`（`transport/http_publish.py`）

### 7.2 DirectoryMesh 冲突规则（当前实现）

`DirectoryMesh._rank` 当前顺序：

1. 目录顺序优先（构造 `DirectoryMesh([...])` 时前面的优先级更高）
2. 同优先级再看过期时间（更“新鲜”优先）
3. 再按 `card_id` 稳定排序

这意味着它不是“纯粹按最新过期时间挑卡”。

### 7.3 会话锚点与复制

- `SessionAuthorityRegistry`：`federation/authority.py`
- 复制检查点：`federation/replication.py`
- 对应 server 方法：`fp/sessions.anchor.*`, `fp/federation.events.*`

---

## 8. 事件流、重放与背压

### 8.1 事件主链

- 事件 API：`src/fp/app/server_ops_events.py`
- 引擎：`src/fp/runtime/async_event_engine.py`
- 背压：`src/fp/runtime/backpressure.py`

### 8.2 流式传输桥

- SSE：`src/fp/transport/sse_runtime.py`
- WebSocket：`src/fp/transport/websocket_runtime.py`
- Streamable HTTP：`src/fp/transport/streamable_http_runtime.py`

### 8.3 游标重放模型

核心接口是：

- `fp/events.stream`
- `fp/events.read`
- `fp/events.ack`
- `fp/events.resubscribe`

在不同传输上表现一致，底层语义统一到同一事件引擎。

---

## 9. 安全能力（当前已实现）

### 9.1 鉴权与身份

`src/fp/security/`：

- `StaticTokenAuthenticator`
- `JWTAuthenticator`（HS256，支持 keyring + revocation）
- `extract_bearer_token`

`src/fp/extensions/oauth2.py`：

- `OAuth2IntrospectionAuthenticator`
- 使用 RFC 7662 introspection
- HTTP 客户端实现为 stdlib `urllib`（不是 `httpx`）

### 9.2 签名与密钥

- HMAC：`security/signatures.py`
- Ed25519：`security/ed25519.py`（依赖 `cryptography` 时启用）
- JWT keyring：`security/keyring.py`
- 撤销：`security/revocation.py`

### 9.3 传输安全

`FPHTTPPublishedServer` 支持：

- TLS（`ssl_context`）
- mTLS（`MTLSConfig`）

文件：`src/fp/transport/http_publish.py`, `src/fp/security/mtls.py`

---

## 10. Economy 能力（当前已实现）

### 10.1 经济对象链

- Meter：`economy/meter.py`
- Receipt：`economy/receipt.py`
- Settlement：`economy/settlement.py`
- Dispute：`economy/dispute.py`

### 10.2 能力边界（务必准确）

FP 当前提供的是 **经济原语与状态语义**：

- 计量、签名收据、结算状态流转、争议对象
- `payment_proof_ref` / `settlement_ref` 等外部对接字段

FP **不内置** 实际资金清算网络。

---

## 11. 存储与一致性现状

### 11.1 已可用后端

- `InMemoryStoreBundle`
- `SQLiteStoreBundle`（WAL + 小连接池）

### 11.2 Redis 现状

`src/fp/stores/redis.py` 为显式 stub：

- 默认抛 `NotImplementedError`
- 需要 `enable_inmemory_stub=True` 才可显式退化到内存行为

所以它不是“可直接生产共享状态后端”。

### 11.3 Async store 形态

`src/fp/stores/async_adapters.py` 提供 async 接口适配层。

当前默认路径下，`AsyncFPServer` 使用 `AsyncStoreBundle.from_sync_bundle(..., use_executor=False)`：

- 语义是 async API 统一
- 底层仍可由 sync store 实现承载

---

## 12. Profiles 与 Extensions（当前语义）

### 12.1 Profiles

目录：`src/fp/profiles/`

- `core-minimal`
- `core-streaming`
- `governed`
- `oauth2-introspection`
- `grpc-bridge`
- `streamable-http`

### 12.2 initialize 的真实行为

`AsyncFPServer.initialize` 当前做的是：

- 版本交集协商（`supported_versions` 与 `SUPPORTED_VERSIONS`）
- 返回 `negotiated_version`
- 回传 `supported_profiles` 字段（作为元数据）

它不是“强制 profile 自动能力裁剪引擎”。

### 12.3 Extensions

目录：`src/fp/extensions/`

- OAuth2 introspection 扩展
- gRPC bridge 扩展（可选 `grpcio`）
- Provider contracts + registry

gRPC 在当前是扩展桥能力，不是 `FPHTTPPublishedServer` 内建发布路径。

---

## 13. CLI 能力（当前）

`fp --help` 当前顶层命令：

- `serve`
- `ping`
- `call`
- `entity`
- `operation`
- `session`
- `envelope`
- `economy`
- `card`
- `directory`
- `skill`

说明：CLI 覆盖的是核心运维与协议操作路径，不等于 1:1 覆盖所有 Python API 细节。

---

## 14. 与旧文档相比，哪些口径已经纠正

本合并文档已按新代码修正以下常见误差：

- 使用 `AsyncFPServer/AsyncFPClient` 作为唯一应用入口描述
- 不再把 `FPServer/FPClient`、`RuntimeBundle/GraphModule/...` 当成当前公开结构
- 不再把 Redis 写成“已内置可生产后端”
- 不再把 OAuth2 写成依赖 `httpx`
- 不再把 DirectoryMesh 写成“只按过期时间挑卡”
- 不再把 profile 写成“已内建强制协商裁剪”

---

## 15. 维护这份文档的最小校验命令

每次代码升级后，至少跑下面几条再更新文档：

```bash
# 1) 方法面数量与命名
PYTHONPATH=src python3 - <<'PY'
from fp.app import AsyncFPServer
from fp.transport.async_jsonrpc import AsyncJSONRPCDispatcher
print(len(AsyncJSONRPCDispatcher.from_server(AsyncFPServer())._method_table))
PY

# 2) CLI 顶层命令
PYTHONPATH=src python3 -m fp.cli --help

# 3) 6.1 类最小 quickstart 可运行性（至少一个样例）
PYTHONPATH=src python3 - <<'PY'
import asyncio
from fp.quickstart import Agent
from fp.app import make_default_entity
from fp.protocol import EntityKind

async def main():
    a = await Agent.create(entity_id='a')
    await a.server.register_entity(make_default_entity('b', EntityKind.AGENT, display_name='b'))
    @a.activity('greet')
    def greet(payload: dict) -> dict:
        return {'greeting': f"Hello, {payload['name']}!"}
    s = await a.start_session(participants={'a','b'}, roles={'a': {'worker'}, 'b': {'observer'}})
    r = await a.start_activity(session_id=s.session_id, operation='greet', input_payload={'name': 'World'})
    print(r.result_payload)

asyncio.run(main())
PY
```

---

## 16. 一句话总结

FP 当前代码已经形成：

- 统一实体语义
- 多方会话与活动状态机
- 可重放事件流
- 治理钩子与审计输出
- 经济原语链路
- 本地 + 联邦组网能力

同时保持清晰边界：把支付执行、外部 IAM、业务策略留给可替换外部系统。
