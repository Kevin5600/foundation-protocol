# Identity & Keys

Every entity in Foundation Protocol carries its own cryptographic identity. There is no shared key, no central key server, and no host-level master key — identity is **per-entity**.

## Key material per entity

An `Entity` is created with two keypairs:

| Purpose | Algorithm | Fields on `Entity` |
|---|---|---|
| Signing | Ed25519 | `sign_public_key` / `sign_private_key` |
| Encryption | X25519 (ECDH) | `encrypt_public_key` / `decrypt_private_key` |

Implementation: `fp/entity.py` (Entity field definitions) and `fp/core/cryptor.py` (`Ed25519SignerVerifier`, `X25519EncryptorDecryptor`).

Key generation uses the standard `cryptography` library:

- Ed25519 private keys are serialized as PKCS8 PEM, public keys as `SubjectPublicKeyInfo` PEM.
- X25519 follows the same encoding.

## EntityCard — the public identity advertisement

When an entity is advertised — over `.well-known`, inside a friend request payload, or via discovery — its **public** identity is packaged into an `EntityCard`:

```python
# fp/core/wellknown.py
class EntityCard(BaseModel):
    name: str
    address: FPAddress
    kind: str
    sign_public_key: str       # PEM
    encrypt_public_key: str    # PEM
    description: str = ""
    is_public: bool
    entity_uid: EntityUid
    host_uid: HostUid
    has_avatar: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)
```

An `EntityCard` is a **portable, public identity document**. It carries both public keys plus addressing information (`address`, `entity_uid`, `host_uid`). Private key material never leaves the owning entity.

## Address vs UID

| Field | Stable across | Used for |
|---|---|---|
| `entity_uid` | Lifetime of the entity | Internal references (e.g. friend list keys) |
| `address` | Lifetime of the entity | Routing — `fp://host/entity` form |
| `host_uid` | Lifetime of the host | Federation lookup |

`address` is what appears as `sender` and `recipient` on every `Mail`.

## Pluggable crypto

`Ed25519SignerVerifier` and `X25519EncryptorDecryptor` are concrete implementations of two abstract interfaces:

```python
class SignerVerifier(ABC):
    @abstractmethod
    def sign(self, data: bytes, private_key: str) -> str: ...
    @abstractmethod
    def verify(self, data: bytes, signature: str, public_key: str) -> bool: ...
    @abstractmethod
    def generate_keypair(self) -> tuple[str, str]: ...

class EncryptorDecryptor(ABC):
    @abstractmethod
    def encrypt(self, data: bytes, public_key: str) -> str: ...
    @abstractmethod
    def decrypt(self, encrypted: str, private_key: str) -> bytes: ...
    @abstractmethod
    def generate_keypair(self) -> tuple[str, str]: ...
```

Profiles or downstream deployments can substitute a different algorithm — for example a hardware-backed signer or a different curve — without changing the `Mail` API.

Next: how these keys are used on the wire — [Mail Envelope](mail-envelope.md).
