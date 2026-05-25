"""Smoke tests for the Trade & Trust protocol layer."""

import asyncio
import time
from pathlib import Path

from fp import EntityKind, Host, Message, MessageKind
from fp.mailbox import Mailbox
from fp.trade import (
    ArbiterCheckPoint,
    ContractActionPayload,
    ContractCreatePayload,
    DeliveryArtifact,
    DeliveryEvidence,
    ExecutionCostReport,
    ContractStatusAckPayload,
    FundingMode,
)
from fp.trade.hashing import sign_receipt, verify_attestation


def test_contract_snapshot_attestation_and_ack_flow():
    async def run_flow():
        host = Host(name="TrustHub")
        arbiter = host.register_entity(name="Arbiter", kind=EntityKind.ARBITER)
        arbiter_cp = arbiter.get_checkpoint(ArbiterCheckPoint)
        alice = host.register_entity(name="Alice", kind=EntityKind.HUMAN)
        bob = host.register_entity(name="Bob", kind=EntityKind.HUMAN)
        arbiter_cp.ledger.deposit(alice.uid, 500)

        alice.add_friend(arbiter.entity_card)
        arbiter.add_friend(alice.entity_card)
        bob.add_friend(arbiter.entity_card)
        arbiter.add_friend(bob.entity_card)

        await alice.send_message(
            to=arbiter.entity_card,
            message=Message(
                kind=MessageKind.CONTRACT_CREATE,
                payload=ContractCreatePayload(
                    party_a=alice.address,
                    party_b=bob.address,
                    party_a_card=alice.entity_card,
                    party_b_card=bob.entity_card,
                    title="Trust smoke",
                    description="minimal trust protocol smoke",
                    amount=120,
                    funding_mode=FundingMode.DIRECT,
                ).model_dump(),
            ),
        )
        await asyncio.sleep(0.05)

        contract = next(iter(arbiter_cp.contracts.values()))
        first_snapshot_hash = contract.current_snapshot_hash
        first_terms_hash = contract.terms_hash

        assert contract.work_session_id == f"contract:{contract.contract_id}"
        assert contract.work_session_name == "Trust smoke"
        assert contract.attestation is not None
        assert verify_attestation(contract.to_snapshot(), arbiter.sign_public_key)
        assert len(contract.snapshot_history) == 1
        assert contract.snapshot_history[0].attestation is not None
        assert contract.snapshot_history[0].attestation.snapshot_hash == first_snapshot_hash

        await bob.send_message(
            to=arbiter.entity_card,
            message=Message(
                kind=MessageKind.CONTRACT_APPROVE,
                payload=ContractActionPayload(
                    contract_id=contract.contract_id,
                    expected_status=contract.status,
                    revision=contract.draft_version,
                    terms_hash=first_terms_hash,
                    source_snapshot_hash=first_snapshot_hash,
                ).model_dump(),
            ),
        )
        await asyncio.sleep(0.05)

        contract = arbiter_cp.contracts[contract.contract_id]
        assert contract.status.value == "active"
        assert contract.current_snapshot_hash != first_snapshot_hash
        assert contract.attestation.prev_snapshot_hash == first_snapshot_hash
        assert verify_attestation(contract.to_snapshot(), arbiter.sign_public_key)
        active_snapshot_hash = contract.current_snapshot_hash
        assert [(a.party_role, a.approved_revision) for a in contract.approvals] == [
            ("party_a", 1),
            ("party_b", 1),
        ]
        assert len(contract.snapshot_history) == 2
        assert contract.snapshot_history[-1].attestation is not None
        assert contract.snapshot_history[-1].attestation.snapshot_hash == active_snapshot_hash
        assert contract.snapshot_history[-1].attestation.prev_snapshot_hash == first_snapshot_hash

        await bob.send_message(
            to=arbiter.entity_card,
            message=Message(
                kind=MessageKind.CONTRACT_COMPLETE,
                payload=ContractActionPayload(
                    contract_id=contract.contract_id,
                    reason="Delivered MVP v1 with a live preview and PR.",
                    expected_status=contract.status,
                    revision=contract.draft_version,
                    terms_hash=contract.terms_hash,
                    source_snapshot_hash=active_snapshot_hash,
                    delivery=DeliveryEvidence(
                        delivery_id="delivery-v1",
                        version="v1.0.0",
                        summary="Vendor portal MVP first delivery",
                        artifacts=[
                            DeliveryArtifact(
                                kind="preview",
                                uri="https://preview.example/v1",
                                label="Preview",
                            ),
                            DeliveryArtifact(
                                kind="commit",
                                uri="git://repo/commit/abc123",
                                label="Commit abc123",
                                digest="sha256:abc123",
                            ),
                        ],
                        source_session_id=contract.work_session_id,
                        produced_by=bob.address,
                        produced_at=time.time(),
                    ),
                    execution_costs=[
                        ExecutionCostReport(
                            report_id="cost-v1",
                            actor=bob.address,
                            phase="implementation",
                            provider="codex",
                            model="gpt-5-codex",
                            input_tokens=1200,
                            output_tokens=450,
                            cost_usd=0.37,
                            runtime_ms=182000,
                            notes="Initial delivery turn",
                            recorded_at=time.time(),
                        ),
                    ],
                ).model_dump(),
            ),
        )
        await asyncio.sleep(0.05)

        contract = arbiter_cp.contracts[contract.contract_id]
        assert contract.status.value == "completing"
        completing_snapshot_hash = contract.current_snapshot_hash
        assert completing_snapshot_hash != active_snapshot_hash
        assert contract.current_delivery is not None
        assert contract.current_delivery.version == "v1.0.0"
        assert len(contract.current_delivery.artifacts) == 2
        assert len(contract.delivery_history) == 1
        assert len(contract.current_execution_costs) == 1
        assert contract.current_execution_costs[0].provider == "codex"
        assert len(contract.cost_history) == 1
        assert contract.snapshot_history[-1].delivery is not None
        assert contract.snapshot_history[-1].delivery.version == "v1.0.0"
        assert len(contract.snapshot_history[-1].execution_costs) == 1

        acked_at = time.time()
        receipt_signature = sign_receipt(
            snapshot_hash_value=contract.current_snapshot_hash,
            status_message_id="status-smoke-1",
            acked_at=acked_at,
            signer_private_key=alice.sign_private_key,
        )
        await alice.send_message(
            to=arbiter.entity_card,
            message=Message(
                kind=MessageKind.CONTRACT_STATUS_ACK,
                payload=ContractStatusAckPayload(
                    contract_id=contract.contract_id,
                    snapshot_hash=contract.current_snapshot_hash,
                    status_message_id="status-smoke-1",
                    acked_at=acked_at,
                    recipient_signature=receipt_signature,
                ).model_dump(),
            ),
        )
        await asyncio.sleep(0.05)

        contract = arbiter_cp.contracts[contract.contract_id]
        assert len(contract.receipts) == 1
        assert contract.receipts[0].recipient.address == alice.address.address
        assert contract.current_snapshot_hash == completing_snapshot_hash
        assert verify_attestation(contract.to_snapshot(), arbiter.sign_public_key)
        assert len(contract.snapshot_history) == 3

    asyncio.run(run_flow())


