# Trade&Trust Reputation System Design

## 0. Team Discussion Checklist

This section is intended to help the team quickly align on the V1 scope before diving into detailed formulas.

Recommended questions to decide in the meeting:

1. Should V1 compute only `party_b` vendor reputation, or also expose a lightweight buyer profile?
2. Should reputation start contributing at `accept`, or only after `rate`?
3. Should `execution_costs` affect the score itself, or only serve as transparency evidence in V1?
4. Should `dispute` immediately count as a strong negative, or stay neutral until dispute resolution exists?
5. Should reputation remain an app-layer derived view in V1, or do we want a protocol-level object later?

Recommended V1 answer set:

- compute `party_b` only
- count signed `accept`, `rate`, `settling`, `settled`, `cancelled`, `disputed`
- show `execution_costs` as evidence, with only light scoring influence
- keep reputation app-layer derived

## 1. Purpose

This document proposes a reputation system built on top of the existing Trade & Trust protocol.

The key idea is:

- `Trust` answers whether a contract fact is authentic and independently verifiable.
- `Rating` answers how one counterparty evaluated one contract outcome.
- `Reputation` answers how an entity has performed across many contracts over time.

This design is intentionally protocol-first and lightweight on infrastructure. It assumes the existing signed contract snapshots, approvals, deliveries, execution costs, and Arbiter attestations are the source of truth.

## 2. Problem Statement

The current implementation already records high-value trust evidence:

- signed snapshot history
- approvals
- delivery evidence
- execution costs
- accept / rework / cancel / dispute / rate outcomes
- Arbiter attestation

However, the system still lacks a derived layer that can answer questions such as:

- Which vendor is more reliable?
- Which vendor usually needs fewer rework loops?
- Which counterparties are fair and stable to work with?
- How can a market or portal rank or filter entities using protocol-backed evidence?

The reputation system should solve this without weakening the protocol guarantees or introducing opaque scoring logic.

## 3. Design Principles

### 3.1 Protocol Facts First

Reputation must be derived only from Arbiter-signed contract facts, not from arbitrary chat text or client-only UI state.

### 3.2 Separate Roles

Reputation should be computed per role:

- `party_b`: delivery / vendor reputation
- `party_a`: buyer / collaboration reputation
- `arbiter`: review / signing service reputation

These should not be mixed into a single undifferentiated score.

### 3.3 Facts Before Scores

We first normalize contract outcomes into explicit reputation events and feature vectors, then compute aggregate scores from those features.

This keeps the system explainable and makes later formula changes safer.

### 3.4 Protocol Layer vs Reputation Layer

- The protocol layer stores the canonical facts.
- The reputation layer stores derived summaries and aggregates.

The protocol remains the trust root. Reputation is a computed view over that root.

## 4. Existing Inputs

The current Trade & Trust implementation already provides most of the raw inputs needed for reputation.

| Existing field | Reputation use |
|---|---|
| `rating`, `review` | Quality evaluation |
| `rework_count` | Collaboration friction / delivery stability |
| `delivery_history` | Multi-version delivery capability |
| `execution_costs` | Efficiency / transparency evidence |
| `snapshot_history` | Signed lifecycle completeness |
| `accept`, `cancel`, `dispute` | Fulfillment outcome |
| `approvals`, `attestation` | Protocol integrity |

Current gap:

- We have `reputation evidence`.
- We do not yet have `reputation computation`.

## 5. Reputation Layer Overview

The proposed reputation pipeline is:

```text
Contract -> ReputationEvent -> ReputationFeatureVector -> ReputationProfile
```

### 5.1 ReputationEvent

A normalized fact record extracted from a contract once it reaches a meaningful lifecycle point.

Suggested shape:

```ts
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

### 5.2 ReputationFeatureVector

A normalized feature vector used for scoring.

```ts
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

### 5.3 ReputationProfile

The aggregate reputation view for one entity in one role.

```ts
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

## 6. Role-Specific Reputation

### 6.1 Vendor Reputation (`party_b`)

This is the first and most important reputation type for the current outsourcing and market scenarios.

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

### 6.2 Buyer Reputation (`party_a`)

Buyers also affect collaboration quality and should eventually receive a separate profile.

| Dimension | Source | Meaning |
|---|---|---|
| Fairness | rating/review consistency | Are evaluations proportional to the actual signed lifecycle? |
| Stability | cancel/dispute frequency | Is the buyer stable or prone to breaking contracts? |
| Collaboration | rework behavior, final acceptance | Does the buyer help close work cleanly? |
| Integrity | signed-chain compliance | Does the buyer operate within protocol rules? |

### 6.3 Arbiter Reputation (`arbiter`)

Arbiter reputation is not transaction reputation. It is review-service reputation.

| Dimension | Source |
|---|---|
| Signature integrity | attestation completeness |
| Protocol correctness | validation behavior, error handling |
| Availability | successful progression of signed transitions |

## 7. Feature Extraction

We should start with closed or near-closed contract states rather than trying to score noisy in-flight contracts.

### 7.1 Vendor Feature Extraction

Suggested initial rules:

```text
quality:
  if rating exists -> rating / 5
  else if accepted -> 0.7
  else -> lower neutral fallback

