"""Checkpoint system for message validation."""

from __future__ import annotations

import time
from abc import abstractmethod
from typing import TYPE_CHECKING, Any, Awaitable, Callable
from uuid import uuid4

from loguru import logger
from pydantic import BaseModel, ConfigDict, Field

from ..message import (
    ApprovalAudience,
    ApprovalFlowSide,
    ApprovalFlowStatus,
    ApprovalRequestPayload,
    ApprovalResponsePayload,
    ApprovalStatusPayload,
    CarbonCopyPayload,
    FriendAcceptPayload,
    FriendRejectPayload,
    FriendRequestPayload,
    Message,
    MessageKind,
)
from .wellknown import EntityCard

if TYPE_CHECKING:
    from ..entity import Entity, PendingApproval
    from ..mail import Mail


def build_approval_status_text(process_text: str) -> str:
    """Build a unified user-facing status text for owner approval flows."""
    prefix = f"{process_text}。" if process_text else ""
    return (
        f"{prefix}消息需要 owner 审核；通过后自动继续发送；"
        "驳回则终止发送；结果会通知你。"
    )


def _build_preview_text(original_preview: str | None) -> str:
    """Build inline preview text for approval notices."""
    if not original_preview:
        return ""
    preview = original_preview.strip()
    if not preview:
        return ""
    return f"【{preview}】"


def build_approval_status_message(
    process_text: str,
    *,
    flow_side: ApprovalFlowSide = ApprovalFlowSide.OUTBOUND,
    status: ApprovalFlowStatus = ApprovalFlowStatus.PENDING,
    original_preview: str | None = None,
    decision: str | None = None,
) -> str:
    """Build user-facing approval status copy for one approval flow."""
    preview_text = _build_preview_text(original_preview)

    if status == ApprovalFlowStatus.PENDING and flow_side == ApprovalFlowSide.OUTBOUND:
        process_prefix = f"{process_text}。" if process_text else ""
        content = (
            f"{preview_text}{process_prefix}"
            "消息需要 owner 审核；通过后自动继续发送；驳回则终止发送；结果会通知你。"
        )
        return content if preview_text else content

    if status == ApprovalFlowStatus.PENDING and flow_side == ApprovalFlowSide.INBOUND:
        content = (
            f"你收到一条{process_text}"
            f"{preview_text}；当前由 owner 处理或审核中；结果会通知你；你可以提醒 owner。"
        )
        return content

    if status == ApprovalFlowStatus.APPROVED and flow_side == ApprovalFlowSide.OUTBOUND:
        content = f"{preview_text}owner 已审核通过；消息已自动继续发送给对方。"
        return content if preview_text else content

    if status == ApprovalFlowStatus.REJECTED and flow_side == ApprovalFlowSide.OUTBOUND:
        content = f"{preview_text}owner 已驳回；消息不会继续发送给对方。"
        return content if preview_text else content

    if status == ApprovalFlowStatus.APPROVED:
        suffix = f"；你可以继续执行{decision}。" if decision else "；你可以继续下一步操作。"
        return f"{preview_text}owner 已处理完成，审核已通过{suffix}"

    suffix = f"；当前结果：{decision}。" if decision else "；当前流程已终止。"
    return f"{preview_text}owner 已处理完成，审核未通过{suffix}"


async def send_approval_status(
    entity: Entity,
    target: Any,
    request_id: str,
    original_kind: str,
    process_text: str,
    *,
    flow_side: ApprovalFlowSide = ApprovalFlowSide.OUTBOUND,
    status: ApprovalFlowStatus = ApprovalFlowStatus.PENDING,
    audience: ApprovalAudience = ApprovalAudience.SELF,
    original_preview: str | None = None,
    decision: str | None = None,
    message_text: str | None = None,
) -> None:
    """Send a lightweight system notice for one approval flow."""
    await entity.send_message(
        to=target,
        message=Message(
            kind=MessageKind.APPROVAL_STATUS,
            payload=ApprovalStatusPayload(
                request_id=request_id,
                original_kind=original_kind,
                message=message_text or build_approval_status_message(
                    process_text,
                    flow_side=flow_side,
                    status=status,
                    original_preview=original_preview,
                    decision=decision,
                ),
                flow_side=flow_side,
                status=status,
                audience=audience,
                original_preview=original_preview,
                decision=decision,
            ),
            metadata={"_skip_cc": True},
        ),
    )


