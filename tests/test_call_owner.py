"""Tests for CallOwner checkpoint mechanism."""

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from fp.core.base import EntityKind, FPAddress
from fp.core.checkpoint import (
    ApprovalResponseCheckPoint,
    CarbonCopyCheckpoint,
    FriendRequestCheckPoint,
    send_approval_status,
)
from fp.mailbox import Mailbox
from fp.entity import Entity, PendingApproval
from fp.host import Host
from fp.mail import Mail
from fp.message import (
    ApprovalRequestPayload,
    ApprovalResponsePayload,
    ApprovalStatusPayload,
    FriendRequestPayload,
    Message,
    MessageKind,
)
from fp.trade import (
    Contract,
    ContractActionPayload,
    ContractAmendPayload,
    ContractApproval,
    ContractApprovalCheckPoint,
    ContractCreatePayload,
    ContractRatePayload,
    ContractStatus,
    ContractStatusPayload,
    FundingMode,
    PayActionPayload,
    PayConfirmReceiptCheckPoint,
    PayMode,
    Payment,
    PaymentMethod,
    PaymentStatus,
)
from fp.trade.checkpoints import (
    request_outbound_contract_action_approval,
    request_outbound_contract_create_approval,
)
from fp.utils import generate_encrypt_keypair, generate_sign_keypair


@pytest.fixture
def temp_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def host(temp_dir):
    return Host(name="TestHost", data_dir=str(temp_dir), bind_host="localhost", port=8000)


def _make_entity(
    host: Host, temp_dir: Path, name: str, owner: FPAddress | None = None
) -> Entity:
    address = FPAddress.create(host.uid)
    sign_pub, sign_priv = generate_sign_keypair()
    enc_pub, dec_priv = generate_encrypt_keypair()
    entity = Entity(
        name=name,
        kind=EntityKind.AGENT,
        address=address,
        sign_public_key=sign_pub,
        sign_private_key=sign_priv,
        encrypt_public_key=enc_pub,
        decrypt_private_key=dec_priv,
        mailbox_path=str(temp_dir / f"mailbox_{name}"),
        host=host,
        owner=owner,
    )
    host.entities[entity.uid] = entity
    return entity


def _make_mail(sender: Entity, recipient: Entity, message: Message) -> Mail:
    return Mail.seal(
        sender=sender.address,
        recipient=recipient.address,
        message=message,
        sign_private_key=sender.sign_private_key,
        encrypt_public_key=None,
    )


def _make_contract_status_message(
    *,
    contract_id: str,
    status: ContractStatus,
    arbiter: Entity,
    party_a: Entity,
    party_b: Entity,
    creator: Entity,
) -> Message:
    contract = Contract(
        contract_id=contract_id,
        party_a=party_a.address,
        party_b=party_b.address,
        creator=creator.address,
        arbiter=arbiter.address,
        title="Build FP UI",
        description="Contract for checkpoint flow",
        amount=128.0,
        funding_mode=FundingMode.ESCROW,
        status=status,
        draft_version=1,
        terms_hash="terms-hash-1",
        current_snapshot_hash="snapshot-hash-1",
        approvals=[
            ContractApproval(
                party_role="party_a",
                approved_revision=1,
                approved_terms_hash="terms-hash-1",
                approved_at=1000.0,
                approved_by=party_a.address,
            )
        ],
        created_at=1000.0,
    )
    payload = ContractStatusPayload(
        contract_id=contract.contract_id,
        status=status,
        contract=contract,
        message="status update",
    )
    return Message(kind=MessageKind.CONTRACT_STATUS, payload=payload.model_dump(mode="json"))


def _make_contract_create_payload(
    *,
    party_a: Entity,
    party_b: Entity,
) -> ContractCreatePayload:
    return ContractCreatePayload(
        party_a=party_a.address,
        party_b=party_b.address,
        title="Owner-approved contract",
        description="Contract needs sender-side approval",
        amount=256.0,
        funding_mode=FundingMode.DIRECT,
    )


def _make_pay_confirm_receipt_message(
    *,
    payer: Entity,
    payee: Entity,
) -> Message:
    payment = Payment(
        payment_id="pay_confirm_receipt_001",
        payer=payer.address,
        payee=payee.address,
        amount=88.0,
        method=PaymentMethod.QR_CODE,
        pay_mode=PayMode.OWNER_PAY,
        status=PaymentStatus.COMPLETED,
        receipt_info="https://pay.example/receipt",
        requested_at=1000.0,
        approved_at=1010.0,
        executed_at=1020.0,
        completed_at=1030.0,
    )
    payload = PayActionPayload(
        payment_id=payment.payment_id,
        payment=payment,
    )
    return Message(
        kind=MessageKind.PAY_CONFIRM_RECEIPT,
        payload=payload.model_dump(mode="json"),
    )


def _sent_messages(mock_send: AsyncMock, kind: MessageKind | None = None) -> list[Message]:
    messages = [call.kwargs["message"] for call in mock_send.await_args_list]
    if kind is None:
        return messages
    return [message for message in messages if message.kind == kind]


