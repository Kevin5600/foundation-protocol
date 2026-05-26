# Reputation

Reputation is a derived layer built on top of the existing Trade & Trust protocol. The protocol layer stores **trust facts**; the reputation layer turns those facts into **profiles** that answer "how has this entity performed over time".

Three definitions to keep separate:

- **Trust** answers whether a contract fact is authentic and independently verifiable.
- **Rating** answers how one counterparty evaluated one contract outcome.
- **Reputation** answers how an entity has performed across many contracts over time.

This page describes the protocol-first reputation design — what events are extracted from signed contracts, how features are derived, and how role-specific profiles are computed.

## What reputation must solve

The current system already records the high-value evidence:

- signed contract snapshots
- approvals and deliveries
- execution costs
- accept / rework / cancel / dispute / rate outcomes
- Arbiter attestations

What it does not yet provide is a derived layer that can answer:

- which vendor is more reliable?
- which vendor needs fewer rework loops?
- which counterparties are stable to work with?
- how can a market or portal rank entities using protocol-backed evidence?

The reputation system solves these without weakening the protocol guarantees and without introducing opaque scoring logic.

## Design principles

**Protocol facts first.** Reputation is derived only from Arbiter-signed contract facts. Chat text, draft fields, and UI-only state never affect a score.

**Roles are separated.** Reputation is computed per role — `party_b` (delivery / vendor), `party_a` (buyer / collaboration), `arbiter` (review service). These should not be mixed into a single undifferentiated score.

**Facts before scores.** Contract outcomes are first normalised into explicit reputation events and feature vectors; aggregate scores come from those features. This keeps the system explainable and makes formula changes safe.

**Trust root unchanged.** The protocol layer stores canonical facts; the reputation layer stores derived summaries. The protocol remains the trust root.

## Existing inputs

The current implementation already provides most of what reputation needs:

| Existing field | Reputation use |
|---|---|
| `rating`, `review` | quality evaluation |
| `rework_count` | collaboration friction / delivery stability |
| `delivery_history` | multi-version delivery capability |
| `execution_costs` | efficiency / transparency evidence |
| `snapshot_history` | signed lifecycle completeness |
| `accept`, `cancel`, `dispute` | fulfilment outcome |
| `approvals`, `attestation` | protocol integrity |

The gap is computation, not data.

## Pipeline

```text
Contract -> ReputationEvent -> ReputationFeatureVector -> ReputationProfile
```

### ReputationEvent

A normalised fact record extracted from a contract once it reaches a meaningful lifecycle point.

```typescript
interface ReputationEvent {
  event_id: string
  contract_id: string
  subject: FPAddressRef
  role: "party_a" | "party_b" | "arbiter"

  counterparty?: FPAddressRef
  arbiter?: FPAddressRef

  outcome: "accepted" | "settled" | "cancelled" | "disputed"
  rating?: number
  review?: string

  delivery_count: number
  rework_count: number
  dispute_count: number
  cancel_count: number

  total_cost_usd?: number
  total_input_tokens?: number
  total_output_tokens?: number

  evidence_complete: boolean
  signed_snapshot_count: number

  created_at: number
  source_snapshot_hash: string
}
```

### ReputationFeatureVector

A normalised feature vector used for scoring.

```typescript
interface ReputationFeatureVector {
  quality_score: number
  reliability_score: number
  collaboration_score: number
  efficiency_score: number
  integrity_score: number

  confidence_weight: number
  recency_weight: number
}
```

### ReputationProfile

The aggregate view for one entity in one role.

```typescript
interface ReputationProfile {
  subject: FPAddressRef
  role: "party_a" | "party_b" | "arbiter"

  overall_score: number
  confidence: number
  sample_size: number

  quality_score: number
  reliability_score: number
  collaboration_score: number
  efficiency_score: number
  integrity_score: number

  recent_events: ReputationEvent[]
  updated_at: number
}
```

## Role-specific reputation

### Vendor reputation (`party_b`)

