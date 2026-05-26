# Security

Foundation Protocol's security model is built into the runtime, not bolted on. Every message between entities is signed; payload encryption is opt-in; every inbound message walks an ordered checkpoint pipeline before reaching a handler.

This section documents how the **reference Python runtime** implements those guarantees today — what's enforced in code, what's still trusted by convention, and where the boundaries are.

## What's in this section

<div class="grid cards" markdown>

-   [:material-key-variant: __Identity & Keys__](identity-and-keys.md)

    How entities are identified, the Ed25519 + X25519 key material every
    entity carries, and how identity is advertised via `EntityCard`.

-   [:material-email-lock-outline: __Mail Envelope__](mail-envelope.md)

    `Mail.seal` and `Mail.unseal` — mandatory signing, optional X25519
    + AES-GCM encryption, and the canonical signable bytes.

-   [:material-server-network: __Federation & Friends__](federation-and-friends.md)

    Host-to-host discovery via `.well-known`, friend request flow, and
    where trust is established between entities.

-   [:material-shield-check: __Checkpoint Pipeline__](checkpoint-and-authorization.md)

    The ordered policy chain every inbound message walks: friendship,
    payment, rate limit, content length — plus contract-action
    authorization.

-   [:material-alert-octagon-outline: __Known Gaps__](known-gaps.md)

    What the current implementation does **not** yet enforce — the
    explicit boundaries operators should know about.

</div>

## Trust model in one paragraph

Every FP entity owns an Ed25519 signing keypair and an X25519 encryption keypair. Every `Mail` that leaves an entity is signed; verification uses either an explicitly-supplied public key or the `sender_card` embedded in the payload (for first-contact flows like friend requests). Encryption is optional and triggered by passing the recipient's `encrypt_public_key` to `Mail.seal`. Between hosts, discovery happens via `.well-known` documents — these are **identity claims**, not strong credentials. Authorization for contract actions is role-based (`party_a`, `party_b`, `arbiter`) and gated on contract status.

For a frank account of where the model is still weak, see [Known Gaps](known-gaps.md).
