# Message

`Message` is the business payload inside a [Mail](mail.md) envelope. It carries the application-layer semantics — what kind of interaction this is, who the sender is, and what they're trying to do.

Mail handles **how** the message gets delivered. Message handles **what** is delivered. Keeping them separated is what lets FP swap transport or crypto without disturbing application logic, and vice versa.

## Structure

```python
# fp/message.py
class Message(BaseModel, Generic[PayloadT]):
    message_id: str               # UUID — unique, for dedup and reply correlation
    kind: MessageKind             # what kind of interaction
    payload: PayloadT             # typed payload, varies by kind
    metadata: dict[str, Any]      # routing-side metadata (sender_address, reply_to, …)
    fp: str = "0.1"               # protocol version
```

`message_id` is generated client-side and stable for the lifetime of the message. The recipient uses it to dedupe (in case of retry) and to thread replies.

`Message` is generic on the payload type, so `Message[InvokePayload]` and `Message[FriendRequestPayload]` are distinct, statically-typed shapes. The sender's identity is **not** stored on `Message` directly — it's the `Mail` envelope that carries `sender: FPAddress`, and first-contact messages embed the sender's [EntityCard](../security/identity-and-keys.md) inside the payload (see `FriendRequestPayload.sender_card` below).

## MessageKind

```python
class MessageKind(str, Enum):
    INVOKE          = "invoke"           # normal call / message
    ERROR           = "error"            # error response
    FRIEND_REQUEST  = "friend_request"   # initial handshake
    FRIEND_ACCEPT   = "friend_accept"    # friendship confirmed
    FRIEND_REJECT   = "friend_reject"    # friendship declined
    CARBON_COPY     = "carbon_copy"      # owner-observability copy
    # … trade and pay kinds extend this enum
```

The trade and pay subsystems extend the enum with their own kinds (`contract_*`, `pay_*`). The runtime's checkpoint pipeline gates which kinds require an established friendship — see [Checkpoint Pipeline](checkpoint.md).

## Payload types

Each `MessageKind` has a typed payload model. Three representative examples:

```python
# Normal call
class InvokePayload(BaseModel):
    text: str
    session_id: str | None = None       # multi-turn conversation grouping
    method: str | None = None           # bridge methods (e.g. MCP "tools/call")
    params: dict[str, Any] | None = None

# Error
class ErrorPayload(BaseModel):
    error_code: str
    error_message: str
    details: dict[str, Any] | None = None

# Friend request — carries the sender's full card for first contact
class FriendRequestPayload(BaseModel):
    sender_card: EntityCard
    text: str | None = None
```

Typed payloads keep handlers honest — a handler for `INVOKE` can rely on `payload.text` existing without runtime guarding.

## Mail and Message in one picture

```text
┌─────────────────────────────────────────────────┐
│  Mail (envelope)                                │
│   sender:    fp://host-1/alice                  │
│   recipient: [fp://host-2/bob]                  │
│   signature: 0x1a2b3c...                        │
│   status:    received                           │
│   ┌─────────────────────────────────────────┐   │
│   │  Message (content)                      │   │
│   │   message_id:  uuid-123                 │   │
│   │   kind:        INVOKE                   │   │
│   │   payload:                              │   │
│   │     text:       "Hello, Bob!"           │   │
│   │     session_id: session-1               │   │
│   └─────────────────────────────────────────┘   │
└─────────────────────────────────────────────────┘
```

## Why split the layers?

| Concern | Owner |
|---|---|
| Routing | Mail |
| Signing | Mail |
| Encryption | Mail |
| Lifecycle / status | Mail |
| Identity claim (first contact) | `FriendRequestPayload.sender_card` |
| Interaction kind | Message |
| Business payload | Message |
| Reply correlation | Message |

Concrete benefits the project has already cashed in on:

- Transport-layer upgrades (changing curves, swapping the encryption scheme) require no changes to handlers.
- New `MessageKind` values (contract, payment) shipped without touching the routing layer.
- The owner-observability flow ([Carbon Copy](carbon-copy.md)) is a new `MessageKind` — not a special case in the envelope.

## Handlers

When a Message reaches the end of an entity's [checkpoint pipeline](checkpoint.md), it is dispatched to whatever handler the entity was registered with. The runtime ships two building blocks in `fp/handler.py`:

- **`BaseHandler`** — the abstract interface (`async def handle(message)`)
- **`CallbackHandler`** — wraps a plain async callback into a handler

Concrete domain handlers (`HumanHandler`, `AgentHandler` for LLM-backed agents, `MCPHandler` for the MCP bridge) live in the application layer — for example in [AI-Link-Net](https://github.com/FoundationAgents/ai-link-net) — not in the `fp` package. Inside `fp`, registering an entity with `handler=my_callback` is the supported way to plug in custom behavior; the runtime wraps the callback in `CallbackHandler` and invokes it after the checkpoint pipeline finishes.

The bridge between the checkpoint pipeline and the handler runs as the final checkpoint, `HandlerBridgeCheckPoint` (order 900).

Next: [Carbon Copy](carbon-copy.md).
