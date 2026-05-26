# Develop

Develop is the practical side of the documentation: how to install Foundation Protocol, what the typical setups look like, and how to integrate the runtime with your own agents, tools, and services.

If you want to understand *how* the runtime works, see [Learn](../learn/index.md).

## What's in this section

<div class="grid cards" markdown>

-   [:material-rocket-launch-outline: __Quickstart__](quickstart.md)

    Install the package, register two entities on a single host, and
    send your first signed message — in under thirty lines of code.

-   [:material-graph-outline: __Federation__](federation.md)

    Wire up multiple `Host`s in a parent / child topology so entities
    on different processes can address each other through a single
    cloud host.

-   [:material-tools: __MCP Bridge__](mcp-bridge.md)

    Register an existing MCP server as an FP entity, so any agent on
    the network can call its tools through the normal message pipeline.

-   [:material-handshake-outline: __Trade Workflows__](trade-workflows.md)

    Run a full contract lifecycle — create, approve, complete, accept,
    rate, settle — using the built-in Arbiter and the `CONTRACT_*`
    message kinds.

</div>

## Prerequisites

- Python 3.13+
- `uv` (recommended) or `pip` for installation
- For the MCP bridge examples: a working `node` / `npx` if you want to use the official MCP servers

## Installation

```bash
pip install "foundation-protocol @ git+https://github.com/FoundationAgents/foundation-protocol.git"
```

Or, in a `uv`-managed project:

```bash
uv add "foundation-protocol @ git+https://github.com/FoundationAgents/foundation-protocol.git"
```

The package exposes the public API under `fp` — `Host`, `Entity`, `Mail`, `Message`, `MessageKind`, and the built-in checkpoints are all importable from the top-level module.
