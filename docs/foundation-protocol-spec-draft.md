# Foundation Protocol (FP) Specification Draft v0.1

Status: Draft  
Authoring basis: `FP-white-paper.pdf` + implementation learnings from current MCP/A2A Python SDKs  
Date: 2026-03-01

## 1. Scope

This document defines the **normative core** of Foundation Protocol (FP):

- Unified entity model across agents/tools/resources/humans/organizations
- Multi-party session and organization semantics
- Eventful collaboration and activity lifecycle
- Ledger-agnostic economy attestations
- Policy/provenance/audit hooks as first-class protocol output

This document does **not** mandate a runtime, scheduler, model provider, payment rail, DID method, or a single transport implementation.

## 2. Design Intent

FP is a **control-plane substrate** for an AI society, not a point protocol for one narrow interaction.

### 2.1 Problems FP solves

1. Fragmented identity and trust semantics across MCP/A2A/UI/commerce stacks.
2. Missing native multi-party organization model (roles/memberships/delegation).
3. Weak shared evidence spine across protocol boundaries.
4. High integration overhead from repeated ad-hoc glue code.
5. Governance and safety handled post-hoc instead of protocol-native.

### 2.2 Non-goals

1. Replacing MCP, A2A, A2UI, DIDComm, or UCP domain semantics.
2. Defining domain-specific vertical business workflows in core.
3. Mandating one ledger or one identity scheme.

## 3. Architecture Planes

FP core is organized as 4+1 planes:

1. Entity & Trust Plane
2. Transport & Routing Plane
3. Interaction & Organization Plane
4. Regulation & Oversight Plane
5. Configuration & Profiles Plane (bindings/extensions/bridges)

Implementations MAY combine planes internally, but wire semantics MUST preserve this separation of responsibilities.

## 4. Normative Conventions

The key words **MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, and **MAY** are to be interpreted as in RFC 2119.

## 5. Core Object Model (Normative)

## 5.1 Entity

An `Entity` is any addressable participant.

```json
{
  "entityId": "fp:agent:travel-assistant-123",
  "kind": "agent",
  "displayName": "Travel Assistant",
  "identity": {
    "method": "did:web",
    "issuer": "example.org",
    "keyRefs": ["did:web:example.org#key-1"],
    "version": "2026-03-01"
  },
  "capabilitySummary": {
    "purpose": ["trip-planning", "booking"],
    "riskTags": ["payment", "pii"],
    "schemaHashes": ["sha256:..."],
    "pricePolicyHints": ["per-call", "token-metered"]
  },
  "capabilityRefs": ["https://example.org/capabilities/travel-agent.json"],
  "privacy": {
    "owner": "fp:org:example-travel",
    "defaultVisibility": "restricted",
    "delegationPolicyRef": "policy:delegation/v1"
  },
  "trustRefs": ["attestation:provider-a:score:0.84"]
}
```

Normative rules:

1. `entityId` MUST be globally unique within a deployment trust domain.
2. `kind` MUST be one of: `agent|tool|resource|human|organization|institution|service|ui`.
3. Capability metadata MUST support progressive disclosure (`capabilitySummary` + fetch-by-reference details).
4. `privacy.owner` MUST resolve to an entity of kind `organization|human|institution`.

## 5.2 Organization

An `Organization` is an entity plus governance semantics.

Required capabilities:

1. Role catalog.
2. Membership lifecycle.
3. Delegation constraints.
4. Governance policy references.

## 5.3 Membership and Delegation

`Membership` is a first-class edge:

```json
{
  "membershipId": "mem-001",
  "organizationId": "fp:org:procurement-coop",
  "memberEntityId": "fp:agent:buyer-007",
  "roles": ["buyer"],
  "delegations": [
    {
      "scope": ["invoke:catalog-search", "negotiate:price"],
      "constraints": {"spendLimit": {"currency": "USD", "amount": 2000}},
      "expiresAt": "2026-03-05T00:00:00Z"
    }
  ],
  "status": "active"
}
```

Normative rules:

