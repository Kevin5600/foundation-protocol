# Trade & Trust

Trade & Trust gives Foundation Protocol entities a native way to **transact** and to **accumulate reputation** from that history. Today, entities can communicate; with this subsystem, they can also exchange value through auditable, signed contracts and earn a verifiable track record.

The design centres on three concepts. **Contracts** are service agreements between two parties — the smallest auditable unit of trade. An **Arbiter** is the entity that drives the contract lifecycle, escrows funds, and signs the resulting audit record. **Reputation** is a derived view computed from an entity's signed contract history.

For the security properties that anchor the system, see [Trust Protocol](trust-protocol.md).

## What's in this section

<div class="grid cards" markdown>

-   [:material-state-machine: __Contract Lifecycle__](lifecycle.md)

    The eight states a contract walks through, from `DRAFT` to
    `SETTLED`, and the funding modes that govern how money moves.

-   [:material-account-multiple-outline: __Interactions__](interactions.md)

    Happy path, rework, timeouts, cancellation, and disputes —
    every flow the Arbiter recognises.

-   [:material-code-braces: __Messages & Models__](messages.md)

    The `CONTRACT_*` message family, the `Contract` data model, and
    the payload types each action uses.

-   [:material-cash-multiple: __Payment__](payment.md)

    How `ESCROW` and `DIRECT` payment rails work, the approval
    pipeline, and the `PAY_*` message family.

-   [:material-shield-check-outline: __Trust Protocol__](trust-protocol.md)

    Signed Contract Snapshots, Arbiter attestation, and the
    authentication / authorisation model that makes the audit chain
    verifiable.

-   [:material-star-outline: __Reputation__](reputation.md)

    How reputation is derived from the signed contract chain —
    events, features, and the role-specific profiles.

</div>

## Core concepts

### Arbiter

A distinguished entity (`EntityKind.ARBITER`) that owns contract state for its participants.

| Duty | Description |
|---|---|
| Drive contract state | Every transition is decided by the Arbiter and propagated to both parties. |
| Escrow funds (ESCROW mode) | Party A pays in → Arbiter holds → at settlement Arbiter releases to Party B. |
| Verify balance | Before activation the Arbiter checks Party A's available balance. |
| Sign snapshots | Each state change produces an Arbiter-signed snapshot, forming an audit chain. |
| Notify participants | Every state change is delivered to both Party A and Party B so the three-way view stays consistent. |

The Arbiter does **not** mediate the business communication between A and B. Once a contract is `ACTIVE`, the parties talk directly via normal `INVOKE` messages; the Arbiter re-enters only when a state-changing message arrives.

The Arbiter's lifecycle logic is a deterministic state machine — transitions are fixed, not configurable. This is what lets both parties rely on a consistent expectation of the flow.

### Contract

A contract is the complete auditable unit of one service exchange. Either side may create it, specifying the A/B roles at creation; the contract is finalised once the other side approves.

Key properties:

- `party_a` is the requester / payer; `party_b` is the provider / payee.
- Contracts are managed and stored by the Arbiter — neither party persists the canonical record.
- Every state change is propagated by the Arbiter, keeping both parties' views consistent.
- A settled contract is **immutable** and carries the Arbiter's SHA256 signature.

### Reputation

Reputation is **derived** from contract history, not stored independently. Each settled contract is signed by the Arbiter; reputation metrics (average rating, completion rate, credit score) are recomputed live from the signed chain. Any entity can ask the Arbiter for another's contract history, verify each signature, and compute reputation themselves — without trusting the Arbiter's summary.

The card-level `metadata` field may carry a small reputation cache (`credit_score`, `avg_rating`) for fast discovery, but the signed chain remains the source of truth.

### Customisable entity-side checkpoints

Where the Arbiter's flow is hard-coded, **the entity's response to contract events is customisable** via the [checkpoint pipeline](../learn/checkpoint.md). An owner-supervised agent might pause on every `CONTRACT_CREATE` for owner approval; a fully autonomous agent might auto-accept anything under a budget threshold. Both are valid — the policy lives in the entity's checkpoint chain, not in the Arbiter.

| Layer | Policy belongs here |
|---|---|
| **Arbiter** | How state moves, how funds move — hard-coded. |
| **Entity** | Whether to take a contract, whether to confirm completion — customisable. |

Next: [Contract Lifecycle](lifecycle.md).
