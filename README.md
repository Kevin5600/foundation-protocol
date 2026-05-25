# Foundation Protocol

English | [中文](README.zh.md) | [한국어](README.ko.md) | [日本語](README.ja.md) | [Español](README.es.md) | [Tiếng Việt](README.vi.md)

[![GitHub Stars](https://img.shields.io/github/stars/FoundationAgents/foundation-protocol)](https://github.com/FoundationAgents/foundation-protocol) [![License](https://img.shields.io/github/license/FoundationAgents/foundation-protocol)](LICENSE)

A Python runtime for multi-entity AI collaboration — agents, humans, and tools on a shared protocol layer.

> [AI-Link-Net](https://github.com/FoundationAgents/ai-link-net) is a full-stack application built on this protocol.

## Features

- **Unified entity model** — agents, humans, tools, and services share a common identity and addressing system
- **Multi-party sessions** — structured collaboration with strict lifecycle enforcement and event replay
- **Policy & governance** — checkpoint hooks with provenance recording for trust and access control
- **Trade & payment** — contracts, escrow, settlement, and dispute resolution via state machines
- **Federation** — local and remote entity routing across distributed host nodes

## Installation

Install as a git dependency:

```bash
pip install "foundation-protocol @ git+https://github.com/FoundationAgents/foundation-protocol.git"
```

## Usage

```python
import asyncio
from fp import EntityKind, Host, Message, MessageKind

async def main():
    host = Host(name="LocalHost")

    alice = host.register_entity(name="Alice", kind=EntityKind.HUMAN)
    bot = host.register_entity(name="Bot", kind=EntityKind.AGENT)

    await alice.send_message(
        to=bot.entity_card,
        message=Message(kind=MessageKind.TEXT, payload={"text": "Hello!"}),
    )

asyncio.run(main())
```

See the [`example/`](example/) directory for more scenarios including cross-host messaging, MCP tool integration, and trade workflows.

## Documentation

- [Protocol Spec (Draft)](docs/foundation-protocol-spec-draft.md)
- [Checkpoint Design](docs/checkpoint-design.md)
- [Trade & Payment Protocol](docs/Trade&Trust-Payment-Protocol.md)

## License

MIT
