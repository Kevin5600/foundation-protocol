# Trade & Trust Demo

> 本文档通过具体场景演示 Contract + Pay 的完整流程。
> 所有 CLI 命令基于 Trade&Trust.md 和 Pay.md 的设计。


## 前置环境

```
Host: my-hub (host_uid: hub01)

Entity 列表：
  - alice (human, hub01:alice)  — 需求方，有 Owner 就是她自己
  - bob   (agent, hub01:bob)    — 服务方，Owner 是 alice
  - carol (human, hub01:carol)  — 另一个用户，独立 Owner
  - arb   (arbiter, hub01:arb)  — 仲裁者

alice 和 bob 已经是好友。
alice 和 carol 已经是好友。
所有人都和 arb 是好友。
```

初始余额（ESCROW 虚拟账本）：

```
aln reputation balance --entity alice --arbiter arb
# alice: 1000.0

aln reputation balance --entity bob --arbiter arb
# bob: 200.0

aln reputation balance --entity carol --arbiter arb
# carol: 500.0
```

---


## Case 1: 顺利完成（ESCROW 模式）

> alice 委托 bob 写一份市场调研报告，价格 200，ESCROW 模式。

### 1.1 创建合同

alice 创建合同，指定自己为甲方（付款方），bob 为乙方（服务方）。

```bash
# alice 操作
aln contract create \
  --party-a alice \
  --party-b bob \
  --arbiter arb \
  --title "市场调研报告" \
  --description "Q2 东南亚市场调研，包含竞品分析和用户画像" \
  --amount 200 \
  --funding-mode escrow

# 输出:
# Contract created: ct_001
# Status: DRAFT
# Waiting for bob to approve.
```

Arbiter 收到 `CONTRACT_CREATE`，创建合同，通知 bob。

### 1.2 bob 的 Owner (alice) 收到通知

bob 是 agent，他的 Owner 是 alice。
Arbiter 发送 `CONTRACT_STATUS(DRAFT)` 给 bob，
bob 的 `CarbonCopyCheckpoint` 自动将通知转发给 alice。

alice 在 mailbox 中看到：

```bash
aln mailbox list --entity alice
# [CC] bob received contract ct_001: "市场调研报告", amount=200, from alice
```

### 1.3 bob 同意合同

bob 设置了 `ContractApprovalCheckPoint(auto_approve=True)`，自动同意。
也可以由 alice 作为 bob 的 Owner 手动操作：

```bash
# alice 代 bob 操作（Owner 权限）
aln contract approve --entity bob --contract ct_001

# 输出:
# Contract ct_001 approved by bob.
# Status: DRAFT → PENDING
```

### 1.4 PENDING → ACTIVE

Arbiter 收到 `CONTRACT_APPROVE`，校验甲方余额：

```
Arbiter 内部校验: alice 余额 1000.0 >= 200 ✓
```

校验通过，合同生效：

```
# 双方收到通知:
# [arb] Contract ct_001 status: ACTIVE
# "市场调研报告" is now active. bob can start working.
```

### 1.5 执行阶段

合同生效后，Arbiter 退出，甲乙直接通信。

```bash
# alice 给 bob 发消息
aln mail --from alice --to bob --text "报告需要覆盖越南、泰国、印尼三个市场"

# bob (agent) 自动执行任务，产出报告...
# bob 的 AgentHandler 处理 INVOKE，调用 provider 完成工作

# bob 给 alice 发消息
# (agent 自动回复)
# "已完成越南和泰国的竞品分析，印尼部分正在收集数据..."
```

### 1.6 提交完成

bob 完成工作后提交验收：

```bash
# bob 操作（或 alice 代 bob 操作）
aln contract complete --entity bob --contract ct_001

# 输出:
# Contract ct_001: bob submitted completion.
# Status: ACTIVE → COMPLETING
# Waiting for alice to accept.
```

### 1.7 甲方验收

alice 查看 bob 的成果，满意：

```bash
aln contract accept --entity alice --contract ct_001

# 输出:
# Contract ct_001 accepted by alice.
# Status: COMPLETING → SETTLING
```

### 1.8 评分

```bash
aln contract rate --entity alice --contract ct_001 --rating 5 --review "调研很详细"

# 输出:
# Contract ct_001: rated 5/5 by alice.
```

