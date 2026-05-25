"""Trade & Trust checkpoints for Entity-side decision making."""

from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger
from pydantic import BaseModel, ConfigDict, Field

from ..core.checkpoint import CallOwnerMixin, CheckPoint, CheckPointResult, send_approval_status
from ..message import ApprovalAudience, ApprovalFlowSide, ApprovalFlowStatus
from ..core.wellknown import FPAddress
from ..mail import Mail
from ..message import Message, MessageKind
from .enums import ContractStatus
from .models import ApprovalRule, PaymentApprovalPolicy
from .payloads import (
    ContractActionPayload,
    ContractAmendPayload,
    ContractCreatePayload,
    ContractRatePayload,
    ContractStatusPayload,
    PayActionPayload,
    PayCollectPayload,
)

if TYPE_CHECKING:
    from ..entity import Entity

CONTRACT_MESSAGE_KINDS = {
    MessageKind.CONTRACT_STATUS,
    MessageKind.CONTRACT_TIMEOUT,
}
OUTBOUND_CONTRACT_ACTION_ONLY_KINDS = {
    MessageKind.CONTRACT_APPROVE,
    MessageKind.CONTRACT_REJECT,
    MessageKind.CONTRACT_COMPLETE,
    MessageKind.CONTRACT_ACCEPT,
    MessageKind.CONTRACT_REWORK,
    MessageKind.CONTRACT_CANCEL,
    MessageKind.CONTRACT_DISPUTE,
}
OUTBOUND_CONTRACT_ACTION_KINDS = OUTBOUND_CONTRACT_ACTION_ONLY_KINDS | {
    MessageKind.CONTRACT_AMEND,
    MessageKind.CONTRACT_RATE,
}

PAY_MESSAGE_KINDS = {
    MessageKind.PAY_REQUEST,
    MessageKind.PAY_TIMEOUT,
}


class ContractOwnerRequest(BaseModel):
    """Normalized owner-approval prompt for one contract status update."""

    description: str
    available_actions: list[str]
    process_text: str


class ContractOwnerDecision(BaseModel):
    """Normalized follow-up action sent from entity back to arbiter."""

    kind: MessageKind
    payload: ContractActionPayload


class OutboundContractCreateApprovalFlow(BaseModel, CallOwnerMixin):
    """Approval flow for outbound contract_create before it reaches the arbiter."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str = "outbound_contract_create_approval"
    call_owner_policy: str = "always_call"


class OutboundContractActionApprovalFlow(BaseModel, CallOwnerMixin):
    """Approval flow for outbound contract actions before they reach the arbiter."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str = "outbound_contract_action_approval"
    call_owner_policy: str = "always_call"


