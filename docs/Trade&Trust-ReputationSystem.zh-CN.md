# Trade&Trust 信誉系统设计

## 0. 团队讨论清单

这一节的目标，是帮助团队在进入公式和实现细节前，先把 V1 的范围快速对齐。

建议在评审会上先拍板这 5 个问题：

1. V1 是否只计算 `party_b` 的 vendor reputation，还是同时给出一个轻量的 buyer profile？
2. 信誉是否从 `accept` 开始贡献，还是必须等到 `rate` 之后？
3. `execution_costs` 在 V1 中是直接影响评分，还是先只作为透明度证据？
4. `dispute` 是否要立刻作为强负向信号，还是等 dispute resolution 机制存在后再强化？
5. V1 的 reputation 是继续保持 app-layer derived view，还是未来要下沉成协议层对象？

建议的 V1 答案集合：

- 先只计算 `party_b`
- 统计已签名的 `accept`、`rate`、`settling`、`settled`、`cancelled`、`disputed`
- 将 `execution_costs` 先作为 evidence，评分影响保持较轻
- reputation 在 V1 保持为 app-layer derived view

## 1. 目的

本文提出一套构建在现有 Trade & Trust 协议之上的信誉系统设计。

核心区分是：

- `Trust` 回答：某个合同事实是否真实、可独立验证。
- `Rating` 回答：某一笔合同结果被对手方如何评价。
- `Reputation` 回答：一个实体在多个合同、多个周期中的总体表现如何。

这份设计刻意保持“协议优先、基建从简”。它默认现有的 signed contract snapshots、approvals、deliveries、execution costs 和 Arbiter attestations 是事实根。

## 2. 问题定义

当前实现其实已经记录了不少高价值的 trust evidence：

- signed snapshot history
- approvals
- delivery evidence
- execution costs
- accept / rework / cancel / dispute / rate 等结果
- Arbiter attestation

但系统仍然缺少一个派生层，去回答这些更偏业务和市场的问题：

- 哪个 vendor 更可靠？
- 哪个 vendor 通常需要更少的 rework？
- 哪些 counterparties 更公平、更稳定？
- market 或 portal 应该如何基于协议支撑的证据进行排序和筛选？

信誉系统需要解决这些问题，同时不能削弱协议保证，也不能引入不可解释的黑箱评分。

## 3. 设计原则

### 3.1 先有协议事实，再有信誉

reputation 必须只从 Arbiter 已签名的合同事实中派生，不能直接来自随意聊天文本或客户端 UI 自己维护的状态。

### 3.2 分角色计算

信誉必须按角色分别计算：

- `party_b`：交付方 / vendor reputation
- `party_a`：需求方 / buyer collaboration reputation
- `arbiter`：审查与签名服务信誉

这三种信誉不应该混成一个没有语义区分的总分。

### 3.3 先提取事实，再算分数

先把合同结果归一化为 reputation events 和 feature vectors，再从这些特征向量聚合出分数。

这样设计更可解释，也方便以后调整公式而不伤到协议本身。

### 3.4 协议层与信誉层解耦

- 协议层负责存 canonical facts
- 信誉层负责存 derived summaries 和 aggregates

协议层仍然是 trust root，reputation 只是建立在它之上的计算视图。

## 4. 已有输入

当前 Trade & Trust 实现里，已经有了信誉系统所需的大部分输入。

| 现有字段 | 可用于信誉的含义 |
|---|---|
| `rating`, `review` | 质量评价 |
| `rework_count` | 协作摩擦 / 交付稳定性 |
| `delivery_history` | 多版本交付能力 |
| `execution_costs` | 效率 / 透明度证据 |
| `snapshot_history` | 已签名生命周期完整性 |
| `accept`, `cancel`, `dispute` | 履约结果 |
| `approvals`, `attestation` | 协议完整性 |

当前真正的缺口是：

- 我们已经有 `reputation evidence`
- 但还没有 `reputation computation`

## 5. 信誉层总体结构

建议的 reputation pipeline 如下：

```text
Contract -> ReputationEvent -> ReputationFeatureVector -> ReputationProfile
```

### 5.1 ReputationEvent

这是从一个合同中提取出来的、归一化后的信誉事实记录。通常在合同达到某个有意义的生命周期节点后生成。

建议结构：