reliability:
  settled / settling / accepted -> 1.0
  disputed -> 0.2
  cancelled -> 0.3

collaboration:
  1 - min(rework_count / max_rework_count, 1)

efficiency:
  initially coarse; fewer delivery loops and reasonable execution-cost footprints score higher

integrity:
  snapshot history exists
  attestation exists
  delivery evidence exists
  artifacts exist
```

### 7.2 Buyer Feature Extraction

Suggested initial rules:

```text
fairness:
  high when the buyer completes accept / rate with evidence-backed review

stability:
  lower when the buyer frequently cancels or disputes

collaboration:
  higher when rework loops are finite and eventually converge to accept
```

## 8. Anti-Abuse and Trust Safeguards

Reputation systems are easy to game if the trust model is weak. The following constraints are required.

### 8.1 Only Signed Facts Count

Only Arbiter-signed contract facts may contribute to reputation.

Unsigned local state, chat drafts, and UI-only data must never affect scores.

### 8.2 Prefer Closed-Loop Events

V1 should only use events extracted from contracts that reached one of:

- `accept`
- `rate`
- `settling`
- `settled`
- `cancelled`
- `disputed`

### 8.3 Counterparty Weight Caps

One counterparty pair must not be able to dominate a reputation profile.

Example policy:

- at most 30 percent of total weight from one counterparty

### 8.4 Confidence, Not Just Score

We must not present one completed 5-star contract as equivalent to a long trusted history.

Every profile should include:

- `overall_score`
- `confidence`
- `sample_size`

### 8.5 Time Decay

Recent contracts should matter more than old ones.

V1 can defer this if needed, but the model should be built with recency weighting in mind.

## 9. Computation Model

The initial model should stay simple:

### Stage 1: Contract -> ReputationEvent

A deterministic extractor walks a signed contract and emits one or more normalized events.

### Stage 2: ReputationEvent -> ReputationProfile

An aggregator computes per-role profiles for each subject.

This keeps the implementation explainable and makes the UI easy to justify during audits or disputes.

## 10. Suggested V1 Scope

V1 should be deliberately narrow.

### In Scope

- define `ReputationEvent`
- define `ReputationProfile`
- compute reputation for `party_b` only
- only use signed contract outcomes
- surface vendor reputation in the Portal

### Out of Scope

- buyer reputation
- arbiter service reputation
- market-wide ranking
- advanced time decay
- complex anti-collusion weighting

## 11. Suggested V2 Scope

Once V1 is stable, extend to:

- `party_a` reputation
- `arbiter` service reputation
- time decay
- counterparty weight caps
- market sorting / filtering
- reputation history charts

## 12. UI Integration

### 12.1 Portal

Portal is the natural first surface for vendor reputation.

Suggested UI blocks:

| UI block | Content |
|---|---|
| Vendor Score | overall score + confidence |
| Breakdown | quality / reliability / collaboration / integrity |
| Recent Evidence | latest contributing reputation events |
| Review Notes | latest review / rating excerpts |

### 12.2 Trade

Trade detail can show:

- whether this contract contributes to reputation
- which extracted features it produced

### 12.3 Observer

Observer can optionally show:

- which actor's reputation event changed after a signed transition

## 13. Suggested Data Ownership

| Layer | Responsibility |
|---|---|
| Protocol layer | Signed contract facts |
| Reputation extractor | Build `ReputationEvent` from signed facts |
| Reputation aggregator | Build `ReputationProfile` from events |
| UI layer | Show scores, evidence, and confidence |

## 14. Open Questions

These are the main discussion points for the team.

1. Should V1 calculate only `party_b` reputation, or also show a lightweight buyer profile?
2. Should a contract contribute reputation only after `rate`, or already after `accept`?
3. How much of `execution_costs` should influence reputation versus only transparency?
4. Should `dispute` be treated as a hard negative immediately, or only after later resolution logic exists?
5. Do we want a protocol-level `ReputationEvent` object eventually, or keep it app-layer derived for now?

## 15. Recommended Next Step

The next concrete step is to implement a minimal reputation design in code:

1. add `ReputationEvent` and `ReputationProfile` types
2. implement `Contract -> ReputationEvent` extraction for `party_b`
3. implement an aggregator
4. add a simple Portal reputation card

This gives the team a concrete V1 without prematurely committing to a complex market-wide reputation engine.
