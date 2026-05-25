"""Derived reputation views built from Arbiter-signed contract facts."""

from __future__ import annotations

import math
import time
from collections import defaultdict
from typing import Iterable, Literal

from pydantic import BaseModel, Field

from ..core.wellknown import FPAddress
from .enums import ContractStatus
from .models import Contract

ReputationRole = Literal["party_a", "party_b", "arbiter"]
ReputationOutcome = Literal["accepted", "settled", "cancelled", "disputed"]

_VENDOR_SCORE_WEIGHTS = {
    "quality": 0.35,
    "reliability": 0.25,
    "collaboration": 0.20,
    "efficiency": 0.10,
    "integrity": 0.10,
}

_VENDOR_REPUTATION_STATUSES = {
    ContractStatus.SETTLING,
    ContractStatus.SETTLED,
    ContractStatus.CANCELLED,
    ContractStatus.DISPUTED,
}


class ReputationEvent(BaseModel):
    """Normalized reputation fact extracted from one signed contract."""

    event_id: str
    contract_id: str
    subject: FPAddress
    role: ReputationRole

    counterparty: FPAddress | None = None
    arbiter: FPAddress | None = None

    outcome: ReputationOutcome
    rating: int | None = None
    review: str | None = None

    delivery_count: int = 0
    rework_count: int = 0
    dispute_count: int = 0
    cancel_count: int = 0

    total_cost_usd: float | None = None
    total_input_tokens: int | None = None
    total_output_tokens: int | None = None

    evidence_complete: bool = False
    signed_snapshot_count: int = 0

    created_at: float
    source_snapshot_hash: str


class ReputationFeatureVector(BaseModel):
    """Normalized feature vector for one reputation event."""

    quality_score: float
    reliability_score: float
    collaboration_score: float
    efficiency_score: float
    integrity_score: float

    confidence_weight: float
    recency_weight: float


class ReputationProfile(BaseModel):
    """Aggregate derived reputation for one entity in one role."""

    subject: FPAddress
    role: ReputationRole

    overall_score: float
    confidence: float
    sample_size: int

    quality_score: float
    reliability_score: float
    collaboration_score: float
    efficiency_score: float
    integrity_score: float

    recent_events: list[ReputationEvent] = Field(default_factory=list)
    updated_at: float


class ContractReputationContribution(BaseModel):
    """One contract's contribution status for vendor reputation."""

    contract_id: str
    title: str
    status: ContractStatus
    subject: FPAddress
    counterparty: FPAddress
    arbiter: FPAddress
    contributes: bool
    reason: str
    contract_score: float | None = None
    event: ReputationEvent | None = None
    feature: ReputationFeatureVector | None = None
    created_at: float
    last_action: str | None = None
    last_action_at: float | None = None


def _clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, value))


def _round_score(value: float) -> float:
    return round(value, 3)


def _round_percent(value: float) -> float:
    return round(value * 100, 1)


def _is_closed_loop_status(status: ContractStatus) -> bool:
    return status in _VENDOR_REPUTATION_STATUSES


def _map_outcome(status: ContractStatus) -> ReputationOutcome | None:
    if status == ContractStatus.SETTLING:
        return "accepted"
    if status == ContractStatus.SETTLED:
        return "settled"
    if status == ContractStatus.CANCELLED:
        return "cancelled"
    if status == ContractStatus.DISPUTED:
        return "disputed"
    return None


def contract_contributes_vendor_reputation(contract: Contract) -> bool:
    """Return whether one contract contributes to vendor reputation."""

    return _is_closed_loop_status(contract.status) and contract.attestation is not None


def explain_vendor_reputation_status(contract: Contract) -> str:
    """Explain whether one contract currently contributes to vendor reputation."""

    if contract.attestation is None:
        return "Waiting for Arbiter attestation before the contract can contribute reputation."
    if contract.status == ContractStatus.DRAFT:
        return "Draft contracts do not contribute reputation until the collaboration reaches a signed closed-loop outcome."
    if contract.status == ContractStatus.PENDING:
        return "Pending contracts are not scored yet; they need to activate and reach a closed-loop result."
    if contract.status == ContractStatus.ACTIVE:
        return "Active contracts are in progress and are not scored yet."
    if contract.status == ContractStatus.COMPLETING:
        return "Delivery is under review. Reputation starts only after accept/settling/settled/cancelled/disputed."
    if contract.status == ContractStatus.SETTLING:
        return "Accepted contract contributes vendor reputation."
    if contract.status == ContractStatus.SETTLED:
        return "Settled contract contributes vendor reputation."
    if contract.status == ContractStatus.CANCELLED:
        return "Cancelled contract contributes a negative reputation outcome."
    if contract.status == ContractStatus.DISPUTED:
        return "Disputed contract contributes a negative reputation outcome."
    return "This contract is not yet included in vendor reputation."