```ts
interface ReputationEvent {
  event_id: string
  contract_id: string
  subject: FPAddressRef
  role: "party_a" | "party_b" | "arbiter"

  counterparty?: FPAddressRef
  arbiter?: FPAddressRef

  outcome: "accepted" | "settled" | "cancelled" | "disputed"
  rating?: number
  review?: string

  delivery_count: number
  rework_count: number
  dispute_count: number
  cancel_count: number

  total_cost_usd?: number
  total_input_tokens?: number
  total_output_tokens?: number

  evidence_complete: boolean
  signed_snapshot_count: number

  created_at: number
  source_snapshot_hash: string
}
```

### 5.2 ReputationFeatureVector

这是用于评分的标准化特征向量。

```ts
interface ReputationFeatureVector {
  quality_score: number
  reliability_score: number
  collaboration_score: number
  efficiency_score: number
  integrity_score: number

  confidence_weight: number
  recency_weight: number
}
```

### 5.3 ReputationProfile

这是某个实体在某个角色上的聚合信誉画像。

```ts
interface ReputationProfile {
  subject: FPAddressRef
  role: "party_a" | "party_b" | "arbiter"

  overall_score: number
  confidence: number
  sample_size: number

  quality_score: number
  reliability_score: number
  collaboration_score: number
  efficiency_score: number
  integrity_score: number

  recent_events: ReputationEvent[]
  updated_at: number
}
```

## 6. 按角色拆分的信誉

### 6.1 Vendor Reputation（`party_b`）

这是当前 outsourcing 和 market 场景里最重要、也最值得先做的一类信誉。

| 维度 | 来源 | 含义 |
|---|---|---|
| Quality | `rating`, `review`, `accept` | 最终交付是否被接受、评价是否好 |
| Reliability | `cancel`, `dispute`, 最终生命周期状态 | 这个 vendor 是否能稳定完成合同 |
| Collaboration | `rework_count`, 多版本收敛情况 | 协作成本有多高 |
| Efficiency | `delivery_count`, `execution_costs` | 交付是否高效 |
| Integrity | `snapshot_history`, `attestation`, `artifacts` | 交付链是否完整且可验证 |

初始加权公式建议：

```text
vendor_contract_score =
  0.35 * quality
+ 0.25 * reliability
+ 0.20 * collaboration
+ 0.10 * efficiency
+ 0.10 * integrity
```

### 6.2 Buyer Reputation（`party_a`）

buyer 同样会显著影响协作体验，所以长期看也应该有独立 profile。

| 维度 | 来源 | 含义 |
|---|---|---|
| Fairness | rating/review 是否一致 | 评价是否和签名链路里的事实相匹配 |
| Stability | cancel/dispute 频率 | buyer 是否容易毁约或反复打断合作 |
| Collaboration | rework 行为、最终 accept | buyer 是否能帮助流程收敛 |
| Integrity | signed-chain compliance | buyer 是否遵守协议规则 |

### 6.3 Arbiter Reputation（`arbiter`）

Arbiter 的信誉不是交易信誉，而是审查与签名服务信誉。

| 维度 | 来源 |
|---|---|
| Signature integrity | attestation 完整性 |
| Protocol correctness | 校验逻辑、错误处理 |
| Availability | 签名状态推进是否稳定完成 |

## 7. 特征提取

建议从闭环或接近闭环的合同状态开始，而不是过早为噪声很大的 in-flight contracts 打分。

### 7.1 Vendor 特征提取

建议的初始规则：

```text
quality:
  如果有 rating -> rating / 5
  否则如果 accepted -> 0.7
  否则 -> 给一个较低的中性回退值

reliability:
  settled / settling / accepted -> 1.0
  disputed -> 0.2
  cancelled -> 0.3

collaboration:
  1 - min(rework_count / max_rework_count, 1)

efficiency:
  初期先做粗粒度；更少的 delivery loops、合理的 execution-cost footprints 得分更高

integrity:
  snapshot history 存在
  attestation 存在
  delivery evidence 存在
  artifacts 存在
```

### 7.2 Buyer 特征提取

建议的初始规则：

```text
fairness:
  当 buyer 能基于证据完成 accept / rate，且 review 有依据时得分较高

stability:
  如果 buyer 频繁 cancel 或 dispute，则得分降低

collaboration:
  如果 rework 次数有限并最终收敛到 accept，则得分较高
```

