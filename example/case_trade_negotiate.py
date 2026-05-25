"""Trade & Trust Demo — Case 3: DRAFT 阶段多轮协商修改

场景：alice 给 carol 创建合同，carol 觉得价格低，双方在 DRAFT 阶段反复修改直到达成一致。

对应 docs/Trade&Trust-demo.md Case 3
"""

import asyncio

from fp import EntityKind, Host, Message, MessageKind
from fp.trade import (
    ArbiterCheckPoint,
    ContractActionPayload,
    ContractAmendPayload,
    ContractCreatePayload,
    FundingMode,
)


async def main():
    host = Host(name="Hub")

    arbiter = host.register_entity(name="Arbiter", kind=EntityKind.ARBITER)
    arbiter_cp = arbiter.get_checkpoint(ArbiterCheckPoint)

    alice = host.register_entity(name="Alice", kind=EntityKind.HUMAN)
    carol = host.register_entity(name="Carol", kind=EntityKind.HUMAN)

    arbiter_cp.ledger.deposit(alice.uid, 1000)

    # ① 创建
    print("=== ① Alice 创建合同 ===")
    await alice.send_message(
        to=arbiter.entity_card,
        message=Message(
            kind=MessageKind.CONTRACT_CREATE,
            payload=ContractCreatePayload(
                party_a=alice.address,
                party_b=carol.address,
                title="数据标注服务",
                description="10000 条文本情感标注",
                amount=50,
                funding_mode=FundingMode.ESCROW,
            ).model_dump(),
        ),
    )
    await asyncio.sleep(0.1)

    contract_id = list(arbiter_cp.contracts.keys())[0]
    c = arbiter_cp.contracts[contract_id]
    print(f"  v{c.draft_version}: amount={c.amount}")
    print()

    # ② Carol 觉得太低，改价
    print("=== ② Carol 修改金额 50 → 120 ===")
    await carol.send_message(
        to=arbiter.entity_card,
        message=Message(
            kind=MessageKind.CONTRACT_AMEND,
            payload=ContractAmendPayload(
                contract_id=contract_id,
                amount=120,
            ).model_dump(),
        ),
    )
    await asyncio.sleep(0.1)
    c = arbiter_cp.contracts[contract_id]
    print(f"  v{c.draft_version}: amount={c.amount}")
    print()

    # ③ Alice 觉得 120 太高，再改
    print("=== ③ Alice 修改金额 120 → 80 ===")
    await alice.send_message(
        to=arbiter.entity_card,
        message=Message(
            kind=MessageKind.CONTRACT_AMEND,
            payload=ContractAmendPayload(
                contract_id=contract_id,
                amount=80,
            ).model_dump(),
        ),
    )
    await asyncio.sleep(0.1)
    c = arbiter_cp.contracts[contract_id]
    print(f"  v{c.draft_version}: amount={c.amount}")
    print()

    # ④ Carol 同意
    print("=== ④ Carol 同意 (v3, amount=80) ===")
    await carol.send_message(
        to=arbiter.entity_card,
        message=Message(
            kind=MessageKind.CONTRACT_APPROVE,
            payload=ContractActionPayload(contract_id=contract_id).model_dump(),
        ),
    )
    await asyncio.sleep(0.1)
    c = arbiter_cp.contracts[contract_id]
    print(f"  Status: {c.status.value}, amount={c.amount}")
    print()

    print("=== 协商完成 ===")
    print(f"  最终金额: {c.amount}")
    print(f"  版本历史: v1(50) → v2(120) → v3(80)")
    print(f"  当前状态: {c.status.value}")


if __name__ == "__main__":
    asyncio.run(main())