class TestPayloadModels:
    def test_approval_request_payload_roundtrip(self):
        p = ApprovalRequestPayload(
            request_id="abc123",
            source_entity_uid="uid1",
            source_entity_name="Agent",
            action_type="require_approval",
            description="test",
            original_kind="friend_request",
            original_payload={"key": "value"},
            available_actions=["approve", "reject"],
        )
        data = p.model_dump()
        restored = ApprovalRequestPayload.model_validate(data)
        assert restored.request_id == "abc123"
        assert restored.available_actions == ["approve", "reject"]

    def test_approval_response_payload_roundtrip(self):
        p = ApprovalResponsePayload(request_id="abc123", action="approve")
        data = p.model_dump()
        restored = ApprovalResponsePayload.model_validate(data)
        assert restored.action == "approve"
        assert restored.input_data is None


class TestFriendRequestAlwaysPass:
    def test_auto_approve_without_owner(self, host, temp_dir):
        agent = _make_entity(host, temp_dir, "Agent")
        sender = _make_entity(host, temp_dir, "Sender")

        cp = FriendRequestCheckPoint(
            name="friend_request_handler",
            order=210,
            message_kinds={MessageKind.FRIEND_REQUEST},
            call_owner_policy="always_pass",
        )

        msg = Message(
            kind=MessageKind.FRIEND_REQUEST,
            payload=FriendRequestPayload(sender_card=sender.entity_card),
        )
        mail = _make_mail(sender, agent, msg)

        with patch.object(Entity, "send_message", new_callable=AsyncMock):
            result = asyncio.run(cp.execute(msg, agent, mail))

        assert result.passed
        assert result.handled
        assert sender.uid in agent.friends


class TestApprovalStatusDelivery:
    def test_self_sent_approval_status_enters_mailbox(self, host, temp_dir):
        """Approval status sent to self should survive unseal and land in inbox."""
        agent = _make_entity(host, temp_dir, "Agent")

        async def run() -> list[dict]:
            await send_approval_status(
                agent,
                agent.entity_card,
                "approval_req_001",
                MessageKind.CONTRACT_CREATE.value,
                "合同创建",
            )
            await asyncio.sleep(0.05)
            return Mailbox(agent.uid, Path(agent.mailbox_path)).list_mails(direction="inbound")

        inbox = asyncio.run(run())
        assert any(
            entry["mail"]["message"]["kind"] == MessageKind.APPROVAL_STATUS.value
            for entry in inbox
        )


class TestFriendRequestAlwaysCallSync:
    def test_auto_reply_defers_friend_request(self, host, temp_dir):
        """Owner-gated friend request should defer immediately and notify both sides."""
        owner = _make_entity(host, temp_dir, "Owner")
        agent = _make_entity(host, temp_dir, "Agent", owner=owner.address)
        sender = _make_entity(host, temp_dir, "Sender")

        cp = FriendRequestCheckPoint(
            name="friend_request_handler",
            order=210,
            message_kinds={MessageKind.FRIEND_REQUEST},
            call_owner_policy="always_call",
        )

        msg = Message(
            kind=MessageKind.FRIEND_REQUEST,
            payload=FriendRequestPayload(sender_card=sender.entity_card),
        )
        mail = _make_mail(sender, agent, msg)

        async def run():
            with patch.object(Entity, "call_owner", new_callable=AsyncMock) as mock_call:
                with patch.object(Entity, "send_message", new_callable=AsyncMock) as mock_send:
                    result = await cp.execute(msg, agent, mail)
            return result, mock_call, mock_send

        result, mock_call, mock_send = asyncio.run(run())
        assert result.passed
        assert result.handled
        assert sender.uid not in agent.friends
        assert len(agent.pending_approvals) == 1
        mock_call.assert_awaited_once()

        status_messages = _sent_messages(mock_send, MessageKind.APPROVAL_STATUS)
        assert len(status_messages) == 1
        assert all(isinstance(message.payload, ApprovalStatusPayload) for message in status_messages)
        assert "你收到一条好友申请" in status_messages[0].payload.message

    def test_auto_reply_pending_request_keeps_original_payload(self, host, temp_dir):
        owner = _make_entity(host, temp_dir, "Owner")
        agent = _make_entity(host, temp_dir, "Agent", owner=owner.address)
        sender = _make_entity(host, temp_dir, "Sender")

        cp = FriendRequestCheckPoint(
            name="friend_request_handler",
            order=210,
            message_kinds={MessageKind.FRIEND_REQUEST},
            call_owner_policy="always_call",
        )

        msg = Message(
            kind=MessageKind.FRIEND_REQUEST,
            payload=FriendRequestPayload(sender_card=sender.entity_card),
        )
        mail = _make_mail(sender, agent, msg)

        async def run():
            with patch.object(Entity, "call_owner", new_callable=AsyncMock):
                with patch.object(Entity, "send_message", new_callable=AsyncMock):
                    return await cp.execute(msg, agent, mail)

        result = asyncio.run(run())
        assert result.passed
        pending = next(iter(agent.pending_approvals.values()))
        assert pending.checkpoint_name == "friend_request_handler"
        assert pending.original_kind == MessageKind.FRIEND_REQUEST.value
        assert pending.original_payload["sender_card"]["entity_uid"] == sender.uid


