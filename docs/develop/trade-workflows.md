# Trade Workflows

A **contract** in Foundation Protocol is a service agreement between two entities — `party_a` (the requester / payer) and `party_b` (the provider / payee) — driven through its lifecycle by an `Arbiter` entity. This page shows how to run the workflow end-to-end against the built-in `ArbiterCheckPoint`.

For the conceptual model, see [Trade & Trust](../trade-and-trust/index.md). For the formal state machine and message kinds, see [Contract Lifecycle](../trade-and-trust/lifecycle.md).

## Setup — an Arbiter and two parties

```python
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

    # Pre-fund both ledger accounts (Arbiter manages a virtual balance)
    arbiter_cp.ledger.deposit(alice.uid, 1000)
    arbiter_cp.ledger.deposit(bob.uid, 200)
```

In `ESCROW` mode the Arbiter holds a virtual ledger and moves balances internally at settlement. `DIRECT` mode delegates payment to an external rail — the Arbiter only provides trust backing.

## The happy path

A complete `ESCROW` contract walks through six messages. The Arbiter's state machine validates each transition and notifies both parties.

### 1. Create

`Party A` (or `Party B`) authors the contract and sends it to the Arbiter:

```python
await alice.send_message(
    to=arbiter.entity_card,
    message=Message(
        kind=MessageKind.CONTRACT_CREATE,
        payload=ContractCreatePayload(
            party_a=alice.address,
            party_b=bob.address,
            title="Market research report",
            description="Q2 SEA market research, including competitor analysis.",
            amount=200,
            funding_mode=FundingMode.ESCROW,
        ).model_dump(),
    ),
)
```

The Arbiter creates the contract in `DRAFT` and notifies Bob for approval.

### 2. Approve

```python
contract_id = next(iter(arbiter_cp.contracts))

await bob.send_message(
    to=arbiter.entity_card,
    message=Message(
        kind=MessageKind.CONTRACT_APPROVE,
        payload=ContractActionPayload(contract_id=contract_id).model_dump(),
    ),
)
```

The Arbiter checks Alice's balance, freezes the amount (`ESCROW`), and transitions the contract to `ACTIVE`.

### 3. Execute

Once active, the Arbiter steps aside and Alice and Bob communicate directly via normal `INVOKE` messages. The Arbiter sees nothing of the execution — it only re-enters when a state-changing message arrives.

### 4. Complete

Bob signals that delivery is done:

```python
await bob.send_message(
    to=arbiter.entity_card,
    message=Message(
        kind=MessageKind.CONTRACT_COMPLETE,
        payload=ContractActionPayload(contract_id=contract_id).model_dump(),
    ),
)
```

State becomes `COMPLETING` and the Arbiter asks Alice to accept.

### 5. Accept and rate

```python
await alice.send_message(
    to=arbiter.entity_card,
    message=Message(
        kind=MessageKind.CONTRACT_ACCEPT,
        payload=ContractActionPayload(contract_id=contract_id).model_dump(),
    ),
)

await alice.send_message(
    to=arbiter.entity_card,
    message=Message(
        kind=MessageKind.CONTRACT_RATE,
        payload=ContractRatePayload(
            contract_id=contract_id,
            rating=5,
            review="Solid work.",
        ).model_dump(),
    ),
)
```

`ACCEPT` moves to `SETTLING`. `RATE` records Alice's review (Party A rates Party B only — see [Trust Protocol](../trade-and-trust/trust-protocol.md) for the rationale).

### 6. Settle

In `ESCROW` mode the Arbiter performs the internal transfer automatically and the contract advances to `SETTLED`. In `DIRECT` mode the Arbiter sends Alice a `PAY_REQUEST`; payment is then handled by the external rail and the contract waits for the receipt before settling.

The full `SETTLED` snapshot is signed by the Arbiter (SHA256) and becomes the immutable audit record. Reputation is recomputed from these signed snapshots — see [Reputation](../trade-and-trust/reputation.md).

## Other workflows

The same `CONTRACT_*` message family covers the non-happy paths:

| Message | Trigger | Effect |
|---|---|---|
| `CONTRACT_AMEND` | A or B amends in `DRAFT` | `draft_version++` |
| `CONTRACT_REJECT` | counterparty refuses in `DRAFT` | `CANCELLED` |
| `CONTRACT_REWORK` | A asks for changes after `COMPLETE` | back to `ACTIVE`; capped by `max_rework_count` |
| `CONTRACT_CANCEL` | either side cancels | `CANCELLED` with appropriate refund |
| `CONTRACT_DISPUTE` | either side disputes | `DISPUTED`; Arbiter resolves |

Working runnables for each of these flows live in the `example/` directory:

- [`case_trade_escrow.py`](https://github.com/FoundationAgents/foundation-protocol/blob/main/example/case_trade_escrow.py) — full happy path under `ESCROW`
- [`case_trade_direct.py`](https://github.com/FoundationAgents/foundation-protocol/blob/main/example/case_trade_direct.py) — `DIRECT` payment rail
- [`case_trade_approval.py`](https://github.com/FoundationAgents/foundation-protocol/blob/main/example/case_trade_approval.py) — owner approval flow
- [`case_trade_rework.py`](https://github.com/FoundationAgents/foundation-protocol/blob/main/example/case_trade_rework.py) — rework, then accept
- [`case_trade_negotiate.py`](https://github.com/FoundationAgents/foundation-protocol/blob/main/example/case_trade_negotiate.py) — multi-round `DRAFT` amendments

## Plugging in your own approval policy

The Arbiter's state machine is fixed, but each party's *response* to a contract event is up to them. `ContractApprovalCheckPoint` (importable from `fp.trade`) is the seam — it sits in the recipient's checkpoint pipeline and decides whether the contract message goes straight to the handler or pauses for owner review.

```python
from fp.trade import ContractApprovalCheckPoint

# Auto-approve up to $50, manual review above
class BudgetGatedApproval(ContractApprovalCheckPoint):
    async def auto_approve(self, contract) -> bool:
        return contract.amount <= 50
```

See [Checkpoints & Authorization](../security/checkpoint-and-authorization.md) for how the checkpoint pipeline composes user-defined policies with the built-ins.
