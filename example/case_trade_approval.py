"""Trade & Trust Demo — Case 5: Owner 审批付款 (DIRECT + 二维码)

场景：carol 委托 bob 做翻译，DIRECT 模式。
bob 发起收款（二维码），carol 扫码付款后，bob 确认收款。
演示完整的 DIRECT 付款流程。

对应 docs/Trade&Trust-demo.md Case 5
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

    carol = host.register_entity(name="Carol", kind=EntityKind.HUMAN)
    bob = host.register_entity(name="Bob", kind=EntityKind.HUMAN)

    # 快速推进到 SETTLING
    await carol.send_message(
        to=arbiter.entity_card,
        message=Message(
            kind=MessageKind.CONTRACT_CREATE,
            payload=ContractCreatePayload(
                party_a=carol.address,
                party_b=bob.address,
                title="翻译服务",
                description="中英互译 5000 字技术文档",
                amount=100,
                funding_mode=FundingMode.DIRECT,
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

    await bob.send_message(
        to=arbiter.entity_card,
        message=Message(
            kind=MessageKind.CONTRACT_COMPLETE,
            payload=ContractActionPayload(contract_id=contract_id).model_dump(),
        ),
    )
    await asyncio.sleep(0.1)

    await carol.send_message(
        to=arbiter.entity_card,
        message=Message(
            kind=MessageKind.CONTRACT_ACCEPT,
            payload=ContractActionPayload(contract_id=contract_id).model_dump(),
        ),
    )
    await asyncio.sleep(0.1)

    c = arbiter_cp.contracts[contract_id]
    print(f"=== 合同已进入 SETTLING: {c.title} ===")
    print(f"  Status: {c.status.value}")
    print()

    # Bob 发送二维码收款
    print("=== ① Bob 发起收款（二维码）===")
    payment_id = "pay_qr_001"
    await bob.send_message(
        to=arbiter.entity_card,
        message=Message(
            kind=MessageKind.PAY_COLLECT,
            payload=PayCollectPayload(
                payment_id=payment_id,
                contract_id=contract_id,
                payer=carol.address,
                payee=bob.address,
                amount=100,
                method=PaymentMethod.QR_CODE,
                receipt_info="data:image/png;base64,iVBOR...QR_CODE_DATA...",
            ).model_dump(),
        ),
    )
    await asyncio.sleep(0.1)
    payment = arbiter_cp.payments[payment_id]
    print(f"  Payment: {payment_id}")
    print(f"  Method: {payment.method.value}")
    print(f"  Status: {payment.status.value}")
    print(f"  QR code sent to Carol")
    print()

    # Carol 扫码付款（协议外）
    print("=== ② Carol 扫码付款（协议外操作）===")
    print("  Carol 在手机上扫描二维码...")
    print("  支付平台确认付款成功")
    print()

    # Bob 确认收款
    print("=== ③ Bob 确认收款 ===")
    await bob.send_message(
        to=arbiter.entity_card,
        message=Message(
            kind=MessageKind.PAY_CONFIRM_RECEIPT,
            payload=PayActionPayload(payment_id=payment_id).model_dump(),
        ),
    )
    await asyncio.sleep(0.1)

    payment = arbiter_cp.payments[payment_id]
    c = arbiter_cp.contracts[contract_id]
    print(f"  Payment: {payment.status.value}")
    print(f"  Contract: {c.status.value}")
    print()

    # Carol 评分
    print("=== ④ Carol 评分 ===")
    await carol.send_message(
        to=arbiter.entity_card,
        message=Message(
            kind=MessageKind.CONTRACT_RATE,
            payload=ContractRatePayload(
                contract_id=contract_id,
                rating=5,
                review="翻译质量很高，专业术语准确",
            ).model_dump(),
        ),
    )
    await asyncio.sleep(0.1)
    c = arbiter_cp.contracts[contract_id]

    print(f"  Rating: {c.rating}/5 — {c.review}")
    print()

    print("=== 最终状态 ===")
    print(f"  Contract: {c.title} — {c.status.value}")
    print(f"  Funding: {c.funding_mode.value}")
    print(f"  Payment: {payment.method.value} — {payment.status.value}")


if __name__ == "__main__":
    asyncio.run(main())
