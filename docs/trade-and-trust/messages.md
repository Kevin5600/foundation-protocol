# Messages & Models

This page documents the `CONTRACT_*` message family and the data models used by the trade subsystem. For the actual flows that use them, see [Interactions](interactions.md); for payment-specific messages, see [Payment](payment.md).

## Message kinds

| MessageKind | Direction | Purpose |
|---|---|---|
| `CONTRACT_CREATE` | either party → Arbiter | create a contract |
| `CONTRACT_AMEND` | either party → Arbiter | amend in `DRAFT` (`draft_version++`) |
| `CONTRACT_APPROVE` | counterparty → Arbiter | approve the current version |
| `CONTRACT_REJECT` | counterparty → Arbiter | reject the contract |
| `CONTRACT_COMPLETE` | either party → Arbiter | request acceptance |
| `CONTRACT_ACCEPT` | Party A → Arbiter | accept; move to `SETTLING` |
| `CONTRACT_REWORK` | Party A → Arbiter | reject acceptance; request rework |
| `CONTRACT_RATE` | Party A → Arbiter | rate in `SETTLING` |
| `CONTRACT_CANCEL` | either party → Arbiter | cancel the contract |
| `CONTRACT_DISPUTE` | either party → Arbiter | open a dispute |
| `CONTRACT_STATUS` | Arbiter → both | state-change notification (carries new status + snapshot) |
| `CONTRACT_STATUS_ACK` | participant → Arbiter | ACK that a snapshot was observed |
| `CONTRACT_TIMEOUT` | Arbiter → affected party | timeout notification |

State transitions like *activation* (entering `ACTIVE`) and *settlement* (entering `SETTLED`) do not have dedicated message kinds. They are conveyed through `CONTRACT_STATUS` carrying the new status and a signed snapshot — the same envelope used for every other transition. The participants reply with `CONTRACT_STATUS_ACK` so the Arbiter can record receipt of each snapshot.

All `CONTRACT_*` messages must be `Mail`-signed by the sender; payment-touching ones (`CONTRACT_CREATE`, `CONTRACT_AMEND`, `CONTRACT_RATE`) are also recommended to be encrypted. See [Trust Protocol](trust-protocol.md) for the full envelope policy.

## Data models

### Contract

```python
class ContractStatus(str, Enum):
    DRAFT = "draft"
    PENDING = "pending"
    ACTIVE = "active"
    COMPLETING = "completing"
    SETTLING = "settling"
    SETTLED = "settled"
    CANCELLED = "cancelled"
    DISPUTED = "disputed"


class FundingMode(str, Enum):
    ESCROW = "escrow"    # Arbiter escrows funds
    DIRECT = "direct"    # Arbiter provides trust backing only


class Contract(BaseModel):
    contract_id: str
    party_a: FPAddress            # requester / payer
    party_b: FPAddress            # provider / payee
    creator: FPAddress            # creator (A or B)
    arbiter: FPAddress

    title: str
    description: str
    amount: float
    funding_mode: FundingMode

    status: ContractStatus = ContractStatus.DRAFT
    draft_version: int = 1

    # Integrity chain — every state change snapshots into snapshot_history
    terms_hash: str = ""
    current_snapshot_hash: str | None = None
    prev_snapshot_hash: str | None = None
    participant_snapshots: list[ParticipantSnapshot] = []
    approvals: list[ContractApproval] = []
    receipts: list[ContractReceipt] = []
    snapshot_history: list[ContractSnapshot] = []

    # Work session linkage (used by the application layer to bind
    # the contract to a multi-turn conversation)
    work_session_id: str | None = None
    work_session_name: str | None = None

    # Delivery & cost — populated by CONTRACT_COMPLETE
    current_delivery: DeliveryEvidence | None = None
    delivery_history: list[DeliveryEvidence] = []
    current_execution_costs: list[ExecutionCostReport] = []
    cost_history: list[ExecutionCostReport] = []

    # Rework
    rework_count: int = 0
    max_rework_count: int = 3

    # Rating (A rates B at settlement)
    rating: int | None = None
    review: str | None = None
    rated_by: FPAddress | None = None
    rated_at: float | None = None

    # Last action audit
    last_action: str | None = None
    last_actor: FPAddress | None = None
    last_reason: str | None = None
    last_action_at: float | None = None

    # Timeline
    created_at: float
    approved_at: float | None = None
    activated_at: float | None = None
    completed_at: float | None = None
    settling_at: float | None = None
    settled_at: float | None = None
    cancelled_at: float | None = None

    # Arbiter Ed25519 signature over the latest snapshot
    arbiter_signature: str | None = None
    arbiter_signature_alg: str = "ed25519-sha256:v1"
    attestation: ArbiterAttestation | None = None
```