def test_contract_requires_both_parties_approval_before_activation():
    async def run_flow():
        host = Host(name="TrustHub")
        arbiter = host.register_entity(name="Arbiter", kind=EntityKind.ARBITER)
        arbiter_cp = arbiter.get_checkpoint(ArbiterCheckPoint)
        alice = host.register_entity(name="Alice", kind=EntityKind.HUMAN)
        bob = host.register_entity(name="Bob", kind=EntityKind.HUMAN)
        arbiter_cp.ledger.deposit(alice.uid, 500)

        alice.add_friend(arbiter.entity_card)
        arbiter.add_friend(alice.entity_card)
        bob.add_friend(arbiter.entity_card)
        arbiter.add_friend(bob.entity_card)

        await alice.send_message(
            to=arbiter.entity_card,
            message=Message(
                kind=MessageKind.CONTRACT_CREATE,
                payload=ContractCreatePayload(
                    party_a=alice.address,
                    party_b=bob.address,
                    party_a_card=alice.entity_card,
                    party_b_card=bob.entity_card,
                    title="Trust unilateral approve",
                    description="creator cannot activate without counterparty",
                    amount=120,
                    funding_mode=FundingMode.DIRECT,
                ).model_dump(),
            ),
        )
        await asyncio.sleep(0.05)

        contract = next(iter(arbiter_cp.contracts.values()))
        await alice.send_message(
            to=arbiter.entity_card,
            message=Message(
                kind=MessageKind.CONTRACT_APPROVE,
                payload=ContractActionPayload(
                    contract_id=contract.contract_id,
                    expected_status=contract.status,
                    revision=contract.draft_version,
                    terms_hash=contract.terms_hash,
                    source_snapshot_hash=contract.current_snapshot_hash,
                ).model_dump(),
            ),
        )
        await asyncio.sleep(0.05)

        contract = arbiter_cp.contracts[contract.contract_id]
        assert contract.work_session_id == f"contract:{contract.contract_id}"
        assert contract.status.value == "draft"
        assert [(a.party_role, a.approved_revision) for a in contract.approvals] == [("party_a", 1)]

    asyncio.run(run_flow())


def test_arbiter_rejects_escrow_contract_create():
    async def run_flow():
        host = Host(name="TrustHub")
        arbiter = host.register_entity(name="Arbiter", kind=EntityKind.ARBITER)
        arbiter_cp = arbiter.get_checkpoint(ArbiterCheckPoint)
        alice = host.register_entity(name="Alice", kind=EntityKind.HUMAN)
        bob = host.register_entity(name="Bob", kind=EntityKind.HUMAN)

        alice.add_friend(arbiter.entity_card)
        arbiter.add_friend(alice.entity_card)
        bob.add_friend(arbiter.entity_card)
        arbiter.add_friend(bob.entity_card)

        await alice.send_message(
            to=arbiter.entity_card,
            message=Message(
                kind=MessageKind.CONTRACT_CREATE,
                payload=ContractCreatePayload(
                    party_a=alice.address,
                    party_b=bob.address,
                    party_a_card=alice.entity_card,
                    party_b_card=bob.entity_card,
                    title="Escrow unsupported",
                    description="should be rejected by arbiter",
                    amount=120,
                    funding_mode=FundingMode.ESCROW,
                ).model_dump(),
            ),
        )
        await asyncio.sleep(0.05)

        inbox = Mailbox(alice.uid, Path(alice.mailbox_path)).list_mails(direction="inbound")
        error_messages = [
            entry["mail"]["message"]
            for entry in inbox
            if entry["mail"]["message"]["kind"] == MessageKind.ERROR.value
        ]

        assert len(arbiter_cp.contracts) == 0
        assert error_messages
        latest_error = error_messages[-1]["payload"]
        assert latest_error["error_code"] == "UNSUPPORTED_FUNDING_MODE"
        assert "Supported modes: direct" in latest_error["error_message"]

    asyncio.run(run_flow())
