"""Contract and Payment state machines.

Pure validation — no IO, no side effects.
Given (current_status, action) → new_status or raise.
"""

from __future__ import annotations

from .enums import ContractStatus, PaymentStatus


class InvalidTransition(Exception):
    """Raised when a state transition is not allowed."""

    def __init__(self, current: str, action: str) -> None:
        self.current = current
        self.action = action
        super().__init__(f"Cannot '{action}' from '{current}'")


# status → {action → new_status}
_CONTRACT_TRANSITIONS: dict[ContractStatus, dict[str, ContractStatus]] = {
    ContractStatus.DRAFT: {
        "amend": ContractStatus.DRAFT,
        "approve": ContractStatus.PENDING,
        "reject": ContractStatus.CANCELLED,
        "cancel": ContractStatus.CANCELLED,
        "timeout": ContractStatus.CANCELLED,
    },
    ContractStatus.PENDING: {
        "activate": ContractStatus.ACTIVE,
        "cancel": ContractStatus.CANCELLED,
        "timeout": ContractStatus.CANCELLED,
    },
    ContractStatus.ACTIVE: {
        "complete": ContractStatus.COMPLETING,
        "cancel": ContractStatus.CANCELLED,
    },
    ContractStatus.COMPLETING: {
        "accept": ContractStatus.SETTLING,
        "rework": ContractStatus.ACTIVE,
        "timeout": ContractStatus.SETTLING,
        "dispute": ContractStatus.DISPUTED,
    },
    ContractStatus.SETTLING: {
        "settle": ContractStatus.SETTLED,
        "dispute": ContractStatus.DISPUTED,
        "timeout": ContractStatus.DISPUTED,
    },
    ContractStatus.DISPUTED: {
        "settle": ContractStatus.SETTLED,
        "cancel": ContractStatus.CANCELLED,
    },
}

_PAYMENT_TRANSITIONS: dict[PaymentStatus, dict[str, PaymentStatus]] = {
    PaymentStatus.REQUESTED: {
        "auto_approve": PaymentStatus.APPROVED,
        "need_approval": PaymentStatus.APPROVING,
    },
    PaymentStatus.APPROVING: {
        "approve": PaymentStatus.APPROVED,
        "reject": PaymentStatus.REJECTED,
        "timeout": PaymentStatus.REJECTED,
    },
    PaymentStatus.APPROVED: {
        "execute": PaymentStatus.EXECUTING,
    },
    PaymentStatus.EXECUTING: {
        "confirm": PaymentStatus.CONFIRMING,
        "auto_complete": PaymentStatus.COMPLETED,
    },
    PaymentStatus.CONFIRMING: {
        "confirm_receipt": PaymentStatus.COMPLETED,
        "claim_completed": PaymentStatus.COMPLETED,
        "dispute": PaymentStatus.DISPUTED,
        "timeout": PaymentStatus.DISPUTED,
    },
}


class ContractStateMachine:
    """Validates and executes contract state transitions."""

    @staticmethod
    def transition(current: ContractStatus, action: str) -> ContractStatus:
        actions = _CONTRACT_TRANSITIONS.get(current)
        if not actions or action not in actions:
            raise InvalidTransition(current.value, action)
        return actions[action]

    @staticmethod
    def allowed_actions(current: ContractStatus) -> list[str]:
        return list(_CONTRACT_TRANSITIONS.get(current, {}).keys())


class PaymentStateMachine:
    """Validates and executes payment state transitions."""

    @staticmethod
    def transition(current: PaymentStatus, action: str) -> PaymentStatus:
        actions = _PAYMENT_TRANSITIONS.get(current)
        if not actions or action not in actions:
            raise InvalidTransition(current.value, action)
        return actions[action]

    @staticmethod
    def allowed_actions(current: PaymentStatus) -> list[str]:
        return list(_PAYMENT_TRANSITIONS.get(current, {}).keys())
