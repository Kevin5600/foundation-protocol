# MCP Bridge

Foundation Protocol is designed to host any [Model Context Protocol](https://modelcontextprotocol.io) server as a first-class FP entity. Once registered, the MCP server is addressable like any other entity — agents on the network call its tools through normal `INVOKE` messages, with the same signing, routing, and checkpoint enforcement as everything else.

## What `fp/` provides

The reference runtime ships the **mechanism**, not a packaged MCP client. Specifically:

- `EntityKind.TOOL` (and `RESOURCE`, `SERVICE`) — classifier tags so application code can branch on entity purpose.
- The `metadata` dict on every entity — a free-form bag where the convention is to put `mcp_config` (transport, command, URL, headers).
- The checkpoint pipeline with a `handler=callable` hook on `register_entity` — the supported way to plug in any custom message-dispatch behavior.

What the `fp` package does **not** include is a concrete `MCPHandler`. The bridge between an incoming `INVOKE` message and the upstream MCP server lives in the application layer — for example in [AI-Link-Net](https://github.com/FoundationAgents/ai-link-net) — because the choice of MCP client library, process lifecycle, and connection pooling is application policy, not protocol.

## The convention

When an application layer wires up an MCP bridge on top of FP, it typically:

1. Registers a `kind=TOOL` entity with an `mcp_config` metadata block.
2. Attaches a callback (or a `BaseHandler` subclass) that knows how to read `mcp_config` and dispatch.
3. The callback runs at the tail of the checkpoint pipeline, just like any other handler.

The shape of `mcp_config` that the example servers and AI-Link-Net both use:

```python
metadata={
    "mcp_config": {
        "transport": "stdio",                  # or "http"
        "command": ["python", "server.py"],    # stdio
        # "url": "https://mcp.example.com",    # http
        # "headers": {"Authorization": "..."}, # http
    }
}
```

## Runnable examples

The `example/` directory has working scripts that drive the full pipeline. They depend on an MCP-handler implementation provided by the runtime in which they're executed (not by `fp` alone):

- [`example/case_mcp.py`](https://github.com/FoundationAgents/foundation-protocol/blob/main/example/case_mcp.py) — local Host, stdio echo server, caller invokes via `INVOKE`.
- [`example/case_mcp_http.py`](https://github.com/FoundationAgents/foundation-protocol/blob/main/example/case_mcp_http.py) — same flow over HTTP transport.
- [`example/case_mcp_filesystem.py`](https://github.com/FoundationAgents/foundation-protocol/blob/main/example/case_mcp_filesystem.py) — driving an official `@modelcontextprotocol/server-filesystem`.
- [`example/case_mcp_list_tools.py`](https://github.com/FoundationAgents/foundation-protocol/blob/main/example/case_mcp_list_tools.py) — discovery via `tools/list`.
- [`example/case_mcp_cross_host.py`](https://github.com/FoundationAgents/foundation-protocol/blob/main/example/case_mcp_cross_host.py) — invoking an MCP entity across federated hosts.

The convention these scripts follow — `INVOKE` payload with `{"method": "tools/call", "params": {...}}` — is the protocol-level shape. The actual MCP dispatch is performed by the application's handler.

## Why bridge instead of using MCP directly

You'd want to put an MCP server behind an FP entity when you want:

- **Identity and audit** — every tool call is signed, routed through the checkpoint pipeline, and recorded in mailboxes.
- **Owner observability** — see [Carbon Copy](../learn/carbon-copy.md). Tool invocations made by an owned agent are visible to the owner without changing the tool.
- **Federation** — the MCP server lives on one host; callers on any federated host can reach it through the parent.
- **Policy** — checkpoints can enforce rate limits, friend-only access, or contract-gated invocation on top of MCP without modifying the upstream server.

If none of those apply, you can keep using MCP directly. The bridge is a packaging choice, not a requirement.
