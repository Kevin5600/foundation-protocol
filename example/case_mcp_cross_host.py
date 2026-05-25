"""跨 Host MCP 调用端到端测试。

拓扑：
    CloudHost
    ├── HostA：alice-agent（kind=agent）
    └── HostB：echo-mcp（kind=tool，STDIO MCP server）

流程：
    1. 注册两个 Host 并连接到 CloudHost
    2. 注册 alice-agent 和 echo-mcp
    3. alice 发送好友请求 → echo-mcp 自动接受 → 双方互为好友
    4. alice 发送 INVOKE（调用 echo 工具）→ 跨 host 路由
    5. echo-mcp 通过 MCPClient 调用本地 MCP server，返回结果
    6. 结果原路经 CloudHost 路由回 alice
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

MCP_SERVER_CMD = [sys.executable, str(Path(__file__).parent / "mcp_server_echo.py")]

SEP = "─" * 60


async def main() -> None:
    logger.info(SEP)
    logger.info("Cross-Host MCP Flow Test")
    logger.info(SEP)

    with patch("fp.host.Host.save"):

        # ── 1. 建立三层 Host 拓扑 ────────────────────────────────
        cloud = Host(name="CloudHost")
        host_a = Host(name="HostA", port=17001)
        host_b = Host(name="HostB", port=17002)

        host_a.set_parent_host(cloud)
        host_b.set_parent_host(cloud)

        logger.info(f"Hosts: Cloud={cloud.uid}  A={host_a.uid}  B={host_b.uid}")

        # ── 2. 注册 Agent entity（HostA） ─────────────────────────
        invoke_responses: asyncio.Queue[Message] = asyncio.Queue()

        async def agent_callback(msg: Message) -> None:
            logger.info(f"[alice-agent] handler received: kind={msg.kind} payload={msg.payload}")
            await invoke_responses.put(msg)

        alice = host_a.register_entity(
            name="alice-agent",
            kind=EntityKind.AGENT,
            handler=agent_callback,
        )
        logger.info(f"[HostA] alice-agent: {alice.address.address}")

        # ── 3. 注册 MCP entity（HostB） ───────────────────────────
        echo_mcp = host_b.register_entity(
            name="echo-mcp",
            kind=EntityKind.TOOL,
            is_public=True,
            description="Echo tool via MCP STDIO",
            metadata={
                "mcp_config": {
                    "transport": "stdio",
                    "command": MCP_SERVER_CMD,
                }
            },
        )
        logger.info(f"[HostB] echo-mcp  : {echo_mcp.address.address}")
        logger.info(f"        handler   : {type(echo_mcp.handler).__name__}")

        # ── 4. 好友握手（跨 host） ────────────────────────────────
        logger.info(f"\n{SEP}")
        logger.info("Step 1: Friend request (alice → echo-mcp, cross-host)")

        await alice.send_message(
            to=echo_mcp.entity_card,
            message=Message(
                kind=MessageKind.FRIEND_REQUEST,
                payload=FriendRequestPayload(
                    sender_card=alice.entity_card,
                    text="Hi echo-mcp, I am alice!",
                ),
            ),
        )

        # 等待好友握手完成（FRIEND_REQUEST → FRIEND_ACCEPT 两跳）
        await asyncio.sleep(0.5)

        alice_friends = list(alice.friends.keys())
        mcp_friends = list(echo_mcp.friends.keys())
        logger.info(f"alice friends : {alice_friends}")
        logger.info(f"echo-mcp friends: {mcp_friends}")

        if echo_mcp.uid not in alice.friends:
            logger.error("FAIL: echo-mcp not in alice's friends after handshake")
            return
        if alice.uid not in echo_mcp.friends:
            logger.error("FAIL: alice not in echo-mcp's friends after handshake")
            return
        logger.info("Friend handshake: OK")

        # ── 5. Alice 调用 MCP 工具（INVOKE，跨 host） ────────────
        logger.info(f"\n{SEP}")
        logger.info("Step 2: INVOKE echo tool (alice → echo-mcp, cross-host)")

        await alice.send_message(
            to=echo_mcp.entity_card,
            message=Message(
                kind=MessageKind.INVOKE,
                payload={
                    "method": "echo",
                    "params": {"text": "Hello MCP across hosts!"},
                },
            ),
        )

        # ── 6. 等待响应并验证 ─────────────────────────────────────
        logger.info(f"\n{SEP}")
        logger.info("Step 3: Waiting for response...")

        try:
            response = await asyncio.wait_for(invoke_responses.get(), timeout=5.0)
        except asyncio.TimeoutError:
            logger.error("FAIL: No response within 5 seconds")
            return

        payload = response.payload
        text = (
            payload.get("text", "") if isinstance(payload, dict)
            else getattr(payload, "text", "")
        )

        expected = "[echo] Hello MCP across hosts!"
        logger.info(f"\n=== Result ===")
        logger.info(f"  kind : {response.kind}")
        logger.info(f"  text : {text}")

        if text == expected:
            logger.info(f"  PASS: '{text}'")
        else:
            logger.error(f"  FAIL: expected '{expected}', got '{text}'")


if __name__ == "__main__":
    asyncio.run(main())
