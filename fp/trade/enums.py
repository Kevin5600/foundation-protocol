"""Trade & Trust enumerations."""

from __future__ import annotations

from enum import Enum


class ContractStatus(str, Enum):
    """Contract lifecycle status."""

    DRAFT = "draft"
    PENDING = "pending"
    ACTIVE = "active"
    COMPLETING = "completing"
    SETTLING = "settling"
    SETTLED = "settled"
    CANCELLED = "cancelled"
    DISPUTED = "disputed"


class FundingMode(str, Enum):
    """Contract payment mode."""

    ESCROW = "escrow"
    DIRECT = "direct"


class PaymentStatus(str, Enum):
    """Payment lifecycle status."""

    REQUESTED = "requested"
    APPROVING = "approving"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXECUTING = "executing"
    CONFIRMING = "confirming"
    COMPLETED = "completed"
    DISPUTED = "disputed"


class PaymentMethod(str, Enum):
    """How payment is executed."""

    ESCROW = "escrow"
    QR_CODE = "qr_code"
    PAY_LINK = "pay_link"
    BANK = "bank"
    CRYPTO = "crypto"
    GATEWAY = "gateway"


class PayMode(str, Enum):
    """Who executes the payment."""

    ENTITY_PAY = "entity_pay"
    OWNER_PAY = "owner_pay"
