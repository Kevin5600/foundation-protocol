"""Trade & Trust Demo — Case 4: 返工流程

场景：alice 委托 bob 写代码，第一次提交不合格，要求返工后通过。

对应 docs/Trade&Trust-demo.md Case 4
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

    alice = host.register_entity(name="Alice", kind=EntityKind.HUMAN)
    bob = host.register_entity(name="Bob", kind=EntityKind.HUMAN)

    arbiter_cp.ledger.deposit(alice.uid, 1000)

    # 创建 + 审批 → ACTIVE
    await alice.send_message(
        to=arbiter.entity_card,
        message=Message(
            kind=MessageKind.CONTRACT_CREATE,
            payload=ContractCreatePayload(
                party_a=alice.address,
                party_b=bob.address,
                title="API 开发",
                description="RESTful API, 包含 CRUD 和认证",
                amount=300,
                funding_mode=FundingMode.ESCROW,
            ).model_dump(),
        ),
    )
    await asyncio.sleep(0.1)
    contract_id = list(arbiter_cp.contracts.keys())[0]

    await bob.send_message(
        to=arbiter.entity_card,
        message=Message(
            kind=MessageKind.CONTRACT_APPROVE,
            payload=ContractActionPayload(contract_id=contract_id).model_dump(),
        ),
    )
    await asyncio.sleep(0.1)
    c = arbiter_cp.contracts[contract_id]
    print(f"=== 合同已激活: {c.title}, amount={c.amount} ===")
    print()

    # ① Bob 第一次提交
    print("=== ① Bob 提交完成（第一次）===")
    await bob.send_message(
        to=arbiter.entity_card,
        message=Message(
            kind=MessageKind.CONTRACT_COMPLETE,
            payload=ContractActionPayload(contract_id=contract_id).model_dump(),
        ),
    )
    await asyncio.sleep(0.1)
    c = arbiter_cp.contracts[contract_id]
    print(f"  Status: {c.status.value}")
    print()

    # ② Alice 要求返工
    print("=== ② Alice 要求返工 ===")
    await alice.send_message(
        to=arbiter.entity_card,
        message=Message(
            kind=MessageKind.CONTRACT_REWORK,
            payload=ContractActionPayload(
                contract_id=contract_id,
                reason="缺少错误处理，接口没有返回标准响应格式",
            ).model_dump(),
        ),
    )
    await asyncio.sleep(0.1)
    c = arbiter_cp.contracts[contract_id]
    print(f"  Status: {c.status.value}")
    print(f"  Rework: {c.rework_count}/{c.max_rework_count}")
    print()

    # ③ Bob 第二次提交
    print("=== ③ Bob 提交完成（第二次）===")
    await bob.send_message(
        to=arbiter.entity_card,
        message=Message(
            kind=MessageKind.CONTRACT_COMPLETE,
            payload=ContractActionPayload(contract_id=contract_id).model_dump(),
        ),
    )
    await asyncio.sleep(0.1)
    c = arbiter_cp.contracts[contract_id]
    print(f"  Status: {c.status.value}")
    print()

    # ④ Alice 验收通过
    print("=== ④ Alice 验收通过 ===")
    await alice.send_message(
        to=arbiter.entity_card,
        message=Message(
            kind=MessageKind.CONTRACT_ACCEPT,
            payload=ContractActionPayload(contract_id=contract_id).model_dump(),
        ),
    )
    await asyncio.sleep(0.1)

    # ⑤ Alice 评分
    await alice.send_message(
        to=arbiter.entity_card,
        message=Message(
            kind=MessageKind.CONTRACT_RATE,
            payload=ContractRatePayload(
                contract_id=contract_id,
                rating=3,
                review="最终结果可以，但第一次提交质量不够",
            ).model_dump(),
        ),
    )
    await asyncio.sleep(0.1)

    c = arbiter_cp.contracts[contract_id]
    print(f"  Status: {c.status.value}")
    print(f"  Rating: {c.rating}/5 — {c.review}")
    print(f"  Rework count: {c.rework_count}")
    print(f"  Alice: {arbiter_cp.ledger.balance(alice.uid)}")
    print(f"  Bob:   {arbiter_cp.ledger.balance(bob.uid)}")


if __name__ == "__main__":
    asyncio.run(main())