The most important reputation type for outsourcing and marketplace scenarios.

| Dimension | Source | Meaning |
|---|---|---|
| Quality | `rating`, `review`, `accept` | Was the final delivery accepted and well reviewed? |
| Reliability | `cancel`, `dispute`, final lifecycle state | Does the vendor consistently complete contracts? |
| Collaboration | `rework_count`, multi-version convergence | How costly is the collaboration loop? |
| Efficiency | `delivery_count`, `execution_costs` | How efficiently does the vendor deliver? |
| Integrity | `snapshot_history`, `attestation`, `artifacts` | Is the delivery chain complete and verifiable? |

Initial weighted formula:

```text
vendor_contract_score =
  0.35 * quality
+ 0.25 * reliability
+ 0.20 * collaboration
+ 0.10 * efficiency
+ 0.10 * integrity
```

### Buyer reputation (`party_a`)

Buyers also affect collaboration quality. A separate profile.

| Dimension | Source | Meaning |
|---|---|---|
| Fairness | rating / review consistency | Are evaluations proportional to the signed lifecycle? |
| Stability | cancel / dispute frequency | Is the buyer stable or prone to breaking contracts? |
| Collaboration | rework behaviour, final acceptance | Does the buyer help close work cleanly? |
| Integrity | signed-chain compliance | Does the buyer operate within protocol rules? |

### Arbiter reputation (`arbiter`)

This is not transaction reputation — it is review-service reputation.

| Dimension | Source |
|---|---|
| Signature integrity | attestation completeness |
| Protocol correctness | validation behaviour, error handling |
| Availability | successful progression of signed transitions |

## Feature extraction

Start with closed (or near-closed) contracts. Scoring noisy in-flight contracts is not worth the complexity.

### Vendor — initial rules

```text
quality:
  if rating exists       -> rating / 5
  else if accepted       -> 0.7
  else                   -> lower neutral fallback

reliability:
  settled / settling / accepted -> 1.0
  disputed                       -> 0.2
  cancelled                      -> 0.3

collaboration:
  1 - min(rework_count / max_rework_count, 1)

efficiency:
  fewer delivery loops and reasonable execution-cost footprints score higher

integrity:
  snapshot history exists
  attestation exists
  delivery evidence exists
  artifacts exist
```

### Buyer — initial rules

```text
fairness:
  high when the buyer completes accept / rate with evidence-backed review

stability:
  lower when the buyer frequently cancels or disputes

collaboration:
  higher when rework loops are finite and eventually converge to accept
```

## Safeguards

A reputation system is easy to game if the trust model is weak. The following constraints are required.

**Only signed facts count.** Unsigned local state, chat drafts, and UI-only data never contribute.

**Prefer closed-loop events.** Only contracts that have reached one of `accept`, `rate`, `settling`, `settled`, `cancelled`, `disputed` produce events.

**Counterparty weight caps.** A single counterparty pair must not dominate a profile. Example policy: at most 30% of total weight from any one counterparty.

**Confidence, not just score.** One completed 5-star contract is not equivalent to a long, trusted history. Every profile must include `overall_score`, `confidence`, and `sample_size`.

**Time decay.** Recent contracts matter more than old ones. The model should be built with recency weighting in mind even if early implementations defer it.

## Computation model

Two stages, both deterministic and explainable:

**Stage 1 — Contract → ReputationEvent.** A deterministic extractor walks a signed contract and emits one or more normalised events.

**Stage 2 — ReputationEvent → ReputationProfile.** An aggregator computes per-role profiles for each subject.

Determinism is what makes the UI auditable — a user (or arbitrator) can ask "why is this score what it is?" and the system can show the exact contracts, events, and weights that produced it.

## Layered ownership

| Layer | Responsibility |
|---|---|
| Protocol layer | Signed contract facts |
| Reputation extractor | `Contract → ReputationEvent` |
| Reputation aggregator | `ReputationEvent → ReputationProfile` |
| UI layer | Display scores, evidence, confidence |