class OutboundPayCollectApprovalFlow(BaseModel, CallOwnerMixin):
    """Approval flow for outbound pay_collect before it reaches the payer."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str = "outbound_pay_collect_approval"
    call_owner_policy: str = "always_call"


def _contract_role_for_entity(contract_payload: ContractStatusPayload, entity: Entity) -> str | None:
    contract = contract_payload.contract
    if entity.address.address == contract.party_a.address:
        return "party_a"
    if entity.address.address == contract.party_b.address:
        return "party_b"
    return None


def _has_current_revision_approval(contract_payload: ContractStatusPayload, role: str) -> bool:
    contract = contract_payload.contract
    return any(
        approval.party_role == role
        and approval.approved_revision == contract.draft_version
        and approval.approved_terms_hash == contract.terms_hash
        for approval in contract.approvals
    )


def build_contract_owner_request(
    contract_payload: ContractStatusPayload,
    entity: Entity,
) -> ContractOwnerRequest | None:
    """Build the owner prompt for one contract status notification."""
    contract = contract_payload.contract
    role = _contract_role_for_entity(contract_payload, entity)
    if role is None:
        return None

    if contract_payload.status == ContractStatus.DRAFT:
        if _has_current_revision_approval(contract_payload, role):
            return None
        return ContractOwnerRequest(
            description=f"收到合同邀请：{contract.title}，金额 ¥{contract.amount:g}",
            available_actions=["approve", "reject"],
            process_text="合同邀请进入审批流程",
        )

    if contract_payload.status == ContractStatus.COMPLETING and role == "party_a":
        return ContractOwnerRequest(
            description=f"合同 {contract.title} 已提交交付，请验收",
            available_actions=["accept", "rework"],
            process_text="合同验收进入审批流程",
        )

    return None


def build_contract_owner_decision(
    contract_payload: ContractStatusPayload,
    action: str,
) -> ContractOwnerDecision | None:
    """Translate an owner action into a contract message for the arbiter."""
    contract = contract_payload.contract
    payload = ContractActionPayload(
        contract_id=contract.contract_id,
        expected_status=contract.status,
        revision=contract.draft_version,
        terms_hash=contract.terms_hash,
        source_snapshot_hash=contract.current_snapshot_hash,
    )

    if contract_payload.status == ContractStatus.DRAFT:
        kind_map = {
            "approve": MessageKind.CONTRACT_APPROVE,
            "reject": MessageKind.CONTRACT_REJECT,
        }
    elif contract_payload.status == ContractStatus.COMPLETING:
        kind_map = {
            "accept": MessageKind.CONTRACT_ACCEPT,
            "rework": MessageKind.CONTRACT_REWORK,
        }
    else:
        return None

    message_kind = kind_map.get(action)
    if message_kind is None:
        return None
    return ContractOwnerDecision(kind=message_kind, payload=payload)


def build_outbound_contract_create_request(
    payload: ContractCreatePayload,
) -> ContractOwnerRequest:
    """Build the owner prompt for one outbound contract_create request."""
    return ContractOwnerRequest(
        description=f"准备发起合同：{payload.title}，金额 ¥{payload.amount:g}",
        available_actions=["approve", "reject"],
        process_text="合同创建进入审批流程",
    )


def _format_amend_summary(payload: ContractAmendPayload) -> str:
    fields: list[str] = []
    if payload.title is not None:
        fields.append(f"标题={payload.title}")
    if payload.amount is not None:
        fields.append(f"金额=¥{payload.amount:g}")
    if payload.description is not None:
        fields.append("描述已修改")
    if payload.funding_mode is not None:
        fields.append(f"模式={payload.funding_mode.value}")
    return "，".join(fields) if fields else "修改合同条款"


def build_outbound_contract_action_request(
    kind: MessageKind,
    payload: ContractActionPayload | ContractAmendPayload | ContractRatePayload,
) -> ContractOwnerRequest:
    """Build the owner prompt for one outbound contract message."""
    if kind in OUTBOUND_CONTRACT_ACTION_ONLY_KINDS:
        assert isinstance(payload, ContractActionPayload)
        reason_suffix = f"，备注：{payload.reason}" if payload.reason else ""
        request_map: dict[MessageKind, tuple[str, str]] = {
            MessageKind.CONTRACT_APPROVE: ("准备同意合同", "合同同意进入审批流程"),
            MessageKind.CONTRACT_REJECT: ("准备拒绝合同", "合同拒绝进入审批流程"),
            MessageKind.CONTRACT_COMPLETE: ("准备提交交付", "合同交付进入审批流程"),
            MessageKind.CONTRACT_ACCEPT: ("准备验收合同", "合同验收进入审批流程"),
            MessageKind.CONTRACT_REWORK: ("准备发起返工", "合同返工进入审批流程"),
            MessageKind.CONTRACT_CANCEL: ("准备取消合同", "合同取消进入审批流程"),
            MessageKind.CONTRACT_DISPUTE: ("准备发起争议", "合同争议进入审批流程"),
        }
        description_prefix, process_text = request_map[kind]
        return ContractOwnerRequest(
            description=f"{description_prefix}：{payload.contract_id}{reason_suffix}",
            available_actions=["approve", "reject"],
            process_text=process_text,
        )

    if kind == MessageKind.CONTRACT_AMEND:
        assert isinstance(payload, ContractAmendPayload)
        return ContractOwnerRequest(
            description=f"准备修改合同：{payload.contract_id}，{_format_amend_summary(payload)}",
            available_actions=["approve", "reject"],
            process_text="合同修改进入审批流程",
        )

    assert isinstance(payload, ContractRatePayload)
    review_suffix = f"，评价：{payload.review}" if payload.review else ""
    return ContractOwnerRequest(
        description=f"准备评价合同：{payload.contract_id}，评分 {payload.rating}/5{review_suffix}",
        available_actions=["approve", "reject"],
        process_text="合同评分进入审批流程",
    )


def validate_outbound_contract_payload(
    kind: MessageKind,
    payload: ContractActionPayload | ContractAmendPayload | ContractRatePayload | dict,
) -> ContractActionPayload | ContractAmendPayload | ContractRatePayload:
    """Validate one outbound contract payload by message kind."""
    if kind in OUTBOUND_CONTRACT_ACTION_ONLY_KINDS:
        return ContractActionPayload.model_validate(payload)
    if kind == MessageKind.CONTRACT_AMEND:
        return ContractAmendPayload.model_validate(payload)
    if kind == MessageKind.CONTRACT_RATE:
        return ContractRatePayload.model_validate(payload)
    raise ValueError(f"Unsupported outbound contract action: {kind.value}")


def _approval_metadata(approval_request_id: str | None) -> dict[str, str]:
    metadata: dict[str, str] = {}
    if approval_request_id:
        metadata["resumed_from_approval"] = approval_request_id
    return metadata


async def _send_contract_message_to_arbiter(
    entity: Entity,
    kind: MessageKind,
    payload: ContractCreatePayload | ContractActionPayload | ContractAmendPayload | ContractRatePayload,
    approval_request_id: str | None = None,
) -> bool:
    """Send one contract message to the arbiter."""
    if entity.arbiter is None:
        logger.warning(f"[{entity.name}] Contract message dropped: no arbiter configured")
        return False

    await entity.send_message(
        to=entity.arbiter,
        message=Message(
            kind=kind,
            payload=payload,
            metadata=_approval_metadata(approval_request_id),
        ),
    )
    logger.info(f"[{entity.name}] Contract message sent to arbiter: {kind.value}")
    return True


async def send_contract_create_to_arbiter(
    entity: Entity,
    payload: ContractCreatePayload,
    approval_request_id: str | None = None,
) -> bool:
    """Send a contract_create message to the arbiter."""
    return await _send_contract_message_to_arbiter(
        entity,
        MessageKind.CONTRACT_CREATE,
        payload,
        approval_request_id,
    )


async def send_outbound_contract_message_to_arbiter(
    entity: Entity,
    kind: MessageKind,
    payload: ContractActionPayload | ContractAmendPayload | ContractRatePayload,
    approval_request_id: str | None = None,
) -> bool:
    """Send one outbound contract message to the arbiter."""
    return await _send_contract_message_to_arbiter(
        entity,
        kind,
        payload,
        approval_request_id,
    )


async def send_contract_owner_decision(
    entity: Entity,
    contract_payload: ContractStatusPayload,
    action: str,
    approval_request_id: str | None = None,
) -> bool:
    """Send the owner-selected contract action back to the arbiter."""
    if entity.arbiter is None:
        logger.warning(f"[{entity.name}] Contract owner decision dropped: no arbiter configured")
        return False

    decision = build_contract_owner_decision(contract_payload, action)
    if decision is None:
        logger.warning(
            f"[{entity.name}] Unsupported contract owner action={action} "
            f"for status={contract_payload.status.value}"
        )
        return False

    await send_outbound_contract_message_to_arbiter(
        entity,
        decision.kind,
        decision.payload,
        approval_request_id,
    )
    logger.info(
        f"[{entity.name}] Contract owner action sent: "
        f"{decision.kind.value} ({contract_payload.contract.contract_id})"
    )
    return True


async def request_outbound_contract_create_approval(
    entity: Entity,
    payload: ContractCreatePayload,
    call_owner_policy: str = "always_call",
) -> str:
    """Request owner approval before sending contract_create."""
    if call_owner_policy != "always_call" or entity.owner is None:
        sent = await send_contract_create_to_arbiter(entity, payload)
        return "sent" if sent else "blocked"

    flow = OutboundContractCreateApprovalFlow(call_owner_policy=call_owner_policy)
    approval_request = build_outbound_contract_create_request(payload)
    draft_message = Message(kind=MessageKind.CONTRACT_CREATE, payload=payload)
    pseudo_recipient = entity.arbiter or entity.address
    pseudo_mail = Mail.seal(
        sender=entity.address,
        recipient=pseudo_recipient,
        message=draft_message,
        sign_private_key=entity.sign_private_key,
        encrypt_public_key=None,
    )
    request_id = await flow.call_owner_for_approval(
        entity=entity,
        mail=pseudo_mail,
        message=draft_message,
        description=approval_request.description,
        available_actions=approval_request.available_actions,
        action_type="require_approval",
    )
    logger.info(
        f"[{entity.name}] Contract create deferred for owner approval: "
        f"{payload.title} ({request_id[:8]})"
    )
    return "pending"


async def request_outbound_contract_action_approval(
    entity: Entity,
    kind: MessageKind,
    payload: ContractActionPayload | ContractAmendPayload | ContractRatePayload,
    call_owner_policy: str = "always_call",
) -> str:
    """Request owner approval before sending one outbound contract action."""
    if kind not in OUTBOUND_CONTRACT_ACTION_KINDS:
        raise ValueError(f"Unsupported outbound contract action: {kind.value}")

    if call_owner_policy != "always_call" or entity.owner is None:
        sent = await send_outbound_contract_message_to_arbiter(entity, kind, payload)
        return "sent" if sent else "blocked"

    flow = OutboundContractActionApprovalFlow(call_owner_policy=call_owner_policy)
    approval_request = build_outbound_contract_action_request(kind, payload)
    draft_message = Message(kind=kind, payload=payload)
    pseudo_recipient = entity.arbiter or entity.address
    pseudo_mail = Mail.seal(
        sender=entity.address,
        recipient=pseudo_recipient,
        message=draft_message,
        sign_private_key=entity.sign_private_key,
        encrypt_public_key=None,
    )
    request_id = await flow.call_owner_for_approval(
        entity=entity,
        mail=pseudo_mail,
        message=draft_message,
        description=approval_request.description,
        available_actions=approval_request.available_actions,
        action_type="require_approval",
    )
    logger.info(
        f"[{entity.name}] Contract action deferred for owner approval: "
        f"{kind.value} ({getattr(payload, 'contract_id', 'unknown')}, {request_id[:8]})"
    )
    return "pending"


# ==================== Outbound PAY_COLLECT approval ====================


def build_outbound_pay_collect_request(
    payload: PayCollectPayload, *, direct: bool,
) -> tuple[ContractOwnerRequest, str]:
    """Build the owner prompt for an outbound pay_collect request. Returns (request, action_type)."""
    mode = "DIRECT" if direct else "ESCROW"
    if direct:
        description = (
            f"准备向 {payload.payer.address} 发起收款（{mode}模式）：\n"
            f"金额 ¥{payload.amount:g}，方式 {payload.method.value}\n"
            f"同意请附上你的收款链接，拒绝请输入拒绝理由"
        )
        action_type = "require_input"
    else:
        description = (
            f"准备向 {payload.payer.address} 发起收款（{mode}模式）：\n"
            f"金额 ¥{payload.amount:g}，方式 {payload.method.value}，"
            f"收款信息 {payload.receipt_info}\n"
            f"拒绝请输入拒绝理由"
        )
        action_type = "require_input"
    request = ContractOwnerRequest(
        description=description,
        available_actions=["approve", "reject"],
        process_text="收款流程进入审批流程",
    )
    return request, action_type


async def send_pay_collect_message(
    entity: Entity,
    payload: PayCollectPayload,
    to_entity: str | None = None,
    approval_request_id: str | None = None,
) -> bool:
    """Send PAY_COLLECT to payer (direct) or arbiter (escrow)."""
    msg = Message(
        kind=MessageKind.PAY_COLLECT,
        payload=payload,
        metadata=_approval_metadata(approval_request_id),
    )
    if to_entity:
        await entity.send_message(to=to_entity, message=msg)
    elif entity.arbiter:
        await entity.send_message(to=entity.arbiter, message=msg)
    else:
        logger.warning(f"[{entity.name}] PAY_COLLECT dropped: no target")
        return False
    logger.info(f"[{entity.name}] PAY_COLLECT sent (to_entity={to_entity})")
    return True


async def request_outbound_pay_collect_approval(
    entity: Entity,
    payload: PayCollectPayload,
    to_entity: str | None = None,
    call_owner_policy: str = "always_call",
) -> str:
    """Request owner approval before sending pay_collect."""
    if call_owner_policy != "always_call" or entity.owner is None:
        sent = await send_pay_collect_message(entity, payload, to_entity)
        return "sent" if sent else "blocked"

    flow = OutboundPayCollectApprovalFlow(call_owner_policy=call_owner_policy)
    direct = to_entity is not None
    approval_request, action_type = build_outbound_pay_collect_request(payload, direct=direct)

    extended_payload = payload.model_dump(mode="json")
    if to_entity:
        extended_payload["_to_entity"] = to_entity
    extended_payload["_direct"] = direct

    draft_message = Message(kind=MessageKind.PAY_COLLECT, payload=extended_payload)
    pseudo_recipient = entity.arbiter or entity.address
    pseudo_mail = Mail.seal(
        sender=entity.address,
        recipient=pseudo_recipient,
        message=draft_message,
        sign_private_key=entity.sign_private_key,
        encrypt_public_key=None,
    )
    request_id = await flow.call_owner_for_approval(
        entity=entity,
        mail=pseudo_mail,
        message=draft_message,
        description=approval_request.description,
        available_actions=approval_request.available_actions,
        action_type=action_type,
    )
    logger.info(
        f"[{entity.name}] PAY_COLLECT deferred for owner approval: "
        f"amount={payload.amount} ({request_id[:8]})"
    )
    return "pending"


class ContractApprovalCheckPoint(CallOwnerMixin, CheckPoint):
    """Entity-side: decide whether contract events need Owner intervention."""

    name: str = "contract_approval"
    message_kinds: set[MessageKind] = Field(default=CONTRACT_MESSAGE_KINDS)

    async def execute(self, message: Message, entity: Entity, mail: Mail) -> CheckPointResult:
        if message.kind != MessageKind.CONTRACT_STATUS:
            return CheckPointResult.success()

        try:
            contract_payload = ContractStatusPayload.model_validate(message.payload)
        except Exception as exc:
            logger.warning(f"[{entity.name}] Invalid contract status payload: {exc}")
            return CheckPointResult.failure(
                error_code="INVALID_PAYLOAD",
                error_message="Invalid contract status payload",
            )

        owner_request = build_contract_owner_request(contract_payload, entity)
        if owner_request is None:
            return CheckPointResult.success()

        if self.call_owner_policy != "always_call" or entity.owner is None:
            logger.debug(
                f"[{entity.name}] Contract owner approval skipped by policy={self.call_owner_policy}"
            )
            return CheckPointResult.success()

        request_id = await self.call_owner_for_approval(
            entity=entity,
            mail=mail,
            message=message,
            description=owner_request.description,
            available_actions=owner_request.available_actions,
            action_type="require_approval",
        )
        await send_approval_status(
            entity,
            entity.entity_card,
            request_id,
            MessageKind.CONTRACT_STATUS.value,
            "合同状态消息",
            flow_side=ApprovalFlowSide.INBOUND,
            status=ApprovalFlowStatus.PENDING,
            audience=ApprovalAudience.SELF,
            original_preview=message.extract_text() or None,
        )
        return CheckPointResult.handled_success()


class PaymentApprovalCheckPoint(CheckPoint):
    """Entity-side: evaluate whether a payment request can be auto-approved."""

    name: str = "payment_approval"
    message_kinds: set[MessageKind] = Field(default=PAY_MESSAGE_KINDS)
    policy: PaymentApprovalPolicy = Field(default_factory=PaymentApprovalPolicy)

    async def execute(self, message: Message, entity: Entity, mail: Mail) -> CheckPointResult:
        if message.kind != MessageKind.PAY_REQUEST:
            return CheckPointResult.success()

        amount = 0.0
        if isinstance(message.payload, dict):
            amount = message.payload.get("amount", 0.0)

        for rule in self.policy.auto_approve_rules:
            if self._matches(rule, amount, message):
                logger.debug(f"[{entity.name}] Payment auto-approved (amount={amount})")
                return CheckPointResult.success()

        logger.info(f"[{entity.name}] Payment requires Owner approval (amount={amount})")
        return CheckPointResult.success()

    @staticmethod
    def _matches(rule: ApprovalRule, amount: float, message: Message) -> bool:
        if rule.max_amount is not None and amount <= rule.max_amount:
            return True
        sender = message.metadata.get("sender_address", "")
        if rule.whitelist and sender in rule.whitelist:
            return True
        return False


# ── Inbound pay_collect approval (payer side) ────────────────────


async def send_pay_claim_completed(
    entity: Entity,
    collect_payload: PayCollectPayload,
    sender_address: str,
    approval_request_id: str | None = None,
) -> None:
    """Send pay_claim_completed to payee (sender of pay_collect)."""
    from .models import Payment

    payment = Payment(
        payment_id=collect_payload.payment_id,
        contract_id=collect_payload.contract_id,
        payer=entity.address,
        payee=collect_payload.payee,
        amount=collect_payload.amount,
        method=collect_payload.method,
        pay_mode="owner_pay",
        status="confirming",
        receipt_info=collect_payload.receipt_info,
        requested_at=__import__("time").time(),
    )
    msg = Message(
        kind=MessageKind.PAY_CLAIM_COMPLETED,
        payload=PayActionPayload(
            payment_id=collect_payload.payment_id,
            payment=payment,
        ),
        metadata=_approval_metadata(approval_request_id),
    )
    await entity.send_message(to=FPAddress(address=sender_address), message=msg)
    logger.info(f"[{entity.name}] PAY_CLAIM_COMPLETED sent (payee={sender_address})")


class PayCollectInboundCheckPoint(CallOwnerMixin, CheckPoint):
    """Payer-side: intercept inbound pay_collect for owner payment confirmation."""

    name: str = "pay_collect_inbound_approval"
    message_kinds: set[MessageKind] = Field(
        default={MessageKind.PAY_COLLECT},
    )

    async def execute(
        self, message: Message, entity: Entity, mail: Mail,
    ) -> CheckPointResult:
        if message.kind != MessageKind.PAY_COLLECT:
            return CheckPointResult.success()

        sender_address = message.metadata.get("sender_address", mail.sender.address)
        if sender_address == entity.address.address:
            return CheckPointResult.success()

        try:
            payload = PayCollectPayload.model_validate(message.payload)
        except Exception as exc:
            logger.warning(f"[{entity.name}] Invalid pay_collect payload: {exc}")
            return CheckPointResult.failure(
                error_code="INVALID_PAYLOAD",
                error_message="Invalid pay_collect payload",
            )

        amount = payload.amount
        receipt_display = "收款码图片" if payload.receipt_info.startswith("data:image/") else payload.receipt_info

        if self.call_owner_policy != "always_call" or entity.owner is None:
            await send_pay_claim_completed(entity, payload, sender_address)
            return CheckPointResult.handled_success()

        extended_payload = payload.model_dump(mode="json")
        extended_payload["_sender_address"] = sender_address

        request_id = await self.call_owner_for_approval(
            entity=entity,
            mail=mail,
            message=Message(
                kind=MessageKind.PAY_COLLECT,
                payload=extended_payload,
            ),
            description=(
                f"收到收款请求 ¥{amount:g}，收款信息：{receipt_display}\n请确认付款"
            ),
            available_actions=["approve", "reject"],
            action_type="require_approval",
        )

        await send_approval_status(
            entity,
            entity.entity_card,
            request_id,
            MessageKind.PAY_COLLECT.value,
            "收款请求",
            flow_side=ApprovalFlowSide.INBOUND,
            status=ApprovalFlowStatus.PENDING,
            audience=ApprovalAudience.SELF,
            original_preview=message.extract_text() or None,
        )
        return CheckPointResult.handled_success()


# ── Inbound pay_claim_completed approval (payee side) ────────────


async def send_pay_confirm_receipt(
    entity: Entity,
    payload: PayActionPayload,
    sender_address: str,
    approval_request_id: str | None = None,
) -> None:
    """Send pay_confirm_receipt to payer and arbiter."""
    msg = Message(
        kind=MessageKind.PAY_CONFIRM_RECEIPT,
        payload=payload,
        metadata=_approval_metadata(approval_request_id),
    )
    payer_address = sender_address
    await entity.send_message(to=FPAddress(address=payer_address), message=msg)
    if entity.arbiter:
        await entity.send_message(to=entity.arbiter, message=msg)
    logger.info(f"[{entity.name}] PAY_CONFIRM_RECEIPT sent (payer={payer_address})")


class PayClaimCheckPoint(CallOwnerMixin, CheckPoint):
    """Entity-side: intercept pay_claim_completed for owner confirmation."""

    name: str = "pay_claim_approval"
    message_kinds: set[MessageKind] = Field(
        default={MessageKind.PAY_CLAIM_COMPLETED},
    )

    async def execute(
        self, message: Message, entity: Entity, mail: Mail,
    ) -> CheckPointResult:
        if message.kind != MessageKind.PAY_CLAIM_COMPLETED:
            return CheckPointResult.success()

        sender_address = message.metadata.get("sender_address", mail.sender.address)
        if sender_address == entity.address.address:
            return CheckPointResult.success()

        try:
            payload = PayActionPayload.model_validate(message.payload)
        except Exception as exc:
            logger.warning(f"[{entity.name}] Invalid pay_claim_completed payload: {exc}")
            return CheckPointResult.failure(
                error_code="INVALID_PAYLOAD",
                error_message="Invalid pay_claim_completed payload",
            )

        sender_address = message.metadata.get("sender_address", mail.sender.address)
        amount = payload.payment.amount if payload.payment else 0
        payer_name = payload.payment.payer.entity_uid if payload.payment else "unknown"

        if self.call_owner_policy != "always_call" or entity.owner is None:
            await send_pay_confirm_receipt(entity, payload, sender_address)
            return CheckPointResult.handled_success()

        extended_payload = payload.model_dump(mode="json")
        extended_payload["_sender_address"] = sender_address

        request_id = await self.call_owner_for_approval(
            entity=entity,
            mail=mail,
            message=Message(
                kind=MessageKind.PAY_CLAIM_COMPLETED,
                payload=extended_payload,
            ),
            description=(
                f"对方（{payer_name}）已标记付款 ¥{amount:g}，请确认到账"
            ),
            available_actions=["approve", "reject"],
            action_type="require_approval",
        )

        await send_approval_status(
            entity,
            entity.entity_card,
            request_id,
            MessageKind.PAY_CLAIM_COMPLETED.value,
            "付款确认",
            flow_side=ApprovalFlowSide.INBOUND,
            status=ApprovalFlowStatus.PENDING,
            audience=ApprovalAudience.SELF,
            original_preview=message.extract_text() or None,
        )
        return CheckPointResult.handled_success()


class PayConfirmReceiptCheckPoint(CallOwnerMixin, CheckPoint):
    """Payer-side: intercept inbound pay_confirm_receipt for owner review."""

    name: str = "pay_confirm_receipt_approval"
    message_kinds: set[MessageKind] = Field(
        default={MessageKind.PAY_CONFIRM_RECEIPT},
    )

    async def execute(
        self, message: Message, entity: Entity, mail: Mail,
    ) -> CheckPointResult:
        if message.kind != MessageKind.PAY_CONFIRM_RECEIPT:
            return CheckPointResult.success()

        sender_address = message.metadata.get("sender_address", mail.sender.address)
        if sender_address == entity.address.address:
            return CheckPointResult.success()

        try:
            payload = PayActionPayload.model_validate(message.payload)
        except Exception as exc:
            logger.warning(f"[{entity.name}] Invalid pay_confirm_receipt payload: {exc}")
            return CheckPointResult.failure(
                error_code="INVALID_PAYLOAD",
                error_message="Invalid pay_confirm_receipt payload",
            )

        amount = payload.payment.amount if payload.payment else 0
        payee_name = payload.payment.payee.entity_uid if payload.payment else "unknown"

        if self.call_owner_policy != "always_call" or entity.owner is None:
            return CheckPointResult.success()

        request_id = await self.call_owner_for_approval(
            entity=entity,
            mail=mail,
            message=Message(
                kind=MessageKind.PAY_CONFIRM_RECEIPT,
                payload=payload.model_dump(mode="json"),
            ),
            description=(
                f"对方（{payee_name}）已确认收款 ¥{amount:g}，请确认查看"
            ),
            available_actions=["approve", "reject"],
            action_type="require_approval",
        )

        await send_approval_status(
            entity,
            entity.entity_card,
            request_id,
            MessageKind.PAY_CONFIRM_RECEIPT.value,
            "收款确认通知",
            flow_side=ApprovalFlowSide.INBOUND,
            status=ApprovalFlowStatus.PENDING,
            audience=ApprovalAudience.SELF,
            original_preview=message.extract_text() or None,
        )
        return CheckPointResult.handled_success()