class CheckPointResult(BaseModel):
    """Result of checkpoint execution."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    passed: bool = Field(..., description="Whether validation passed")
    handled: bool = Field(
        default=False, description="Whether message was fully handled (stop processing)"
    )
    error_code: str | None = Field(
        default=None, description="Error code if validation failed"
    )
    error_message: str | None = Field(
        default=None, description="Error message if validation failed"
    )

    @classmethod
    def success(cls, handled: bool = False) -> CheckPointResult:
        """Create a successful result."""
        return cls(passed=True, handled=handled)

    @classmethod
    def failure(cls, error_code: str, error_message: str) -> CheckPointResult:
        """Create a failed result."""
        return cls(passed=False, error_code=error_code, error_message=error_message)

    @classmethod
    def handled_success(cls) -> CheckPointResult:
        """Create a result indicating message was handled successfully."""
        return cls(passed=True, handled=True)


class CheckPoint(BaseModel):
    """Base checkpoint for message validation and processing.

    order convention:
        100-199  session/identity validation
        200-299  relationship/permission (FriendCheckPoint)
        300-399  rate limit / content validation
        400-499  business validation (PaymentCheckPoint)
        500-599  user-defined (default)
        800-899  side-effects (CarbonCopyCheckpoint)
        900-999  execution (replaces Handler)
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str = Field(..., description="Checkpoint name")
    order: int = Field(default=500, description="Execution order, lower runs first")
    message_kinds: set[MessageKind] = Field(
        ..., description="Message kinds this checkpoint applies to"
    )
    call_owner_policy: str = Field(
        default="always_pass",
        description="Owner approval policy: always_pass | conditional | always_call",
    )

    @abstractmethod
    async def execute(
        self, message: Message, entity: Entity, mail: Mail
    ) -> CheckPointResult:
        """Execute checkpoint logic.

        Args:
            message: Message to validate/process
            entity: Entity that owns this checkpoint
            mail: Original mail envelope

        Returns:
            CheckPointResult indicating validation status and whether message was handled
        """
        raise NotImplementedError


class CallOwnerMixin:
    """Mixin for checkpoints that can request owner approval."""

    async def call_owner_for_approval(
        self,
        entity: Entity,
        mail: Mail,
        message: Message,
        description: str,
        available_actions: list[str],
        action_type: str = "require_approval",
    ) -> str:
        """Send approval request to owner and defer processing immediately."""
        from ..entity import PendingApproval

        original_payload: dict[str, Any] = {}
        if hasattr(message.payload, "model_dump"):
            original_payload = message.payload.model_dump(mode="json")
        elif isinstance(message.payload, dict):
            original_payload = message.payload

        request_id = uuid4().hex
        payload = ApprovalRequestPayload(
            request_id=request_id,
            source_entity_uid=entity.uid,
            source_entity_name=entity.name,
            action_type=action_type,
            description=description,
            original_kind=message.kind.value if isinstance(message.kind, MessageKind) else str(message.kind),
            original_payload=original_payload,
            available_actions=available_actions,
        )
        approval_msg = Message(kind=MessageKind.APPROVAL_REQUEST, payload=payload)
        await entity.call_owner(approval_msg)
        logger.info(f"[{entity.name}] Approval request {request_id[:8]} deferred immediately")
        entity.pending_approvals[request_id] = PendingApproval(
            request_id=request_id,
            original_kind=payload.original_kind,
            original_payload=original_payload,
            original_sender_address=mail.sender.address,
            original_mail_id=getattr(mail, "mail_id", ""),
            original_preview=message.extract_text() or None,
            created_at=time.time(),
            checkpoint_name=getattr(self, "name", ""),
        )
        entity.host.save()
        return request_id


class SessionCheckPoint(CheckPoint):
    """Validate that the session exists in the entity."""

    async def execute(
        self, message: Message, entity: Entity, mail: Mail
    ) -> CheckPointResult:
        """Check if session_id exists in entity.sessions"""
        session_id = None

        # Extract session_id from payload
        if hasattr(message.payload, "session_id"):
            session_id = message.payload.session_id
        elif isinstance(message.payload, dict):
            session_id = message.payload.get("session_id")

        if session_id is None:
            return CheckPointResult.success()

        if session_id in entity.sessions:
            return CheckPointResult.success()

        return CheckPointResult.failure(
            error_code="INVALID_SESSION",
            error_message=f"Session '{session_id}' does not exist",
        )