class TestFriendRequestTimeout:
    def test_call_owner_returns_request_id_immediately(self, host, temp_dir):
        """call_owner_for_approval should return request_id without waiting."""
        owner = _make_entity(host, temp_dir, "Owner")
        agent = _make_entity(host, temp_dir, "Agent", owner=owner.address)
        sender = _make_entity(host, temp_dir, "Sender")

        cp = FriendRequestCheckPoint(
            name="friend_request_handler",
            order=210,
            message_kinds={MessageKind.FRIEND_REQUEST},
            call_owner_policy="always_call",
        )

        msg = Message(
            kind=MessageKind.FRIEND_REQUEST,
            payload=FriendRequestPayload(sender_card=sender.entity_card),
        )
        mail = _make_mail(sender, agent, msg)

        async def run():
            with patch.object(Entity, "send_message", new_callable=AsyncMock):
                with patch.object(Entity, "call_owner", new_callable=AsyncMock):
                    result = await cp.call_owner_for_approval(
                        entity=agent,
                        mail=mail,
                        message=msg,
                        description="test",
                        available_actions=["approve", "reject"],
                    )
            return result

        result = asyncio.run(run())
        assert isinstance(result, str)
        assert len(agent.pending_approvals) == 1
        pending = next(iter(agent.pending_approvals.values()))
        assert pending.checkpoint_name == "friend_request_handler"
        assert pending.original_kind == MessageKind.FRIEND_REQUEST.value


class TestContractApprovalCheckPoint:
    def test_draft_contract_auto_reply_defers(self, host, temp_dir):
        owner = _make_entity(host, temp_dir, "Owner")
        arbiter = _make_entity(host, temp_dir, "Arbiter")
        client = _make_entity(host, temp_dir, "Client")
        agent = _make_entity(host, temp_dir, "Agent", owner=owner.address)
        agent.arbiter = arbiter.address

        cp = ContractApprovalCheckPoint(
            name="contract_approval",
            order=400,
            message_kinds={MessageKind.CONTRACT_STATUS},
            call_owner_policy="always_call",
        )
        msg = _make_contract_status_message(
            contract_id="ctr_sync_approve",
            status=ContractStatus.DRAFT,
            arbiter=arbiter,
            party_a=client,
            party_b=agent,
            creator=client,
        )
        mail = _make_mail(arbiter, agent, msg)

        async def run():
            with patch.object(Entity, "call_owner", new_callable=AsyncMock) as mock_call:
                with patch.object(Entity, "send_message", new_callable=AsyncMock) as mock_send:
                    result = await cp.execute(msg, agent, mail)
            return result, mock_call, mock_send

        result, mock_call, mock_send = asyncio.run(run())
        assert result.passed
        assert result.handled
        mock_call.assert_awaited_once()
        assert len(agent.pending_approvals) == 1
        sent_message = mock_send.await_args.kwargs["message"]
        assert sent_message.kind == MessageKind.APPROVAL_STATUS
        assert "你收到一条合同状态消息" in sent_message.payload.message


class TestPayConfirmReceiptCheckPoint:
    def test_inbound_pay_confirm_receipt_defers_to_owner(self, host, temp_dir):
        owner = _make_entity(host, temp_dir, "Owner")
        payer = _make_entity(host, temp_dir, "Payer", owner=owner.address)
        payee = _make_entity(host, temp_dir, "Payee")

        cp = PayConfirmReceiptCheckPoint(
            name="pay_confirm_receipt_approval",
            order=460,
            message_kinds={MessageKind.PAY_CONFIRM_RECEIPT},
            call_owner_policy="always_call",
        )
        msg = _make_pay_confirm_receipt_message(payer=payer, payee=payee)
        mail = _make_mail(payee, payer, msg)

        async def run():
            with patch.object(Entity, "call_owner", new_callable=AsyncMock) as mock_call:
                with patch.object(Entity, "send_message", new_callable=AsyncMock) as mock_send:
                    result = await cp.execute(msg, payer, mail)
            return result, mock_call, mock_send

        result, mock_call, mock_send = asyncio.run(run())
        assert result.passed
        assert result.handled
        mock_call.assert_awaited_once()
        pending = next(iter(payer.pending_approvals.values()))
        assert pending.checkpoint_name == "pay_confirm_receipt_approval"
        assert pending.original_kind == MessageKind.PAY_CONFIRM_RECEIPT.value
        status_messages = _sent_messages(mock_send, MessageKind.APPROVAL_STATUS)
        assert len(status_messages) == 1
        assert "你收到一条收款确认通知" in status_messages[0].payload.message

    def test_completing_contract_auto_reply_defers(self, host, temp_dir):
        owner = _make_entity(host, temp_dir, "Owner")
        arbiter = _make_entity(host, temp_dir, "Arbiter")
        client = _make_entity(host, temp_dir, "Client", owner=owner.address)
        worker = _make_entity(host, temp_dir, "Worker")
        client.arbiter = arbiter.address

        cp = ContractApprovalCheckPoint(
            name="contract_approval",
            order=400,
            message_kinds={MessageKind.CONTRACT_STATUS},
            call_owner_policy="always_call",
        )
        msg = _make_contract_status_message(
            contract_id="ctr_sync_rework",
            status=ContractStatus.COMPLETING,
            arbiter=arbiter,
            party_a=client,
            party_b=worker,
            creator=client,
        )
        mail = _make_mail(arbiter, client, msg)

        async def run():
            with patch.object(Entity, "call_owner", new_callable=AsyncMock) as mock_call:
                with patch.object(Entity, "send_message", new_callable=AsyncMock) as mock_send:
                    result = await cp.execute(msg, client, mail)
            return result, mock_call, mock_send

        result, mock_call, mock_send = asyncio.run(run())
        assert result.passed
        assert result.handled
        mock_call.assert_awaited_once()
        assert len(client.pending_approvals) == 1
        sent_message = mock_send.await_args.kwargs["message"]
        assert sent_message.kind == MessageKind.APPROVAL_STATUS
        assert "你收到一条合同状态消息" in sent_message.payload.message


