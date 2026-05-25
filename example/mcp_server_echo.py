#!/usr/bin/env python3
"""Minimal MCP server exposing an 'echo' tool — used for flow testing.

Speaks MCP STDIO protocol (JSON-RPC 2.0, newline-delimited).
Run standalone: python example/mcp_server_echo.py
"""

import json
import sys


def send(msg: dict) -> None:
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


def recv() -> dict | None:
    line = sys.stdin.readline()
    return json.loads(line) if line.strip() else None


TOOLS = [
    {
        "name": "echo",
        "description": "Echo the input text back",
        "inputSchema": {
            "type": "object",
            "properties": {"text": {"type": "string", "description": "Text to echo"}},
            "required": ["text"],
        },
    }
]


def handle(msg: dict) -> None:
    method = msg.get("method")
    msg_id = msg.get("id")

    if method == "initialize":
        send({"jsonrpc": "2.0", "id": msg_id, "result": {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "mcp-echo", "version": "0.1"},
        }})

    elif method == "notifications/initialized":
        pass  # notification — no response

    elif method == "tools/list":
        send({"jsonrpc": "2.0", "id": msg_id, "result": {"tools": TOOLS}})

    elif method == "tools/call":
        params = msg.get("params", {})
        name = params.get("name")
        args = params.get("arguments", {})
        if name == "echo":
            text = args.get("text", "")
            send({"jsonrpc": "2.0", "id": msg_id, "result": {
                "content": [{"type": "text", "text": f"[echo] {text}"}],
                "isError": False,
            }})
        else:
            send({"jsonrpc": "2.0", "id": msg_id, "error": {
                "code": -32601, "message": f"Unknown tool: {name}",
            }})

    elif msg_id is not None:
        send({"jsonrpc": "2.0", "id": msg_id, "error": {
            "code": -32601, "message": f"Unknown method: {method}",
        }})


if __name__ == "__main__":
    while True:
        msg = recv()
        if msg is None:
            break
        handle(msg)