class ApprovalResponseCheckPoint(CheckPoint):
    """Handle APPROVAL_RESPONSE from owner — resume deferred approvals."""

    @staticmethod
    def _checkpoint_name_for_original_kind(original_kind: str) -> str:
        """Map original message kind to the checkpoint responsible for resuming it."""
        mapping = {
            MessageKind.FRIEND_REQUEST.value: "friend_request_handler",
            MessageKind.CONTRACT_CREATE.value: "outbound_contract_create_approval",
            MessageKind.CONTRACT_STATUS.value: "contract_approval",
            MessageKind.CONTRACT_APPROVE.value: "outbound_contract_action_approval",
            MessageKind.CONTRACT_REJECT.value: "outbound_contract_action_approval",
            MessageKind.CONTRACT_COMPLETE.value: "outbound_contract_action_approval",
            MessageKind.CONTRACT_ACCEPT.value: "outbound_contract_action_approval",
            MessageKind.CONTRACT_REWORK.value: "outbound_contract_action_approval",
            MessageKind.CONTRACT_AMEND.value: "outbound_contract_action_approval",
            MessageKind.CONTRACT_RATE.value: "outbound_contract_action_approval",
            MessageKind.CONTRACT_CANCEL.value: "outbound_contract_action_approval",
            MessageKind.CONTRACT_DISPUTE.value: "outbound_contract_action_approval",
            MessageKind.PAY_COLLECT.value: "outbound_pay_collect_approval",
            MessageKind.PAY_CLAIM_COMPLETED.value: "pay_claim_approval",
            MessageKind.PAY_CONFIRM_RECEIPT.value: "pay_confirm_receipt_approval",
        }
        return mapping.get(original_kind, f"{original_kind}_handler")

    async def execute(
        self, message: Message, entity: Entity, mail: Mail
    ) -> CheckPointResult:
        payload = message.payload
        if isinstance(payload, ApprovalResponsePayload):
            request_id = payload.request_id
            action = payload.action
            input_data = payload.input_data
        elif isinstance(payload, dict):
            request_id = str(payload.get("request_id", ""))
            action = str(payload.get("action", ""))
            input_data = payload.get("input_data")
        else:
            return CheckPointResult.handled_success()

        # Async path: retrieve from pending
        pending = entity.pending_approvals.pop(request_id, None)
        if pending is None:
            # Fallback: reconstruct from response payload (server may have restarted)
            original_kind = (
                payload.original_kind if isinstance(payload, ApprovalResponsePayload)
                else payload.get("original_kind") if isinstance(payload, dict) else None
            )
            original_payload = (
                payload.original_payload if isinstance(payload, ApprovalResponsePayload)
                else payload.get("original_payload") if isinstance(payload, dict) else None
            )
            if original_kind and original_payload:
                from ..entity import PendingApproval
                pending = PendingApproval(
                    request_id=request_id,
                    original_kind=original_kind,
                    original_payload=original_payload,
                    original_sender_address=mail.sender.address,
                    original_mail_id="",
                    created_at=0.0,
                    checkpoint_name=self._checkpoint_name_for_original_kind(original_kind),
                )
                logger.info(f"[{entity.name}] Approval {request_id[:8]} reconstructed from response payload")
            else:
                logger.warning(f"[{entity.name}] Approval {request_id[:8]} not found (stale/duplicate)")
                return CheckPointResult.handled_success()

        logger.info(f"[{entity.name}] Resuming approval {request_id[:8]} (async): {action}")

        if pending.checkpoint_name == "friend_request_handler":
            await self._resume_friend_request(entity, pending, action)
        elif pending.checkpoint_name == "outbound_contract_create_approval":
            await self._resume_outbound_contract_create(entity, pending, action)
        elif pending.checkpoint_name == "outbound_contract_action_approval":
            await self._resume_outbound_contract_action(entity, pending, action)
        elif pending.checkpoint_name == "contract_approval":
            await self._resume_contract_approval(entity, pending, action)
        elif pending.checkpoint_name == "outbound_pay_collect_approval":
            await self._resume_outbound_pay_collect(entity, pending, action, input_data)
        elif pending.checkpoint_name == "pay_claim_approval":
            await self._resume_pay_claim(entity, pending, action)
        elif pending.checkpoint_name == "pay_collect_inbound_approval":
            await self._resume_pay_collect_inbound(entity, pending, action)
        elif pending.checkpoint_name == "pay_confirm_receipt_approval":
            await self._resume_pay_confirm_receipt(entity, pending, action)

        entity.host.save()
        return CheckPointResult.handled_success()

    async def _resume_friend_request(
        self, entity: Entity, pending: PendingApproval, action: str
    ) -> None:
        """Resume a deferred friend request."""
        from ..core.wellknown import EntityCard
        from ..message import FriendAcceptPayload, FriendRejectPayload, Message as Msg

        sender_card = EntityCard.model_validate(pending.original_payload.get("sender_card"))

        if action == "approve":
            accept_msg = Msg(
                kind="friend_accept",
                payload=FriendAcceptPayload(
                    sender_card=entity.entity_card,
                    text=f"{entity.name} accepted your friend request",
                ),
                metadata={"resumed_from_approval": pending.request_id},
            )
            await entity.send_message(to=sender_card, message=accept_msg)
            entity.add_friend(sender_card)
            await send_approval_status(
                entity,
                entity.entity_card,
                pending.request_id,
                MessageKind.FRIEND_REQUEST.value,
                "好友申请",
                flow_side=ApprovalFlowSide.INBOUND,
                status=ApprovalFlowStatus.APPROVED,
                audience=ApprovalAudience.SELF,
                original_preview=pending.original_preview,
                decision="与对方建立好友关系",
            )
            logger.info(f"[{entity.uid}] Accepted friend request from {sender_card.name} (async)")
        else:
            reject_msg = Msg(
                kind="friend_reject",
                payload=FriendRejectPayload(
                    sender_card=entity.entity_card,
                    text=f"{entity.name} rejected your friend request",
                ),
                metadata={"resumed_from_approval": pending.request_id},
            )
            await entity.send_message(to=sender_card, message=reject_msg)
            await send_approval_status(
                entity,
                entity.entity_card,
                pending.request_id,
                MessageKind.FRIEND_REQUEST.value,
                "好友申请",
                flow_side=ApprovalFlowSide.INBOUND,
                status=ApprovalFlowStatus.REJECTED,
                audience=ApprovalAudience.SELF,
                original_preview=pending.original_preview,
                decision="好友申请已被拒绝",
            )
            logger.info(f"[{entity.uid}] Rejected friend request from {sender_card.name} (async)")

    async def _resume_contract_approval(
        self, entity: Entity, pending: PendingApproval, action: str
    ) -> None:
        """Resume a deferred contract approval decision."""
        from ..trade.checkpoints import send_contract_owner_decision
        from ..trade.payloads import ContractStatusPayload

        contract_payload = ContractStatusPayload.model_validate(pending.original_payload)
        await send_contract_owner_decision(
            entity,
            contract_payload,
            action,
            approval_request_id=pending.request_id,
        )

        notify_msg = Message(
            kind=MessageKind.CONTRACT_STATUS,
            payload=pending.original_payload,
            metadata={
                "sender_address": pending.original_sender_address,
                "owner_approval_completed": True,
                "owner_action": action,
                "approval_request_id": pending.request_id,
                "resumed_from_approval": pending.request_id,
            },
        )
        await entity.notify_handler(notify_msg)
        decision_text = {
            "approve": "合同已同意，等待后续状态更新",
            "reject": "合同已拒绝",
            "accept": "合同验收已通过",
            "rework": "已要求对方返工",
        }.get(action, "合同审批已处理")
        await send_approval_status(
            entity,
            entity.entity_card,
            pending.request_id,
            MessageKind.CONTRACT_STATUS.value,
            "合同消息",
            flow_side=ApprovalFlowSide.INBOUND,
            status=ApprovalFlowStatus.APPROVED if action in {"approve", "accept"} else ApprovalFlowStatus.REJECTED,
            audience=ApprovalAudience.SELF,
            original_preview=pending.original_preview,
            decision=decision_text,
        )

    async def _resume_outbound_contract_create(
        self, entity: Entity, pending: PendingApproval, action: str
    ) -> None:
        """Resume a deferred outbound contract_create request."""
        from ..trade.checkpoints import send_contract_create_to_arbiter
        from ..trade.payloads import ContractCreatePayload

        if action != "approve":
            logger.info(
                f"[{entity.name}] Outbound contract create rejected after defer: "
                f"{pending.request_id[:8]}"
            )
            await send_approval_status(
                entity,
                entity.entity_card,
                pending.request_id,
                MessageKind.CONTRACT_CREATE.value,
                "合同创建",
                flow_side=ApprovalFlowSide.OUTBOUND,
                status=ApprovalFlowStatus.REJECTED,
                audience=ApprovalAudience.SELF,
                original_preview=pending.original_preview,
                decision="合同创建已终止",
            )
            return

        payload = ContractCreatePayload.model_validate(pending.original_payload)
        await send_contract_create_to_arbiter(
            entity,
            payload,
            approval_request_id=pending.request_id,
        )
        await send_approval_status(
            entity,
            entity.entity_card,
            pending.request_id,
            MessageKind.CONTRACT_CREATE.value,
            "合同创建",
            flow_side=ApprovalFlowSide.OUTBOUND,
            status=ApprovalFlowStatus.APPROVED,
            audience=ApprovalAudience.SELF,
            original_preview=pending.original_preview,
        )

    async def _resume_outbound_contract_action(
        self, entity: Entity, pending: PendingApproval, action: str
    ) -> None:
        """Resume a deferred outbound contract action."""
        from ..trade.checkpoints import (
            send_outbound_contract_message_to_arbiter,
            validate_outbound_contract_payload,
        )

        if action != "approve":
            logger.info(
                f"[{entity.name}] Outbound contract action rejected after defer: "
                f"{pending.request_id[:8]}"
            )
            await send_approval_status(
                entity,
                entity.entity_card,
                pending.request_id,
                pending.original_kind,
                "合同操作",
                flow_side=ApprovalFlowSide.OUTBOUND,
                status=ApprovalFlowStatus.REJECTED,
                audience=ApprovalAudience.SELF,
                original_preview=pending.original_preview,
                decision="合同操作已终止",
            )
            return

        kind = MessageKind(pending.original_kind)
        payload = validate_outbound_contract_payload(kind, pending.original_payload)
        await send_outbound_contract_message_to_arbiter(
            entity,
            kind,
            payload,
            approval_request_id=pending.request_id,
        )
        await send_approval_status(
            entity,
            entity.entity_card,
            pending.request_id,
            pending.original_kind,
            "合同操作",
            flow_side=ApprovalFlowSide.OUTBOUND,
            status=ApprovalFlowStatus.APPROVED,
            audience=ApprovalAudience.SELF,
            original_preview=pending.original_preview,
        )

    async def _resume_outbound_pay_collect(
        self, entity: Entity, pending: PendingApproval, action: str,
        input_data: str | None = None,
    ) -> None:
        """Resume a deferred outbound pay_collect."""
        from ..trade.checkpoints import send_pay_collect_message
        from ..trade.payloads import PayCollectPayload

        if action != "approve":
            reason = input_data or "无理由"
            logger.info(
                f"[{entity.name}] Outbound pay_collect rejected: "
                f"{pending.request_id[:8]}，理由：{reason}"
            )
            await send_approval_status(
                entity,
                entity.entity_card,
                pending.request_id,
                MessageKind.PAY_COLLECT.value,
                "收款请求",
                flow_side=ApprovalFlowSide.OUTBOUND,
                status=ApprovalFlowStatus.REJECTED,
                audience=ApprovalAudience.SELF,
                original_preview=pending.original_preview,
                decision=f"收款请求已被 owner 拒绝，理由：{reason}",
            )
            return

        to_entity = pending.original_payload.pop("_to_entity", None)
        direct = pending.original_payload.pop("_direct", False)
        payload = PayCollectPayload.model_validate(pending.original_payload)
        if direct and input_data:
            payload.receipt_info = input_data
        await send_pay_collect_message(
            entity,
            payload,
            to_entity=to_entity,
            approval_request_id=pending.request_id,
        )
        receipt_display = "收款码图片" if payload.receipt_info.startswith("data:image/") else payload.receipt_info
        await send_approval_status(
            entity,
            entity.entity_card,
            pending.request_id,
            MessageKind.PAY_COLLECT.value,
            "收款请求",
            flow_side=ApprovalFlowSide.OUTBOUND,
            status=ApprovalFlowStatus.APPROVED,
            audience=ApprovalAudience.SELF,
            original_preview=pending.original_preview,
            decision=f"收款信息：{receipt_display}",
        )

    async def _resume_pay_claim(
        self, entity: Entity, pending: PendingApproval, action: str,
    ) -> None:
        """Resume a deferred pay_claim_completed confirmation."""
        from ..trade.checkpoints import send_pay_confirm_receipt
        from ..trade.payloads import PayActionPayload

        sender_address = pending.original_payload.pop("_sender_address", "")
        payload = PayActionPayload.model_validate(pending.original_payload)

        if action != "approve":
            logger.info(
                f"[{entity.name}] Pay claim confirmation rejected: "
                f"{pending.request_id[:8]}"
            )
            await send_approval_status(
                entity,
                entity.entity_card,
                pending.request_id,
                MessageKind.PAY_CLAIM_COMPLETED.value,
                "收款确认",
                flow_side=ApprovalFlowSide.INBOUND,
                status=ApprovalFlowStatus.REJECTED,
                audience=ApprovalAudience.SELF,
                original_preview=pending.original_preview,
                decision="收款确认已被 owner 拒绝",
            )
            return

        await send_pay_confirm_receipt(
            entity, payload, sender_address,
            approval_request_id=pending.request_id,
        )
        await send_approval_status(
            entity,
            entity.entity_card,
            pending.request_id,
            MessageKind.PAY_CLAIM_COMPLETED.value,
            "收款确认",
            flow_side=ApprovalFlowSide.INBOUND,
            status=ApprovalFlowStatus.APPROVED,
            audience=ApprovalAudience.SELF,
            original_preview=pending.original_preview,
            decision="确认收款",
        )

    async def _resume_pay_collect_inbound(
        self, entity: Entity, pending: PendingApproval, action: str,
    ) -> None:
        """Resume a deferred inbound pay_collect (payer confirms payment)."""
        from ..trade.checkpoints import send_pay_claim_completed
        from ..trade.payloads import PayCollectPayload

        sender_address = pending.original_payload.pop("_sender_address", "")
        payload = PayCollectPayload.model_validate(pending.original_payload)

        if action != "approve":
            logger.info(
                f"[{entity.name}] Inbound pay_collect rejected: "
                f"{pending.request_id[:8]}"
            )
            await send_approval_status(
                entity,
                entity.entity_card,
                pending.request_id,
                MessageKind.PAY_COLLECT.value,
                "付款请求",
                flow_side=ApprovalFlowSide.INBOUND,
                status=ApprovalFlowStatus.REJECTED,
                audience=ApprovalAudience.SELF,
                original_preview=pending.original_preview,
                decision="付款已被 owner 拒绝",
            )
            return

        await send_pay_claim_completed(
            entity, payload, sender_address,
            approval_request_id=pending.request_id,
        )
        await send_approval_status(
            entity,
            entity.entity_card,
            pending.request_id,
            MessageKind.PAY_COLLECT.value,
            "付款请求",
            flow_side=ApprovalFlowSide.INBOUND,
            status=ApprovalFlowStatus.APPROVED,
            audience=ApprovalAudience.SELF,
            original_preview=pending.original_preview,
            decision="确认付款",
        )

    async def _resume_pay_confirm_receipt(
        self, entity: Entity, pending: PendingApproval, action: str,
    ) -> None:
        """Resume a deferred inbound pay_confirm_receipt review."""
        if action != "approve":
            logger.info(
                f"[{entity.name}] Inbound pay_confirm_receipt rejected: "
                f"{pending.request_id[:8]}"
            )
            await send_approval_status(
                entity,
                entity.entity_card,
                pending.request_id,
                MessageKind.PAY_CONFIRM_RECEIPT.value,
                "收款确认通知",
                flow_side=ApprovalFlowSide.INBOUND,
                status=ApprovalFlowStatus.REJECTED,
                audience=ApprovalAudience.SELF,
                original_preview=pending.original_preview,
                decision="收款确认通知已被 owner 驳回",
            )
            return

        await send_approval_status(
            entity,
            entity.entity_card,
            pending.request_id,
            MessageKind.PAY_CONFIRM_RECEIPT.value,
            "收款确认通知",
            flow_side=ApprovalFlowSide.INBOUND,
            status=ApprovalFlowStatus.APPROVED,
            audience=ApprovalAudience.SELF,
            original_preview=pending.original_preview,
            decision="查看支付完成结果",
        )


