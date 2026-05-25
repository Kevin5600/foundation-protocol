from __future__ import annotations

from fp.core.wellknown import FPAddress
from fp.message import MessageKind
from fp.trade import ArbiterCheckPoint, Contract, ContractStatus, FundingMode, ParticipantSnapshot


def test_contract_status_message_contains_contract_context():
    arbiter = FPAddress(address="host:arbiter")
    party_a = FPAddress(address="host:alice")
    party_b = FPAddress(address="host:bob")
    contract = Contract(
        contract_id="contract-123",
        party_a=party_a,
        party_b=party_b,
        creator=party_a,
        arbiter=arbiter,
        title="Build FP UI",
        description="A fuller status message should be emitted",
        amount=128.0,
        funding_mode=FundingMode.DIRECT,
        status=ContractStatus.COMPLETING,
        participant_snapshots=[
            ParticipantSnapshot.from_address(party_a, "party_a", "Alice"),
            ParticipantSnapshot.from_address(party_b, "party_b", "Bob"),
        ],
        created_at=1000.0,
    )
    contract.last_action = "complete"
    contract.last_actor = party_b

    checkpoint = ArbiterCheckPoint(
        name="arbiter",
        order=900,
        message_kinds={MessageKind.CONTRACT_STATUS},
    )

    message = checkpoint._build_contract_status_message(contract, "complete: ")

    assert 'Contract "Build FP UI" (contract-123) update.' in message
    assert "Bob submitted completion." in message
    assert "Current status: completing." in message
    assert "Revision: v1." in message
    assert "Amount: ¥128." in message
