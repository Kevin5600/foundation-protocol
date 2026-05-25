"""ArbiterCheckPoint — processes CONTRACT_* and PAY_* messages, drives state machines."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING
from uuid import uuid4

from loguru import logger
from pydantic import Field

from ..core.checkpoint import CheckPoint, CheckPointResult
from ..core.wellknown import EntityCard, FPAddress
from ..message import ErrorPayload, Message, MessageKind
from .authorize import authorize
from .enums import ContractStatus, FundingMode, PaymentMethod, PaymentStatus, PayMode
from .hashing import sign_snapshot, terms_hash, verify_receipt
from .ledger import InsufficientBalance, Ledger
from .models import (
    ArbiterState,
    Contract,
    ContractApproval,
    ContractReceipt,
    DeliveryEvidence,
    ExecutionCostReport,
    ParticipantSnapshot,
    Payment,
)
from .payloads import (
    ContractActionPayload,
    ContractAmendPayload,
    ContractCreatePayload,
    ContractRatePayload,
    ContractStatusAckPayload,
    ContractStatusPayload,
    PayActionPayload,
    PayCollectPayload,
    PayRequestPayload,
    PayStatusPayload,
)
from .state_machine import ContractStateMachine, InvalidTransition, PaymentStateMachine

if TYPE_CHECKING:
    from ..entity import Entity
    from ..mail import Mail

_CONTRACT_PAY_KINDS = {
    MessageKind.CONTRACT_CREATE,
    MessageKind.CONTRACT_AMEND,
    MessageKind.CONTRACT_APPROVE,
    MessageKind.CONTRACT_REJECT,
    MessageKind.CONTRACT_COMPLETE,
    MessageKind.CONTRACT_ACCEPT,
    MessageKind.CONTRACT_REWORK,
    MessageKind.CONTRACT_RATE,
    MessageKind.CONTRACT_CANCEL,
    MessageKind.CONTRACT_DISPUTE,
    MessageKind.CONTRACT_STATUS_ACK,
    MessageKind.PAY_COLLECT,
    MessageKind.PAY_CONFIRM_RECEIPT,
    MessageKind.PAY_CLAIM_COMPLETED,
}


class ArbiterCheckPoint(CheckPoint):
    """Arbiter execution checkpoint — manages contracts, payments, and ledger."""

    supported_funding_modes: set[FundingMode] = Field(default_factory=lambda: {FundingMode.DIRECT})
    ledger: Ledger = Field(default_factory=Ledger)
    contracts: dict[str, Contract] = Field(default_factory=dict)
    payments: dict[str, Payment] = Field(default_factory=dict)

    def save_state(self, host_uid: str) -> None:
        """Persist contracts, payments, and ledger to disk."""
        from ..utils.storage import get_storage_manager
        state = ArbiterState(
            contracts=list(self.contracts.values()),
            payments=list(self.payments.values()),
            ledger=self.ledger.to_snapshot(),
        )
        get_storage_manager().save_arbiter_state(host_uid, state)
        logger.info(
            f"[Arbiter] State saved: {len(state.contracts)} contracts, "
            f"{len(state.payments)} payments"
        )

    def load_state(self, host_uid: str) -> None:
        """Restore contracts, payments, and ledger from disk."""
        from ..utils.storage import get_storage_manager
        raw = get_storage_manager().load_arbiter_state_raw(host_uid)
        if raw is None:
            return
        state = ArbiterState.model_validate_json(raw)
        self.contracts = {c.contract_id: c for c in state.contracts}
        self.payments = {p.payment_id: p for p in state.payments}
        self.ledger = Ledger.from_snapshot(state.ledger)
        logger.info(
            f"[Arbiter] State loaded: {len(self.contracts)} contracts, "
            f"{len(self.payments)} payments"
        )

    async def execute(
        self, message: Message, entity: Entity, mail: Mail
    ) -> CheckPointResult:
        handler_map = {
            MessageKind.CONTRACT_CREATE: self._on_contract_create,
            MessageKind.CONTRACT_AMEND: self._on_contract_amend,
            MessageKind.CONTRACT_APPROVE: self._on_contract_action,
            MessageKind.CONTRACT_REJECT: self._on_contract_action,
            MessageKind.CONTRACT_COMPLETE: self._on_contract_action,
            MessageKind.CONTRACT_ACCEPT: self._on_contract_action,
            MessageKind.CONTRACT_REWORK: self._on_contract_rework,
            MessageKind.CONTRACT_RATE: self._on_contract_rate,
            MessageKind.CONTRACT_CANCEL: self._on_contract_action,
            MessageKind.CONTRACT_DISPUTE: self._on_contract_action,
            MessageKind.CONTRACT_STATUS_ACK: self._on_contract_status_ack,
            MessageKind.PAY_COLLECT: self._on_pay_collect,
            MessageKind.PAY_CONFIRM_RECEIPT: self._on_pay_action,
            MessageKind.PAY_CLAIM_COMPLETED: self._on_pay_action,
        }
        fn = handler_map.get(message.kind)
        if fn:
            await fn(message, entity)
        else:
            logger.warning(f"[Arbiter] Unhandled message kind: {message.kind}")
        return CheckPointResult.handled_success()

    # ==================== Contract ====================

    async def _on_contract_create(self, message: Message, entity: Entity) -> None:
        payload = ContractCreatePayload.model_validate(message.payload)
        sender = self._sender_address(message)
        if sender.address not in {payload.party_a.address, payload.party_b.address}:
            await self._send_protocol_error(entity, sender, "UNAUTHORIZED", "Contract creator must be party_a or party_b")
            return
        if not await self._ensure_supported_funding_mode(entity, sender, payload.funding_mode):
            return

        contract = Contract(
            contract_id=uuid4().hex[:12],
            party_a=payload.party_a,
            party_b=payload.party_b,
            creator=sender,
            arbiter=entity.address,
            title=payload.title,
            description=payload.description,
            amount=payload.amount,
            funding_mode=payload.funding_mode,
            created_at=time.time(),
        )
        contract.work_session_id = payload.work_session_id or f"contract:{contract.contract_id}"
        contract.work_session_name = payload.work_session_name or payload.title
        self._refresh_terms_hash(contract)
        contract.participant_snapshots = self._build_participant_snapshots(entity, payload, contract)
        self._record_approval(contract, sender, message.metadata.get("mail_id"))
        self._stamp_action(contract, "create", sender, None)
        self._sign_contract(entity, contract)
        self.contracts[contract.contract_id] = contract
        logger.info(f"[Arbiter] Contract {contract.contract_id} created: {contract.title}")
        await self._notify_parties(entity, contract, "Contract created")

    async def _on_contract_amend(self, message: Message, entity: Entity) -> None:
        payload = ContractAmendPayload.model_validate(message.payload)
        contract = self._get_contract(payload.contract_id)
        sender = self._sender_address(message)
        if not await self._validate_contract_message(entity, contract, payload, "amend", sender):
            return

        ContractStateMachine.transition(contract.status, "amend")
        if payload.title is not None:
            contract.title = payload.title
        if payload.description is not None:
            contract.description = payload.description
        if payload.amount is not None:
            contract.amount = payload.amount
        if payload.funding_mode is not None:
            if not await self._ensure_supported_funding_mode(entity, sender, payload.funding_mode):
                return
            contract.funding_mode = payload.funding_mode
        contract.draft_version += 1
        self._refresh_terms_hash(contract)
        contract.approvals = []
        self._record_approval(contract, sender, message.metadata.get("mail_id"))
        self._stamp_action(contract, "amend", sender, None)
        self._sign_contract(entity, contract)

        logger.info(f"[Arbiter] Contract {contract.contract_id} amended to v{contract.draft_version}")
        await self._notify_parties(entity, contract, f"Amended to v{contract.draft_version}")

    async def _on_contract_action(self, message: Message, entity: Entity) -> None:
        payload = ContractActionPayload.model_validate(message.payload)
        contract = self._get_contract(payload.contract_id)

        action = self._kind_to_action(message.kind)
        sender = self._sender_address(message)
        if not await self._validate_contract_message(entity, contract, payload, action, sender):
            return

        if action == "approve":
            self._record_approval(contract, sender, message.metadata.get("mail_id"))
            if not self._has_current_approvals(contract):
                self._stamp_action(contract, action, sender, payload.reason)
                self._sign_contract(entity, contract)
                logger.info(
                    f"[Arbiter] Contract {contract.contract_id}: approval recorded, "
                    "waiting for counterparty"
                )
                await self._notify_parties(entity, contract, "Approval recorded, waiting for counterparty")
                return
        if action == "complete":
            self._record_delivery(contract, payload, sender, message.metadata.get("mail_id"))
        new_status = ContractStateMachine.transition(contract.status, action)
        old_status = contract.status
        contract.status = new_status
        self._stamp_time(contract, new_status)
        self._stamp_action(contract, action, sender, payload.reason)

        logger.info(
            f"[Arbiter] Contract {contract.contract_id}: "
            f"{old_status.value} → {new_status.value} ({action})"
        )

        if new_status == ContractStatus.PENDING:
            await self._on_pending(entity, contract)
        elif new_status == ContractStatus.SETTLING:
            await self._on_settling(entity, contract)
        self._sign_contract(entity, contract)

        await self._notify_parties(entity, contract, f"{action}: {payload.reason or ''}")

    async def _on_contract_rework(self, message: Message, entity: Entity) -> None:
        payload = ContractActionPayload.model_validate(message.payload)
        contract = self._get_contract(payload.contract_id)
        sender = self._sender_address(message)
        if not await self._validate_contract_message(entity, contract, payload, "rework", sender):
            return

        if contract.rework_count >= contract.max_rework_count:
            contract.status = ContractStatus.DISPUTED
            self._stamp_action(contract, "rework_limit_exceeded", sender, payload.reason)
            self._sign_contract(entity, contract)
            logger.info(f"[Arbiter] Contract {contract.contract_id}: rework limit exceeded → DISPUTED")
            await self._notify_parties(entity, contract, "Rework limit exceeded")
            return

        new_status = ContractStateMachine.transition(contract.status, "rework")
        contract.status = new_status
        contract.rework_count += 1
        self._stamp_action(contract, "rework", sender, payload.reason)
        self._sign_contract(entity, contract)
        logger.info(
            f"[Arbiter] Contract {contract.contract_id}: "
            f"rework #{contract.rework_count}/{contract.max_rework_count}"
        )
        await self._notify_parties(entity, contract, f"Rework requested: {payload.reason or ''}")

    async def _on_contract_rate(self, message: Message, entity: Entity) -> None:
        payload = ContractRatePayload.model_validate(message.payload)
        contract = self._get_contract(payload.contract_id)
        sender = self._sender_address(message)
        if not await self._validate_contract_message(entity, contract, payload, "rate", sender):
            return

        if contract.status not in (ContractStatus.SETTLING, ContractStatus.SETTLED):
            logger.warning(f"[Arbiter] Cannot rate contract in {contract.status.value}")
            return

        contract.rating = payload.rating
        contract.review = payload.review
        contract.rated_by = sender
        contract.rated_at = time.time()
        self._stamp_action(contract, "rate", sender, None)
        self._sign_contract(entity, contract)
        logger.info(f"[Arbiter] Contract {contract.contract_id}: rated {payload.rating}/5")

    async def _on_contract_status_ack(self, message: Message, entity: Entity) -> None:
        payload = ContractStatusAckPayload.model_validate(message.payload)
        contract = self._get_contract(payload.contract_id)
        sender = self._sender_address(message)

        if payload.snapshot_hash != contract.current_snapshot_hash:
            await self._send_protocol_error(entity, sender, "STALE_SNAPSHOT", "ACK snapshot_hash does not match current contract snapshot")
            return

        receipt = ContractReceipt(
            recipient=sender,
            status_message_id=payload.status_message_id,
            snapshot_hash=payload.snapshot_hash,
            acked_at=payload.acked_at,
            recipient_signature=payload.recipient_signature,
        )
        snapshot = contract.to_snapshot()
        if not verify_receipt(receipt, snapshot):
            await self._send_protocol_error(entity, sender, "INVALID_RECEIPT", "CONTRACT_STATUS_ACK signature verification failed")
            return

        contract.receipts = [
            r for r in contract.receipts
            if not (
                r.recipient.address == receipt.recipient.address
                and r.snapshot_hash == receipt.snapshot_hash
                and r.status_message_id == receipt.status_message_id
            )
        ]
        contract.receipts.append(receipt)
        logger.info(f"[Arbiter] Contract {contract.contract_id}: observed by {sender.entity_uid}")

    async def _on_pending(self, entity: Entity, contract: Contract) -> None:
        if contract.funding_mode == FundingMode.ESCROW:
            try:
                self.ledger.freeze(contract.party_a.entity_uid, contract.amount)
                logger.info(
                    f"[Arbiter] Froze {contract.amount} from {contract.party_a.entity_uid}"
                )
            except InsufficientBalance as e:
                contract.status = ContractStatus.CANCELLED
                contract.cancelled_at = time.time()
                self._stamp_action(contract, "escrow_insufficient_balance", entity.address, str(e))
                logger.warning(f"[Arbiter] Insufficient balance: {e}")
                return

        contract.status = ContractStatus.ACTIVE
        contract.activated_at = time.time()
        self._stamp_action(contract, "activate", entity.address, None)
        logger.info(f"[Arbiter] Contract {contract.contract_id}: PENDING → ACTIVE")

    async def _on_settling(self, entity: Entity, contract: Contract) -> None:
        contract.settling_at = time.time()
        if contract.funding_mode == FundingMode.ESCROW:
            self.ledger.escrow_transfer(
                contract.party_a.entity_uid,
                contract.party_b.entity_uid,
                contract.amount,
            )
            payment = Payment(
                payment_id=uuid4().hex[:12],
                contract_id=contract.contract_id,
                payer=contract.party_a,
                payee=contract.party_b,
                amount=contract.amount,
                method=PaymentMethod.ESCROW,
                pay_mode=PayMode.ENTITY_PAY,
                status=PaymentStatus.COMPLETED,
                receipt_info="escrow_internal",
                requested_at=time.time(),
                completed_at=time.time(),
            )
            self.payments[payment.payment_id] = payment
            contract.status = ContractStatus.SETTLED
            contract.settled_at = time.time()
            self._stamp_action(contract, "settle", entity.address, None)
            logger.info(
                f"[Arbiter] ESCROW settled: {contract.party_a.entity_uid} → "
                f"{contract.party_b.entity_uid} ({contract.amount})"
            )

    # ==================== Pay ====================

    async def _on_pay_collect(self, message: Message, entity: Entity) -> None:
        payload = PayCollectPayload.model_validate(message.payload)
        sender = self._sender_address(message)

        is_deposit = sender.address == payload.payer.address
        payee = entity.address if is_deposit else sender

        payment = Payment(
            payment_id=payload.payment_id or uuid4().hex[:12],
            contract_id=payload.contract_id,
            payer=payload.payer,
            payee=payee,
            amount=payload.amount,
            method=payload.method,
            pay_mode=PayMode.OWNER_PAY,
            status=PaymentStatus.REQUESTED,
            receipt_info=payload.receipt_info,
            requested_at=time.time(),
        )
        self.payments[payment.payment_id] = payment

        payment.status = PaymentStateMachine.transition(payment.status, "auto_approve")
        payment.approved_at = time.time()
        payment.status = PaymentStateMachine.transition(payment.status, "execute")
        payment.executed_at = time.time()
        payment.status = PaymentStateMachine.transition(payment.status, "confirm")

        logger.info(f"[Arbiter] Payment {payment.payment_id}: REQUESTED → CONFIRMING")
        await self._notify_pay_request(entity, payment)

    async def _on_pay_action(self, message: Message, entity: Entity) -> None:
        payload = PayActionPayload.model_validate(message.payload)
        sender = self._sender_address(message)
        action = {
            MessageKind.PAY_CONFIRM_RECEIPT: "confirm_receipt",
            MessageKind.PAY_CLAIM_COMPLETED: "claim_completed",
        }[message.kind]

        payment = await self._get_or_register_payment(entity, payload, sender)
        if payment is None:
            return

        if action == "confirm_receipt" and sender.address != payment.payee.address:
            await self._send_protocol_error(entity, sender, "UNAUTHORIZED", "Only payee can confirm receipt")
            return

        if payment.status == PaymentStatus.COMPLETED:
            return

        new_status = PaymentStateMachine.transition(payment.status, action)
        payment.status = new_status
        payment.completed_at = time.time()

        logger.info(f"[Arbiter] Payment {payment.payment_id}: → {new_status.value}")

        if new_status == PaymentStatus.COMPLETED:
            if payment.payee.address == entity.address.address:
                self.ledger.deposit(payment.payer.entity_uid, payment.amount)
                logger.info(
                    f"[Arbiter] Deposit: {payment.payer.entity_uid} +{payment.amount}"
                )
            elif payment.contract_id:
                contract = self.contracts.get(payment.contract_id)
                if contract and contract.status == ContractStatus.SETTLING:
                    contract.status = ContractStatus.SETTLED
                    contract.settled_at = time.time()
                    self._stamp_action(contract, "settle", entity.address, None)
                    self._sign_contract(entity, contract)
                    logger.info(
                        f"[Arbiter] Contract {contract.contract_id}: "
                        f"SETTLING → SETTLED (payment done)"
                    )
                    await self._notify_parties(entity, contract, "Payment completed, contract settled")
            await self._broadcast_pay_completed(entity, payment)

    async def _broadcast_pay_completed(self, entity: Entity, payment: Payment) -> None:
        status_payload = PayStatusPayload(
            payment_id=payment.payment_id,
            status=payment.status,
            payment=payment,
            message="Payment completed",
        )
        msg = Message(kind=MessageKind.PAY_COMPLETED, payload=status_payload.model_dump())
        for addr in (payment.payer, payment.payee):
            if addr.address == entity.address.address:
                continue
            await self._send_outbound_message(entity, addr, msg)

    async def _get_or_register_payment(
        self, entity: Entity, payload: PayActionPayload, sender: FPAddress
    ) -> Payment | None:
        """Return existing payment, or register one from payload (DIRECT flow). None on error."""
        payment = self.payments.get(payload.payment_id)
        if payment is not None:
            return payment
        if payload.payment is None:
            await self._send_protocol_error(
                entity, sender, "PAYMENT_NOT_FOUND",
                f"Payment {payload.payment_id} not found and no payment data provided",
            )
            return None
        payment = payload.payment
        payment.status = PaymentStatus.CONFIRMING
        self.payments[payment.payment_id] = payment
        logger.info(f"[Arbiter] Payment {payment.payment_id}: registered from direct flow")
        return payment

    # ==================== Helpers ====================

    def _get_contract(self, contract_id: str) -> Contract:
        contract = self.contracts.get(contract_id)
        if not contract:
            raise ValueError(f"Contract {contract_id} not found")
        return contract

    @staticmethod
    def _sender_address(message: Message):
        addr = message.metadata.get("sender_address", "unknown:unknown")
        return FPAddress(address=addr)

    @staticmethod
    def _kind_to_action(kind: MessageKind) -> str:
        return {
            MessageKind.CONTRACT_APPROVE: "approve",
            MessageKind.CONTRACT_REJECT: "reject",
            MessageKind.CONTRACT_COMPLETE: "complete",
            MessageKind.CONTRACT_ACCEPT: "accept",
            MessageKind.CONTRACT_CANCEL: "cancel",
            MessageKind.CONTRACT_DISPUTE: "dispute",
        }[kind]

    @staticmethod
    def _stamp_time(contract: Contract, status: ContractStatus) -> None:
        now = time.time()
        stamps = {
            ContractStatus.PENDING: "approved_at",
            ContractStatus.ACTIVE: "activated_at",
            ContractStatus.COMPLETING: "completed_at",
            ContractStatus.SETTLING: "settling_at",
            ContractStatus.SETTLED: "settled_at",
            ContractStatus.CANCELLED: "cancelled_at",
        }
        attr = stamps.get(status)
        if attr:
            setattr(contract, attr, now)

    @staticmethod
    def _resolve_recipient(entity: Entity, address: FPAddress) -> FPAddress | EntityCard:
        """Resolve one outbound recipient, preferring friend cards when available."""
        return entity.friends.get(address.entity_uid) or address

    async def _send_outbound_message(
        self,
        entity: Entity,
        recipient: FPAddress,
        message: Message,
    ) -> None:
        """Send one arbiter message even when friendship metadata is missing."""
        await entity.send_message(self._resolve_recipient(entity, recipient), message)

    async def _notify_parties(self, entity: Entity, contract: Contract, note: str) -> None:
        snapshot = contract.to_snapshot()
        status_payload = ContractStatusPayload(
            contract_id=contract.contract_id,
            status=contract.status,
            contract=contract,
            snapshot=snapshot,
            message=self._build_contract_status_message(contract, note),
        )
        msg = Message(kind=MessageKind.CONTRACT_STATUS, payload=status_payload.model_dump())

        for party_addr in (contract.party_a, contract.party_b):
            if party_addr == entity.address:
                continue
            await self._send_outbound_message(entity, party_addr, msg)

    def _build_contract_status_message(self, contract: Contract, note: str | None) -> str:
        summary = self._normalize_contract_status_note(contract, note)
        if summary is None:
            summary = self._build_contract_status_summary(contract)

        message = (
            f'Contract "{contract.title}" ({contract.contract_id}) update. '
            f"{summary} "
            f"Current status: {contract.status.value}. "
            f"Revision: v{contract.draft_version}. "
            f"Amount: ¥{contract.amount:g}."
        )
        return " ".join(message.split())

    def _normalize_contract_status_note(
        self, contract: Contract, note: str | None,
    ) -> str | None:
        if note is None:
            return None

        normalized = " ".join(note.strip().split())
        if not normalized:
            return None

        trailing_trimmed = normalized.rstrip(":").strip()
        if trailing_trimmed == contract.last_action:
            return None
        return normalized if normalized.endswith(".") else f"{normalized}."

    def _build_contract_status_summary(self, contract: Contract) -> str:
        action = contract.last_action
        actor = self._resolve_participant_name(contract, contract.last_actor)

        action_summary_map = {
            "create": "The contract was created.",
            "activate": "The contract has been activated.",
            "approve": self._build_actor_summary(actor, "approved the contract"),
            "reject": self._build_actor_summary(actor, "rejected the contract"),
            "complete": self._build_actor_summary(actor, "submitted completion"),
            "accept": self._build_actor_summary(actor, "accepted the delivery"),
            "rework": self._build_actor_summary(actor, "requested rework"),
            "settle": "The contract has been settled.",
            "cancel": self._build_actor_summary(actor, "cancelled the contract"),
            "dispute": self._build_actor_summary(actor, "raised a dispute"),
            "amend": self._build_actor_summary(actor, f"amended the contract to v{contract.draft_version}"),
            "rate": self._build_actor_summary(actor, "rated the contract"),
        }

        summary = action_summary_map.get(action, "The contract state changed.")
        if contract.last_reason:
            return f"{summary.rstrip('.')} Reason: {contract.last_reason}."
        return summary

    @staticmethod
    def _build_actor_summary(actor: str | None, action_text: str) -> str:
        if actor:
            return f"{actor} {action_text}."
        return f"Someone {action_text}."

    def _resolve_participant_name(
        self, contract: Contract, actor: FPAddress | None,
    ) -> str | None:
        if actor is None:
            return None
        for participant in contract.participant_snapshots:
            if participant.address.address == actor.address:
                return participant.display_name
        return actor.entity_uid or None

    async def _notify_pay_request(self, entity: Entity, payment: Payment) -> None:
        payload = PayRequestPayload(
            payment_id=payment.payment_id,
            contract_id=payment.contract_id or "",
            payee=payment.payee,
            amount=payment.amount,
            method=payment.method,
            receipt_info=payment.receipt_info,
        )
        msg = Message(kind=MessageKind.PAY_REQUEST, payload=payload.model_dump())
        await self._send_outbound_message(entity, payment.payer, msg)

    def _refresh_terms_hash(self, contract: Contract) -> None:
        terms = contract.terms()
        terms.terms_hash = ""
        contract.terms_hash = terms_hash(terms)

    def _sign_contract(self, entity: Entity, contract: Contract) -> None:
        snapshot = contract.to_snapshot()
        snapshot.attestation = None
        attestation = sign_snapshot(
            snapshot,
            signer_private_key=entity.sign_private_key,
            signer_address=entity.address,
            prev_snapshot_hash=contract.current_snapshot_hash,
        )
        contract.prev_snapshot_hash = contract.current_snapshot_hash
        contract.current_snapshot_hash = attestation.snapshot_hash
        contract.arbiter_signature = attestation.signature
        contract.arbiter_signature_alg = attestation.signature_alg
        contract.attestation = attestation
        signed_snapshot = contract.to_snapshot()
        if (
            not contract.snapshot_history
            or contract.snapshot_history[-1].attestation is None
            or contract.snapshot_history[-1].attestation.snapshot_hash != attestation.snapshot_hash
        ):
            contract.snapshot_history.append(signed_snapshot)

    def _build_participant_snapshots(
        self,
        entity: Entity,
        payload: ContractCreatePayload,
        contract: Contract,
    ) -> list[ParticipantSnapshot]:
        return [
            self._participant_snapshot(entity, payload.party_a, "party_a", payload.party_a_card),
            self._participant_snapshot(entity, payload.party_b, "party_b", payload.party_b_card),
            ParticipantSnapshot.from_card(entity.entity_card, "arbiter"),
        ]

    def _participant_snapshot(
        self,
        entity: Entity,
        address: FPAddress,
        role: str,
        card: EntityCard | None,
    ) -> ParticipantSnapshot:
        if card is not None and card.address.address == address.address:
            return ParticipantSnapshot.from_card(card, role)
        friend = entity.friends.get(address.entity_uid)
        if friend is not None and friend.address.address == address.address:
            return ParticipantSnapshot.from_card(friend, role)
        return ParticipantSnapshot.from_address(address, role)

    def _role_for(self, contract: Contract, sender: FPAddress) -> str | None:
        if sender.address == contract.party_a.address:
            return "party_a"
        if sender.address == contract.party_b.address:
            return "party_b"
        if sender.address == contract.arbiter.address:
            return "arbiter"
        return None

    def _record_approval(self, contract: Contract, sender: FPAddress, mail_id: str | None) -> None:
        role = self._role_for(contract, sender)
        if role not in {"party_a", "party_b"}:
            return
        contract.approvals = [
            a for a in contract.approvals
            if not (a.party_role == role and a.approved_revision == contract.draft_version)
        ]
        contract.approvals.append(
            ContractApproval(
                party_role=role,
                approved_revision=contract.draft_version,
                approved_terms_hash=contract.terms_hash,
                approved_at=time.time(),
                approved_by=sender,
                source_mail_id=mail_id,
            )
        )

    def _record_delivery(
        self,
        contract: Contract,
        payload: ContractActionPayload,
        sender: FPAddress,
        mail_id: str | None,
    ) -> None:
        now = time.time()
        delivery = payload.delivery
        if delivery is None:
            delivery = DeliveryEvidence(
                delivery_id=uuid4().hex[:12],
                version=f"delivery-{len(contract.delivery_history) + 1}",
                summary=payload.reason or "Delivery submitted",
                source_session_id=contract.work_session_id,
                source_message_id=mail_id,
                produced_by=sender,
                produced_at=now,
            )
        else:
            updates: dict[str, object] = {}
            if not delivery.delivery_id:
                updates["delivery_id"] = uuid4().hex[:12]
            if delivery.produced_by.address != sender.address:
                updates["produced_by"] = sender
            if not delivery.produced_at:
                updates["produced_at"] = now
            if delivery.source_session_id is None and contract.work_session_id is not None:
                updates["source_session_id"] = contract.work_session_id
            if delivery.source_message_id is None and mail_id is not None:
                updates["source_message_id"] = mail_id
            if updates:
                delivery = delivery.model_copy(update=updates)

        normalized_costs: list[ExecutionCostReport] = []
        for index, report in enumerate(payload.execution_costs):
            report_id = report.report_id or f"{contract.contract_id}-cost-{len(contract.cost_history) + index + 1}"
            updated = report.model_copy(
                update={
                    "report_id": report_id,
                    "actor": sender if report.actor.address != sender.address else report.actor,
                }
            )
            normalized_costs.append(updated)

        contract.current_delivery = delivery
        contract.delivery_history.append(delivery)
        contract.current_execution_costs = normalized_costs
        contract.cost_history.extend(normalized_costs)

    @staticmethod
    def _has_current_approvals(contract: Contract) -> bool:
        current_roles = {
            approval.party_role
            for approval in contract.approvals
            if (
                approval.approved_revision == contract.draft_version
                and approval.approved_terms_hash == contract.terms_hash
            )
        }
        return {"party_a", "party_b"}.issubset(current_roles)

    def _stamp_action(
        self,
        contract: Contract,
        action: str,
        actor: FPAddress,
        reason: str | None,
    ) -> None:
        contract.last_action = action
        contract.last_actor = actor
        contract.last_reason = reason
        contract.last_action_at = time.time()

    async def _validate_contract_message(
        self,
        entity: Entity,
        contract: Contract,
        payload,
        action: str,
        sender: FPAddress,
    ) -> bool:
        auth = authorize(action, sender, contract)
        if not auth.allowed:
            await self._send_protocol_error(entity, sender, "UNAUTHORIZED", auth.reason or "unauthorized contract action")
            return False

        checks = {
            "source_snapshot_hash": (getattr(payload, "source_snapshot_hash", None), contract.current_snapshot_hash),
            "terms_hash": (getattr(payload, "terms_hash", None), contract.terms_hash),
            "expected_status": (getattr(payload, "expected_status", None), contract.status),
            "revision": (getattr(payload, "revision", None), contract.draft_version),
        }
        for field, (actual, expected) in checks.items():
            if actual is None:
                continue
            if hasattr(actual, "value"):
                actual = actual.value
            if hasattr(expected, "value"):
                expected = expected.value
            if actual != expected:
                await self._send_protocol_error(
                    entity,
                    sender,
                    "CONTRACT_PRECONDITION_FAILED",
                    f"{field} mismatch: expected {expected}, got {actual}",
                )
                return False
        return True

    async def _ensure_supported_funding_mode(
        self,
        entity: Entity,
        sender: FPAddress,
        funding_mode: FundingMode,
    ) -> bool:
        if funding_mode in self.supported_funding_modes:
            return True

        supported = ", ".join(mode.value for mode in sorted(self.supported_funding_modes, key=lambda item: item.value))
        await self._send_protocol_error(
            entity,
            sender,
            "UNSUPPORTED_FUNDING_MODE",
            f"Funding mode '{funding_mode.value}' is not supported. Supported modes: {supported}",
        )
        logger.info(
            f"[Arbiter] Rejected funding_mode={funding_mode.value}; supported={supported}"
        )
        return False

    async def _send_protocol_error(self, entity: Entity, recipient: FPAddress, error_code: str, message: str) -> None:
        payload = ErrorPayload(error_code=error_code, error_message=message)
        await self._send_outbound_message(
            entity,
            recipient,
            Message(kind=MessageKind.ERROR, payload=payload.model_dump()),
        )