The integrity sub-models (`ContractSnapshot`, `ContractApproval`, `ContractReceipt`, `ArbiterAttestation`, `ParticipantSnapshot`, `DeliveryEvidence`, `ExecutionCostReport`) all live in `fp/trade/models.py`. Each `CONTRACT_STATUS` carries a fresh `ContractSnapshot` signed by the Arbiter, and the chain of `prev_snapshot_hash → current_snapshot_hash` lets either party (or a third-party auditor) replay the full lifecycle.

### Reputation view

Reputation is not persisted independently. It is computed live from the Arbiter-signed contract list. The model below is used for transport and display only:

```python
class Reputation(BaseModel):
    """Reputation view computed from the signed contract chain (not stored)."""
    entity_uid: EntityUid
    balance: float = 0.0
    total_contracts: int = 0
    completed_contracts: int = 0
    cancelled_contracts: int = 0
    timeout_count: int = 0
    avg_rating_as_provider: float = 0.0
    credit_score: float = 0.0
```

See [Reputation](reputation.md) for the derivation rules.

## Message payloads

```python
class ContractCreatePayload(BaseModel):
    """Create a contract. Cards are carried inline so the Arbiter can
    freeze each participant's identity into the contract on creation."""
    party_a: FPAddress
    party_b: FPAddress
    party_a_card: EntityCard | None = None
    party_b_card: EntityCard | None = None
    title: str
    description: str
    amount: float
    funding_mode: FundingMode
    work_session_id: str | None = None
    work_session_name: str | None = None


class ContractAmendPayload(BaseModel):
    """Amend the contract in DRAFT."""
    contract_id: str
    title: str | None = None
    description: str | None = None
    amount: float | None = None
    funding_mode: FundingMode | None = None
    # Optimistic-concurrency fields — the Arbiter rejects the amendment
    # if the contract has moved on since the sender last observed it.
    expected_status: ContractStatus | None = None
    revision: int | None = None
    terms_hash: str | None = None
    source_snapshot_hash: str | None = None


class ContractActionPayload(BaseModel):
    """Generic contract action (approve / reject / complete /
    accept / cancel / dispute / rework). Delivery evidence and cost
    reports are attached at COMPLETE time."""
    contract_id: str
    reason: str | None = None
    expected_status: ContractStatus | None = None
    revision: int | None = None
    terms_hash: str | None = None
    source_snapshot_hash: str | None = None
    delivery: DeliveryEvidence | None = None
    execution_costs: list[ExecutionCostReport] = []


class ContractRatePayload(BaseModel):
    """Rate the contract in SETTLING."""
    contract_id: str
    rating: int                  # 1-5
    review: str | None = None
    expected_status: ContractStatus | None = None
    revision: int | None = None
    terms_hash: str | None = None
    source_snapshot_hash: str | None = None


class ContractStatusPayload(BaseModel):
    """Arbiter state-change notification. Carries both the full Contract
    (for application-layer convenience) and a signed snapshot (for the
    integrity chain)."""
    contract_id: str
    status: ContractStatus
    contract: Contract
    snapshot: ContractSnapshot | None = None
    message: str | None = None


class ContractStatusAckPayload(BaseModel):
    """Participant ACK that one snapshot was observed."""
    contract_id: str
    snapshot_hash: str
    status_message_id: str
    acked_at: float
    recipient_signature: str | None = None
```

The `expected_status` / `revision` / `terms_hash` / `source_snapshot_hash` block on the action and amend payloads is what makes the contract chain replay-safe: each action declares which snapshot it believes it is acting on, and the Arbiter refuses the action if reality has moved on.

## Layered responsibilities

| Layer | Responsibility |
|---|---|
| **fp** | `Contract` / `Reputation` models, `ContractStatus`, `CONTRACT_*` kinds, payload models |
| **fp** | `ArbiterCheckPoint` — handles `CONTRACT_*` messages |
| **fp** | `ContractCheckPoint` — validates contract-related messages |
| **app** | Arbiter entity registration, contract persistence, reputation persistence, settlement API |
| **cli** | `aln contract *` commands |
| **web** | Contract management UI, reputation display |

## Integration with the existing system

Trade & Trust reuses the existing primitives:

- `EntityKind` adds `ARBITER`.
- `MessageKind` adds the `CONTRACT_*` family.
- `EntityCard.metadata` may carry `credit_score` for discovery hints.
- Contract signing reuses the existing Ed25519 key infrastructure.
- A new `ContractApprovalCheckPoint` on the entity side enables owner involvement via the standard checkpoint chain (optional).

Next: [Payment](payment.md).
