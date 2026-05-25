"""Trade & Trust Demo — Case 1: ESCROW 模式完整流程

场景：alice 委托 bob 写市场调研报告，价格 200，ESCROW 模式。
流程：创建 → 审批 → 执行 → 验收 → ESCROW 自动结算

对应 docs/Trade&Trust-demo.md Case 1
"""

import asyncio

from fp import EntityKind, Host, Message, MessageKind
from fp.trade import (
    ArbiterCheckPoint,
    ContractActionPayload,
    ContractCreatePayload,
    ContractRatePayload,
    FundingMode,
)


async def main():
    host = Host(name="Hub")

    arbiter = host.register_entity(name="Arbiter", kind=EntityKind.ARBITER)
    arbiter_cp = arbiter.get_checkpoint(ArbiterCheckPoint)

    # 注册普通 Entity
    alice = host.register_entity(name="Alice", kind=EntityKind.HUMAN)
    bob = host.register_entity(name="Bob", kind=EntityKind.HUMAN)

    # 给 alice 和 bob 充值
    arbiter_cp.ledger.deposit(alice.uid, 1000)
    arbiter_cp.ledger.deposit(bob.uid, 200)

    print("=== 初始余额 ===")
    print(f"  Alice: {arbiter_cp.ledger.balance(alice.uid)}")
    print(f"  Bob:   {arbiter_cp.ledger.balance(bob.uid)}")
    print()

    # ① alice 创建合同
    print("=== ① Alice 创建合同 ===")
    await alice.send_message(
        to=arbiter.entity_card,
        message=Message(
            kind=MessageKind.CONTRACT_CREATE,
            payload=ContractCreatePayload(
                party_a=alice.address,
                party_b=bob.address,
                title="市场调研报告",
                description="Q2 东南亚市场调研，包含竞品分析和用户画像",
                amount=200,
                funding_mode=FundingMode.ESCROW,
            ).model_dump(),
        ),
    )
    await asyncio.sleep(0.1)

    contract_id = list(arbiter_cp.contracts.keys())[0]
    contract = arbiter_cp.contracts[contract_id]
    print(f"  Contract ID: {contract_id}")
    print(f"  Status: {contract.status.value}")
    print()

    # ② bob 同意合同
    print("=== ② Bob 同意合同 ===")
    await bob.send_message(
        to=arbiter.entity_card,
        message=Message(
            kind=MessageKind.CONTRACT_APPROVE,
            payload=ContractActionPayload(contract_id=contract_id).model_dump(),
        ),
    )
    await asyncio.sleep(0.1)

    contract = arbiter_cp.contracts[contract_id]
    print(f"  Status: {contract.status.value}")
    print(f"  Alice frozen: {arbiter_cp.ledger._frozen.get(alice.uid, 0)}")
    print(f"  Alice available: {arbiter_cp.ledger.available(alice.uid)}")
    print()

    # ③ 执行阶段 — alice 和 bob 直接通信（模拟）
    print("=== ③ 执行阶段（甲乙直接通信）===")
    print("  Alice → Bob: 报告需要覆盖越南、泰国、印尼三个市场")
    print("  Bob → Alice: 已完成，请查收")
    print()

    # ④ bob 提交完成
    print("=== ④ Bob 提交完成 ===")
    await bob.send_message(
        to=arbiter.entity_card,
        message=Message(
            kind=MessageKind.CONTRACT_COMPLETE,
            payload=ContractActionPayload(contract_id=contract_id).model_dump(),
        ),
    )
    await asyncio.sleep(0.1)

    contract = arbiter_cp.contracts[contract_id]
    print(f"  Status: {contract.status.value}")
    print()

    # ⑤ alice 验收通过
    print("=== ⑤ Alice 验收通过 ===")
    await alice.send_message(
        to=arbiter.entity_card,
        message=Message(
            kind=MessageKind.CONTRACT_ACCEPT,
            payload=ContractActionPayload(contract_id=contract_id).model_dump(),
        ),
    )
    await asyncio.sleep(0.1)

    contract = arbiter_cp.contracts[contract_id]
    print(f"  Status: {contract.status.value}")
    print()

    # ⑥ alice 评分
    print("=== ⑥ Alice 评分 ===")
    await alice.send_message(
        to=arbiter.entity_card,
        message=Message(
            kind=MessageKind.CONTRACT_RATE,
            payload=ContractRatePayload(
                contract_id=contract_id,
                rating=5,
                review="调研很详细",
            ).model_dump(),
        ),
    )
    await asyncio.sleep(0.1)

    contract = arbiter_cp.contracts[contract_id]
    print(f"  Rating: {contract.rating}/5 — {contract.review}")
    print()

    # 最终状态
    print("=== 最终状态 ===")
    print(f"  Contract: {contract.status.value}")
    print(f"  Alice 余额: {arbiter_cp.ledger.balance(alice.uid)}")
    print(f"  Bob 余额:   {arbiter_cp.ledger.balance(bob.uid)}")


if __name__ == "__main__":
    asyncio.run(main())
