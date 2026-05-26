# Mail Envelope

`Mail` is the signed envelope every protocol-level message travels in. Signing is **mandatory**. Encryption is **opt-in**.

Implementation: `fp/mail.py`, `fp/core/cryptor.py`.

## Seal — building an outbound envelope

```python
# fp/mail.py
@classmethod
def seal(
    cls,
    sender: FPAddress,
    recipient: FPAddress,
    message: Message,
    sign_private_key: str,
    encrypt_public_key: str | None = None,
) -> Mail:
    ...
```

Two paths:

| `encrypt_public_key` | Result |
|---|---|
| `None` | Signed plaintext mail. `mail.message` is the `Message` object. |
| Provided | Encrypt first (X25519 + AES-GCM), then sign the encrypted form. `mail.message` is a ciphertext string. |

In both paths, the final mail carries an Ed25519 `signature` over the canonical signable bytes.

## Canonical signable bytes

Signatures are over a stable JSON form of the envelope (not the raw object):

```python
data = {
    "sender": str(self.sender),
    "recipient": [str(r) for r in self.recipient],
    "message": self.message.model_dump()
        if hasattr(self.message, "model_dump")
        else str(self.message),
}
return json.dumps(data, sort_keys=True).encode("utf-8")
```

`sort_keys=True` ensures byte-stable serialization regardless of dict ordering. The signature covers sender, recipient list, **and** the message payload — including the encrypted form when encryption is used. Tampering with any of these invalidates the signature.

## Unseal — verifying and decrypting

```python
def unseal(
    self,
    verify_public_key: str | None = None,
    decrypt_private_key: str | None = None,
) -> Mail | None:
    ...
```

Behavior depends on whether the message is encrypted:

**Encrypted mail (`message` is a string)**

1. Both `verify_public_key` and `decrypt_private_key` are required.
2. Verify the Ed25519 signature.
3. Decrypt with the provided X25519 private key.
4. Return a new `Mail` with the decrypted `Message`, or `None` on any failure.

**Plaintext mail (`message` is a `Message` object)**

1. If an explicit `verify_public_key` is supplied, use it.
2. Otherwise, attempt to extract `sender_card.sign_public_key` from the payload — this enables first-contact flows like friend requests where the recipient does not yet hold the sender's key.
3. If no key is available, return `None`.
4. Verify the signature; return `None` on failure.

## Encryption — X25519 + HKDF-SHA256 + AES-GCM

When encryption is enabled, `X25519EncryptorDecryptor` produces a self-describing JSON payload:

```json
{
  "v": 1,
  "alg": "X25519+AESGCM",
  "epk":   "<base64 ephemeral X25519 public key>",
  "salt":  "<base64 16-byte salt>",
  "nonce": "<base64 12-byte nonce>",
  "ct":    "<base64 AES-GCM ciphertext>"
}
```

Properties:

- **Forward secrecy** at the message level — every encrypt call generates a fresh ephemeral X25519 keypair (`epk`).
- The AES-256 key is derived via HKDF-SHA256 with a fresh 16-byte salt and the context string `b"fp/x25519-aesgcm/v1"`.
- The 12-byte nonce is randomly generated per message.
- The recipient's long-term X25519 private key plus the ephemeral public key reconstruct the shared secret, then HKDF rederives the AES key.

The ephemeral key is discarded after encryption, so compromise of a recipient's long-term key does not retroactively expose past messages **that used distinct ephemeral keys** — provided the long-term key is not used to derive the AES key directly.

## Failure modes

`Mail.unseal()` returns `None` on **every** failure mode, including:

- Missing signature
- Invalid signature
- Missing verify key (and no `sender_card` in payload)
- Missing decrypt key on an encrypted mail
- Decryption / AES-GCM tag check failure

This is intentional — a failed unseal is indistinguishable from a malformed or hostile envelope; the receiving entity simply drops the message.

Next: how mail moves between hosts — [Federation & Friends](federation-and-friends.md).
