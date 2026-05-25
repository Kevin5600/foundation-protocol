"""MCP entity 端到端流程测试。

场景：
  - 本地 Host 上注册一个 MCP entity（kind=tool），指向 mcp_server_echo.py
  - 同一 Host 上注册一个 caller entity（kind=human），用 callback 捕获响应
  - Caller 发送 INVOKE 消息（调用 echo 工具）给 MCP entity
  - 验证 MCP entity 通过 MCPHandler → StdioMCPClient → echo server 处理后，响应正确回到 caller
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# 确保从项目根目录运行
sys.path.insert(0, str(Path(__file__).parent.parent))

from unittest.mock import patch

from loguru import logger

from fp import Host, Message, MessageKind
from fp.core.base import EntityKind

MCP_SERVER_CMD = [sys.executable, str(Path(__file__).parent / "mcp_server_echo.py")]


async def main() -> None:
    logger.info("=== MCP Entity Flow Test ===")
    patcher = patch("fp.host.Host.save")
    patcher.start()

    # ── 1. 创建本地 Host（patch save 避免旧磁盘数据干扰） ──────────
    host = Host(name="TestHost", port=17001)
    logger.info(f"Host created: {host.name} ({host.uid})")

    # ── 2. 注册 MCP entity（TOOL kind，指向 echo server） ─────────
    mcp_entity = host.register_entity(
        name="echo-mcp",
        kind=EntityKind.TOOL,
        description="Echo tool via MCP STDIO",
        metadata={
            "mcp_config": {
                "transport": "stdio",
                "command": MCP_SERVER_CMD,
            }
        },
    )
    logger.info(f"MCP entity registered: {mcp_entity.name} ({mcp_entity.uid})")
    logger.info(f"  address: {mcp_entity.address.address}")
    logger.info(f"  checkpoints: {[cp.name for cp in mcp_entity.checkpoints]}")

    # ── 3. 注册 Caller entity，用 asyncio.Queue 捕获响应 ──────────
    received: asyncio.Queue[Message] = asyncio.Queue()

    async def caller_handler(msg: Message) -> None:
        logger.info(f"[Caller] Received response: kind={msg.kind}, payload={msg.payload}")
        await received.put(msg)

    caller = host.register_entity(
        name="caller",
        kind=EntityKind.HUMAN,
        handler=caller_handler,
    )
    logger.info(f"Caller entity registered: {caller.name} ({caller.uid})")
    logger.info(f"  friends: {list(caller.friends.keys())}")

    # ── 4. Caller 发送 INVOKE → MCP entity ────────────────────────
    invoke_message = Message(
        kind=MessageKind.INVOKE,
        payload={
            "method": "echo",
            "params": {"text": "Hello from FP through MCP!"},
        },
    )
    logger.info(f"\n[Caller] Sending INVOKE to MCP entity: method=echo")
    await caller.send_message(to=mcp_entity.entity_card, message=invoke_message)

    # ── 5. 等待响应（最多 5 秒） ──────────────────────────────────
    try:
        response = await asyncio.wait_for(received.get(), timeout=5.0)
    except asyncio.TimeoutError:
        logger.error("TIMEOUT: No response received within 5 seconds")
        return

    # ── 6. 验证结果 ───────────────────────────────────────────────
    payload = response.payload
    text = payload.get("text", "") if isinstance(payload, dict) else getattr(payload, "text", "")

    logger.info("\n=== Result ===")
    logger.info(f"  Response kind : {response.kind}")
    logger.info(f"  Response text : {text}")

    expected = "[echo] Hello from FP through MCP!"
    if text == expected:
        logger.info(f"  PASS: text matches expected '{expected}'")
    else:
        logger.error(f"  FAIL: expected '{expected}', got '{text}'")


if __name__ == "__main__":
    asyncio.run(main())
