# Trade & Trust 实现 TODO

> 当前阶段：fp 核心抽象 + example 验证
>
> 暂不实现 CLI、App、WebUI。先在 fp 层完成核心模型和状态机，
> 用 example/ 下的 Python 脚本跑通完整流程。


## Phase 1: fp 层核心模型

在 `fp/` 下新建 `trade/` 子包，存放所有 Trade & Trust 相关的协议层代码。

```
fp/trade/
  __init__.py          # 导出所有公开类型
  models.py            # Contract, Payment, Reputation 数据模型
  enums.py             # ContractStatus, PaymentStatus, FundingMode 等枚举
  payloads.py          # CONTRACT_*, PAY_* 消息的 Payload 定义
  state_machine.py     # ContractStateMachine, PaymentStateMachine
  checkpoints.py       # ContractApprovalCheckPoint, PaymentApprovalCheckPoint
  arbiter_handler.py   # ArbiterHandler — 处理 CONTRACT_*/PAY_* 消息
  ledger.py            # Ledger — Arbiter 虚拟账本（余额管理）
```

### 1.1 enums.py

| 内容 | 说明 |
|------|------|
| `ContractStatus` | DRAFT / PENDING / ACTIVE / COMPLETING / SETTLING / SETTLED / CANCELLED / DISPUTED |
| `PaymentStatus` | REQUESTED / APPROVING / APPROVED / REJECTED / EXECUTING / CONFIRMING / COMPLETED / DISPUTED |
| `FundingMode` | ESCROW / DIRECT |
| `PaymentMethod` | ESCROW / QR_CODE / PAY_LINK / BANK / CRYPTO / GATEWAY |
| `PayMode` | ENTITY_PAY / OWNER_PAY |

### 1.2 models.py

| 内容 | 说明 |
|------|------|
| `Contract` | 合同数据模型（参见 Trade&Trust.md §6.1） |
| `Payment` | 支付数据模型（参见 Pay.md §7.1） |
| `Reputation` | 信誉视图模型（从 Contract 链计算，非存储） |
| `ApprovalRule` | 免审批规则 |
| `PaymentApprovalPolicy` | Entity 支付审批策略 |

### 1.3 payloads.py

CONTRACT_* 系列：
- `ContractCreatePayload`
- `ContractAmendPayload`
- `ContractActionPayload`（approve/reject/complete/accept/cancel/dispute/rework）
- `ContractRatePayload`
- `ContractStatusPayload`

PAY_* 系列：
- `PayCollectPayload`
- `PayRequestPayload`
- `PayActionPayload`（approve/reject/confirm_receipt/claim_completed）
- `PayStatusPayload`

### 1.4 MessageKind 扩展

在 `fp/message.py` 的 `MessageKind` 枚举中新增：

```python
# Contract
CONTRACT_CREATE = "contract_create"
CONTRACT_AMEND = "contract_amend"
CONTRACT_APPROVE = "contract_approve"
CONTRACT_REJECT = "contract_reject"
CONTRACT_COMPLETE = "contract_complete"
CONTRACT_ACCEPT = "contract_accept"
CONTRACT_REWORK = "contract_rework"
CONTRACT_RATE = "contract_rate"
CONTRACT_CANCEL = "contract_cancel"
CONTRACT_DISPUTE = "contract_dispute"
CONTRACT_STATUS = "contract_status"
CONTRACT_TIMEOUT = "contract_timeout"

# Pay
PAY_COLLECT = "pay_collect"
PAY_REQUEST = "pay_request"
PAY_APPROVE = "pay_approve"
PAY_REJECT = "pay_reject"
PAY_CONFIRM_RECEIPT = "pay_confirm_receipt"
PAY_CLAIM_COMPLETED = "pay_claim_completed"
PAY_COMPLETED = "pay_completed"
PAY_FAILED = "pay_failed"
PAY_TIMEOUT = "pay_timeout"
```

### 1.5 EntityKind 扩展

在 `fp/core/base.py` 的 `EntityKind` 枚举中新增：

```python
ARBITER = "arbiter"
```


## Phase 2: 状态机 + 账本

### 2.1 state_machine.py

| 内容 | 说明 |
|------|------|
| `ContractStateMachine` | 校验 Contract 状态转换合法性，硬编码转换规则 |
| `PaymentStateMachine` | 校验 Payment 状态转换合法性 |

两个状态机都是纯函数式的：接收 (current_status, action) → new_status 或 raise。
不持有状态，不做 IO。

### 2.2 ledger.py

| 内容 | 说明 |
|------|------|
| `Ledger` | Arbiter 虚拟账本，管理 Entity 余额 |

方法：
- `balance(entity_uid)` → float
- `deposit(entity_uid, amount)` — 充值
- `transfer(from_uid, to_uid, amount)` — 划转（校验余额）
- `freeze(entity_uid, amount)` — 冻结（ESCROW 合同激活时）
- `unfreeze(entity_uid, amount)` — 解冻（取消时）

v0.1 用内存 dict 实现，后续可替换为持久化。


## Phase 3: Handler + CheckPoint

### 3.1 arbiter_handler.py

`ArbiterHandler(BaseHandler)` — Arbiter Entity 的消息处理器。

职责：
- 接收 CONTRACT_* 和 PAY_* 消息
- 通过 ContractStateMachine 校验状态转换
- 维护 Contract 存储（v0.1 内存 dict）
- 维护 Ledger
- 发送 CONTRACT_STATUS / PAY_* 通知给双方

### 3.2 checkpoints.py

| 内容 | 说明 |
|------|------|
| `ContractApprovalCheckPoint` | Entity 侧：收到合同通知时决定是否需要 Owner 介入 |
| `PaymentApprovalCheckPoint` | Entity 侧：收到付款请求时评估是否免审批 |


## Phase 4: fp/__init__.py 导出

更新 `fp/__init__.py`，导出 `fp/trade/` 下的所有公开类型。
更新 `fp/trade/__init__.py`，统一导出入口。


## Phase 5: example 验证

在 `example/` 下编写流程脚本，每个 case 对应 Trade&Trust-demo.md 中的场景：

| 文件 | 对应 | 场景 |
|------|------|------|
| `example/case_trade_escrow.py` | Demo Case 1 | ESCROW 模式完整流程：创建→审批→执行→验收→ESCROW 结算 |
| `example/case_trade_direct.py` | Demo Case 2 | DIRECT 模式：创建→执行→验收→收款方发起收款→付款→确认 |
| `example/case_trade_negotiate.py` | Demo Case 3 | DRAFT 阶段多轮协商修改 |
| `example/case_trade_rework.py` | Demo Case 4 | 返工流程 |
| `example/case_trade_approval.py` | Demo Case 5 | Owner 审批付款 |


## 执行顺序

```
Phase 1  →  Phase 2  →  Phase 3  →  Phase 4  →  Phase 5
 模型定义     状态机+账本   Handler      导出       example 验证
```

Phase 1-4 是代码实现，Phase 5 是验证。
每完成一个 Phase 就跑一次 example 确保不 break 现有功能。
