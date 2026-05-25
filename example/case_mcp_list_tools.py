"""验证 agent 能否发现并获取 MCP entity 的工具列表。

场景：
  - HostA: alice-agent
  - HostB: filesystem-mcp（官方 STDIO server）
  - HostB: echo-http-mcp（自建 HTTP server）
  - alice 与两个 MCP entity 握手后发一次 INVOKE 触发连接
  - 验证 entity.metadata["mcp_tools"] 被正确填充
  - 模拟 agent 读取工具列表并格式化为 prompt 片段
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

MCP_FS_CMD = ["npx", "-y", "@modelcontextprotocol/server-filesystem", "/private/tmp"]
HTTP_PORT = 8766
HTTP_CMD = [sys.executable, str(Path(__file__).parent / "mcp_server_echo_http.py"), str(HTTP_PORT)]
SEP = "─" * 60


def format_tools_for_prompt(entity_name: str, tools: list[dict]) -> str:
    """模拟 agent 读工具列表生成 prompt 片段。"""
    if not tools:
        return f"[{entity_name}] No tools available."
    lines = [f"Tools provided by '{entity_name}':"]
    for t in tools:
        schema = t.get("inputSchema", {})
        props = schema.get("properties", {})
        params = ", ".join(f"{k}: {v.get('type','any')}" for k, v in props.items())
        lines.append(f"  - {t['name']}({params}): {t.get('description', '')}")
    return "\n".join(lines)


async def start_http_server() -> asyncio.subprocess.Process:
    proc = await asyncio.create_subprocess_exec(
        *HTTP_CMD,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    line = await asyncio.wait_for(proc.stdout.readline(), timeout=5.0)
    logger.info(f"HTTP server: {line.decode().strip()}")
    return proc


async def trigger_and_wait(
    caller,
    target,
    received: asyncio.Queue,
) -> None:
    """发一次 INVOKE 触发 MCPHandler 连接并拉取工具列表。"""
    await caller.send_message(
        to=target.entity_card,
        message=Message(
            kind=MessageKind.INVOKE,
            payload={"method": "list_directory" if "filesystem" in target.name else "echo",
                     "params": {"path": "/private/tmp"} if "filesystem" in target.name else {"text": "ping"}},
        ),
    )
    await asyncio.wait_for(received.get(), timeout=15.0)


async def main() -> None:
    logger.info(SEP)
    logger.info("MCP list_tools — Agent Discovery Test")
    logger.info(SEP)

    http_proc = await start_http_server()

    try:
        with patch("fp.host.Host.save"):

            cloud = Host(name="CloudHost")
            host_a = Host(name="HostA", port=17001)
            host_b = Host(name="HostB", port=17002)
            host_a.set_parent_host(cloud)
            host_b.set_parent_host(cloud)

            received: asyncio.Queue[Message] = asyncio.Queue()

            async def agent_callback(msg: Message) -> None:
                await received.put(msg)

            alice = host_a.register_entity(
                name="alice-agent", kind=EntityKind.AGENT, handler=agent_callback,
            )
            fs_mcp = host_b.register_entity(
                name="filesystem-mcp", kind=EntityKind.TOOL, is_public=True,
                metadata={"mcp_config": {"transport": "stdio", "command": MCP_FS_CMD}},
            )
            echo_http = host_b.register_entity(
                name="echo-http-mcp", kind=EntityKind.TOOL, is_public=True,
                metadata={"mcp_config": {"transport": "http", "url": f"http://localhost:{HTTP_PORT}"}},
            )

            # ── 好友握手 ─────────────────────────────────────────
            logger.info("\nStep 1: Friend handshakes")
            for target in [fs_mcp, echo_http]:
                await alice.send_message(
                    to=target.entity_card,
                    message=Message(
                        kind=MessageKind.FRIEND_REQUEST,
                        payload=FriendRequestPayload(sender_card=alice.entity_card),
                    ),
                )
            await asyncio.sleep(0.5)
            logger.info(f"alice friends: {list(alice.friends.keys())}")

            # ── 触发连接（各发一次 INVOKE）────────────────────────
            logger.info(f"\n{SEP}")
            logger.info("Step 2: Trigger connections (INVOKE each MCP entity)")

            await trigger_and_wait(alice, fs_mcp, received)
            logger.info("filesystem-mcp: first call done")

            await trigger_and_wait(alice, echo_http, received)
            logger.info("echo-http-mcp: first call done")

            # ── 从 agent 视角读取工具列表 ─────────────────────────
            logger.info(f"\n{SEP}")
            logger.info("Step 3: Agent reads mcp_tools from entity metadata\n")

            for mcp_entity in [fs_mcp, echo_http]:
                tools = mcp_entity.metadata.get("mcp_tools", [])
                logger.info(f"[{mcp_entity.name}] mcp_tools count: {len(tools)}")

                prompt_snippet = format_tools_for_prompt(mcp_entity.name, tools)
                logger.info(f"\n{prompt_snippet}\n")

                if tools:
                    logger.info(f"  PASS: {mcp_entity.name} tools discovered")
                else:
                    logger.error(f"  FAIL: {mcp_entity.name} mcp_tools is empty")

    finally:
        http_proc.terminate()
        await http_proc.wait()


if __name__ == "__main__":
    asyncio.run(main())
