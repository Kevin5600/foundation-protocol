"""Trade & Trust data models."""

from __future__ import annotations

from pydantic import BaseModel, Field

from ..core.base import EntityUid
from ..core.wellknown import EntityCard, FPAddress
from .enums import (
    ContractStatus,
    FundingMode,
    PaymentMethod,
    PaymentStatus,
    PayMode,
)


class ParticipantSnapshot(BaseModel):
    """Frozen participant identity used to verify one contract lifecycle."""

    address: FPAddress
    role: str
    host_uid: str
    entity_uid: str
    sign_public_key: str
    encrypt_public_key: str
    display_name: str

    @classmethod
    def from_card(cls, card: EntityCard, role: str) -> ParticipantSnapshot:
        return cls(
            address=card.address,
            role=role,
            host_uid=card.host_uid,
            entity_uid=card.entity_uid,
            sign_public_key=card.sign_public_key,
            encrypt_public_key=card.encrypt_public_key,
            display_name=card.name,
        )

    @classmethod
    def from_address(cls, address: FPAddress, role: str, display_name: str = "") -> ParticipantSnapshot:
        return cls(
            address=address,
            role=role,
            host_uid=address.host_uid,
            entity_uid=address.entity_uid,
            sign_public_key="",
            encrypt_public_key="",
            display_name=display_name or address.entity_uid,
        )


class ContractTerms(BaseModel):
    """Versioned contract terms signed through terms_hash."""

    revision: int
    title: str
    description: str
    amount: float
    funding_mode: FundingMode
    terms_hash: str = ""


class ContractApproval(BaseModel):
    """A party approval bound to one exact terms revision/hash."""

    party_role: str
    approved_revision: int
    approved_terms_hash: str
    approved_at: float
    approved_by: FPAddress
    source_mail_id: str | None = None


class ContractReceipt(BaseModel):
    """A participant ACK that it observed one contract snapshot."""

    recipient: FPAddress
    status_message_id: str
    snapshot_hash: str
    acked_at: float
    recipient_signature: str | None = None


class ArbiterAttestation(BaseModel):
    """Arbiter signature over a ContractSnapshot."""

    snapshot_hash: str
    prev_snapshot_hash: str | None = None
    signed_at: float
    signer: FPAddress
    signature_alg: str = "ed25519-sha256:v1"
    signature: str


class ContractRating(BaseModel):
    """Rating input for later reputation calculation."""

    rating: int
    review: str | None = None
    rated_by: FPAddress
    rated_at: float


class DeliveryArtifact(BaseModel):
    """One concrete artifact produced by a delivery step."""

    kind: str
    uri: str
    label: str | None = None
    digest: str | None = None
    size_bytes: int | None = None


class DeliveryEvidence(BaseModel):
    """Structured delivery evidence attached to one completion step."""

    delivery_id: str
    version: str
    summary: str
    artifacts: list[DeliveryArtifact] = Field(default_factory=list)
    source_session_id: str | None = None
    source_message_id: str | None = None
    produced_by: FPAddress
    produced_at: float


class ExecutionCostReport(BaseModel):
    """Optional execution-cost report for one participant turn or delivery."""

    report_id: str | None = None
    actor: FPAddress
    phase: str | None = None
    provider: str | None = None
    model: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: float | None = None
    runtime_ms: int | None = None
    notes: str | None = None
    recorded_at: float


class ContractSnapshot(BaseModel):
    """Protocol-level auditable contract snapshot."""

    contract_id: str
    protocol_version: str = "trust:0.1"
    status: ContractStatus
    participants: list[ParticipantSnapshot] = Field(default_factory=list)
    terms: ContractTerms
    approvals: list[ContractApproval] = Field(default_factory=list)
    rating: ContractRating | None = None
    receipts: list[ContractReceipt] = Field(default_factory=list)
    delivery: DeliveryEvidence | None = None
    execution_costs: list[ExecutionCostReport] = Field(default_factory=list)
    last_action: str | None = None
    last_actor: FPAddress | None = None
    last_reason: str | None = None
    last_action_at: float | None = None
    attestation: ArbiterAttestation | None = None


