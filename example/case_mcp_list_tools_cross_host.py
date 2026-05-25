"""验证 agent 能通过 mcp.list_tools INVOKE 获取 MCP 工具列表（跨 host 场景）。

场景：
  - CloudHost → HostA (alice-agent) + HostB (echo-http-mcp)
  - alice 跨 host 发 INVOKE(method="mcp.list_tools") 给 echo-mcp
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

HTTP_PORT = 8768
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
    logger.info("mcp.list_tools — Cross-Host Test")
    logger.info(SEP)

    http_proc = await start_http_server()

    try:
        with patch("fp.host.Host.save"):
            cloud = Host(name="CloudHost")
            host_a = Host(name="HostA", port=19001)
            host_b = Host(name="HostB", port=19002)
            host_a.set_parent_host(cloud)
            host_b.set_parent_host(cloud)

            received: asyncio.Queue[Message] = asyncio.Queue()

            async def agent_callback(msg: Message) -> None:
                await received.put(msg)

            alice = host_a.register_entity(
                name="alice-agent", kind=EntityKind.AGENT, handler=agent_callback,
            )
            echo_mcp = host_b.register_entity(
                name="echo-http-mcp",
                kind=EntityKind.TOOL,
                is_public=True,
                metadata={"mcp_config": {"transport": "http", "url": f"http://localhost:{HTTP_PORT}"}},
            )

            logger.info(f"alice    : {alice.address.address}")
            logger.info(f"echo-mcp : {echo_mcp.address.address}")

            # ── 好友握手 ─────────────────────────────────────────
            logger.info(f"\n{SEP}")
            logger.info("Step 1: Cross-host friend handshake")
            await alice.send_message(
                to=echo_mcp.entity_card,
                message=Message(
                    kind=MessageKind.FRIEND_REQUEST,
                    payload=FriendRequestPayload(sender_card=alice.entity_card),
                ),
            )
            await asyncio.sleep(0.5)

            if echo_mcp.uid not in alice.friends:
                logger.error("FAIL: friend handshake did not complete")
                return
            logger.info("Friend handshake: OK")

            # ── 发 mcp.list_tools ─────────────────────────────────
            logger.info(f"\n{SEP}")
            logger.info("Step 2: INVOKE mcp.list_tools (cross-host)")
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
                logger.info(f"\n  PASS: alice received {len(tools)} tool(s) from cross-host echo-http-mcp")
            else:
                logger.error("  FAIL: mcp_tools is empty in response")

    finally:
        http_proc.terminate()
        await http_proc.wait()


if __name__ == "__main__":
    asyncio.run(main())
