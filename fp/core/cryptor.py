"""Cryptographic abstractions and default implementations."""

from __future__ import annotations

import base64
import json
import os
from abc import ABC, abstractmethod


class SignerVerifier(ABC):
    """Abstract signature API."""

    @abstractmethod
    def sign(self, data: bytes, private_key: str) -> str:
        """Sign bytes with private key PEM and return base64 signature."""

    @abstractmethod
    def verify(self, data: bytes, signature: str, public_key: str) -> bool:
        """Verify base64 signature with public key PEM."""

    @abstractmethod
    def generate_keypair(self) -> tuple[str, str]:
        """Generate (public_key_pem, private_key_pem)."""


class EncryptorDecryptor(ABC):
    """Abstract encryption API."""

    @abstractmethod
    def encrypt(self, data: bytes, public_key: str) -> str:
        """Encrypt bytes with public key PEM and return encoded payload."""

    @abstractmethod
    def decrypt(self, encrypted: str, private_key: str) -> bytes:
        """Decrypt encoded payload with private key PEM and return plaintext bytes."""

    @abstractmethod
    def generate_keypair(self) -> tuple[str, str]:
        """Generate (public_key_pem, private_key_pem)."""


class Ed25519SignerVerifier(SignerVerifier):
    """Ed25519 signer/verifier implementation."""

    def sign(self, data: bytes, private_key: str) -> str:
        from cryptography.hazmat.primitives.serialization import load_pem_private_key

        private_key_obj = load_pem_private_key(
            private_key.encode("utf-8"), password=None
        )
        signature_bytes = private_key_obj.sign(data)
        return base64.b64encode(signature_bytes).decode("utf-8")

    def verify(self, data: bytes, signature: str, public_key: str) -> bool:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.serialization import load_pem_public_key

        try:
            signature_bytes = base64.b64decode(signature)
            public_key_obj = load_pem_public_key(public_key.encode("utf-8"))
            public_key_obj.verify(signature_bytes, data)
            return True
        except InvalidSignature:
            return False
        except Exception:
            return False

    def generate_keypair(self) -> tuple[str, str]:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        from cryptography.hazmat.primitives.serialization import (
            Encoding,
            NoEncryption,
            PrivateFormat,
            PublicFormat,
        )

        private_key_obj = Ed25519PrivateKey.generate()
        public_key_obj = private_key_obj.public_key()

        public_key_pem = public_key_obj.public_bytes(
            encoding=Encoding.PEM,
            format=PublicFormat.SubjectPublicKeyInfo,
        ).decode("utf-8")
        private_key_pem = private_key_obj.private_bytes(
            encoding=Encoding.PEM,
            format=PrivateFormat.PKCS8,
            encryption_algorithm=NoEncryption(),
        ).decode("utf-8")

        return public_key_pem, private_key_pem


class X25519EncryptorDecryptor(EncryptorDecryptor):
    """X25519 + HKDF-SHA256 + AES-GCM encrypt/decrypt implementation."""

    _KDF_INFO = b"fp/x25519-aesgcm/v1"

    def encrypt(self, data: bytes, public_key: str) -> str:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric.x25519 import (
            X25519PrivateKey,
            X25519PublicKey,
        )
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        from cryptography.hazmat.primitives.kdf.hkdf import HKDF

        recipient_key_obj = serialization.load_pem_public_key(
            public_key.encode("utf-8")
        )
        if not isinstance(recipient_key_obj, X25519PublicKey):
            raise ValueError("encrypt public key is not a valid X25519 public key")

        ephemeral_private = X25519PrivateKey.generate()
        shared_secret = ephemeral_private.exchange(recipient_key_obj)

        salt = os.urandom(16)
        nonce = os.urandom(12)
        aes_key = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            info=self._KDF_INFO,
        ).derive(shared_secret)

        ciphertext = AESGCM(aes_key).encrypt(nonce, data, None)
        ephemeral_public_raw = ephemeral_private.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )

        payload = {
            "v": 1,
            "alg": "X25519+AESGCM",
            "epk": base64.b64encode(ephemeral_public_raw).decode("utf-8"),
            "salt": base64.b64encode(salt).decode("utf-8"),
            "nonce": base64.b64encode(nonce).decode("utf-8"),
            "ct": base64.b64encode(ciphertext).decode("utf-8"),
        }
        return json.dumps(payload, separators=(",", ":"))

    def decrypt(self, encrypted: str, private_key: str) -> bytes:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric.x25519 import (
            X25519PrivateKey,
            X25519PublicKey,
        )
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        from cryptography.hazmat.primitives.kdf.hkdf import HKDF

        payload = json.loads(encrypted)
        if not isinstance(payload, dict):
            raise ValueError("encrypted payload must be a JSON object")

        private_key_obj = serialization.load_pem_private_key(
            private_key.encode("utf-8"),
            password=None,
        )
        if not isinstance(private_key_obj, X25519PrivateKey):
            raise ValueError("decrypt private key is not a valid X25519 private key")

        ephemeral_public_raw = base64.b64decode(payload["epk"])
        salt = base64.b64decode(payload["salt"])
        nonce = base64.b64decode(payload["nonce"])
        ciphertext = base64.b64decode(payload["ct"])

        ephemeral_public = X25519PublicKey.from_public_bytes(ephemeral_public_raw)
        shared_secret = private_key_obj.exchange(ephemeral_public)
        aes_key = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            info=self._KDF_INFO,
        ).derive(shared_secret)
        return AESGCM(aes_key).decrypt(nonce, ciphertext, None)

    def generate_keypair(self) -> tuple[str, str]:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey

        private_key_obj = X25519PrivateKey.generate()
        public_key_obj = private_key_obj.public_key()

        public_key_pem = public_key_obj.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode("utf-8")
        private_key_pem = private_key_obj.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode("utf-8")

        return public_key_pem, private_key_pem
