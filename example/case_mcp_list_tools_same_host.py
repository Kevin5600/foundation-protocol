"""验证 agent 能通过 mcp.list_tools INVOKE 获取 MCP 工具列表（同 host 场景）。

场景：
  - 单一 Host，alice-agent 和 echo-mcp 都在同一 host
  - alice 发 INVOKE(method="mcp.list_tools") 给 echo-mcp
  - 验证 alice 收到的响应包含正确的工具列表
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

HTTP_PORT = 8767
HTTP_CMD = [sys.executable, str(Path(__file__).parent / "mcp_server_echo_http.py"), str(HTTP_PORT)]
SEP = "─" * 60


async def start_http_server() -> asyncio.subprocess.Process:
    proc = await asyncio.create_subprocess_exec(
        *HTTP_CMD,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    line = await asyncio.wait_for(proc.stdout.readline(), timeout=5.0)
    logger.info(f"HTTP server: {line.decode().strip()}")
    return proc


async def main() -> None:
    logger.info(SEP)
    logger.info("mcp.list_tools — Same-Host Test")
    logger.info(SEP)

    http_proc = await start_http_server()

    try:
        with patch("fp.host.Host.save"):
            host = Host(name="SingleHost", port=18001)

            received: asyncio.Queue[Message] = asyncio.Queue()

            async def agent_callback(msg: Message) -> None:
                await received.put(msg)

            alice = host.register_entity(
                name="alice-agent", kind=EntityKind.AGENT, handler=agent_callback,
            )
            echo_mcp = host.register_entity(
                name="echo-http-mcp",
                kind=EntityKind.TOOL,
                is_public=True,
                metadata={"mcp_config": {"transport": "http", "url": f"http://localhost:{HTTP_PORT}"}},
            )

            # ── 好友握手 ─────────────────────────────────────────
            logger.info("\nStep 1: Friend handshake")
            await alice.send_message(
                to=echo_mcp.entity_card,
                message=Message(
                    kind=MessageKind.FRIEND_REQUEST,
                    payload=FriendRequestPayload(sender_card=alice.entity_card),
                ),
            )
            await asyncio.sleep(0.3)
            logger.info(f"alice friends: {list(alice.friends.keys())}")

            # ── 发 mcp.list_tools ─────────────────────────────────
            logger.info(f"\n{SEP}")
            logger.info("Step 2: INVOKE mcp.list_tools")
            await alice.send_message(
                to=echo_mcp.entity_card,
                message=Message(
                    kind=MessageKind.INVOKE,
                    payload={"method": "mcp.list_tools", "params": {}},
                ),
            )

            # ── 等待响应 ───────────────────────────────────────────
            logger.info(f"\n{SEP}")
            logger.info("Step 3: Waiting for tool list response...")
            try:
                response = await asyncio.wait_for(received.get(), timeout=10.0)
            except asyncio.TimeoutError:
                logger.error("FAIL: No response within 10 seconds")
                return

            payload = response.payload
            tools = payload.get("mcp_tools", []) if isinstance(payload, dict) else []

            logger.info(f"\n=== Result ===")
            logger.info(f"  kind       : {response.kind}")
            logger.info(f"  mcp_tools  : {len(tools)} tool(s)")
            for t in tools:
                logger.info(f"    - {t['name']}: {t.get('description', '')}")

            if tools:
                logger.info(f"\n  PASS: received {len(tools)} tool(s) from echo-http-mcp")
            else:
                logger.error("  FAIL: mcp_tools is empty in response")

    finally:
        http_proc.terminate()
        await http_proc.wait()


if __name__ == "__main__":
    asyncio.run(main())
