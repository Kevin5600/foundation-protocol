"""Trade & Trust message payloads."""

from __future__ import annotations

from uuid import uuid4

from pydantic import BaseModel, Field

from ..core.wellknown import EntityCard, FPAddress
from .enums import ContractStatus, FundingMode, PaymentMethod, PaymentStatus
from .models import (
    Contract,
    ContractSnapshot,
    DeliveryEvidence,
    ExecutionCostReport,
    Payment,
)


# ========== Contract Payloads ==========


class ContractCreatePayload(BaseModel):
    """Create a new contract."""

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
    """Amend contract terms during DRAFT."""

    contract_id: str
    title: str | None = None
    description: str | None = None
    amount: float | None = None
    funding_mode: FundingMode | None = None
    expected_status: ContractStatus | None = None
    revision: int | None = None
    terms_hash: str | None = None
    source_snapshot_hash: str | None = None


class ContractActionPayload(BaseModel):
    """Generic contract action (approve/reject/complete/accept/cancel/dispute/rework)."""

    contract_id: str
    reason: str | None = None
    expected_status: ContractStatus | None = None
    revision: int | None = None
    terms_hash: str | None = None
    source_snapshot_hash: str | None = None
    delivery: DeliveryEvidence | None = None
    execution_costs: list[ExecutionCostReport] = Field(default_factory=list)


class ContractRatePayload(BaseModel):
    """Rate the contract during SETTLING."""

    contract_id: str
    rating: int
    review: str | None = None
    expected_status: ContractStatus | None = None
    revision: int | None = None
    terms_hash: str | None = None
    source_snapshot_hash: str | None = None


class ContractStatusPayload(BaseModel):
    """Arbiter status notification to both parties."""

    contract_id: str
    status: ContractStatus
    contract: Contract
    snapshot: ContractSnapshot | None = None
    message: str | None = None


class ContractStatusAckPayload(BaseModel):
    """Participant acknowledgement that a contract snapshot was observed."""

    contract_id: str
    snapshot_hash: str
    status_message_id: str
    acked_at: float
    recipient_signature: str | None = None


# ========== Pay Payloads ==========


class PayCollectPayload(BaseModel):
    """Payee initiates collection."""

    payment_id: str = Field(default_factory=lambda: uuid4().hex[:12])
    contract_id: str | None = None
    payer: FPAddress
    payee: FPAddress
    amount: float
    method: PaymentMethod
    receipt_info: str


class PayRequestPayload(BaseModel):
    """Contract SETTLING triggers payment request."""

    payment_id: str
    contract_id: str
    payee: FPAddress
    amount: float
    method: PaymentMethod
    receipt_info: str


class PayActionPayload(BaseModel):
    """Payment action (approve/reject/confirm_receipt/claim_completed)."""

    payment_id: str
    reason: str | None = None
    payment: Payment | None = None


class PayStatusPayload(BaseModel):
    """Payment status notification."""

    payment_id: str
    status: PaymentStatus
    payment: Payment
    message: str | None = None
