"""Smoke tests for derived Trade & Trust reputation views."""

from __future__ import annotations

import asyncio
import time

from fp import EntityKind, Host, Message, MessageKind
from fp.trade import (
    ArbiterCheckPoint,
    ContractActionPayload,
    ContractCreatePayload,
    ContractRatePayload,
    DeliveryArtifact,
    DeliveryEvidence,
    ExecutionCostReport,
    FundingMode,
    aggregate_vendor_reputation,
    extract_vendor_reputation_event,
)


async def _create_rated_vendor_contract():
    host = Host(name="TrustHub", auto_friend=True)
    arbiter = host.register_entity(name="Arbiter", kind=EntityKind.ARBITER)
    arbiter_cp = arbiter.get_checkpoint(ArbiterCheckPoint)
    assert arbiter_cp is not None
    alice = host.register_entity(name="Alice", kind=EntityKind.HUMAN)
    bob = host.register_entity(name="Bob", kind=EntityKind.HUMAN)

    alice.add_friend(arbiter.entity_card)
    arbiter.add_friend(alice.entity_card)
    bob.add_friend(arbiter.entity_card)
    arbiter.add_friend(bob.entity_card)
    alice.add_friend(bob.entity_card)
    bob.add_friend(alice.entity_card)

    await alice.send_message(
        to=arbiter.entity_card,
        message=Message(
            kind=MessageKind.CONTRACT_CREATE,
            payload=ContractCreatePayload(
                party_a=alice.address,
                party_b=bob.address,
                party_a_card=alice.entity_card,
                party_b_card=bob.entity_card,
                title="Reputation smoke",
                description="vendor reputation smoke contract",
                amount=150,
                funding_mode=FundingMode.DIRECT,
            ).model_dump(),
        ),
    )
    await asyncio.sleep(0.05)

    contract = next(iter(arbiter_cp.contracts.values()))
    await bob.send_message(
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
    await bob.send_message(
        to=arbiter.entity_card,
        message=Message(
            kind=MessageKind.CONTRACT_COMPLETE,
            payload=ContractActionPayload(
                contract_id=contract.contract_id,
                expected_status=contract.status,
                revision=contract.draft_version,
                terms_hash=contract.terms_hash,
                source_snapshot_hash=contract.current_snapshot_hash,
                reason="Delivered v1 with structured evidence",
                delivery=DeliveryEvidence(
                    delivery_id="delivery-v1",
                    version="v1.0.0",
                    summary="First accepted delivery",
                    artifacts=[
                        DeliveryArtifact(
                            kind="preview",
                            uri="https://preview.example/v1",
                            label="Preview v1",
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
                        input_tokens=900,
                        output_tokens=320,
                        cost_usd=0.22,
                        runtime_ms=120000,
                        notes="Initial delivery",
                        recorded_at=time.time(),
                    ),
                ],
            ).model_dump(),
        ),
    )
    await asyncio.sleep(0.05)

    contract = arbiter_cp.contracts[contract.contract_id]
    await alice.send_message(
        to=arbiter.entity_card,
        message=Message(
            kind=MessageKind.CONTRACT_ACCEPT,
            payload=ContractActionPayload(
                contract_id=contract.contract_id,
                expected_status=contract.status,
                revision=contract.draft_version,
                terms_hash=contract.terms_hash,
                source_snapshot_hash=contract.current_snapshot_hash,
                reason="Accepted after review",
            ).model_dump(),
        ),
    )
    await asyncio.sleep(0.05)

    contract = arbiter_cp.contracts[contract.contract_id]
    await alice.send_message(
        to=arbiter.entity_card,
        message=Message(
            kind=MessageKind.CONTRACT_RATE,
            payload=ContractRatePayload(
                contract_id=contract.contract_id,
                rating=5,
                review="Delivered with complete evidence and low friction",
                expected_status=contract.status,
                revision=contract.draft_version,
                terms_hash=contract.terms_hash,
                source_snapshot_hash=contract.current_snapshot_hash,
            ).model_dump(),
        ),
    )
    await asyncio.sleep(0.05)
    return arbiter_cp.contracts[contract.contract_id]


def test_vendor_reputation_is_derived_from_signed_contract_outcome() -> None:
    contract = asyncio.run(_create_rated_vendor_contract())

    event = extract_vendor_reputation_event(contract)
    assert event is not None
    assert event.role == "party_b"
    assert event.outcome == "accepted"
    assert event.rating == 5
    assert event.delivery_count == 1
    assert event.total_cost_usd == 0.22
    assert event.evidence_complete is True
    assert event.signed_snapshot_count >= 4

    profiles = aggregate_vendor_reputation([contract])
    assert len(profiles) == 1

    profile = profiles[0]
    assert profile.role == "party_b"
    assert profile.subject.address == contract.party_b.address
    assert profile.sample_size == 1
    assert profile.overall_score >= 80
    assert profile.quality_score >= 95
    assert profile.reliability_score == 100
    assert profile.integrity_score == 100
    assert profile.recent_events[0].contract_id == contract.contract_id
