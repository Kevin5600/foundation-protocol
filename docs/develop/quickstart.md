# Quickstart

This page walks through the smallest possible Foundation Protocol program: one host, two entities, one signed message. It assumes you have already installed the package — see the [Develop overview](index.md) for installation.

## A single host, two entities

A `Host` is a process-local container that owns a set of `Entity` objects, signs and routes mail on their behalf, and persists their state. Entities are the addressable participants — humans, agents, tools, services, or arbiters.

```python
import asyncio

from fp import EntityKind, Host, Message, MessageKind


async def main():
    host = Host(name="LocalHost")

    alice = host.register_entity(name="Alice", kind=EntityKind.HUMAN)
    bot = host.register_entity(name="Bot", kind=EntityKind.AGENT)

    await alice.send_message(
        to=bot.entity_card,
        message=Message(
            kind=MessageKind.INVOKE,
            payload={"text": "Hello, bot."},
        ),
    )


asyncio.run(main())
```

What happens behind that one call:

1. Alice's entity builds a `Message`, seals it inside a signed `Mail`, and writes it to her outbound mailbox.
2. The host routes the mail to Bob (same host, so the hand-off is in-process).
3. Bob's checkpoint pipeline runs — see [Checkpoint Pipeline](../learn/checkpoint.md) for the full chain.
4. Whatever handler was attached to Bob receives the message (here, the default no-op — to actually do something on receipt, see [Adding a custom callback](#adding-a-custom-callback) below).

## EntityKind — choosing the right kind

`EntityKind` (in `fp/core/base.py`) is a free-form classifier. It tags what *role* an entity plays so application layers can pick the right handler, but the runtime itself does not bundle any domain-specific handlers — every entity uses the same checkpoint pipeline and dispatches to whatever handler you provide.

| Kind | When to use |
|---|---|
| `HUMAN` | A person operating through a UI or CLI |
| `AGENT` | An LLM-driven actor |
| `TOOL` | A function or MCP server bridged into FP |
| `RESOURCE` | Static data, fetched on demand |
| `SERVICE` | A long-running internal service |
| `ARBITER` | The trade arbiter that owns contract state (pairs with `ArbiterCheckPoint`) |
| `ORGANIZATION` | A multi-member entity (governance / membership) |

Pass `handler=callable` to `register_entity` to attach business logic. Concrete LLM-aware handlers (Claude, Codex, MCP bridges) live in application layers like [AI-Link-Net](https://github.com/FoundationAgents/ai-link-net), not in the `fp` package.

## Adding a custom callback

A callable handler is the fastest way to attach business logic to an entity without writing a `BaseHandler` subclass:

```python
import asyncio

from fp import Host, Message, MessageKind
from fp.core.base import EntityKind

received: asyncio.Queue[Message] = asyncio.Queue()


async def agent_callback(msg: Message) -> None:
    await received.put(msg)


host = Host(name="TestHost", port=17001)
agent = host.register_entity(
    name="echo-agent",
    kind=EntityKind.AGENT,
    handler=agent_callback,
)
```

The callback receives the `Message` after the checkpoint pipeline has accepted it. It runs in the host's event loop, so anything blocking should be offloaded.

## Sending by name vs. by card

`send_message` accepts two forms of recipient:

```python
# By card — fully qualified, includes the public keys
await alice.send_message(to=bob.entity_card, message=...)

# By name — looked up via the host's directory; the recipient must already be a friend
await alice.send_message(to="Bob", message=...)
```

First contact between two entities always goes by card and uses `MessageKind.FRIEND_REQUEST` — the recipient cannot verify a signature against a key it has never seen, so the card travels inside the friend-request payload. See [Federation & Friends](../security/federation-and-friends.md) for the full handshake.

## Where state goes

Each host persists entity state, mailboxes, and host metadata under `~/.fp/` by default — JSONL for mailboxes, JSON for entity cards, host descriptors, and friend tables. To override the location:

```python
import os
os.environ["FP_HOME"] = "/tmp/my-fp-test"
```

The full directory layout is documented in [Storage](storage.md). Mailboxes are append-only, so any backup tool that can copy a directory works.

## Next steps

- [Federation](federation.md) — wire two hosts together so entities on different processes can talk.
- [MCP Bridge](mcp-bridge.md) — register a stdio or HTTP MCP server as an FP entity.
- [Trade Workflows](trade-workflows.md) — run a full ESCROW contract end-to-end.