def extract_vendor_reputation_event(contract: Contract) -> ReputationEvent | None:
    """Extract one vendor-side reputation event from a signed contract."""

    outcome = _map_outcome(contract.status)
    if outcome is None or contract.attestation is None:
        return None

    total_cost_usd = sum(report.cost_usd or 0.0 for report in contract.cost_history)
    total_input_tokens = sum(report.input_tokens or 0 for report in contract.cost_history)
    total_output_tokens = sum(report.output_tokens or 0 for report in contract.cost_history)
    has_delivery = len(contract.delivery_history) > 0
    has_artifacts = any(delivery.artifacts for delivery in contract.delivery_history)
    evidence_complete = bool(
        contract.snapshot_history
        and contract.attestation
        and has_delivery
        and has_artifacts
    )
    source_snapshot_hash = contract.current_snapshot_hash or contract.attestation.snapshot_hash

    return ReputationEvent(
        event_id=f"{contract.contract_id}:party_b",
        contract_id=contract.contract_id,
        subject=contract.party_b,
        role="party_b",
        counterparty=contract.party_a,
        arbiter=contract.arbiter,
        outcome=outcome,
        rating=contract.rating,
        review=contract.review,
        delivery_count=len(contract.delivery_history),
        rework_count=contract.rework_count,
        dispute_count=1 if contract.status == ContractStatus.DISPUTED else 0,
        cancel_count=1 if contract.status == ContractStatus.CANCELLED else 0,
        total_cost_usd=round(total_cost_usd, 4) if contract.cost_history else None,
        total_input_tokens=total_input_tokens or None,
        total_output_tokens=total_output_tokens or None,
        evidence_complete=evidence_complete,
        signed_snapshot_count=len(contract.snapshot_history),
        created_at=(
            contract.rated_at
            or contract.settled_at
            or contract.settling_at
            or contract.cancelled_at
            or contract.last_action_at
            or contract.created_at
        ),
        source_snapshot_hash=source_snapshot_hash,
    )


def build_vendor_reputation_feature(event: ReputationEvent) -> ReputationFeatureVector:
    """Compute an explainable feature vector for one vendor reputation event."""

    if event.rating is not None:
        quality = _clamp(event.rating / 5.0)
    elif event.outcome in {"accepted", "settled"}:
        quality = 0.7
    elif event.outcome == "cancelled":
        quality = 0.3
    else:
        quality = 0.2

    if event.outcome in {"accepted", "settled"}:
        reliability = 1.0
    elif event.outcome == "cancelled":
        reliability = 0.3
    else:
        reliability = 0.2

    collaboration = _clamp(1.0 - min(event.rework_count / 3.0, 1.0))

    delivery_loop_score = _clamp(1.0 - max(event.delivery_count - 1, 0) * 0.15, 0.4, 1.0)
    transparency_score = 1.0 if event.total_cost_usd is not None else 0.6
    efficiency = _clamp((delivery_loop_score * 0.7) + (transparency_score * 0.3))

    integrity_signals = [
        1.0 if event.signed_snapshot_count > 0 else 0.0,
        1.0 if event.source_snapshot_hash else 0.0,
        1.0 if event.delivery_count > 0 else 0.0,
        1.0 if event.evidence_complete else 0.0,
    ]
    integrity = sum(integrity_signals) / len(integrity_signals)

    confidence_weight = _clamp(
        0.55
        + min(event.signed_snapshot_count, 5) * 0.08
        + (0.1 if event.rating is not None else 0.0),
        0.4,
        1.0,
    )

    age_days = max(0.0, (time.time() - event.created_at) / 86400.0)
    if age_days <= 30:
        recency_weight = 1.0
    elif age_days <= 180:
        recency_weight = 0.9
    elif age_days <= 365:
        recency_weight = 0.75
    else:
        recency_weight = 0.6

    return ReputationFeatureVector(
        quality_score=_round_score(quality),
        reliability_score=_round_score(reliability),
        collaboration_score=_round_score(collaboration),
        efficiency_score=_round_score(efficiency),
        integrity_score=_round_score(integrity),
        confidence_weight=_round_score(confidence_weight),
        recency_weight=_round_score(recency_weight),
    )


