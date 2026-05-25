# Foundation Protocol

[English](README.md) | [中文](README.zh.md) | 한국어 | [日本語](README.ja.md) | [Español](README.es.md) | [Tiếng Việt](README.vi.md)

[![GitHub Stars](https://img.shields.io/github/stars/FoundationAgents/foundation-protocol)](https://github.com/FoundationAgents/foundation-protocol) [![License](https://img.shields.io/github/license/FoundationAgents/foundation-protocol)](LICENSE)

다중 엔티티 AI 협업을 위한 Python 런타임 — 에이전트, 인간, 도구가 하나의 프로토콜 레이어에서 함께 작동합니다.

> [AI-Link-Net](https://github.com/FoundationAgents/ai-link-net)은 이 프로토콜 위에 구축된 풀스택 애플리케이션입니다.

## 특징

- **통합 엔티티 모델** — 에이전트, 인간, 도구, 서비스가 공통 ID 및 주소 체계를 공유
- **다자간 세션** — 엄격한 생명주기 관리와 이벤트 리플레이를 갖춘 구조화된 협업
- **정책 및 거버넌스** — 신뢰와 접근 제어를 위한 체크포인트 훅 및 출처 기록
- **거래 및 결제** — 상태 머신 기반의 계약, 에스크로, 정산 및 분쟁 해결
- **페더레이션** — 분산 호스트 노드 간 로컬 및 원격 엔티티 라우팅

## 설치

git 의존성으로 설치:

```bash
pip install "foundation-protocol @ git+https://github.com/FoundationAgents/foundation-protocol.git"
```

## 사용법

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

크로스 호스트 메시징, MCP 도구 통합, 거래 워크플로우 등 더 많은 시나리오는 [`example/`](example/) 디렉토리를 참고하세요.

## 문서

- [프로토콜 사양 (Draft)](docs/foundation-protocol-spec-draft.md)
- [체크포인트 설계](docs/checkpoint-design.md)
- [거래 및 결제 프로토콜](docs/Trade&Trust-Payment-Protocol.md)

## 라이선스

MIT