### 1.9 ESCROW 结算

Arbiter 在 SETTLING 阶段自动执行内部划转：

```
Arbiter 内部操作:
  alice 余额: 1000.0 - 200 = 800.0
  bob 余额:   200.0 + 200 = 400.0
  Payment pay_001: COMPLETED (ESCROW 自动完成)
```

```
# 双方收到通知:
# [arb] Contract ct_001 status: SETTLED
# Payment completed. alice: 800.0, bob: 400.0
```

### 1.10 最终状态

```bash
aln contract show --contract ct_001
# Contract ct_001
# Title: 市场调研报告
# Party A: alice (payer)
# Party B: bob (provider)
# Amount: 200.0
# Funding: ESCROW
# Status: SETTLED
# Rating: ★★★★★ (5/5) "调研很详细"

aln reputation balance --entity alice --arbiter arb
# alice: 800.0

aln reputation balance --entity bob --arbiter arb
# bob: 400.0
```

---


## Case 2: 顺利完成（DIRECT 模式 + 付款链接）

> carol 委托 alice 做 Logo 设计，价格 150，DIRECT 模式。
> carol 通过支付链接付款。

### 2.1 创建合同

```bash
# carol 操作
aln contract create \
  --party-a carol \
  --party-b alice \
  --arbiter arb \
  --title "Logo 设计" \
  --description "品牌 Logo，需要 3 个备选方案" \
  --amount 150 \
  --funding-mode direct

# 输出:
# Contract created: ct_002
# Status: DRAFT
```

### 2.2 alice 同意

```bash
aln contract approve --entity alice --contract ct_002

# 输出:
# Contract ct_002 approved by alice.
# Status: DRAFT → PENDING → ACTIVE
# (DIRECT 模式无需余额校验，Arbiter 确认后直接 ACTIVE)
```

### 2.3 执行 & 验收

```bash
# (alice 完成设计，通过 mail 交付作品)

aln contract complete --entity alice --contract ct_002
# Status: ACTIVE → COMPLETING

aln contract accept --entity carol --contract ct_002
# Status: COMPLETING → SETTLING

aln contract rate --entity carol --contract ct_002 --rating 4 --review "第二版方案很好"
```

### 2.4 SETTLING — 进入付款流程

DIRECT 模式下，Arbiter 进入 SETTLING 后触发 Pay 流程。
Arbiter 通知 alice（Payee）提供收款信息，通知 carol（Payer）准备付款。

**alice 发起收款**（提供付款链接）：

```bash
# alice 操作
aln pay collect \
  --entity alice \
  --contract ct_002 \
  --method pay_link \
  --receipt-info "https://pay.example.com/alice/inv_002?amount=150"

# 输出:
# Payment pay_002 created.
# Status: REQUESTED
# Pay link sent to carol.
```

Arbiter 创建 Payment，发送 `PAY_REQUEST` 给 carol（携带付款链接）。

### 2.5 carol 侧审批

carol 收到付款请求，她的 `PaymentApprovalCheckPoint` 评估：

```
规则: amount <= 200 → 自动通过 ✓
Payment pay_002: REQUESTED → APPROVED → EXECUTING
```

carol 在 mailbox 中看到：

```bash
aln mailbox list --entity carol
# [arb] Payment request: 150.0 to alice for "Logo 设计"
#       Pay link: https://pay.example.com/alice/inv_002?amount=150
#       Auto-approved. Please complete payment.
```

### 2.6 carol 执行支付

carol（或她的 Owner，就是她自己）打开链接完成支付。
**这一步发生在协议之外** — carol 在浏览器里完成付款。

```
Payment pay_002: EXECUTING → CONFIRMING (等待收款确认)
```

### 2.7 alice 确认收款

alice 的支付平台通知她收到 150 元，她向 Arbiter 报告：

```bash
aln pay confirm --entity alice --payment pay_002

# 输出:
# Payment pay_002: alice confirmed receipt.
# Status: CONFIRMING → COMPLETED
```

### 2.8 合同完成

Arbiter 收到 `PAY_CONFIRM_RECEIPT`，Payment COMPLETED，触发合同结算：

```
# 双方收到通知:
# [arb] Contract ct_002 status: SETTLED
# Payment completed via pay_link.
```

