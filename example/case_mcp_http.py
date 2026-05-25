"""HTTP transport MCP 流程测试。

场景：
  - 先启动本地 HTTP MCP server（mcp_server_echo_http.py）
  - HostA: alice-agent
  - HostB: echo-http-mcp（kind=tool，transport=http，指向本地 HTTP server）
  - 完整走：注册 → 好友握手 → INVOKE → 跨 host 路由 → HttpMCPClient → 结果回路
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

HTTP_SERVER_PORT = 8765
HTTP_SERVER_URL = f"http://localhost:{HTTP_SERVER_PORT}"
HTTP_SERVER_CMD = [sys.executable, str(Path(__file__).parent / "mcp_server_echo_http.py"), str(HTTP_SERVER_PORT)]

SEP = "─" * 60


async def start_http_server() -> asyncio.subprocess.Process:
    """启动 HTTP MCP server，等待它打印 ready 信号。"""
    proc = await asyncio.create_subprocess_exec(
        *HTTP_SERVER_CMD,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    # 等待 ready 信号（最多 5 秒）
    try:
        line = await asyncio.wait_for(proc.stdout.readline(), timeout=5.0)
        logger.info(f"HTTP server: {line.decode().strip()}")
    except asyncio.TimeoutError:
        proc.kill()
        raise RuntimeError("HTTP MCP server failed to start within 5s")
    return proc


async def main() -> None:
    logger.info(SEP)
    logger.info("HTTP Transport MCP Flow Test")
    logger.info(SEP)

    # ── 启动 HTTP MCP server ──────────────────────────────────────
    logger.info("Starting HTTP MCP server...")
    server_proc = await start_http_server()

    try:
        with patch("fp.host.Host.save"):

            # ── 建立拓扑 ──────────────────────────────────────────
            cloud = Host(name="CloudHost")
            host_a = Host(name="HostA", port=17001)
            host_b = Host(name="HostB", port=17002)
            host_a.set_parent_host(cloud)
            host_b.set_parent_host(cloud)

            # ── 注册 entities ──────────────────────────────────────
            received: asyncio.Queue[Message] = asyncio.Queue()

            async def agent_callback(msg: Message) -> None:
                await received.put(msg)

            alice = host_a.register_entity(
                name="alice-agent",
                kind=EntityKind.AGENT,
                handler=agent_callback,
            )

            echo_http = host_b.register_entity(
                name="echo-http-mcp",
                kind=EntityKind.TOOL,
                is_public=True,
                metadata={
                    "mcp_config": {
                        "transport": "http",
                        "url": HTTP_SERVER_URL,
                    }
                },
            )

            logger.info(f"alice         : {alice.address.address}")
            logger.info(f"echo-http-mcp : {echo_http.address.address}")
            logger.info(f"mcp server    : {HTTP_SERVER_URL}")

            # ── 好友握手 ──────────────────────────────────────────
            logger.info(f"\n{SEP}")
            logger.info("Step 1: Friend handshake (cross-host)")
            await alice.send_message(
                to=echo_http.entity_card,
                message=Message(
                    kind=MessageKind.FRIEND_REQUEST,
                    payload=FriendRequestPayload(sender_card=alice.entity_card),
                ),
            )
            await asyncio.sleep(0.5)

            if echo_http.uid not in alice.friends:
                logger.error("FAIL: friend handshake did not complete")
                return
            logger.info("Friend handshake: OK")

            # ── INVOKE echo 工具 ───────────────────────────────────
            logger.info(f"\n{SEP}")
            logger.info("Step 2: INVOKE echo via HTTP transport")
            await alice.send_message(
                to=echo_http.entity_card,
                message=Message(
                    kind=MessageKind.INVOKE,
                    payload={
                        "method": "echo",
                        "params": {"text": "Hello via HTTP MCP transport!"},
                    },
                ),
            )

            # ── 等待结果 ───────────────────────────────────────────
            logger.info(f"\n{SEP}")
            logger.info("Step 3: Waiting for response...")
            try:
                response = await asyncio.wait_for(received.get(), timeout=5.0)
            except asyncio.TimeoutError:
                logger.error("FAIL: No response within 5 seconds")
                return

            payload = response.payload
            text = (
                payload.get("text", "") if isinstance(payload, dict)
                else getattr(payload, "text", "")
            )

            expected = "[echo-http] Hello via HTTP MCP transport!"
            logger.info(f"\n=== Result ===")
            logger.info(f"  kind : {response.kind}")
            logger.info(f"  text : {text}")

            if text == expected:
                logger.info(f"  PASS: '{text}'")
            else:
                logger.error(f"  FAIL: expected '{expected}', got '{text}'")

    finally:
        server_proc.terminate()
        await server_proc.wait()
        logger.info("HTTP server stopped")


if __name__ == "__main__":
    asyncio.run(main())
