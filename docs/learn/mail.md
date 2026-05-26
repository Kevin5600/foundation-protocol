# Mail

`Mail` is the signed envelope every FP message travels in. It is the **transport-layer** abstraction: routing, signature, optional encryption, and lifecycle state. The business payload — what the message *means* — lives in [Message](message.md).

This split (envelope vs. content) is intentional. Mail does not parse, validate, or care about the business kind of the message it carries; Message does not know about routing, signing, or delivery. Either layer can evolve independently.

## Structure

```python
# fp/mail.py
class Mail(MailBase[FPAddress, list[FPAddress], Message | str, str]):
    sender: FPAddress              # who sent it
    recipient: list[FPAddress]     # one or more recipients
    message: Message | str         # plaintext Message, or ciphertext string
    signature: str                 # Ed25519 signature
    status: MailStatus             # current lifecycle state
    fp: str = "0.1"                # protocol version
```

The base class `MailBase` is generic — `Mail` pins concrete types for FP's defaults: `FPAddress` routing, `Message` payload, base64 string signature. Profiles can substitute their own.

## Lifecycle

`MailStatus` (in `fp/core/base.py`) tracks a Mail from send to processed:

| State | Meaning |
|---|---|
| `sent` | Created by `entity.send_message` |
| `delivering` | Picked up by `host.route_mail` |
| `queued` | Recipient host is offline; awaiting reconnect |
| `failed` | No route to recipient; routing aborted |
| `received` | Recipient entity persisted to its mailbox |
| `processing` | Handler is running (Agent flow only) |
| `done` | Handler finished |

Typical flows:

```text
Agent recipient: sent → delivering → received → processing → done
Human recipient: sent → delivering → received → done
Offline:         sent → delivering → queued
No route:        sent → delivering → failed
```

Human entities skip `processing` — there is no LLM step, so the runtime jumps `received → done` once the message is recorded.

Every status change can be pushed to the **sender** over the host's WebSocket channel, so a sending UI can show "delivering → received → processing → done" in real time.

## Seal — building an outbound envelope

```python
mail = Mail.seal(
    sender=alice.address,
    recipient=bob.address,
    message=message,
    sign_private_key=alice.sign_private_key,
    encrypt_public_key=bob.encrypt_public_key,  # optional
)
```

If `encrypt_public_key` is provided, the message is encrypted first (X25519 + AES-GCM) and the encrypted form is signed. If omitted, the plaintext `Message` object is signed. Either way, the result is ready to route.

For the full encryption scheme and the canonical signable bytes, see [Mail Envelope](../security/mail-envelope.md).

## Unseal — verifying inbound mail

```python
recovered = mail.unseal(
    verify_public_key=peer_card.sign_public_key,
    decrypt_private_key=me.decrypt_private_key,  # only for encrypted mail
)
```

`unseal` verifies the Ed25519 signature and, if the payload is encrypted, decrypts it. On any failure (missing signature, wrong key, corrupted ciphertext) it returns `None` — and the receiving entity drops the message without invoking any handler.

For first-contact messages (friend requests), the recipient does not yet hold the sender's `sign_public_key`. In that case `unseal` will extract it from `payload.sender_card` and verify the signature against the card itself.

## End-to-end send

A complete send, from Alice to Bob:

```python
import asyncio
from fp import EntityKind, Host, Message, MessageKind

async def main():
    host = Host(name="LocalHost")
    alice = host.register_entity(name="Alice", kind=EntityKind.HUMAN)
    bot = host.register_entity(name="Bot", kind=EntityKind.AGENT)

    await alice.send_message(
        to=bot.entity_card,
        message=Message(kind=MessageKind.INVOKE, payload={"text": "Hello!"}),
    )

asyncio.run(main())
```

Under the hood:

1. Alice's entity builds a `Message` and seals it as a `Mail` (`status=sent`).
2. The mail is persisted to Alice's **outbound mailbox**.
3. `host.route_mail` picks it up (`status=delivering`) and locates Bob — locally, on a child host, or on a parent host.
4. Bob's entity calls `receive_mail` (`status=received`), persists to its **inbound mailbox**, and notifies Alice.
5. Bob's handler runs (`status=processing` for agents, skipped for humans).
6. On completion the mail is marked `done` and Alice is notified again.

## Mailbox

Each entity has a local **Mailbox** (`fp/mailbox.py`) storing inbound and outbound mail as JSONL on disk. The Mailbox exposes:

- `save_inbound(mail)` / `save_outbound(mail)`
- `list_mails(is_read=…, is_handled=…, direction=…)`
- `mark_as_read(mail_id)` / `mark_as_handled(mail_id)`
- `mark_mail_status(mail_id, status)`

JSONL was chosen for the obvious reasons: no database dependency, append-friendly writes, trivial to back up or relocate.

Next: [Message](message.md).
