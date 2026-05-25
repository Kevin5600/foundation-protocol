"""Role-based authorization for Contract lifecycle actions."""

from __future__ import annotations

from pydantic import BaseModel

from ..core.wellknown import FPAddress
from .enums import ContractStatus
from .models import Contract


class AuthorizeResult(BaseModel):
    allowed: bool
    role: str | None = None
    reason: str | None = None


def _role_for(sender: FPAddress, contract: Contract) -> str:
    if sender.address == contract.party_a.address:
        return "party_a"
    if sender.address == contract.party_b.address:
        return "party_b"
    if sender.address == contract.arbiter.address:
        return "arbiter"
    return "stranger"


def authorize(action: str, sender: FPAddress, contract: Contract) -> AuthorizeResult:
    """Authorize one contract action against sender role and current status."""

    role = _role_for(sender, contract)
    if role == "stranger":
        return AuthorizeResult(allowed=False, role=role, reason="sender is not a contract participant")

    status = contract.status
    allowed = False
    reason = None

    if action in {"amend", "approve", "reject"}:
        allowed = role in {"party_a", "party_b"} and status == ContractStatus.DRAFT
        reason = "draft action requires party_a/party_b and draft status"
    elif action == "complete":
        allowed = role == "party_b" and status == ContractStatus.ACTIVE
        reason = "complete requires party_b and active status"
    elif action in {"accept", "rework"}:
        allowed = role == "party_a" and status == ContractStatus.COMPLETING
        reason = f"{action} requires party_a and completing status"
    elif action == "rate":
        allowed = role == "party_a" and status in {ContractStatus.SETTLING, ContractStatus.SETTLED}
        reason = "rate requires party_a and settling/settled status"
    elif action in {"cancel", "dispute"}:
        allowed = role in {"party_a", "party_b"}
        reason = f"{action} requires a contract party"
    elif action in {"activate", "settle", "timeout"}:
        allowed = role == "arbiter"
        reason = f"{action} is arbiter-only"
    else:
        reason = f"unknown action: {action}"

    return AuthorizeResult(allowed=allowed, role=role, reason=None if allowed else reason)
