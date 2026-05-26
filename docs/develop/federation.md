# Federation

A single `Host` is enough for examples and tests, but most real deployments run multiple hosts — one per process, machine, or trust boundary. **Federation** is FP's term for the parent / child host topology that lets entities on different hosts address each other.

This page walks through the minimal three-host setup used in [`example/case1.py`](https://github.com/FoundationAgents/foundation-protocol/blob/main/example/case1.py): two leaf hosts connected through a shared cloud host.

## The topology

```text
              CloudHost
                  │
        ┌─────────┴─────────┐
   LocalHostA           LocalHostB
        │                   │
      Alice                Bob
```

`CloudHost` is the **parent**; `LocalHostA` and `LocalHostB` are **children**. Mail addressed from `Alice` to `Bob` flows:

```text
Alice → LocalHostA → CloudHost → LocalHostB → Bob
```

A parent host knows about all child hosts that have registered with it; children know only their parent. There is no global directory — discovery walks up to the parent and back down, so the parent is the trust seam for the federation.

## Setting it up

```python
import asyncio

from fp import EntityKind, Host, Message, MessageKind
from fp.message import FriendRequestPayload


async def main():
    cloud = Host(name="CloudHost")
    host_a = Host(name="LocalHostA")
    host_b = Host(name="LocalHostB")

    host_a.set_parent_host(cloud)
    host_b.set_parent_host(cloud)

    alice = host_a.register_entity(name="Alice", kind=EntityKind.HUMAN)
    bob = host_b.register_entity(name="Bob", kind=EntityKind.HUMAN)

    # First contact — Alice introduces herself by card
    await alice.send_message(
        to=bob.entity_card,
        message=Message(
            kind=MessageKind.FRIEND_REQUEST,
            payload=FriendRequestPayload(
                sender_card=alice.entity_card,
                text="Alice wants to be friends",
            ),
        ),
    )
    await asyncio.sleep(0.1)

    # After friendship is established, Alice can send by name
    await alice.send_message(
        to="Bob",
        message=Message(
            kind=MessageKind.INVOKE,
            payload={"text": "Hello, Bob!"},
        ),
    )


asyncio.run(main())
```

The same `Host` API works whether the children are in the same process (as above), separate processes on one machine, or separate machines connected over WebSocket. The transport layer abstracts the difference — federation traffic uses the same signed `Mail` envelope described in [Mail](../learn/mail.md).

## What's actually shared between hosts

A parent host knows about each child's:

- `name` and `uid`
- The URL it accepts connections at (when running across processes)
- The list of public entity cards the child advertises via its `.well-known`

It does **not** automatically know about an entity that has been marked `is_public=False`. Private entities are still routable, but only via direct address (the parent never advertises them on the directory).

## When the recipient is offline

If `Bob`'s host is unreachable when Alice sends, the mail stays in Alice's outbound mailbox with `status=queued`. When the route comes back, the host retries automatically. There is no explicit retry API — you write to the mailbox and the host handles delivery, queueing, and eventual `received` notification.

See [Mail](../learn/mail.md#lifecycle) for the full `MailStatus` lifecycle.

## Cross-process federation

For two hosts in different processes, give each a port:

```python
cloud = Host(name="CloudHost", port=17000)
host_a = Host(name="HostA", port=17001)
host_b = Host(name="HostB", port=17002)

host_a.set_parent_host(cloud)
host_b.set_parent_host(cloud)
```

Each host runs a WebSocket endpoint on its port. Parent / child connections are persistent WebSocket connections — the parent pushes inbound mail to the child as soon as it arrives, and the child reports status changes back. Reconnection is automatic.

## Trust at the federation boundary

`.well-known` is currently a **claim**, not a credential — a child host's identity is self-reported, and the parent does not verify it against an external authority. This is sufficient for development and intranet deployments but should not be treated as strict identity authentication on an open network. See [Known Gaps](../security/known-gaps.md) for the full picture.

Friend requests, on the other hand, *are* cryptographically anchored: every subsequent message from a known friend is signature-verified against the card that was accepted at first contact.
