# Checkpoint Pipeline

Every inbound `Message` walks an ordered pipeline of **checkpoints** before reaching a handler. A checkpoint can validate, reject, or take over handling of a message — and policy-bearing checkpoints can request out-of-band approval from the entity's owner.

Implementation: `fp/core/checkpoint.py`, `fp/entity.py`.

## Pipeline order

Checkpoints declare a numeric `order` field. The entity sorts them ascending and runs them in turn:

| Range | Role |
|---|---|
| `100–199` | Session / lifecycle |
| `200–299` | Relationship & permission (e.g. `FriendCheckPoint`) |
| `300–399` | Rate limiting |
| `400–499` | Business validation (e.g. `PaymentCheckPoint`) |
| `500–599` | User-defined policy |
| `800–899` | Side effects (audit, logging) |
| `900–999` | Execution (handler bridge, callbacks) |

`Entity.add_checkpoint` re-sorts the list on insertion (`fp/entity.py`).

## Built-in checkpoints

| Class | Order range | What it does |
|---|---|---|
| `SessionCheckPoint` | 100 | Validates session state |
| `ApprovalResponseCheckPoint` | 150 | Routes inbound `APPROVAL_RESPONSE` messages back to the original paused flow |
| `FriendCheckPoint` | 200 | Rejects messages from peers not in `entity.friends`. Returns `NOT_FRIEND` |
| `FriendRequestCheckPoint` | 200 | Handles inbound `FRIEND_REQUEST` — optional owner approval |
| `PaymentCheckPoint` | 400 | Requires `payment_proof` + `payment_verified` in message metadata |
| `RateLimitCheckPoint` | 300 | Sliding 1-minute window, default 60 messages per sender |
| `ContentLengthCheckPoint` | 400 | Rejects messages over a max character length (default 10000) |
| `HandlerBridgeCheckPoint` | 900 | Dispatches to the user-registered handler for the message kind |
| `CallbackCheckPoint` | 900 | Invokes registered callbacks |

## CheckPointResult

Each checkpoint returns one of three results:

```python
CheckPointResult.success()          # validation passed, continue pipeline
CheckPointResult.handled_success()  # this checkpoint owned the message, stop pipeline
CheckPointResult.failure(code, msg) # reject with an error code, stop pipeline
```

`handled_success` is how `FriendRequestCheckPoint` and `ApprovalResponseCheckPoint` short-circuit the pipeline once they have taken responsibility for a message.

## Owner approval — pausing the pipeline

Sensitive flows (friend request, contract invitation, payment authorization, contract acceptance, rating) all extend `CallOwnerMixin` (`fp/core/checkpoint.py`). When a `CallOwnerMixin` checkpoint runs:

1. It records a `PendingApproval` describing the original message and the checkpoint name.
2. It sends an `APPROVAL_REQUEST` message to the entity's owner.
3. It returns `handled_success` — the pipeline stops; the inbound message is not delivered to a handler.

When the owner replies with `APPROVAL_RESPONSE`, `ApprovalResponseCheckPoint` looks up the pending entry and resumes the original flow (e.g. continues the friend-request handler, or sends the contract decision to the arbiter). `_checkpoint_name_for_original_kind` (`fp/core/checkpoint.py`) tracks the mapping.

Effectively, owner approval turns the linear pipeline into a **suspendable state machine** for human-in-the-loop decisions.

## Trust enforcement by the pipeline

The friendship checkpoint is the runtime's first line of trust enforcement. For the kinds of messages that require friendship (the `FRIENDSHIP_REQUIRED_KINDS` set in `fp/core/checkpoint.py` — covering `INVOKE`, `HEARTBEAT`, `contract_*`, `pay_*`), `FriendCheckPoint` rejects anything from a non-friend with `NOT_FRIEND`. A peer cannot send invocations or trade messages until both sides have completed a signed friend handshake.

`Mail` signature verification happens **before** the pipeline — at `Entity.receive_mail` (`fp/entity.py`), via `mail.unseal()`. Signature failure means the mail is dropped without ever reaching a checkpoint.

## Contract authorization — role × status

Inside the trade subsystem, an additional authorization step gates contract-lifecycle actions:

```python
# fp/trade/authorize.py
def authorize(action: str, sender: FPAddress, contract: Contract) -> AuthorizeResult:
    role = _role_for(sender, contract)  # party_a | party_b | arbiter | stranger
    ...
```

The function maps the sender's address to a role on the contract and gates each action by role and current contract status:

| Action | Allowed role | Required status |
|---|---|---|
| `amend`, `approve`, `reject` | `party_a` or `party_b` | `DRAFT` |
| `complete` | `party_b` | `ACTIVE` |
| `accept`, `rework` | `party_a` | `COMPLETING` |
| `rate` | `party_a` | `SETTLING` or `SETTLED` |
| `cancel`, `dispute` | `party_a` or `party_b` | any |
| `activate`, `settle`, `timeout` | `arbiter` only | any |

Strangers (sender address matches no party) are rejected outright. This is the only role-aware authorization currently in the runtime — there is no general entity-wide RBAC model.

Next: [Known Gaps](known-gaps.md).