class TestOutboundContractCreateApproval:
    def test_contract_create_returns_pending_immediately(self, host, temp_dir):
        owner = _make_entity(host, temp_dir, "Owner")
        creator = _make_entity(host, temp_dir, "Creator", owner=owner.address)
        counterparty = _make_entity(host, temp_dir, "Counterparty")
        arbiter = _make_entity(host, temp_dir, "Arbiter")
        creator.arbiter = arbiter.address
        payload = _make_contract_create_payload(party_a=creator, party_b=counterparty)

        async def run():
            with patch.object(Entity, "call_owner", new_callable=AsyncMock) as mock_call:
                with patch.object(Entity, "send_message", new_callable=AsyncMock) as mock_send:
                    status = await request_outbound_contract_create_approval(creator, payload)
            return status, mock_call, mock_send

        status, mock_call, mock_send = asyncio.run(run())
        assert status == "pending"
        mock_call.assert_awaited_once()
        mock_send.assert_not_awaited()
        pending = next(iter(creator.pending_approvals.values()))
        assert pending.checkpoint_name == "outbound_contract_create_approval"
        assert pending.original_kind == MessageKind.CONTRACT_CREATE.value

    def test_no_owner_sends_contract_create_immediately(self, host, temp_dir):
        creator = _make_entity(host, temp_dir, "Creator", owner=None)
        counterparty = _make_entity(host, temp_dir, "Counterparty")
        arbiter = _make_entity(host, temp_dir, "Arbiter")
        creator.arbiter = arbiter.address
        payload = _make_contract_create_payload(party_a=creator, party_b=counterparty)

        async def run():
            with patch.object(Entity, "send_message", new_callable=AsyncMock) as mock_send:
                status = await request_outbound_contract_create_approval(creator, payload)
            return status, mock_send

        status, mock_send = asyncio.run(run())
        assert status == "sent"
        sent_message = mock_send.await_args.kwargs["message"]
        assert sent_message.kind == MessageKind.CONTRACT_CREATE
        assert sent_message.payload.title == payload.title


class TestOutboundContractActionApproval:
    def test_contract_accept_returns_pending_immediately(self, host, temp_dir):
        owner = _make_entity(host, temp_dir, "Owner")
        client = _make_entity(host, temp_dir, "Client", owner=owner.address)
        arbiter = _make_entity(host, temp_dir, "Arbiter")
        client.arbiter = arbiter.address
        payload = ContractActionPayload(contract_id="ctr_accept_pending", reason="Looks good")

        async def run():
            with patch.object(Entity, "call_owner", new_callable=AsyncMock) as mock_call:
                with patch.object(Entity, "send_message", new_callable=AsyncMock) as mock_send:
                    status = await request_outbound_contract_action_approval(
                        client,
                        MessageKind.CONTRACT_ACCEPT,
                        payload,
                    )
            return status, mock_call, mock_send

        status, mock_call, mock_send = asyncio.run(run())
        assert status == "pending"
        mock_call.assert_awaited_once()
        mock_send.assert_not_awaited()
        pending = next(iter(client.pending_approvals.values()))
        assert pending.checkpoint_name == "outbound_contract_action_approval"
        assert pending.original_kind == MessageKind.CONTRACT_ACCEPT.value

    def test_no_owner_sends_contract_action_immediately(self, host, temp_dir):
        worker = _make_entity(host, temp_dir, "Worker", owner=None)
        arbiter = _make_entity(host, temp_dir, "Arbiter")
        worker.arbiter = arbiter.address
        payload = ContractActionPayload(contract_id="ctr_complete_direct", reason="done")

        async def run():
            with patch.object(Entity, "send_message", new_callable=AsyncMock) as mock_send:
                status = await request_outbound_contract_action_approval(
                    worker,
                    MessageKind.CONTRACT_COMPLETE,
                    payload,
                )
            return status, mock_send

        status, mock_send = asyncio.run(run())
        assert status == "sent"
        sent_message = mock_send.await_args.kwargs["message"]
        assert sent_message.kind == MessageKind.CONTRACT_COMPLETE
        assert sent_message.payload.contract_id == payload.contract_id

    def test_contract_amend_returns_pending_immediately(self, host, temp_dir):
        owner = _make_entity(host, temp_dir, "Owner")
        creator = _make_entity(host, temp_dir, "Creator", owner=owner.address)
        arbiter = _make_entity(host, temp_dir, "Arbiter")
        creator.arbiter = arbiter.address
        payload = ContractAmendPayload(contract_id="ctr_amend_pending", title="Updated title")

        async def run():
            with patch.object(Entity, "call_owner", new_callable=AsyncMock) as mock_call:
                with patch.object(Entity, "send_message", new_callable=AsyncMock) as mock_send:
                    status = await request_outbound_contract_action_approval(
                        creator,
                        MessageKind.CONTRACT_AMEND,
                        payload,
                    )
            return status, mock_call, mock_send

        status, mock_call, mock_send = asyncio.run(run())
        assert status == "pending"
        mock_call.assert_awaited_once()
        mock_send.assert_not_awaited()
        pending = next(iter(creator.pending_approvals.values()))
        assert pending.checkpoint_name == "outbound_contract_action_approval"
        assert pending.original_kind == MessageKind.CONTRACT_AMEND.value

    def test_no_owner_sends_contract_rate_immediately(self, host, temp_dir):
        worker = _make_entity(host, temp_dir, "Worker", owner=None)
        arbiter = _make_entity(host, temp_dir, "Arbiter")
        worker.arbiter = arbiter.address
        payload = ContractRatePayload(contract_id="ctr_rate_direct", rating=5, review="great")

        async def run():
            with patch.object(Entity, "send_message", new_callable=AsyncMock) as mock_send:
                status = await request_outbound_contract_action_approval(
                    worker,
                    MessageKind.CONTRACT_RATE,
                    payload,
                )
            return status, mock_send

        status, mock_send = asyncio.run(run())
        assert status == "sent"
        sent_message = mock_send.await_args.kwargs["message"]
        assert sent_message.kind == MessageKind.CONTRACT_RATE
        assert sent_message.payload.contract_id == payload.contract_id