class FriendCheckPoint(CheckPoint):
    """Validate that the sender is a friend of the entity."""

    async def execute(
        self, message: Message, entity: Entity, mail: Mail
    ) -> CheckPointResult:
        """Check if sender is in entity.friends"""
        sender_uid = message.metadata.get("sender_uid") or message.metadata.get(
            "from_entity_uid"
        )

        if sender_uid is None:
            return CheckPointResult.failure(
                error_code="MISSING_SENDER_UID", error_message="Sender UID not found in metadata"
            )

        if sender_uid in entity.friends:
            return CheckPointResult.success()

        return CheckPointResult.failure(
            error_code="NOT_FRIEND",
            error_message="You are no longer friends. Please send a friend request to reconnect.",
        )


class PaymentCheckPoint(CheckPoint):
    """Validate that the message has been paid for."""

    async def execute(
        self, message: Message, _entity: Entity, _mail: Mail
    ) -> CheckPointResult:
        """Check if payment proof exists in message metadata"""
        payment_proof = message.metadata.get("payment_proof")
        payment_verified = message.metadata.get("payment_verified", False)

        if payment_proof is not None and payment_verified is True:
            return CheckPointResult.success()

        return CheckPointResult.failure(
            error_code="PAYMENT_REQUIRED", error_message="Message requires payment"
        )


