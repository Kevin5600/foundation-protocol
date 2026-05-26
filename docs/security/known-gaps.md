# Known Gaps

Foundation Protocol is in fast iteration. The runtime enforces strong cryptographic guarantees at the **message** layer, but several boundaries are still trusted by convention. This page documents them honestly so operators can reason about deployment risk.

## 1. `.well-known` is a claim, not a credential

`.well-known` documents (`fp/core/wellknown.py`) carry a host's `name`, `uid`, `url`, and the list of public entity cards it advertises. The runtime does **not** require the document to be signed by an external authority, and a parent host accepting a child's registration does not verify the child against an out-of-band credential.

In practice:

- A child registering with a parent presents its own `.well-known`. The parent accepts it.
- The WebSocket handshake between hosts is driven by the same self-reported identity.
- There is no host-level Ed25519 signature on the `.well-known` document itself.

This is sufficient for controlled environments — development, test, intranet deployments with an external trust boundary — but should **not** be treated as strict identity authentication on an open network.

## 2. Friend cards are self-asserted at first contact

The first `FRIEND_REQUEST` between two entities carries the sender's `EntityCard` inside the payload. `Mail.unseal` verifies the signature on the request **using the public key from the card itself** (`fp/mail.py`, `_extract_sender_card_key`). This binds the *message* to the *card* — a third party cannot forge a request that appears to come from a given card — but it does not externally validate that the card belongs to the human, agent, or organization it names.

What this means concretely:

- If you accept a friend request, you are accepting **the identity claim made by the sender card**.
- Once accepted, every subsequent message from that peer is signature-verified against the stored card. Impersonation after acceptance requires private-key compromise.
- The window of trust risk is **first contact**, not steady state.

Mitigation today is the owner-approval flow ([Checkpoint Pipeline](checkpoint-and-authorization.md)): an entity with an `owner` set pauses every friend request and asks the owner to confirm.

## 3. No host-level identity attestation

There is currently no equivalent of a DID, a CA-signed host certificate, or a multi-party attestation for hosts. The improvement direction has two reasonable shapes, both still pending:

**Option A — central trust platform.** A registry signs host and entity identity material; parents verify the registry's signature before accepting registration. Self-reported identity becomes platform-backed identity.

**Option B — peer-to-peer / multi-party verification.** New friend relationships or host registrations require confirmation against multiple known nodes, an observation period, or a multi-signature scheme. No single self-report establishes trust.

In either direction, the reference runtime currently meets identity-authentication guarantees at the **message** layer (every mail is signed) but not at the **host federation** layer.

## 4. No general RBAC

The only role-aware authorization in the runtime is contract-action gating (`fp/trade/authorize.py`) — sender role on a contract crossed with contract status. There is no entity-wide permission model: no ACLs on `invoke`, no scope-bounded delegations, no role catalog at the entity level.

## 5. Rate limiting is per-process

`RateLimitCheckPoint` (`fp/core/checkpoint.py`) uses an in-memory dict keyed by `sender_uid` with a sliding one-minute window. It resets on process restart, is not shared across replicas, and is not durable. For deployments that need durable rate limiting across multiple host processes, a custom checkpoint backed by a shared store is required.

## Recommendation

> `.well-known` is discovery information and an initial claim. It is not a sufficient basis for strict identity authentication.

Until host-level attestation and friend-card validation are in place, the runtime is best suited to:

- Controlled environments
- Development and test deployments
- Intranet deployments with an external trust boundary

For multi-host federation on open networks, prioritize:

- A host credential mechanism with external attestation
- Identity verification at the registration stage
- Peer authentication during the WebSocket handshake
- A stronger validation path for friend-building (owner approval already helps, but is not sufficient alone)

Operators deploying FP today should document and design around these boundaries.
