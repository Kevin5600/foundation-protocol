"""用官方 @modelcontextprotocol/server-filesystem 测试完整 MCP 链路。

场景：
  - HostA: alice-agent
  - HostB: filesystem-mcp（kind=tool，指向官方 filesystem server）
  - alice 通过好友握手后调用 list_directory 工具，列出 /tmp 目录
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger

from fp import Host, Message, MessageKind
from fp.core.base import EntityKind
from fp.message import FriendRequestPayload

# 官方 filesystem MCP server，授权访问 /tmp
MCP_FS_CMD = ["npx", "-y", "@modelcontextprotocol/server-filesystem", "/private/tmp"]

SEP = "─" * 60


async def main() -> None:
    logger.info(SEP)
    logger.info("Official Filesystem MCP Server — Flow Test")
    logger.info(SEP)

    with patch("fp.host.Host.save"):

        # ── 建立拓扑 ─────────────────────────────────────────────
        cloud = Host(name="CloudHost")
        host_a = Host(name="HostA", port=17001)
        host_b = Host(name="HostB", port=17002)
        host_a.set_parent_host(cloud)
        host_b.set_parent_host(cloud)

        # ── 注册 entities ─────────────────────────────────────────
        received: asyncio.Queue[Message] = asyncio.Queue()

        async def agent_callback(msg: Message) -> None:
            await received.put(msg)

        alice = host_a.register_entity(
            name="alice-agent",
            kind=EntityKind.AGENT,
            handler=agent_callback,
        )

        fs_mcp = host_b.register_entity(
            name="filesystem-mcp",
            kind=EntityKind.TOOL,
            is_public=True,
            description="Official MCP filesystem server, root=/tmp",
            metadata={
                "mcp_config": {
                    "transport": "stdio",
                    "command": MCP_FS_CMD,
                }
            },
        )

        logger.info(f"alice       : {alice.address.address}")
        logger.info(f"filesystem  : {fs_mcp.address.address}")

        # ── 好友握手 ──────────────────────────────────────────────
        logger.info(f"\n{SEP}")
        logger.info("Step 1: Friend handshake")
        await alice.send_message(
            to=fs_mcp.entity_card,
            message=Message(
                kind=MessageKind.FRIEND_REQUEST,
                payload=FriendRequestPayload(sender_card=alice.entity_card),
            ),
        )
        await asyncio.sleep(0.5)

        if fs_mcp.uid not in alice.friends:
            logger.error("FAIL: friend handshake did not complete")
            return
        logger.info("Friend handshake: OK")

        # ── 调用 list_directory ───────────────────────────────────
        logger.info(f"\n{SEP}")
        logger.info("Step 2: INVOKE list_directory('/tmp')")
        await alice.send_message(
            to=fs_mcp.entity_card,
            message=Message(
                kind=MessageKind.INVOKE,
                payload={
                    "method": "list_directory",
                    "params": {"path": "/private/tmp"},
                },
            ),
        )

        # ── 等待结果（filesystem server 启动可能慢一点，给 15s） ──
        logger.info(f"\n{SEP}")
        logger.info("Step 3: Waiting for response (up to 15s)...")
        try:
            response = await asyncio.wait_for(received.get(), timeout=15.0)
        except asyncio.TimeoutError:
            logger.error("FAIL: No response within 15 seconds")
            return

        payload = response.payload
        text = (
            payload.get("text", "") if isinstance(payload, dict)
            else getattr(payload, "text", "")
        )

        logger.info(f"\n=== Result ===")
        logger.info(f"  kind : {response.kind}")
        logger.info(f"  text :\n{text}")

        if text:
            logger.info("  PASS: got non-empty response from official MCP server")
        else:
            logger.error("  FAIL: empty response")


if __name__ == "__main__":
    asyncio.run(main())