class RateLimitCheckPoint(CheckPoint):
    """Validate message rate limit to prevent spam."""

    max_messages_per_minute: int = Field(default=60, description="Maximum messages per minute")
    _message_timestamps: dict[str, list[float]] = {}

    async def execute(
        self, message: Message, _entity: Entity, _mail: Mail
    ) -> CheckPointResult:
        """Check if sender exceeds rate limit"""
        import time

        sender_uid = message.metadata.get("sender_uid") or message.metadata.get(
            "from_entity_uid"
        )

        if sender_uid is None:
            return CheckPointResult.success()

        current_time = time.time()
        one_minute_ago = current_time - 60

        if sender_uid not in self._message_timestamps:
            self._message_timestamps[sender_uid] = []

        # Clean old timestamps
        self._message_timestamps[sender_uid] = [
            ts for ts in self._message_timestamps[sender_uid] if ts > one_minute_ago
        ]

        if len(self._message_timestamps[sender_uid]) >= self.max_messages_per_minute:
            return CheckPointResult.failure(
                error_code="RATE_LIMIT_EXCEEDED",
                error_message=f"Rate limit exceeded: {self.max_messages_per_minute} messages per minute",
            )

        self._message_timestamps[sender_uid].append(current_time)
        return CheckPointResult.success()