class TestApprovalResponseCheckPoint:
    def test_async_resume_approve(self, host, temp_dir):
        """Pending approval resumed via ApprovalResponseCheckPoint → friend added."""
        agent = _make_entity(host, temp_dir, "Agent")
        sender = _make_entity(host, temp_dir, "Sender")
        owner = _make_entity(host, temp_dir, "Owner")

        request_id = "test_req_123"
        agent.pending_approvals[request_id] = PendingApproval(
            request_id=request_id,
            original_kind="friend_request",
            original_payload={"sender_card": sender.entity_card.model_dump(mode="json")},
            original_sender_address=sender.address.address,
            original_mail_id="mail_001",
            created_at=1000.0,
            checkpoint_name="friend_request_handler",
        )

        cp = ApprovalResponseCheckPoint(
            name="approval_response_handler",
            order=150,
            message_kinds={MessageKind.APPROVAL_RESPONSE},
        )

        response_msg = Message(
            kind=MessageKind.APPROVAL_RESPONSE,
            payload=ApprovalResponsePayload(request_id=request_id, action="approve"),
        )
        mail = _make_mail(owner, agent, response_msg)

        async def run():
            with patch.object(Entity, "send_message", new_callable=AsyncMock):
                result = await cp.execute(response_msg, agent, mail)
            return result

        result = asyncio.run(run())
        assert result.passed
        assert result.handled
        assert sender.uid in agent.friends
        assert request_id not in agent.pending_approvals

    def test_async_resume_contract_accept(self, host, temp_dir):
        owner = _make_entity(host, temp_dir, "Owner")
        arbiter = _make_entity(host, temp_dir, "Arbiter")
        client = _make_entity(host, temp_dir, "Client")
        worker = _make_entity(host, temp_dir, "Worker")
        client.arbiter = arbiter.address

        request_id = "contract_req_123"
        original_message = _make_contract_status_message(
            contract_id="ctr_async_accept",
            status=ContractStatus.COMPLETING,
            arbiter=arbiter,
            party_a=client,
            party_b=worker,
            creator=client,
        )
        client.pending_approvals[request_id] = PendingApproval(
            request_id=request_id,
            original_kind="contract_status",
            original_payload=original_message.payload,
            original_sender_address=arbiter.address.address,
            original_mail_id="mail_contract_001",
            created_at=1000.0,
            checkpoint_name="contract_approval",
        )

        cp = ApprovalResponseCheckPoint(
            name="approval_response_handler",
            order=150,
            message_kinds={MessageKind.APPROVAL_RESPONSE},
        )

        response_msg = Message(
            kind=MessageKind.APPROVAL_RESPONSE,
            payload=ApprovalResponsePayload(request_id=request_id, action="accept"),
        )
        mail = _make_mail(owner, client, response_msg)

        async def run():
            with patch.object(Entity, "send_message", new_callable=AsyncMock) as mock_send:
                result = await cp.execute(response_msg, client, mail)
            return result, mock_send

        result, mock_send = asyncio.run(run())
        assert result.passed
        assert result.handled
        assert request_id not in client.pending_approvals
        contract_messages = _sent_messages(mock_send, MessageKind.CONTRACT_ACCEPT)
        status_messages = _sent_messages(mock_send, MessageKind.APPROVAL_STATUS)
        assert len(contract_messages) == 1
        assert len(status_messages) == 1

    def test_async_resume_outbound_contract_create(self, host, temp_dir):
        owner = _make_entity(host, temp_dir, "Owner")
        creator = _make_entity(host, temp_dir, "Creator")
        counterparty = _make_entity(host, temp_dir, "Counterparty")
        arbiter = _make_entity(host, temp_dir, "Arbiter")
        creator.arbiter = arbiter.address
        payload = _make_contract_create_payload(party_a=creator, party_b=counterparty)

        request_id = "contract_create_req_123"
        creator.pending_approvals[request_id] = PendingApproval(
            request_id=request_id,
            original_kind="contract_create",
            original_payload=payload.model_dump(mode="json"),
            original_sender_address=creator.address.address,
            original_mail_id="mail_contract_create_001",
            created_at=1000.0,
            checkpoint_name="outbound_contract_create_approval",
        )

        cp = ApprovalResponseCheckPoint(
            name="approval_response_handler",
            order=150,
            message_kinds={MessageKind.APPROVAL_RESPONSE},
        )
        response_msg = Message(
            kind=MessageKind.APPROVAL_RESPONSE,
            payload=ApprovalResponsePayload(request_id=request_id, action="approve"),
        )
        mail = _make_mail(owner, creator, response_msg)

        async def run():
            with patch.object(Entity, "send_message", new_callable=AsyncMock) as mock_send:
                result = await cp.execute(response_msg, creator, mail)
            return result, mock_send

        result, mock_send = asyncio.run(run())
        assert result.passed
        assert result.handled
        assert request_id not in creator.pending_approvals
        contract_messages = _sent_messages(mock_send, MessageKind.CONTRACT_CREATE)
        status_messages = _sent_messages(mock_send, MessageKind.APPROVAL_STATUS)
        assert len(contract_messages) == 1
        assert len(status_messages) == 1

    def test_async_resume_outbound_contract_action(self, host, temp_dir):
        owner = _make_entity(host, temp_dir, "Owner")
        client = _make_entity(host, temp_dir, "Client")
        arbiter = _make_entity(host, temp_dir, "Arbiter")
        client.arbiter = arbiter.address
        payload = ContractActionPayload(contract_id="ctr_resume_accept", reason="ok")

        request_id = "contract_action_req_123"
        client.pending_approvals[request_id] = PendingApproval(
            request_id=request_id,
            original_kind=MessageKind.CONTRACT_ACCEPT.value,
            original_payload=payload.model_dump(mode="json"),
            original_sender_address=client.address.address,
            original_mail_id="mail_contract_action_001",
            created_at=1000.0,
            checkpoint_name="outbound_contract_action_approval",
        )

        cp = ApprovalResponseCheckPoint(
            name="approval_response_handler",
            order=150,
            message_kinds={MessageKind.APPROVAL_RESPONSE},
        )
        response_msg = Message(
            kind=MessageKind.APPROVAL_RESPONSE,
            payload=ApprovalResponsePayload(request_id=request_id, action="approve"),
        )
        mail = _make_mail(owner, client, response_msg)

        async def run():
            with patch.object(Entity, "send_message", new_callable=AsyncMock) as mock_send:
                result = await cp.execute(response_msg, client, mail)
            return result, mock_send

        result, mock_send = asyncio.run(run())
        assert result.passed
        assert result.handled
        assert request_id not in client.pending_approvals
        contract_messages = _sent_messages(mock_send, MessageKind.CONTRACT_ACCEPT)
        status_messages = _sent_messages(mock_send, MessageKind.APPROVAL_STATUS)
        assert len(contract_messages) == 1
        assert len(status_messages) == 1

    def test_async_resume_outbound_contract_amend(self, host, temp_dir):
        owner = _make_entity(host, temp_dir, "Owner")
        creator = _make_entity(host, temp_dir, "Creator")
        arbiter = _make_entity(host, temp_dir, "Arbiter")
        creator.arbiter = arbiter.address
        payload = ContractAmendPayload(contract_id="ctr_resume_amend", amount=512.0)

        request_id = "contract_amend_req_123"
        creator.pending_approvals[request_id] = PendingApproval(
            request_id=request_id,
            original_kind=MessageKind.CONTRACT_AMEND.value,
            original_payload=payload.model_dump(mode="json"),
            original_sender_address=creator.address.address,
            original_mail_id="mail_contract_amend_001",
            created_at=1000.0,
            checkpoint_name="outbound_contract_action_approval",
        )

        cp = ApprovalResponseCheckPoint(
            name="approval_response_handler",
            order=150,
            message_kinds={MessageKind.APPROVAL_RESPONSE},
        )
        response_msg = Message(
            kind=MessageKind.APPROVAL_RESPONSE,
            payload=ApprovalResponsePayload(request_id=request_id, action="approve"),
        )
        mail = _make_mail(owner, creator, response_msg)

        async def run():
            with patch.object(Entity, "send_message", new_callable=AsyncMock) as mock_send:
                result = await cp.execute(response_msg, creator, mail)
            return result, mock_send

        result, mock_send = asyncio.run(run())
        assert result.passed
        assert result.handled
        assert request_id not in creator.pending_approvals
        contract_messages = _sent_messages(mock_send, MessageKind.CONTRACT_AMEND)
        status_messages = _sent_messages(mock_send, MessageKind.APPROVAL_STATUS)
        assert len(contract_messages) == 1
        assert len(status_messages) == 1

    def test_async_resume_pay_confirm_receipt(self, host, temp_dir):
        owner = _make_entity(host, temp_dir, "Owner")
        payer = _make_entity(host, temp_dir, "Payer")
        payee = _make_entity(host, temp_dir, "Payee")
        original_message = _make_pay_confirm_receipt_message(payer=payer, payee=payee)

        request_id = "pay_confirm_receipt_req_123"
        payer.pending_approvals[request_id] = PendingApproval(
            request_id=request_id,
            original_kind=MessageKind.PAY_CONFIRM_RECEIPT.value,
            original_payload=original_message.payload,
            original_sender_address=payee.address.address,
            original_mail_id="mail_pay_confirm_receipt_001",
            original_preview=original_message.extract_text(),
            created_at=1000.0,
            checkpoint_name="pay_confirm_receipt_approval",
        )

        cp = ApprovalResponseCheckPoint(
            name="approval_response_handler",
            order=150,
            message_kinds={MessageKind.APPROVAL_RESPONSE},
        )
        response_msg = Message(
            kind=MessageKind.APPROVAL_RESPONSE,
            payload=ApprovalResponsePayload(request_id=request_id, action="approve"),
        )
        mail = _make_mail(owner, payer, response_msg)

        async def run():
            with patch.object(Entity, "send_message", new_callable=AsyncMock) as mock_send:
                result = await cp.execute(response_msg, payer, mail)
            return result, mock_send

        result, mock_send = asyncio.run(run())
        assert result.passed
        assert result.handled
        assert request_id not in payer.pending_approvals
        status_messages = _sent_messages(mock_send, MessageKind.APPROVAL_STATUS)
        assert len(status_messages) == 1
        assert status_messages[0].payload.status == "approved"

    def test_stale_request_handled_gracefully(self, host, temp_dir):
        """Unknown request_id → handled without error."""
        agent = _make_entity(host, temp_dir, "Agent")
        owner = _make_entity(host, temp_dir, "Owner")

        cp = ApprovalResponseCheckPoint(
            name="approval_response_handler",
            order=150,
            message_kinds={MessageKind.APPROVAL_RESPONSE},
        )

        response_msg = Message(
            kind=MessageKind.APPROVAL_RESPONSE,
            payload=ApprovalResponsePayload(request_id="nonexistent", action="approve"),
        )
        mail = _make_mail(owner, agent, response_msg)

        result = asyncio.run(cp.execute(response_msg, agent, mail))
        assert result.passed
        assert result.handled

    def test_fallback_reconstruction_after_restart(self, host, temp_dir):
        """pending_approvals lost (e.g. server restart) → response carries
        original_kind/original_payload → friend still added."""
        agent = _make_entity(host, temp_dir, "Agent")
        sender = _make_entity(host, temp_dir, "Sender")
        owner = _make_entity(host, temp_dir, "Owner")

        assert len(agent.pending_approvals) == 0

        cp = ApprovalResponseCheckPoint(
            name="approval_response_handler",
            order=150,
            message_kinds={MessageKind.APPROVAL_RESPONSE},
        )

        response_msg = Message(
            kind=MessageKind.APPROVAL_RESPONSE,
            payload=ApprovalResponsePayload(
                request_id="lost_req_456",
                action="approve",
                original_kind="friend_request",
                original_payload={"sender_card": sender.entity_card.model_dump(mode="json")},
            ),
        )
        mail = _make_mail(owner, agent, response_msg)

        async def run():
            with patch.object(Entity, "send_message", new_callable=AsyncMock):
                return await cp.execute(response_msg, agent, mail)

        result = asyncio.run(run())
        assert result.passed
        assert result.handled
        assert sender.uid in agent.friends

    def test_contract_fallback_reconstruction_after_restart(self, host, temp_dir):
        owner = _make_entity(host, temp_dir, "Owner")
        arbiter = _make_entity(host, temp_dir, "Arbiter")
        client = _make_entity(host, temp_dir, "Client")
        worker = _make_entity(host, temp_dir, "Worker")
        client.arbiter = arbiter.address

        cp = ApprovalResponseCheckPoint(
            name="approval_response_handler",
            order=150,
            message_kinds={MessageKind.APPROVAL_RESPONSE},
        )
        original_message = _make_contract_status_message(
            contract_id="ctr_restart_rework",
            status=ContractStatus.COMPLETING,
            arbiter=arbiter,
            party_a=client,
            party_b=worker,
            creator=client,
        )
        response_msg = Message(
            kind=MessageKind.APPROVAL_RESPONSE,
            payload=ApprovalResponsePayload(
                request_id="lost_contract_req",
                action="rework",
                original_kind="contract_status",
                original_payload=original_message.payload,
            ),
        )
        mail = _make_mail(owner, client, response_msg)

        async def run():
            with patch.object(Entity, "send_message", new_callable=AsyncMock) as mock_send:
                result = await cp.execute(response_msg, client, mail)
            return result, mock_send

        result, mock_send = asyncio.run(run())
        assert result.passed
        assert result.handled
        contract_messages = _sent_messages(mock_send, MessageKind.CONTRACT_REWORK)
        status_messages = _sent_messages(mock_send, MessageKind.APPROVAL_STATUS)
        assert len(contract_messages) == 1
        assert len(status_messages) == 1


