from pathlib import Path
from typing import TypedDict
from uuid import uuid4

from fp.core.cryptor import Ed25519SignerVerifier, X25519EncryptorDecryptor

from .path import get_fp_home


class EntityKeyMaterial(TypedDict):
    sign_public_key: str
    sign_private_key: str
    encrypt_public_key: str
    decrypt_private_key: str


def _new_message_id() -> str:
    return uuid4().hex


def default_mailbox_path(entity_uid: str, host_uid: str) -> str:
    """Generate default mailbox path under host directory."""
    return str(
        Path(get_fp_home()) / "hosts" / host_uid / "mailboxes" / f"{entity_uid}.jsonl"
    )


def generate_sign_keypair() -> tuple[str, str]:
    """Generate (sign_public_key_pem, sign_private_key_pem)."""
    return Ed25519SignerVerifier().generate_keypair()


def generate_encrypt_keypair() -> tuple[str, str]:
    """Generate (encrypt_public_key_pem, decrypt_private_key_pem)."""
    return X25519EncryptorDecryptor().generate_keypair()


def generate_entity_key_material() -> EntityKeyMaterial:
    """Generate all key materials required by one Entity."""
    sign_public_key, sign_private_key = generate_sign_keypair()
    encrypt_public_key, decrypt_private_key = generate_encrypt_keypair()
    return {
        "sign_public_key": sign_public_key,
        "sign_private_key": sign_private_key,
        "encrypt_public_key": encrypt_public_key,
        "decrypt_private_key": decrypt_private_key,
    }


def generate_keypair(entity_uid: str | None = None) -> tuple[str, str]:
    """Backward-compatible alias: return signing keypair."""
    del entity_uid
    return generate_sign_keypair()
