#!/usr/bin/env python3
"""Minimal HTTP MCP server — accepts plain JSON-RPC POST, responds with JSON.

Usage: python mcp_server_echo_http.py [port]
"""

import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer


class MCPHTTPHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length))

        method = body.get("method")
        msg_id = body.get("id")
        response = self._dispatch(method, msg_id, body.get("params", {}))

        data = json.dumps(response).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _dispatch(self, method: str, msg_id, params: dict) -> dict:
        if method == "tools/list":
            return {"jsonrpc": "2.0", "id": msg_id, "result": {"tools": [
                {"name": "echo", "description": "Echo back the input text",
                 "inputSchema": {"type": "object",
                                 "properties": {"text": {"type": "string"}},
                                 "required": ["text"]}},
            ]}}
        if method == "tools/call":
            return self._handle_tool_call(msg_id, params)
        return {"jsonrpc": "2.0", "id": msg_id,
                "error": {"code": -32601, "message": f"Unknown method: {method}"}}

    def _handle_tool_call(self, msg_id, params: dict) -> dict:
        name = params.get("name")
        args = params.get("arguments", {})
        if name == "echo":
            text = args.get("text", "")
            return {"jsonrpc": "2.0", "id": msg_id, "result": {
                "content": [{"type": "text", "text": f"[echo-http] {text}"}],
                "isError": False,
            }}
        return {"jsonrpc": "2.0", "id": msg_id,
                "error": {"code": -32601, "message": f"Unknown tool: {name}"}}

    def log_message(self, *_) -> None:
        pass  # suppress access logs


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    server = HTTPServer(("0.0.0.0", port), MCPHTTPHandler)
    print(f"MCP HTTP server ready on port {port}", flush=True)
    server.serve_forever()