class TestPendingApprovalsPersistence:
    def test_save_and_load_pending_approvals(self, host, temp_dir):
        """pending_approvals survive Entity save/load cycle."""
        agent = _make_entity(host, temp_dir, "Agent")
        sender = _make_entity(host, temp_dir, "Sender")

        request_id = "persist_test_789"
        agent.pending_approvals[request_id] = PendingApproval(
            request_id=request_id,
            original_kind="friend_request",
            original_payload={"sender_card": sender.entity_card.model_dump(mode="json")},
            original_sender_address=sender.address.address,
            original_mail_id="mail_xyz",
            created_at=1000.0,
            checkpoint_name="friend_request_handler",
        )

        host.save()

        loaded = Entity.load(agent.uid, host)
        assert request_id in loaded.pending_approvals
        pa = loaded.pending_approvals[request_id]
        assert pa.original_kind == "friend_request"
        assert pa.checkpoint_name == "friend_request_handler"
        assert "sender_card" in pa.original_payload


class TestFriendRequestNoOwnerFallback:
    def test_always_call_no_owner_auto_approves(self, host, temp_dir):
        """always_call policy but no owner → auto-approve."""
        agent = _make_entity(host, temp_dir, "Agent", owner=None)
        sender = _make_entity(host, temp_dir, "Sender")

        cp = FriendRequestCheckPoint(
            name="friend_request_handler",
            order=210,
            message_kinds={MessageKind.FRIEND_REQUEST},
            call_owner_policy="always_call",
        )

        msg = Message(
            kind=MessageKind.FRIEND_REQUEST,
            payload=FriendRequestPayload(sender_card=sender.entity_card),
        )
        mail = _make_mail(sender, agent, msg)

        with patch.object(Entity, "send_message", new_callable=AsyncMock):
            result = asyncio.run(cp.execute(msg, agent, mail))

        assert result.passed
        assert result.handled
        assert sender.uid in agent.friends