1. Delegation MUST be scope-bounded and time-bounded for high-risk scopes.
2. Role changes MUST emit auditable events.

## 5.4 Session

A `Session` is a multi-party collaboration container.

```json
{
  "sessionId": "sess-abc",
  "participants": ["fp:agent:a", "fp:agent:b", "fp:human:u1"],
  "roles": {
    "fp:agent:a": ["coordinator"],
    "fp:agent:b": ["provider"],
    "fp:human:u1": ["approver"]
  },
  "policyRef": "policy:session-risk-tier-2",
  "budget": {
    "spendLimit": {"currency": "USD", "amount": 100},
    "tokenLimit": 50000
  },
  "state": "active"
}
```

Session states MUST support at least: `created|active|paused|closing|closed|failed`.

## 5.5 Activity

An `Activity` models long-running or stateful work in a session.

Canonical `ActivityState`:

- `submitted`
- `working`
- `input_required`
- `auth_required`
- `completed`
- `failed`
- `canceled`
- `rejected`

Compatibility note:

- MCP `cancelled` and A2A `canceled` MUST be normalized to `canceled` in FP canonical state.

## 5.6 Event

All reportable actions are typed events.

Required event fields:

- `eventId`
- `eventType`
- `sessionId`
- `activityId` (if applicable)
- `traceId`
- `causationId` (optional)
- `producerEntityId`
- `occurredAt`
- `payload`
- `policyRef` (optional)
- `evidenceRefs` (optional)

## 6. Envelope and Message Families

FP defines an envelope independent of transport.

```json
{
  "fpVersion": "0.1",
  "messageId": "msg-001",
  "family": "FP.INVOKE",
  "traceId": "trace-123",
  "spanId": "span-456",
  "causationId": "msg-000",
  "from": "fp:agent:buyer",
  "to": "fp:agent:seller",
  "sessionId": "sess-abc",
  "activityId": "act-1",
  "sentAt": "2026-03-01T12:00:00Z",
  "ttlMs": 30000,
  "extensions": ["urn:fp:ext:risk-scoring:v1"],
  "policyRef": "policy:purchase-tier-2",
  "payload": {}
}
```

Supported family anchors:

1. `FP.MSG` (informational messages)
2. `FP.SHARE` (data/resource sharing)
3. `FP.INVOKE` (action invocation)
4. `FP.EVENT` (stream/update emission)
5. `FP.RECEIPT` (metering/delivery attestation)
6. `FP.SETTLE` (settlement reference/confirmation)
7. `FP.NEGOTIATE` (proposal/counterproposal/agreement)
8. `FP.DISPUTE` (challenge/revocation/escalation)

Normative rules:

1. Every non-notification message MUST carry `messageId` and `traceId`.
2. Every settlement/dispute message MUST reference at least one receipt or evidence record.

## 7. Protocol Methods (Core JSON-RPC Binding)

FP core method namespace is `fp/*`.

## 7.1 Handshake

1. `fp/initialize`
2. `fp/initialized` (notification)
3. `fp/ping`

`fp/initialize` request MUST include:

- `supportedVersions`
- `entityCardRef` or inline compact card
- `capabilities`
- `supportedProfiles`
- `supportedExtensions`
- `authSchemes`

Version negotiation:

1. Parties MUST choose the highest mutually supported version.
2. If no intersection exists, return `FP_VERSION_UNSUPPORTED`.

## 7.2 Entity and Organization

1. `fp/entities.get`
2. `fp/entities.search`
3. `fp/orgs.create`
4. `fp/orgs.get`
5. `fp/orgs.members.add`
6. `fp/orgs.members.remove`
7. `fp/orgs.roles.grant`
8. `fp/orgs.roles.revoke`

## 7.3 Session Lifecycle

1. `fp/sessions.create`
2. `fp/sessions.join`
3. `fp/sessions.update`
4. `fp/sessions.leave`
5. `fp/sessions.close`
6. `fp/sessions.get`

## 7.4 Activity Lifecycle

1. `fp/activities.start`
2. `fp/activities.update`
3. `fp/activities.get`
4. `fp/activities.cancel`
5. `fp/activities.result`
6. `fp/activities.list`

