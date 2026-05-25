# Trade & Trust 外包软件持续交付场景

> 状态：场景设计草案
>
> 目标：把 Trade & Trust 的协议层能力映射到一个真实可演示的外包软件交付过程。


## 1. 场景概述

这是一个典型的外包软件交付场景：

- `Alex`：甲方 / 需求方 / 验收方
- `Bob`：乙方 / 开发方 / 交付方
- `Arbiter`：协议审查者，不写业务代码，只负责校验、签名、形成可信状态链

项目不是一次性交付，而是一个会持续多个版本的交付过程。
这类场景最适合用 Contract trust，因为每一轮都要明确：

- 这次交付是基于哪个已签名版本继续的
- 返工意见针对的是哪一个具体版本
- 最终验收和评分到底落在哪条责任链上


## 2. 为什么这个场景适合 Trust Protocol

普通聊天只能表达“大家说了什么”，但很难独立验证：

- Bob 到底交付了哪一版
- Alex 的返工针对哪一版
- Bob 的新版本是否真的响应了那次返工
- 最终评分是否对应完整交付链

Trade & Trust 在这里的价值是：

- 聊天仍然保留协作语义
- 合同快照负责锚定责任和状态
- Arbiter 负责把每次关键动作变成可验签的状态链


## 3. 三层模型

这个场景里有三层对象：

### 3.1 Conversation

表示自然语言协作过程，例如：

- Alex 说需求
- Bob 说开发计划
- Alex 提 bug 和返工意见
- Bob 说明修复内容

它回答的是：`为什么做这一步`

### 3.2 Contract

表示合作边界，例如：

- 项目标题
- 金额
- 参与方
- Funding mode
- 谁能 approve / deliver / rework / accept / rate

它回答的是：`这次合作的规则是什么`

### 3.3 Trust

表示状态可信链，例如：

- `source_snapshot_hash`
- `snapshot_hash`
- `terms_hash`
- `last_actor`
- `Arbiter attestation`

它回答的是：`这一步是否真的发生，并且是否基于当前合法状态`


## 4. 推荐的最小故事线

推荐把 demo 固定成一个外包软件项目：

- 项目：`Vendor Portal MVP`
- 目标：开发一个供应商门户最小版本
- 付款：`direct`
- 合作方式：先交 v1，再返工，再交 v2，最终验收和评分

### 4.1 S0_CREATE

Alex 创建合同。

内容示例：

- 标题：`Vendor Portal MVP Outsourcing Delivery`
- 描述：开发一个供应商门户 MVP，包含登录、项目列表、合同详情、版本化交付
- 金额：300

协议意义：

- Arbiter 冻结 `Alex / Bob / Arbiter` 三方身份
- 形成第一份 `terms_hash`
- 签出 `S0`

### 4.2 S1_APPROVE

Bob 接单。

协议意义：

- Bob 不是“口头说我接了”
- 而是对 `revision + terms_hash + source_snapshot_hash` 做明确 approve

### 4.3 S2_DELIVER_V1

Bob 交付 v1。

交付说明示例：

- 已完成登录页
- 已完成项目列表
- 已完成基础合同卡片

协议意义：

- 这次交付绑定到 `S1`
- 后续所有返工都针对这个具体版本

### 4.4 S3_REWORK

Alex 要求返工。

返工意见示例：

- 缺少 trust evidence
- 没有 snapshot chain
- 无法看到 approvals 和 Arbiter attestation

协议意义：

- 返工不是模糊反馈
- 而是对 `S2` 这一个快照的责任性反馈

### 4.5 S4_DELIVER_V2

Bob 交付 v2。

交付说明示例：

- 补充 snapshot timeline
- 补充 approvals 展示
- 补充 Arbiter review 面板

协议意义：

- Bob 明确从 `S3` 继续
- 不会和旧版 delivery 混淆

### 4.6 S5_ACCEPT

Alex 验收通过。

协议意义：

- Alex 接受的是 `S4`
- 不是接受某个模糊的“最新版”

### 4.7 S6_RATE

Alex 对 Bob 评分。

协议意义：

- 评分绑定完整交付链
- 后续 reputation 计算可以直接使用这条已签名链


## 5. UI 应该怎么讲清楚

如果要让协议小白也能理解，这个场景建议在 UI 中同时展示三条线：

### 5.1 左侧：Alex

展示：

- 创建任务
- 提出返工
- 验收
- 评分

### 5.2 中间：Arbiter

展示：

- 检查 actor 是否有权限
- 检查 `expected_status / revision / terms_hash / source_snapshot_hash`
- 对新快照签名

### 5.3 右侧：Bob

展示：

- 接单
- 提交 v1
- 提交 v2

### 5.4 中轴

必须明确显示：

- `source_snapshot_hash -> signed_snapshot_hash`

这样用户能一眼看出：

- 每一步是不是从当前状态继续的
- Arbiter 到底签了哪个快照


## 6. 为什么这是“持续交付”而不是“一次性交付”

一次性交付场景里，trust 价值不够明显，因为只有：

- create
- accept
- finish

而持续交付会自然出现：

- 多个 delivery
- 多轮 rework
- 多个版本之间的责任归属

这正是 `Contract trust` 和 `Session trust` 拉开差异的地方：

- 聊天可以断
- 但状态链不能断


## 7. 推荐的下一步

如果要把这个场景进一步产品化，推荐按下面顺序推进：

1. 在现有 `Replay` 中固定采用外包交付故事，不再用抽象 trust demo 文案。
2. 给每次 delivery 增加结构化 artifact：
   - `delivery_version`
   - `artifact_url`
   - `change_summary`
3. 把 conversation 和 contract snapshot 绑定起来：
   - 每个关键状态推进都可以引用对应消息
4. 后续再做 milestone：
   - 需求确认
   - 中期演示
   - 最终验收


## 8. 结论

外包软件持续交付是 Trade & Trust 最适合的演示场景之一。

因为它天然需要回答：

- 谁发起了这次变更
- 这次交付基于哪个版本
- 谁要求返工
- 谁最终验收
- Arbiter 到底签了什么

Trust Protocol 在这个场景里的价值，不是替代对话，而是把对话中最关键的协作节点，变成可以独立验证的合同状态链。