class ContentLengthCheckPoint(CheckPoint):
    """Validate message content length."""

    max_length: int = Field(default=10000, description="Maximum content length in characters")

    async def execute(
        self, message: Message, _entity: Entity, _mail: Mail
    ) -> CheckPointResult:
        """Check if message content exceeds max length"""
        content_text = message.extract_text()
        if not content_text or len(content_text) <= self.max_length:
            return CheckPointResult.success()

        return CheckPointResult.failure(
            error_code="CONTENT_TOO_LONG",
            error_message=f"Content length {len(content_text)} exceeds maximum {self.max_length}",
        )


class FriendRequestCheckPoint(CallOwnerMixin, CheckPoint):
    """Handle friend request, accept, and reject messages."""

    async def execute(
        self, message: Message, entity: Entity, mail: Mail
    ) -> CheckPointResult:
        """Process friend-related messages and return handled result"""
        # Extract sender_card from payload
        try:
            if isinstance(
                message.payload,
                FriendRequestPayload | FriendAcceptPayload | FriendRejectPayload,
            ):
                sender_card = message.payload.sender_card
            else:
                sender_card = EntityCard.model_validate(message.payload.get("sender_card"))
        except Exception as e:
            logger.warning(
                f"Failed to extract entity card from {mail.sender.entity_uid}: {e}"
            )
            return CheckPointResult.failure(
                error_code="INVALID_PAYLOAD",
                error_message="Failed to extract entity card from payload",
            )

        if message.kind == MessageKind.FRIEND_REQUEST:
            logger.info(f"[{entity.uid}] Received friend request from {sender_card.name}")

            # Owner's own request → auto-approve (no circular approval)
            is_from_owner = (
                entity.owner is not None
                and mail.sender.address == entity.owner.address
            )

            if self.call_owner_policy == "always_call" and entity.owner is not None and not is_from_owner:
                request_id = await self.call_owner_for_approval(
                    entity=entity,
                    mail=mail,
                    message=message,
                    description=f"{sender_card.name} wants to add {entity.name} as a friend",
                    available_actions=["approve", "reject"],
                )
                await send_approval_status(
                    entity,
                    entity.entity_card,
                    request_id,
                    MessageKind.FRIEND_REQUEST.value,
                    "好友申请",
                    flow_side=ApprovalFlowSide.INBOUND,
                    status=ApprovalFlowStatus.PENDING,
                    audience=ApprovalAudience.SELF,
                    original_preview=message.extract_text() or None,
                )
                return CheckPointResult.handled_success()

            accept_message = Message(
                kind="friend_accept",
                payload=FriendAcceptPayload(
                    sender_card=entity.entity_card,
                    text=f"{entity.name} accepted your friend request",
                ),
                metadata={"ack_of_message_id": message.message_id},
            )
            await entity.send_message(to=sender_card, message=accept_message)
            entity.add_friend(sender_card)
            logger.info(f"[{entity.uid}] Accepted friend request from {sender_card.name}")
            return CheckPointResult.handled_success()

        if message.kind == MessageKind.FRIEND_ACCEPT:
            logger.info(f"[{entity.uid}] Friend request accepted by {sender_card.name}")
            entity.add_friend(sender_card)
            return CheckPointResult.success()

        if message.kind == MessageKind.FRIEND_REJECT:
            logger.info(f"[{entity.uid}] Friend request rejected by {sender_card.name}")
            return CheckPointResult.success()

        return CheckPointResult.handled_success()


