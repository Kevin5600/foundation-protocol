"""Canonical hashing and signing helpers for Trade & Trust snapshots."""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any

from pydantic import BaseModel

from ..core.cryptor import Ed25519SignerVerifier
from .models import ArbiterAttestation, ContractReceipt, ContractSnapshot, ContractTerms


def _to_jsonable(obj: Any) -> Any:
    if isinstance(obj, BaseModel):
        return obj.model_dump(mode="json")
    if isinstance(obj, dict):
        return {k: _to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_to_jsonable(v) for v in obj]
    return obj


def canonical_json(obj: dict | BaseModel) -> bytes:
    """Protocol canonical JSON: sorted keys, compact separators, UTF-8."""

    return json.dumps(
        _to_jsonable(obj),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def terms_hash(terms: ContractTerms) -> str:
    """SHA256 over canonical terms excluding terms_hash itself."""

    data = terms.model_dump(mode="json")
    data.pop("terms_hash", None)
    return sha256_hex(canonical_json(data))


def snapshot_hash(snapshot: ContractSnapshot) -> str:
    """SHA256 over canonical snapshot excluding auxiliary observation blocks."""

    data = snapshot.model_dump(mode="json")
    data.pop("attestation", None)
    data.pop("receipts", None)
    return sha256_hex(canonical_json(data))


def sign_snapshot(
    snapshot: ContractSnapshot,
    *,
    signer_private_key: str,
    signer_address,
    prev_snapshot_hash: str | None = None,
) -> ArbiterAttestation:
    digest = snapshot_hash(snapshot)
    signature = Ed25519SignerVerifier().sign(digest.encode("utf-8"), signer_private_key)
    return ArbiterAttestation(
        snapshot_hash=digest,
        prev_snapshot_hash=prev_snapshot_hash,
        signed_at=time.time(),
        signer=signer_address,
        signature_alg="ed25519-sha256:v1",
        signature=signature,
    )


def verify_attestation(snapshot: ContractSnapshot, signer_public_key: str) -> bool:
    if snapshot.attestation is None:
        return False
    digest = snapshot_hash(snapshot)
    if digest != snapshot.attestation.snapshot_hash:
        return False
    return Ed25519SignerVerifier().verify(
        digest.encode("utf-8"),
        snapshot.attestation.signature,
        signer_public_key,
    )


def receipt_payload(snapshot_hash_value: str, status_message_id: str, acked_at: float) -> dict[str, Any]:
    return {
        "snapshot_hash": snapshot_hash_value,
        "status_message_id": status_message_id,
        "acked_at": acked_at,
    }


def sign_receipt(
    *,
    snapshot_hash_value: str,
    status_message_id: str,
    acked_at: float,
    signer_private_key: str,
) -> str:
    return Ed25519SignerVerifier().sign(
        canonical_json(receipt_payload(snapshot_hash_value, status_message_id, acked_at)),
        signer_private_key,
    )


def verify_receipt(receipt: ContractReceipt, snapshot: ContractSnapshot) -> bool:
    if not receipt.recipient_signature:
        return False
    recipient = next(
        (p for p in snapshot.participants if p.address.address == receipt.recipient.address),
        None,
    )
    if recipient is None or not recipient.sign_public_key:
        return False
    return Ed25519SignerVerifier().verify(
        canonical_json(receipt_payload(receipt.snapshot_hash, receipt.status_message_id, receipt.acked_at)),
        receipt.recipient_signature,
        recipient.sign_public_key,
    )