class TestOwnerFriendRequestAutoApprove:
    def test_owner_request_skips_call_owner(self, host, temp_dir):
        """Owner sends friend request to own agent → auto-approve, no circular approval."""
        owner = _make_entity(host, temp_dir, "Owner")
        agent = _make_entity(host, temp_dir, "Agent", owner=owner.address)

        cp = FriendRequestCheckPoint(
            name="friend_request_handler",
            order=210,
            message_kinds={MessageKind.FRIEND_REQUEST},
            call_owner_policy="always_call",
        )

        msg = Message(
            kind=MessageKind.FRIEND_REQUEST,
            payload=FriendRequestPayload(sender_card=owner.entity_card),
        )
        mail = _make_mail(owner, agent, msg)

        with patch.object(Entity, "send_message", new_callable=AsyncMock):
            with patch.object(Entity, "call_owner", new_callable=AsyncMock) as mock_call:
                result = asyncio.run(cp.execute(msg, agent, mail))

        assert result.passed
        assert result.handled
        assert owner.uid in agent.friends
        mock_call.assert_not_called()


class TestCCSkipsApprovalMessages:
    def test_cc_skips_approval_request(self, host, temp_dir):
        """CarbonCopyCheckpoint returns success() for approval_request."""
        owner = _make_entity(host, temp_dir, "Owner")
        agent = _make_entity(host, temp_dir, "Agent", owner=owner.address)
        sender = _make_entity(host, temp_dir, "Sender")

        cc = CarbonCopyCheckpoint(
            name="carbon_copy_handler",
            order=800,
            message_kinds=set(MessageKind),
        )

        msg = Message(
            kind=MessageKind.APPROVAL_REQUEST,
            payload=ApprovalRequestPayload(
                request_id="x",
                source_entity_uid=agent.uid,
                source_entity_name=agent.name,
                action_type="require_approval",
                description="test",
                original_kind="friend_request",
                original_payload={},
                available_actions=["approve"],
            ),
        )
        mail = _make_mail(sender, agent, msg)

        result = asyncio.run(cc.execute(msg, agent, mail))
        assert result.passed
        assert not result.handled

    def test_cc_skips_approval_response(self, host, temp_dir):
        """CarbonCopyCheckpoint returns success() for approval_response."""
        owner = _make_entity(host, temp_dir, "Owner")
        agent = _make_entity(host, temp_dir, "Agent", owner=owner.address)

        cc = CarbonCopyCheckpoint(
            name="carbon_copy_handler",
            order=800,
            message_kinds=set(MessageKind),
        )

        msg = Message(
            kind=MessageKind.APPROVAL_RESPONSE,
            payload=ApprovalResponsePayload(request_id="x", action="approve"),
        )
        mail = _make_mail(owner, agent, msg)

        result = asyncio.run(cc.execute(msg, agent, mail))
        assert result.passed
        assert not result.handled

    def test_cc_skips_approval_status(self, host, temp_dir):
        owner = _make_entity(host, temp_dir, "Owner")
        agent = _make_entity(host, temp_dir, "Agent", owner=owner.address)

        cc = CarbonCopyCheckpoint(
            name="carbon_copy_handler",
            order=800,
            message_kinds=set(MessageKind),
        )

        msg = Message(
            kind=MessageKind.APPROVAL_STATUS,
            payload=ApprovalStatusPayload(
                request_id="x",
                original_kind=MessageKind.FRIEND_REQUEST.value,
                message="消息已经送达，好友申请进入审批流程。",
            ),
            metadata={"_skip_cc": True},
        )
        mail = _make_mail(agent, agent, msg)

        result = asyncio.run(cc.execute(msg, agent, mail))
        assert result.passed
        assert not result.handled
