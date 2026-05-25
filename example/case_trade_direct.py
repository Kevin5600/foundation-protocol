"""Trade & Trust Demo — Case 2: DIRECT 模式 + 付款链接

场景：carol 委托 alice 做 Logo 设计，价格 150，DIRECT 模式。
流程：创建 → 审批 → 执行 → 验收 → Payee 发起收款(付款链接) → Payer 付款 → Payee 确认

对应 docs/Trade&Trust-demo.md Case 2
"""

import asyncio

from fp import EntityKind, Host, Message, MessageKind
from fp.trade import (
    ArbiterCheckPoint,
    ContractActionPayload,
    ContractCreatePayload,
    ContractRatePayload,
    FundingMode,
    PayActionPayload,
    PayCollectPayload,
    PaymentMethod,
)


async def main():
    host = Host(name="Hub")

    arbiter = host.register_entity(name="Arbiter", kind=EntityKind.ARBITER)
    arbiter_cp = arbiter.get_checkpoint(ArbiterCheckPoint)

    alice = host.register_entity(name="Alice", kind=EntityKind.HUMAN)
    carol = host.register_entity(name="Carol", kind=EntityKind.HUMAN)

    print("=== ① Carol 创建合同 (DIRECT) ===")
    await carol.send_message(
        to=arbiter.entity_card,
        message=Message(
            kind=MessageKind.CONTRACT_CREATE,
            payload=ContractCreatePayload(
                party_a=carol.address,
                party_b=alice.address,
                title="Logo 设计",
                description="品牌 Logo，需要 3 个备选方案",
                amount=150,
                funding_mode=FundingMode.DIRECT,
            ).model_dump(),
        ),
    )
    await asyncio.sleep(0.1)

    contract_id = list(arbiter_cp.contracts.keys())[0]
    contract = arbiter_cp.contracts[contract_id]
    print(f"  Contract: {contract_id}, Status: {contract.status.value}")
    print()

    print("=== ② Alice 同意合同 ===")
    await alice.send_message(
        to=arbiter.entity_card,
        message=Message(
            kind=MessageKind.CONTRACT_APPROVE,
            payload=ContractActionPayload(contract_id=contract_id).model_dump(),
        ),
    )
    await asyncio.sleep(0.1)
    contract = arbiter_cp.contracts[contract_id]
    print(f"  Status: {contract.status.value}")
    print()

    print("=== ③ 执行阶段 ===")
    print("  Alice 完成设计，交付作品")
    print()

    print("=== ④ Alice 提交完成 ===")
    await alice.send_message(
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

    print("=== ⑤ Carol 验收通过 ===")
    await carol.send_message(
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

    print("=== ⑥ Carol 评分 ===")
    await carol.send_message(
        to=arbiter.entity_card,
        message=Message(
            kind=MessageKind.CONTRACT_RATE,
            payload=ContractRatePayload(
                contract_id=contract_id,
                rating=4,
                review="第二版方案很好",
            ).model_dump(),
        ),
    )
    await asyncio.sleep(0.1)
    contract = arbiter_cp.contracts[contract_id]
    print(f"  Rating: {contract.rating}/5 — {contract.review}")
    print()

    print("=== ⑦ Alice 发起收款（付款链接）===")
    payment_id = "pay_direct_001"
    await alice.send_message(
        to=arbiter.entity_card,
        message=Message(
            kind=MessageKind.PAY_COLLECT,
            payload=PayCollectPayload(
                payment_id=payment_id,
                contract_id=contract_id,
                payer=carol.address,
                payee=alice.address,
                amount=150,
                method=PaymentMethod.PAY_LINK,
                receipt_info="https://pay.example.com/alice/inv_002?amount=150",
            ).model_dump(),
        ),
    )
    await asyncio.sleep(0.1)
    payment = arbiter_cp.payments[payment_id]
    print(f"  Payment: {payment_id}, Status: {payment.status.value}")
    print(f"  Pay link: {payment.receipt_info}")
    print()

    print("=== ⑧ Carol 通过链接付款（协议外操作）===")
    print("  Carol 打开链接，完成支付...")
    print()

    print("=== ⑨ Alice 确认收款 ===")
    await alice.send_message(
        to=arbiter.entity_card,
        message=Message(
            kind=MessageKind.PAY_CONFIRM_RECEIPT,
            payload=PayActionPayload(payment_id=payment_id).model_dump(),
        ),
    )
    await asyncio.sleep(0.1)
    payment = arbiter_cp.payments[payment_id]
    contract = arbiter_cp.contracts[contract_id]
    print(f"  Payment: {payment.status.value}")
    print(f"  Contract: {contract.status.value}")
    print()

    print("=== 最终状态 ===")
    print(f"  Contract: {contract.title} — {contract.status.value}")
    print(f"  Funding: {contract.funding_mode.value}")
    print(f"  Rating: {contract.rating}/5 — {contract.review}")
    print(f"  Payment: {payment.method.value} — {payment.status.value}")


if __name__ == "__main__":
    asyncio.run(main())