class Contract(BaseModel):
    """A service contract between two entities, managed by an Arbiter."""

    contract_id: str
    party_a: FPAddress
    party_b: FPAddress
    creator: FPAddress
    arbiter: FPAddress

    title: str
    description: str
    amount: float
    funding_mode: FundingMode

    status: ContractStatus = ContractStatus.DRAFT
    draft_version: int = 1
    terms_hash: str = ""
    current_snapshot_hash: str | None = None
    prev_snapshot_hash: str | None = None
    work_session_id: str | None = None
    work_session_name: str | None = None
    participant_snapshots: list[ParticipantSnapshot] = Field(default_factory=list)
    approvals: list[ContractApproval] = Field(default_factory=list)
    receipts: list[ContractReceipt] = Field(default_factory=list)
    snapshot_history: list[ContractSnapshot] = Field(default_factory=list)
    current_delivery: DeliveryEvidence | None = None
    delivery_history: list[DeliveryEvidence] = Field(default_factory=list)
    current_execution_costs: list[ExecutionCostReport] = Field(default_factory=list)
    cost_history: list[ExecutionCostReport] = Field(default_factory=list)

    rework_count: int = 0
    max_rework_count: int = 3

    rating: int | None = None
    review: str | None = None
    rated_by: FPAddress | None = None
    rated_at: float | None = None

    last_action: str | None = None
    last_actor: FPAddress | None = None
    last_reason: str | None = None
    last_action_at: float | None = None

    created_at: float
    approved_at: float | None = None
    activated_at: float | None = None
    completed_at: float | None = None
    settling_at: float | None = None
    settled_at: float | None = None
    cancelled_at: float | None = None

    arbiter_signature: str | None = None
    arbiter_signature_alg: str = "ed25519-sha256:v1"
    attestation: ArbiterAttestation | None = None

    def terms(self) -> ContractTerms:
        return ContractTerms(
            revision=self.draft_version,
            title=self.title,
            description=self.description,
            amount=self.amount,
            funding_mode=self.funding_mode,
            terms_hash=self.terms_hash,
        )

    def to_snapshot(self) -> ContractSnapshot:
        rating = None
        if self.rating is not None and self.rated_by is not None and self.rated_at is not None:
            rating = ContractRating(
                rating=self.rating,
                review=self.review,
                rated_by=self.rated_by,
                rated_at=self.rated_at,
            )
        return ContractSnapshot(
            contract_id=self.contract_id,
            status=self.status,
            participants=self.participant_snapshots,
            terms=self.terms(),
            approvals=self.approvals,
            rating=rating,
            receipts=self.receipts,
            delivery=self.current_delivery,
            execution_costs=self.current_execution_costs,
            last_action=self.last_action,
            last_actor=self.last_actor,
            last_reason=self.last_reason,
            last_action_at=self.last_action_at,
            attestation=self.attestation,
        )


class Payment(BaseModel):
    """A payment record, decoupled from Contract."""

    payment_id: str
    contract_id: str | None = None
    payer: FPAddress
    payee: FPAddress
    amount: float

    method: PaymentMethod
    pay_mode: PayMode
    status: PaymentStatus = PaymentStatus.REQUESTED

    receipt_info: str

    requested_at: float
    approved_at: float | None = None
    executed_at: float | None = None
    completed_at: float | None = None


class Reputation(BaseModel):
    """Computed reputation view from signed Contract chain."""

    entity_uid: EntityUid
    balance: float = 0.0
    total_contracts: int = 0
    completed_contracts: int = 0
    cancelled_contracts: int = 0
    timeout_count: int = 0
    avg_rating_as_provider: float = 0.0
    credit_score: float = 0.0


class LedgerSnapshot(BaseModel):
    """Serializable snapshot of Ledger state."""

    balances: dict[str, float] = Field(default_factory=dict)
    frozen: dict[str, float] = Field(default_factory=dict)


class ArbiterState(BaseModel):
    """Serializable snapshot of Arbiter state."""

    contracts: list[Contract] = Field(default_factory=list)
    payments: list[Payment] = Field(default_factory=list)
    ledger: LedgerSnapshot = Field(default_factory=LedgerSnapshot)


class ApprovalRule(BaseModel):
    """A single auto-approve condition."""

    max_amount: float | None = None
    whitelist: list[str] | None = None
    daily_limit: float | None = None


class PaymentApprovalPolicy(BaseModel):
    """Entity's payment approval strategy."""

    auto_approve_rules: list[ApprovalRule] = Field(default_factory=list)
    default_action: str = "reject"
    timeout_seconds: int = 3600
    timeout_action: str = "reject"