## 7.5 Event Streaming and Resumption

1. `fp/events.stream`
2. `fp/events.resubscribe`
3. `fp/events.ack`
4. `fp/events.pushConfig.set`
5. `fp/events.pushConfig.get`
6. `fp/events.pushConfig.list`
7. `fp/events.pushConfig.delete`

Design basis:

- `stream + resubscribe + push config` is retained because A2A implementations prove this is necessary for long-running workloads.
- `last-event-id` style replay semantics are retained because MCP Streamable HTTP implementations prove this is necessary for resilient delivery.

## 8. Transport Binding Requirements

FP core is transport-agnostic. A compliant implementation MUST provide at least one binding profile.

## 8.1 Required HTTP Binding Properties

If HTTP binding is implemented, it MUST support:

1. Request-response for control methods.
2. Streaming updates (SSE or equivalent).
3. Session correlation header: `fp-session-id`.
4. Protocol version header: `fp-protocol-version`.
5. Resumption token support (`last-event-id` equivalent).

## 8.2 Extension Header

HTTP extension activation header SHOULD be `X-FP-Extensions` (comma-separated URIs).

## 9. Backpressure, Ordering, and Delivery

1. Event streams MUST provide monotonic ordering within `(sessionId, activityId, producerEntityId)`.
2. Consumers MUST be able to signal backpressure.
3. Producers MUST honor backpressure or return explicit overflow error.
4. Resubscribe replay MUST be idempotent for duplicate delivery.

## 10. Economy Primitives (Ledger-Agnostic)

## 10.1 Metering

A meter record MUST include:

- `meterId`
- `subject` (`sessionId/activityId/entity`)
- `unit` (`token|ms|byte|call|custom`)
- `quantity`
- `meteredAt`
- `meteringPolicyRef`

## 10.2 Receipt

`FP.RECEIPT` MUST bind:

- referenced invocation/activity
- metering summary
- provider identity
- integrity proof (signature/hash)

## 10.3 Settlement

`FP.SETTLE` MUST carry:

- receipt references
- settlement reference (rail-specific URI/hash)
- amount and currency (if monetary)
- settlement status

## 10.4 Dispute

`FP.DISPUTE` MUST support:

- target references (receipt/settlement/activity)
- reason code
- claimant
- evidence references
- lifecycle state

## 11. Regulation, Oversight, and Provenance

FP defines policy and provenance as protocol data, not log-side artifacts.

## 11.1 Policy Enforcement Points (PEP)

Implementations SHOULD support PEP hooks at minimum:

1. Before high-risk invoke (`PRE_INVOKE`)
2. Before settlement (`PRE_SETTLE`)
3. Before delegation/role changes (`PRE_ROLE_CHANGE`)
4. On critical emitted events (`POST_EVENT_AUDIT`)

## 11.2 Provenance

A provenance record SHOULD include:

- `recordId`
- subject references
- input digest references
- applied policy refs
- decision outcome
- signer/verifier refs
- timestamp

## 11.3 Portable Audit

Audit consumers MUST be able to validate decisions from references/hashes without requiring raw sensitive payload.

## 12. Profiles and Extensions

## 12.1 Profile Model

A profile binds core FP semantics to concrete choices:

- transport
- identity/auth
- codec
- security controls
- extension set

Profile identifiers SHOULD be URI-like, e.g., `urn:fp:profile:http-sse-oauth2:v1`.

## 12.2 Extension Rules

1. Extensions MUST be URI identified.
2. Unknown optional extensions MAY be ignored.
3. Unknown required extensions MUST fail fast with explicit error.

## 13. Bridge Profiles

## 13.1 FP-MCP Bridge (Required Mappings)

1. MCP server/tool/resource/prompt endpoints map to FP entities and capabilities.
2. `tools/call` maps to `FP.INVOKE` + activity/event correlation.
3. MCP progress and notifications map to `FP.EVENT`.
4. MCP `sampling/createMessage`, `elicitation/create`, and `roots/list` MUST preserve reverse-request trace links in FP envelope.
5. MCP task experimental methods map to FP activities with explicit experimental flag.

