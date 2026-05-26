# Federation & Friends

Foundation Protocol's federation layer connects multiple `Host` nodes; the friendship layer connects two entities across (or within) those hosts. Both are gated by self-presented identity, with cryptographic verification at the message layer.

Implementation: `fp/core/wellknown.py`, `fp/host.py`, `fp/core/checkpoint.py` (`FriendRequestCheckPoint`).

## Host discovery — `.well-known`

When two hosts come into contact, each side exposes a `.well-known` document:

```python
# fp/core/wellknown.py
class HostWellKnown(BaseModel):
    name: str
    uid: HostUid
    url: str
    public_entities: list[EntityCard] = Field(default_factory=list)
```

A `.well-known` contains:

- The host's identity (`name`, `uid`, `url`)
- The list of **public** entity cards the host advertises

It does **not** contain private host credentials, and the current implementation does **not** require the document itself to be signed by an external authority.

For a child host registering with a parent, the parent reads the child's `.well-known` and accepts the declared identity. This is best thought of as an **identity claim**, not an authentication credential. The boundary is documented explicitly under [Known Gaps](known-gaps.md).

## Friend request — first contact between two entities

Entities only accept most message kinds from peers already in their `friends` list (see [Checkpoint Pipeline](checkpoint-and-authorization.md)). Bootstrapping that relationship is the job of the `FRIEND_REQUEST` / `FRIEND_ACCEPT` / `FRIEND_REJECT` message family, handled by `FriendRequestCheckPoint` (`fp/core/checkpoint.py`).

The flow:

```
Alice                                                Bob
  │                                                   │
  │  FRIEND_REQUEST                                   │
  │  payload.sender_card = Alice.entity_card  ───────►│
  │                                                   │
  │           (Bob's mail.unseal extracts             │
  │            sender_card.sign_public_key            │
  │            and verifies signature)                │
  │                                                   │
  │                                                   ├─► if Bob has an owner:
  │                                                   │     queue APPROVAL_REQUEST
  │                                                   │     to the owner
  │                                                   │
  │                                                   ├─► owner approves
  │                                                   │
  │  FRIEND_ACCEPT                                    │
  │◄────────────  payload.sender_card = Bob.entity_card
  │                                                   │
  │  Alice.add_friend(Bob)        Bob.add_friend(Alice)
```

Two security-relevant properties:

1. **The friend request itself is signed.** `Mail.unseal` verifies the signature using the `sign_public_key` embedded in `payload.sender_card`. So while the *identity claim* in `sender_card` is self-asserted, the *binding between that claim and the message* is cryptographic — a third party cannot forge a request that appears to come from a given sender card.

2. **Owner approval is supported.** Entities with an `owner` field can route friend requests through `CallOwnerMixin` (`fp/core/checkpoint.py`) and pause the request as an `APPROVAL_REQUEST` to the owner. The friendship is not established until the owner responds with `APPROVAL_RESPONSE`. See [Checkpoint Pipeline](checkpoint-and-authorization.md) for the resume mechanics.

## Friend list and storage

```python
# fp/entity.py
def add_friend(self, card: EntityCard) -> None:
    """Store a friend's EntityCard, keyed by entity_uid."""
    self.friends[card.entity_uid] = card
```

The friend list is just a dict from `entity_uid` to `EntityCard`. Every subsequent inbound message from that peer will be verified against the `sign_public_key` stored on the card.

## What this gives you, and what it does not

| The runtime guarantees | The runtime does **not** yet guarantee |
|---|---|
| Sender of a friend request cannot be impersonated **once you trust the card** | The card itself is not an externally-attested credential |
| Every subsequent message from a friend is signature-verified | A host serving a `.well-known` is who it claims to be |
| Owner approval, if configured, is mandatory before friendship is recorded | Multi-party confirmation of friendship |

These boundaries are spelled out under [Known Gaps](known-gaps.md).

Next: how every inbound message is gated — [Checkpoint Pipeline](checkpoint-and-authorization.md).
