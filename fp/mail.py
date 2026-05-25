# NOTE: Use from __future__ import annotations for forward references, cleaner and less error-prone, don't use -> "MailBase" with quotes
from __future__ import annotations

import json
from typing import Any

from pydantic import ConfigDict, Field

from .core import FPAddress, MailBase
from .core.cryptor import (
    Ed25519SignerVerifier,
    EncryptorDecryptor,
    SignerVerifier,
    X25519EncryptorDecryptor,
)
from .message import Message


class Mail(MailBase[FPAddress, list[FPAddress], Message | str, str]):
    """Mail type with FPAddress routing and convenient crypto methods.

    fp@v0.1:Uses Ed25519 signing and X25519+AESGCM encryption by default.
    Manages signer/cipher internally to simplify method calls.

    Note: message field can be either Message (unencrypted) or str (encrypted).
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)
    signer: SignerVerifier = Field(
        default_factory=Ed25519SignerVerifier,
        exclude=True,
        description="Signature provider instance",
    )
    cipher: EncryptorDecryptor = Field(
        default_factory=X25519EncryptorDecryptor,
        exclude=True,
        description="Encryption provider instance",
    )
    def to_signable_bytes(self) -> bytes:
        """Convert mail to bytes for signing"""
        recipient_str = [str(r) for r in self.recipient]
        data = {
            "sender": str(self.sender),
            "recipient": recipient_str,
            "message": self.message.model_dump()
            if hasattr(self.message, "model_dump")
            else str(self.message),
        }
        return json.dumps(data, sort_keys=True).encode("utf-8")

    def _sign(self, sign_private_key: str) -> Mail:
        """Sign mail using private key"""
        signable_bytes = self.to_signable_bytes()
        signature = self.signer.sign(signable_bytes, sign_private_key)
        return self.model_copy(update={"signature": signature})

    def _verify_signature(self, verify_public_key: str) -> bool:
        """Verify mail signature using public key"""
        if not self.signature:
            return False
        try:
            signable_bytes = self.to_signable_bytes()
            return self.signer.verify(signable_bytes, self.signature, verify_public_key)
        except Exception:
            return False

    def _encrypt_message(self, encrypt_public_key: str) -> Mail:
        """Encrypt message using recipient's public key"""
        # Serialize message to JSON
        message_json = json.dumps(self.message.model_dump())
        message_bytes = message_json.encode("utf-8")
        encrypted = self.cipher.encrypt(message_bytes, encrypt_public_key)
        return self.model_copy(update={"message": encrypted})

    def _decrypt_message(self, decrypt_private_key: str) -> Mail:
        """Decrypt message using private key"""
        if not isinstance(self.message, str):
            raise ValueError("Message is not encrypted (not a string)")
        decrypted_bytes = self.cipher.decrypt(self.message, decrypt_private_key)
        message_json = decrypted_bytes.decode("utf-8")
        message_data = json.loads(message_json)
        decrypted_message = Message.model_validate(message_data)
        return self.model_copy(update={"message": decrypted_message})

    def _extract_sender_card_key(self) -> str | None:
        """Try to extract sign_public_key from payload.sender_card (for friend requests)."""
        try:
            payload = self.message.payload
            if hasattr(payload, "sender_card"):
                return payload.sender_card.sign_public_key
            if isinstance(payload, dict) and "sender_card" in payload:
                card_data = payload["sender_card"]
                if hasattr(card_data, "sign_public_key"):
                    return card_data.sign_public_key
                return card_data.get("sign_public_key")
            return None
        except Exception:
            return None

    @classmethod
    def seal(
        cls,
        sender: FPAddress,
        recipient: FPAddress,
        message: Message,
        sign_private_key: str,
        encrypt_public_key: str | None = None,
    ) -> Mail:
        """Seal message into envelope: auto-select encryption based on encrypt_public_key"""
        mail = cls(
            sender=sender,
            recipient=[recipient],
            message=message,
            signature="",
            signer=Ed25519SignerVerifier(),
            cipher=X25519EncryptorDecryptor(),
        )
        if encrypt_public_key is None:
            sealed_mail = mail._sign(sign_private_key)
        else:
            encrypted_mail = mail._encrypt_message(encrypt_public_key)
            sealed_mail = encrypted_mail._sign(sign_private_key)

        return sealed_mail

    def unseal(
        self,
        verify_public_key: str | None = None,
        decrypt_private_key: str | None = None,
    ) -> Mail | None:
        """Unseal envelope: verify signature and decrypt if needed

        Args:
            verify_public_key: Public key for signature verification (required for encrypted messages)
            decrypt_private_key: Private key for decryption (required only if message is encrypted str)

        Returns:
            Unsealed Mail, or None if verification/decryption fails
        """
        # Case 1: Encrypted message (str)
        if isinstance(self.message, str):
            if verify_public_key is None or decrypt_private_key is None:
                return None

            if not self._verify_signature(verify_public_key):
                return None

            try:
                return self._decrypt_message(decrypt_private_key)
            except Exception:
                return None

        # Case 2: Unencrypted message (Message object)
        # Priority: explicit verify_public_key > payload.sender_card
        effective_key = verify_public_key
        if not effective_key:
            effective_key = self._extract_sender_card_key()

        if not effective_key:
            return None
        if not self._verify_signature(effective_key):
            return None
        return self

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(exclude={"signer", "cipher"})

    @classmethod
    def from_dict(
        cls,
        data: dict[str, Any],
        signer: SignerVerifier | None = None,
        cipher: EncryptorDecryptor | None = None,
    ) -> Mail:
        """Create Mail from dict"""
        mail = cls.model_validate(data)
        object.__setattr__(mail, "signer", signer or Ed25519SignerVerifier())
        object.__setattr__(mail, "cipher", cipher or X25519EncryptorDecryptor())
        return mail
