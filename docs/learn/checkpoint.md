# Checkpoint Pipeline & CallOwner

How Foundation Protocol routes incoming mail through a pipeline of
checkpoints, and how those checkpoints escalate to a human owner when a
decision requires human judgement.

## Core Idea

**CallOwner is a generic capability of every checkpoint.** When an entity
receives a message that needs human authorization or input, the relevant
checkpoint forwards the request to the entity's owner.

## Pipeline

Each entity holds an ordered `checkpoints: list[CheckPoint]`. Every inbound
mail flows through it before it reaches the application layer:

```
Mail received → unseal → store in mailbox → _points_checking (pipeline)
  100-199  Session verification
  200-299  Permissions  (FriendCheckPoint, FriendRequestCheckPoint)
  300-399  Rate / content
  400-499  Business validation
  500-599  User-defined
  800-899  Side effects (CarbonCopyCheckpoint)
  900-999  Execution    (ArbiterCheckPoint)
```

## CallOwner Policies

Every checkpoint supports three call-owner policies, conditional on the
entity having an owner:

| Policy | Behaviour |
|---|---|
| `always_pass` | Always pass; never call the owner. The agent decides on its own. |
| `conditional` | Call the owner only when a checkpoint-specific condition is met (e.g. amount above threshold). The condition is defined per checkpoint; reserved for future use. |
| `always_call` | Always call the owner. If no owner is attached, fall back to `always_pass`. |

The current implementation targets the `always_call` policy.

## Where CallOwner Applies

### 1. Friend request

| Field | Value |
|---|---|
| Trigger | `friend_request` received |
| Today | `FriendRequestCheckPoint` hardcodes `approved = True` |
| `action_type` | `require_approval` |
| Description | "{name} wants to add you as a friend" |
| Actions | [Accept] → `friend_accept` / [Reject] → `friend_reject` |
| Auto reply | "Friend request received, awaiting confirmation" |

### 2. Contract invitation

| Field | Value |
|---|---|
| Trigger | `contract_status` with `status=draft` (counterparty drafted a contract awaiting your approval) |
| Today | `ContractApprovalCheckPoint` hardcodes `auto_approve = True` |
| `action_type` | `require_approval` |
| Description | "Contract invitation: {title}, amount ¥{amount}" |
| Actions | [Sign] → `contract_approve` / [Reject] → `contract_reject` |
| Auto reply | "Contract invitation received, awaiting owner review" |

### 3. Delivery acceptance

| Field | Value |
|---|---|
| Trigger | Party A receives `contract_status` with `status=completing` |
| Today | No handling; must use the Trade UI manually |
| `action_type` | `require_approval` |
| Description | "Contract {title} delivered, awaiting acceptance" |
| Actions | [Accept] → `contract_accept` / [Request rework] → `contract_rework` |
| Auto reply | "Delivery received, awaiting owner acceptance" |

### 4. Escrow payment authorization

| Field | Value |
|---|---|
| Trigger | Contract approved; Arbiter is about to freeze funds |
| Today | Funds deducted directly; cancelled if balance insufficient |
| `action_type` | `require_approval` |
| Description | "Contract {title} requires ¥{amount} to be frozen — authorize?" |
| Actions | [Authorize] → allow Arbiter to debit / [Reject] → `contract_cancel` |
| Auto reply | "Payment authorization request received, awaiting owner confirmation" |

### 5. Direct mode — payee provides payment link

| Field | Value |
|---|---|
| Trigger | An agent as payee needs to initiate collection |
| Today | No such flow |
| `action_type` | `require_input` |
| Description | "Contract {title} entered the payment phase — please provide a payment link or QR code" |
| Input | URL or image (base64) |
| Auto reply | — |

### 6. Direct mode — payer executes payment

| Field | Value |
|---|---|
| Trigger | `pay_request` received |
| Today | `PaymentApprovalCheckPoint` has a policy but always passes |
| `action_type` | `require_input` |
| Description | "Payment request received for ¥{amount}" |
| UI | Payment link / QR + an [I have paid] button |
| Auto reply | "Payment request received and forwarded to the owner" |

### 7. Direct mode — payee confirms receipt

| Field | Value |
|---|---|
| Trigger | `pay_claim_completed` received |
| Today | No checkpoint |
| `action_type` | `require_approval` |
| Description | "Counterparty marked ¥{amount} as paid — please confirm receipt" |
| Actions | [Confirm] → `pay_confirm_receipt` / [Dispute] → `pay_dispute` |
| Auto reply | "Payment notification received, awaiting confirmation" |

### 8. Contract rating

| Field | Value |
|---|---|
| Trigger | Contract entered `settling` |
| Today | Must use the Trade UI manually |
| `action_type` | `require_input` |
| Description | "Contract {title} completed — please rate it" |
| Input | Rating (1–5) plus a written review |
| Auto reply | — |

## Message Protocol

Two new message kinds carry the request/response:

- `APPROVAL_REQUEST` — Entity → Owner
- `APPROVAL_RESPONSE` — Owner → Entity

```python
class ApprovalRequestPayload(BaseModel):
    request_id: str
    source_entity_uid: str
    source_entity_name: str
    action_type: str              # "require_approval" | "require_input"
    description: str
    original_kind: str
    original_payload: dict
    available_actions: list[str]  # e.g. ["approve", "reject"]


class ApprovalResponsePayload(BaseModel):
    request_id: str
    action: str                   # "approve" | "reject" | "submit_input"
    input_data: str | None = None
    method: str | None = None
```

## Waiting Strategy

```
call_owner emits an approval_request, then:
  ├── synchronously waits 10s
  │   ├── owner responds within 10s → return OwnerResponse immediately
  │   └── timeout → suspend the message and persist it in pending_approvals
  │
  └── after the timeout, when the owner eventually responds →
      ApprovalResponseCheckPoint picks it up →
      retrieves the suspended message from pending_approvals →
      resumes processing
```

Agent-side message: "Sent to mailbox, awaiting confirmation. You can keep
working on other things — you will be notified when the counterparty replies."

## Implementation

### `CallOwnerMixin`

```python
class CallOwnerMixin:
    call_owner_policy: str = "always_call"  # always_pass | conditional | always_call

    async def call_owner(self, entity, message, mail, action_type, description, ...):
        if self.call_owner_policy == "always_pass" or not entity.owner:
            return OwnerResponse(action="approve")
        # ... emit request, await response, time out, suspend
```

The mixin is added to existing checkpoints — no new checkpoint type is
introduced. A single `call_owner` implementation covers all eight scenarios.

### Frontend — a single `ApprovalCard`

One component renders dynamically based on `action_type` plus
`original_kind`, covering every scenario. No per-scenario cards.

## Implementation Steps

1. Define the new message kinds and payloads.
2. Build `CallOwnerMixin` with the wait / timeout / suspend logic.
3. Add `ApprovalResponseCheckPoint` to consume owner responses.
4. Wire `CallOwnerMixin` into the existing checkpoints.
5. Implement the frontend `ApprovalCard` and the `approval_response` send path.
6. Expose `aln set checkpoint` parameters via the CLI.
7. Update the Arbiter so that `settling` in DIRECT mode triggers payment.
8. Add full unit-test coverage.
