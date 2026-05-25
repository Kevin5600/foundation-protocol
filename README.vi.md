# Foundation Protocol

[English](README.md) | [中文](README.zh.md) | [한국어](README.ko.md) | [日本語](README.ja.md) | [Español](README.es.md) | Tiếng Việt

[![GitHub Stars](https://img.shields.io/github/stars/FoundationAgents/foundation-protocol)](https://github.com/FoundationAgents/foundation-protocol) [![License](https://img.shields.io/github/license/FoundationAgents/foundation-protocol)](LICENSE)

Runtime Python cho cộng tác AI đa thực thể — agent, con người và công cụ hoạt động trên một lớp giao thức chung.

> [AI-Link-Net](https://github.com/FoundationAgents/ai-link-net) là ứng dụng full-stack được xây dựng trên giao thức này.

## Tính năng

- **Mô hình thực thể thống nhất** — agent, con người, công cụ và dịch vụ chia sẻ hệ thống định danh và địa chỉ chung
- **Phiên đa bên** — cộng tác có cấu trúc với quản lý vòng đời nghiêm ngặt và phát lại sự kiện
- **Chính sách và quản trị** — hook checkpoint với ghi nhận nguồn gốc cho tin cậy và kiểm soát truy cập
- **Giao dịch và thanh toán** — hợp đồng, ký quỹ, quyết toán và giải quyết tranh chấp qua máy trạng thái
- **Liên bang** — định tuyến thực thể cục bộ và từ xa qua các node host phân tán

## Cài đặt

Cài đặt dưới dạng phụ thuộc git:

```bash
pip install "foundation-protocol @ git+https://github.com/FoundationAgents/foundation-protocol.git"
```

## Sử dụng

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

Xem thư mục [`example/`](example/) để biết thêm các tình huống bao gồm nhắn tin xuyên host, tích hợp công cụ MCP và quy trình giao dịch.

## Tài liệu

- [Đặc tả giao thức (Draft)](docs/foundation-protocol-spec-draft.md)
- [Thiết kế checkpoint](docs/checkpoint-design.md)
- [Giao thức giao dịch và thanh toán](docs/Trade&Trust-Payment-Protocol.md)

## Giấy phép

MIT