```bash
aln contract show --contract ct_002
# Contract ct_002
# Title: Logo 设计
# Party A: carol (payer)
# Party B: alice (provider)
# Amount: 150.0
# Funding: DIRECT (pay_link)
# Status: SETTLED
# Rating: ★★★★☆ (4/5) "第二版方案很好"
```

---


## Case 3: DRAFT 阶段协商修改

> alice 给 carol 创建合同，carol 觉得价格不合理，双方在 DRAFT 阶段协商。

### 3.1 创建

```bash
# alice 操作
aln contract create \
  --party-a alice \
  --party-b carol \
  --arbiter arb \
  --title "数据标注服务" \
  --description "10000 条文本情感标注" \
  --amount 50 \
  --funding-mode escrow

# Contract created: ct_003, Status: DRAFT (v1)
```

### 3.2 carol 觉得价格太低，修改条款

```bash
aln contract show --contract ct_003
# Contract ct_003 (DRAFT v1)
# Title: 数据标注服务
# Amount: 50.0
# ...

# carol 修改金额
aln contract amend --entity carol --contract ct_003 --amount 120

# 输出:
# Contract ct_003 amended by carol.
# Status: DRAFT (v2)
# Changed: amount 50.0 → 120.0
# Waiting for alice to review.
```

### 3.3 alice 觉得 120 太高，再改

```bash
aln contract amend --entity alice --contract ct_003 --amount 80

# 输出:
# Contract ct_003 amended by alice.
# Status: DRAFT (v3)
# Changed: amount 120.0 → 80.0
# Waiting for carol to review.
```

### 3.4 carol 同意

```bash
aln contract approve --entity carol --contract ct_003

# 输出:
# Contract ct_003 approved by carol.
# Status: DRAFT (v3) → PENDING
# Final amount: 80.0
```

后续流程同 Case 1（ESCROW）。

---


## Case 4: 返工流程

> alice 委托 bob 写代码，第一次提交不合格。

### 4.1 合同已在执行中

```bash
# (假设 ct_004 已经 ACTIVE)
aln contract show --contract ct_004
# Contract ct_004: "API 开发", amount=300, ESCROW, Status: ACTIVE
```

### 4.2 bob 提交完成

```bash
aln contract complete --entity bob --contract ct_004
# Status: ACTIVE → COMPLETING
```

### 4.3 alice 验收不通过，要求返工

```bash
aln contract rework --entity alice --contract ct_004 \
  --reason "缺少错误处理，接口没有返回标准响应格式"

# 输出:
# Contract ct_004: rework requested by alice. (1/3)
# Status: COMPLETING → ACTIVE
# Reason: 缺少错误处理，接口没有返回标准响应格式
```

bob 收到返工通知，继续修改。

### 4.4 bob 再次提交

```bash
aln contract complete --entity bob --contract ct_004
# Status: ACTIVE → COMPLETING
```

### 4.5 alice 验收通过

```bash
aln contract accept --entity alice --contract ct_004
# Status: COMPLETING → SETTLING

aln contract rate --entity alice --contract ct_004 --rating 3 \
  --review "最终结果可以，但第一次提交质量不够"
```

后续 ESCROW 自动结算。

---


## Case 5: Owner 审批付款（DIRECT + 二维码）

> carol 委托 bob 做翻译，DIRECT 模式。bob 的 Owner 是 alice，alice 需要审批付款。

### 5.1 合同已到 SETTLING

```bash
# ct_005: carol(甲) → bob(乙), amount=100, DIRECT, Status: SETTLING
```

### 5.2 bob 发起收款（发送二维码）

alice 作为 bob 的 Owner 操作：

```bash
aln pay collect \
  --entity bob \
  --contract ct_005 \
  --method qr_code \
  --receipt-info "data:image/png;base64,iVBOR...（二维码图片数据）"

# 输出:
# Payment pay_005 created.
# QR code sent to carol.
```

### 5.3 carol 侧审批

carol 收到付款请求。她的审批策略：amount > 50 需要 Owner 审批。
carol 的 Owner 就是她自己，所以她自己审批：

```bash
aln mailbox list --entity carol
# [arb] Payment request: 100.0 to bob for "翻译服务"
#       Method: QR code
#       ⚠ Requires your approval (amount > 50)

aln pay approve --entity carol --payment pay_005
# Payment pay_005: approved by carol.
# Status: APPROVING → APPROVED → EXECUTING
# Please scan the QR code to complete payment.
```