## 13.2 FP-A2A Bridge (Required Mappings)

1. A2A `message/send` and `message/stream` map to FP message/activity flows.
2. A2A task states map to FP canonical state set.
3. A2A task streaming events map to `FP.EVENT` with `status-update` and `artifact-update` types.
4. A2A push notification config methods map to `fp/events.pushConfig.*`.
5. A2A `agent/getAuthenticatedExtendedCard` maps to FP entity detail expansion.
6. A2A extension header `X-A2A-Extensions` maps to `X-FP-Extensions` at bridge boundaries.

Bridge invariant:

- A bridge MUST preserve `traceId` lineage and MUST NOT drop policy/evidence references when present.

## 14. Error Model

FP error object:

```json
{
  "code": "FP_POLICY_DENIED",
  "message": "Settlement blocked by policy",
  "details": {
    "policyRef": "policy:finance/settlement-v3",
    "decisionId": "dec-778"
  },
  "retryable": false
}
```

Minimum standard codes:

1. `FP_VERSION_UNSUPPORTED`
2. `FP_AUTH_REQUIRED`
3. `FP_AUTHZ_DENIED`
4. `FP_POLICY_DENIED`
5. `FP_INVALID_STATE_TRANSITION`
6. `FP_NOT_FOUND`
7. `FP_RATE_LIMITED`
8. `FP_BACKPRESSURE`
9. `FP_EXTENSION_REQUIRED`
10. `FP_INTERNAL_ERROR`

Bindings MAY map to JSON-RPC numeric ranges or gRPC/HTTP status codes, but semantic code strings MUST be preserved.

## 15. Security and Privacy Requirements

1. All networked bindings MUST support transport confidentiality/integrity (e.g., TLS).
2. High-risk operations MUST require authenticated entity identity.
3. Delegations MUST be least-privilege and revocable.
4. Sensitive payload SHOULD use reference-based disclosure and access-controlled retrieval.
5. Provenance/evidence metadata MUST avoid leaking unnecessary secret content.

## 16. Conformance Levels

## 16.1 FP-Core

MUST implement:

- Entity model
- Session + activity + event semantics
- Handshake/version negotiation
- Basic policy reference carriage

## 16.2 FP-Core+Bridge

MUST additionally implement at least one bridge profile (MCP or A2A) and trace-preserving mapping.

## 16.3 FP-Governed

MUST additionally implement:

- PEP enforcement hooks
- Provenance emission
- Receipt + settlement + dispute semantics

## 17. Recommended Reference Test Matrix

1. Version negotiation mismatch/overlap cases.
2. Session lifecycle state transitions.
3. Activity state transitions (including interrupt states).
4. Streaming + resubscribe replay correctness.
5. Push config CRUD behavior.
6. Bridge mapping parity (MCP and A2A method families).
7. Policy denied path with auditable evidence.
8. Receipt/settlement/dispute round-trip integrity.

## 18. Open Issues (for v0.2)

1. Canonical event codec registry governance.
2. Cross-domain trust attestation interoperability profile.
3. Standard budget semantics for mixed token/fiat/quota environments.
4. Portable proof format for policy decisions.
5. Recommended secure defaults per deployment tier (local, enterprise, public web).

---

### Appendix A: Minimal Example Flow (Cross-Protocol)

1. `fp/initialize` between coordinator agent and bridge gateway.
2. `fp/sessions.create` with participants (user agent, tool agent, seller agent) and policy ref.
3. MCP tool call through bridge => `FP.INVOKE` + `FP.EVENT(progress)`.
4. A2A delegation through bridge => `FP.EVENT(status-update/artifact-update)`.
5. Provider emits `FP.RECEIPT` (metering + delivery).
6. Consumer emits `FP.SETTLE` with external settlement reference.
7. If mismatch occurs, emit `FP.DISPUTE` with evidence refs.

This flow keeps identity, trace, policy, and evidence coherent across MCP + A2A boundaries.