class CarbonCopyCheckpoint(CheckPoint):
    """Handle carbon copy forwarding to entity owner.

    For non-CARBON_COPY messages: forward to owner if exists.
    For CARBON_COPY messages: log and mark as handled.
    """

    def _format_cc_log(self, payload: CarbonCopyPayload | dict) -> str:
        """格式化 CarbonCopy 日志，气泡样式。"""
        if isinstance(payload, dict):
            direction = payload.get("direction", "?")
            sender = payload.get("original_sender", "?")
            sender_name = payload.get("original_sender_name") or sender.split(":")[-1]
            recipient = payload.get("original_recipient", "?")
            recipient_name = payload.get("original_recipient_name") or recipient.split(":")[-1]
            kind = payload.get("original_kind", "?")
            summary = payload.get("summary", "")
        else:
            direction = payload.direction
            sender = payload.original_sender
            sender_name = payload.original_sender_name or sender.split(":")[-1]
            recipient = payload.original_recipient
            recipient_name = payload.original_recipient_name or recipient.split(":")[-1]
            kind = payload.original_kind
            summary = payload.summary or ""

        arrow = "→" if direction == "outbound" else "←"
        direction_label = "📤 出站" if direction == "outbound" else "📥 入站"

        return (
            f"\n┌─────────────────────────────────────────\n"
            f"│ 📋 CarbonCopy {direction_label}\n"
            f"├─────────────────────────────────────────\n"
            f"│ From: {sender_name} ({sender})\n"
            f"│   {arrow}\n"
            f"│ To:   {recipient_name} ({recipient})\n"
            f"├─────────────────────────────────────────\n"
            f"│ Kind: {kind}\n"
            f"│ Content: {summary}\n"
            f"└─────────────────────────────────────────"
        )

    async def execute(
        self, message: Message, entity: Entity, mail: Mail
    ) -> CheckPointResult:
        """Process carbon copy logic."""
        from datetime import datetime

        from .base import EntityKind

        # Skip CC for approval protocol messages (owner gets them directly)
        if message.metadata.get("_skip_cc") or message.kind in {
            MessageKind.APPROVAL_REQUEST,
            MessageKind.APPROVAL_RESPONSE,
            MessageKind.APPROVAL_STATUS,
        }:
            return CheckPointResult.success()

        # Case 1: CARBON_COPY message - log and push to web if human
        if message.kind == MessageKind.CARBON_COPY:
            payload = message.payload
            log_msg = self._format_cc_log(payload)
            logger.info(f"[{entity.name}] {log_msg}")

            # 如果是 human entity，推送给 web UI
            kind_value = entity.kind.value if isinstance(entity.kind, EntityKind) else str(entity.kind).lower()
            if kind_value == EntityKind.HUMAN.value:
                await entity.host.push_to_web(entity.uid, message)

            return CheckPointResult.handled_success()

        # Case 2: Non-CARBON_COPY message - check owner and forward
        if entity.owner is None:
            return CheckPointResult.success()

        # 如果发送方是 owner，不抄送（owner 自己发的消息不需要抄送给自己）
        sender_address = mail.sender.address
        if sender_address == entity.owner.address:
            return CheckPointResult.success()

        # Build CarbonCopyPayload
        recipient_address = mail.recipient[0].address if mail.recipient else ""

        # 获取名字
        sender_name = entity.resolve_name(sender_address)
        recipient_name = entity.resolve_name(recipient_address)

        # Extract summary from payload
        summary: str | None = None
        if hasattr(message.payload, "text"):
            summary = message.payload.text
        elif isinstance(message.payload, dict) and "text" in message.payload:
            summary = message.payload["text"]

        # Serialize original payload for full forwarding
        original_payload: dict[str, Any] | None = None
        if hasattr(message.payload, "model_dump"):
            original_payload = message.payload.model_dump(mode="json")
        elif isinstance(message.payload, dict):
            original_payload = message.payload

        cc_payload = CarbonCopyPayload(
            original_sender=sender_address,
            original_sender_name=sender_name,
            original_recipient=recipient_address,
            original_recipient_name=recipient_name,
            original_kind=message.kind.value if isinstance(message.kind, MessageKind) else str(message.kind),
            original_message_id=message.message_id,
            direction="inbound",
            timestamp=datetime.utcnow().isoformat(),
            summary=summary,
            original_payload=original_payload,
        )

        cc_message = Message(
            kind=MessageKind.CARBON_COPY,
            payload=cc_payload,
            metadata={"forwarded_from": entity.uid},
        )

        try:
            await entity.send_message(to=entity.owner, message=cc_message)
            logger.debug(
                f"[{entity.name}] 📤 CarbonCopy sent to owner {entity.owner.entity_uid}"
            )
        except Exception as e:
            logger.warning(f"[{entity.name}] Failed to send CarbonCopy to owner: {e}")

        return CheckPointResult.success()


class CallbackCheckPoint(CheckPoint):
    """Execution checkpoint wrapping an async callback."""

    callback: Callable[..., Awaitable[None]] = Field(exclude=True)

    async def execute(
        self, message: Message, entity: Entity, mail: Mail
    ) -> CheckPointResult:
        await self.callback(message)
        return CheckPointResult.handled_success()


class HandlerBridgeCheckPoint(CheckPoint):
    """Bridge: wraps a legacy BaseHandler as execution checkpoint (transitional)."""

    handler: Any = Field(exclude=True)

    async def execute(
        self, message: Message, entity: Entity, mail: Mail
    ) -> CheckPointResult:
        await self.handler.handle(message)
        return CheckPointResult.handled_success()