### 5.4 carol 扫码付款

carol 在手机上扫描二维码完成支付。**协议之外的操作。**

```
Payment pay_005: EXECUTING → CONFIRMING
```

### 5.5 bob 确认收款

alice 作为 bob 的 Owner，看到支付平台通知已到账：

```bash
aln pay confirm --entity bob --payment pay_005

# 输出:
# Payment pay_005: bob confirmed receipt.
# Status: CONFIRMING → COMPLETED
```

```
# 双方收到通知:
# [arb] Contract ct_005 status: SETTLED
```

---


## Case 6: 付款超时 → 争议

> carol 和 alice 的合同进入 SETTLING，carol 一直不付款。

### 6.1 SETTLING 阶段

```bash
# ct_006: carol(甲) → alice(乙), amount=200, DIRECT, Status: SETTLING
# alice 发起收款
aln pay collect --entity alice --contract ct_006 \
  --method pay_link \
  --receipt-info "https://pay.example.com/alice/inv_006?amount=200"

# carol 收到付款请求，自动审批通过
# Payment pay_006: EXECUTING
```

### 6.2 carol 超时未付款

carol 在 EXECUTING 状态下一直没有完成支付。Arbiter 超时检测触发：

```
Arbiter 超时检测:
  Payment pay_006 EXECUTING 超过 72h
  → PAY_TIMEOUT 通知 carol
  → Payment DISPUTED
  → Contract ct_006: SETTLING → DISPUTED
```

```bash
aln contract show --contract ct_006
# Contract ct_006
# Status: DISPUTED
# Reason: Payment timeout - payer did not complete payment within deadline

aln mailbox list --entity alice
# [arb] Contract ct_006 entered DISPUTED: payment timeout by carol.
```

### 6.3 carol 的信誉受损

```bash
aln reputation show --entity carol --arbiter arb
# carol's reputation:
#   Total contracts: 5
#   Completed: 3
#   Cancelled: 1
#   Timeout events: 1  ← 新增
#   Credit score: 72.0 (↓ from 85.0)
```

---


## Case 7: Payer 申请完成（Payee 未主动确认）

> alice 给 carol 付完款了，但 carol 迟迟没确认收款。alice 主动申请完成。

### 7.1 支付已执行

```bash
# Payment pay_007: EXECUTING → CONFIRMING
# alice 已经通过链接完成付款
# carol 一直没有执行 aln pay confirm
```

### 7.2 alice 主动申请完成

```bash
aln pay claim-completed --entity alice --payment pay_007

# 输出:
# Payment pay_007: alice claims payment completed.
# Arbiter will verify and confirm.
```

Arbiter 收到 `PAY_CLAIM_COMPLETED`，通知 carol 限时确认：

```bash
aln mailbox list --entity carol
# [arb] alice claims payment pay_007 completed.
#       Please confirm receipt within 24h, or payment will be auto-confirmed.
```

### 7.3 结果

- carol 在 24h 内确认 → `COMPLETED`
- carol 在 24h 内否认 → `DISPUTED`（Arbiter 介入仲裁）
- carol 超时未响应 → `COMPLETED`（Arbiter 默认接受 Payer 的主张）

---


## 流程速查表

| 阶段 | 甲方操作 | 乙方操作 | Arbiter |
|------|---------|---------|---------|
| DRAFT | `contract create` | — | 创建合同，通知乙方 |
| DRAFT | `contract amend` | `contract amend` | 记录版本，通知对方 |
| DRAFT → PENDING | — | `contract approve` | 校验条件，推进状态 |
| PENDING → ACTIVE | — | — | 自动确认，通知双方 |
| ACTIVE | `mail`（沟通需求） | `mail`（交付成果） | 不介入 |
| ACTIVE → COMPLETING | — | `contract complete` | 通知甲方验收 |
| COMPLETING | `contract accept` | — | 推进到 SETTLING |
| COMPLETING | `contract rework` | — | 退回 ACTIVE |
| SETTLING | `contract rate` | `pay collect` | 触发 Pay 流程 |
| SETTLING (ESCROW) | — | — | 自动划转 → SETTLED |
| SETTLING (DIRECT) | `pay approve` | `pay confirm` | 协调确认 → SETTLED |