## 8. 防刷分与可信约束

如果 trust model 不够强，信誉系统非常容易被刷。以下约束是必要的。

### 8.1 只有已签名事实才计入

只有 Arbiter 已签名的合同事实才允许进入信誉计算。

未签名的本地状态、聊天草稿、UI-only data 都不能影响分数。

### 8.2 优先使用闭环事件

V1 建议只使用从以下状态中提取出的事件：

- `accept`
- `rate`
- `settling`
- `settled`
- `cancelled`
- `disputed`

### 8.3 Counterparty Weight Caps

同一对 counterparty 不能主导整个 reputation profile。

示例策略：

- 单一 counterparty 贡献权重最多不超过总权重的 30%

### 8.4 不只显示分数，还要显示置信度

我们不能把“一笔 5 星合同”展示成“等同于长期稳定高信誉”。

每个 profile 都应该至少包含：

- `overall_score`
- `confidence`
- `sample_size`

### 8.5 时间衰减

近期合同应当比远古合同更重要。

V1 可以先不做，但模型设计时要预留 recency weighting 的位置。

## 9. 计算模型

初版模型应该保持简单。

### Stage 1: Contract -> ReputationEvent

写一个确定性的 extractor，遍历已签名合同，提取一个或多个标准化事件。

### Stage 2: ReputationEvent -> ReputationProfile

再由 aggregator 按 `subject + role` 聚合成 profile。

这样做的好处是：

- 逻辑可解释
- 易于调试
- 在审计或 dispute 场景里容易说明“这个分数是怎么来的”

## 10. 建议的 V1 范围

V1 应该刻意收窄。

### In Scope

- 定义 `ReputationEvent`
- 定义 `ReputationProfile`
- 先只计算 `party_b`
- 只使用已签名的合同结果
- 在 Portal 中展示 vendor reputation

### Out of Scope

- buyer reputation
- arbiter service reputation
- market-wide ranking
- advanced time decay
- 复杂 anti-collusion weighting

## 11. 建议的 V2 范围

等 V1 稳定后，再扩展这些内容：

- `party_a` reputation
- `arbiter` service reputation
- 时间衰减
- counterparty weight caps
- market sorting / filtering
- reputation history charts

## 12. UI 集成建议

### 12.1 Portal

Portal 是 vendor reputation 最自然的第一落点。

建议的 UI 区块：

| UI block | 内容 |
|---|---|
| Vendor Score | 总分 + confidence |
| Breakdown | quality / reliability / collaboration / integrity |
| Recent Evidence | 最近贡献 reputation 的事件 |
| Review Notes | 最近 review / rating 摘要 |

### 12.2 Trade

Trade detail 可以显示：

- 该合同是否会贡献 reputation
- 它提取出了哪些 reputation features

### 12.3 Observer

Observer 可以选择性显示：

- 某个签名状态推进之后，哪一方的 reputation event 被更新了

## 13. 建议的数据归属

| 层 | 职责 |
|---|---|
| Protocol layer | 存 signed contract facts |
| Reputation extractor | 从 signed facts 构造 `ReputationEvent` |
| Reputation aggregator | 从 events 聚合 `ReputationProfile` |
| UI layer | 展示 score、evidence、confidence |

## 14. Open Questions

这些是最适合团队讨论的几个问题：

1. V1 是否只计算 `party_b` reputation，还是也要顺带展示一个轻量 buyer profile？
2. 一笔合同应当在 `accept` 后就贡献 reputation，还是必须等到 `rate` 后？
3. `execution_costs` 应该多大程度影响 reputation，还是在 V1 先主要承担透明度作用？
4. `dispute` 是否应立刻作为强负向信号，还是等 dispute resolution 机制补齐后再强化？
5. 长期看我们是否希望有协议层的 `ReputationEvent` 对象，还是继续保持 app-layer derived？

## 15. 推荐的下一步

下一步最合适的落地方式，是先做一个足够小的 V1：

1. 增加 `ReputationEvent` 和 `ReputationProfile` 类型
2. 先实现 `Contract -> ReputationEvent` 的 `party_b` 提取逻辑
3. 实现一个简单 aggregator
4. 在 Portal 增加一张基础 reputation card

这样团队可以先拿到一个真实可用的 V1，而不用一开始就承诺一个复杂的 market-wide reputation engine。