def _event_weight(feature: ReputationFeatureVector) -> float:
    return feature.confidence_weight * feature.recency_weight


def _vendor_contract_score(feature: ReputationFeatureVector) -> float:
    return (
        _VENDOR_SCORE_WEIGHTS["quality"] * feature.quality_score
        + _VENDOR_SCORE_WEIGHTS["reliability"] * feature.reliability_score
        + _VENDOR_SCORE_WEIGHTS["collaboration"] * feature.collaboration_score
        + _VENDOR_SCORE_WEIGHTS["efficiency"] * feature.efficiency_score
        + _VENDOR_SCORE_WEIGHTS["integrity"] * feature.integrity_score
    )


def aggregate_vendor_reputation(contracts: Iterable[Contract]) -> list[ReputationProfile]:
    """Aggregate vendor reputation profiles from signed contracts."""

    grouped_events: dict[str, list[tuple[ReputationEvent, ReputationFeatureVector]]] = defaultdict(list)

    for contract in contracts:
        event = extract_vendor_reputation_event(contract)
        if event is None:
            continue
        feature = build_vendor_reputation_feature(event)
        grouped_events[event.subject.address].append((event, feature))

    profiles: list[ReputationProfile] = []
    for subject_address, entries in grouped_events.items():
        total_weight = sum(_event_weight(feature) for _, feature in entries) or 1.0
        sample_size = len(entries)
        subject = entries[0][0].subject

        overall_score = sum(
            _vendor_contract_score(feature) * _event_weight(feature)
            for _, feature in entries
        ) / total_weight

        quality_score = sum(
            feature.quality_score * _event_weight(feature)
            for _, feature in entries
        ) / total_weight
        reliability_score = sum(
            feature.reliability_score * _event_weight(feature)
            for _, feature in entries
        ) / total_weight
        collaboration_score = sum(
            feature.collaboration_score * _event_weight(feature)
            for _, feature in entries
        ) / total_weight
        efficiency_score = sum(
            feature.efficiency_score * _event_weight(feature)
            for _, feature in entries
        ) / total_weight
        integrity_score = sum(
            feature.integrity_score * _event_weight(feature)
            for _, feature in entries
        ) / total_weight

        confidence = _clamp(total_weight / 3.0) * _clamp(math.sqrt(sample_size) / 3.0)
        recent_events = [event for event, _ in sorted(entries, key=lambda item: item[0].created_at, reverse=True)[:5]]

        profiles.append(
            ReputationProfile(
                subject=subject,
                role="party_b",
                overall_score=_round_percent(overall_score),
                confidence=round(confidence, 3),
                sample_size=sample_size,
                quality_score=_round_percent(quality_score),
                reliability_score=_round_percent(reliability_score),
                collaboration_score=_round_percent(collaboration_score),
                efficiency_score=_round_percent(efficiency_score),
                integrity_score=_round_percent(integrity_score),
                recent_events=recent_events,
                updated_at=time.time(),
            )
        )

    return sorted(profiles, key=lambda profile: (-profile.overall_score, profile.subject.address))


def build_contract_reputation_contribution(contract: Contract) -> ContractReputationContribution:
    """Build one contract-level reputation contribution view."""

    event = extract_vendor_reputation_event(contract)
    feature = build_vendor_reputation_feature(event) if event is not None else None
    contract_score = (
        _round_percent(_vendor_contract_score(feature))
        if feature is not None
        else None
    )
    return ContractReputationContribution(
        contract_id=contract.contract_id,
        title=contract.title,
        status=contract.status,
        subject=contract.party_b,
        counterparty=contract.party_a,
        arbiter=contract.arbiter,
        contributes=event is not None,
        reason=explain_vendor_reputation_status(contract),
        contract_score=contract_score,
        event=event,
        feature=feature,
        created_at=contract.created_at,
        last_action=contract.last_action,
        last_action_at=contract.last_action_at,
    )


def list_contract_reputation_contributions(contracts: Iterable[Contract]) -> list[ContractReputationContribution]:
    """Return contract-level vendor reputation contribution rows."""

    rows = [build_contract_reputation_contribution(contract) for contract in contracts]
    return sorted(
        rows,
        key=lambda row: (
            0 if row.contributes else 1,
            -(row.last_action_at or row.created_at),
        ),
    )
