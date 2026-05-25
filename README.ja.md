# Foundation Protocol

[English](README.md) | [中文](README.zh.md) | [한국어](README.ko.md) | 日本語 | [Español](README.es.md) | [Tiếng Việt](README.vi.md)

[![GitHub Stars](https://img.shields.io/github/stars/FoundationAgents/foundation-protocol)](https://github.com/FoundationAgents/foundation-protocol) [![License](https://img.shields.io/github/license/FoundationAgents/foundation-protocol)](LICENSE)

マルチエンティティAIコラボレーションのためのPythonランタイム — エージェント、人間、ツールが共通のプロトコルレイヤー上で連携します。

> [AI-Link-Net](https://github.com/FoundationAgents/ai-link-net)は、このプロトコル上に構築されたフルスタックアプリケーションです。

## 特徴

- **統一エンティティモデル** — エージェント、人間、ツール、サービスが共通のIDとアドレス体系を共有
- **マルチパーティセッション** — 厳格なライフサイクル管理とイベントリプレイによる構造化コラボレーション
- **ポリシーとガバナンス** — 信頼とアクセス制御のためのチェックポイントフックと来歴記録
- **取引と決済** — ステートマシンによる契約、エスクロー、精算、紛争解決
- **フェデレーション** — 分散ホストノード間のローカル・リモートエンティティルーティング

## インストール

git依存としてインストール：

```bash
pip install "foundation-protocol @ git+https://github.com/FoundationAgents/foundation-protocol.git"
```

## 使い方

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

クロスホストメッセージング、MCPツール統合、取引ワークフローなどのシナリオは[`example/`](example/)ディレクトリをご覧ください。

## ドキュメント

- [プロトコル仕様 (Draft)](docs/foundation-protocol-spec-draft.md)
- [チェックポイント設計](docs/checkpoint-design.md)
- [取引・決済プロトコル](docs/Trade&Trust-Payment-Protocol.md)

## ライセンス

MIT
