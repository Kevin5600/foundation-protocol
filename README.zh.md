# Foundation Protocol

[English](README.md) | 中文 | [한국어](README.ko.md) | [日本語](README.ja.md) | [Español](README.es.md) | [Tiếng Việt](README.vi.md)

[![GitHub Stars](https://img.shields.io/github/stars/FoundationAgents/foundation-protocol)](https://github.com/FoundationAgents/foundation-protocol) [![License](https://img.shields.io/github/license/FoundationAgents/foundation-protocol)](LICENSE)

多实体 AI 协作的 Python 运行时 —— 让 Agent、人类和工具在统一协议层上协同工作。

> [AI-Link-Net](https://github.com/FoundationAgents/ai-link-net) 是基于此协议构建的全栈应用。

## 特性

- **统一实体模型** —— Agent、人类、工具和服务共享通用的身份与寻址体系
- **多方会话** —— 结构化协作，严格的生命周期管理与事件回放
- **策略与治理** —— 检查点钩子与溯源记录，用于信任和访问控制
- **交易与支付** —— 合约、托管、结算与争议解决，基于状态机驱动
- **联邦路由** —— 跨分布式 Host 节点的本地与远程实体路由

## 安装

作为 git 依赖安装：

```bash
pip install "foundation-protocol @ git+https://github.com/FoundationAgents/foundation-protocol.git"
```

## 使用

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

更多示例请查看 [`example/`](example/) 目录，包括跨 Host 通信、MCP 工具集成和交易流程。

## 文档

- [协议规范 (Draft)](docs/foundation-protocol-spec-draft.md)
- [检查点设计](docs/checkpoint-design.md)
- [交易与支付协议](docs/Trade&Trust-Payment-Protocol.md)

## 许可证

MIT
