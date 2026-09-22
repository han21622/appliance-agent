# Appliance Control AI Agent — Tool Calling + MCP Demo

A mini AI agent that controls home appliances (air conditioner / washing machine / refrigerator / air purifier) from natural-language commands, using Claude Tool Use (function calling) and the Model Context Protocol (MCP). Built to actually implement two lines from a Pangyo AI Intern job posting — "prototyping product features with LLM/VLM APIs" and "designing and verifying AI agent workflows with tool calling, MCP, etc."

## Problem

For an LLM to control appliances, it has to safely map natural-language commands onto real device actions. That requires three things: (1) a tool schema design that lets the model decide for itself which tool to call and with what arguments, (2) error handling that catches bad input (out-of-range temperature, a device that doesn't exist, a device that's offline) without crashing, and hands it back to the model in a form it can reason about, and (3) a structure where the same tool set can be reused across multiple clients (a custom agent, an MCP client like Claude Desktop). This project implements all three at a small scale and verifies them with automated tests.

## My Role

Solo project — I designed, implemented, and tested the whole thing myself: the domain layer (simulated appliance state), the tool schema/dispatch layer, the Claude tool-use agent loop, the MCP server, and pytest-based verification covering both success and failure paths.

## Where AI Is Actually Used

- **Tool schema design**: defined 6 tools — `list_devices`, `get_device_status`, `set_power`, `set_temperature`, `set_mode`, `start_cycle` — as JSON Schema and passed them via the `tools` parameter of the Claude Messages API (`src/appliance_agent/tools.py`).
- **Output schema**: every tool call result is normalized to either `{"ok": true, "result": {...}}` or `{"ok": false, "error": {"type": ..., "message": ...}}`, so the model can always parse success/failure the same way.
- **Error handling**: the domain layer raises custom exceptions for things like an unknown device, an offline device, an out-of-range temperature, or an invalid mode/cycle value; the dispatch layer catches these and converts them into the output schema above. The process never crashes on these errors — the model gets an error it can explain to the user or work around.
- **Agent workflow**: `run_agent()` in `agent.py` implements the loop of tool_use → execute the tool → return a tool_result → repeat → final answer.
- **MCP server**: the same tool set is also exposed as an MCP server in `mcp_server.py`, so any MCP client (e.g. Claude Desktop) can control this "appliance home" directly. The agent loop and the MCP server never duplicate the domain logic or error handling — both reach devices only through the same `call_tool()` dispatch function.

## Results (Verification)

Verified with 17 pytest tests: 9 covering the domain layer's happy/error paths (out-of-range temperature, unsupported operation, offline device, etc.), 5 covering the consistency of the tool dispatch output schema, and 3 covering the correctness of the agent loop itself — using a scripted fake Claude client (no real network calls) to confirm the "tool call → state change → result handed back next turn" flow, and that exceeding `max_turns` terminates safely instead of looping forever. The MCP server was directly checked to register all 6 tools with the correct input schemas.

```
$ python -m pytest tests/ -v
======================== 17 passed in 0.03s ========================
```

## Architecture

```
                    ┌────────────────────┐
 natural language ─▶│  agent.py (CLI)    │──┐
                     │  Claude tool-use   │  │
                     └────────────────────┘  │
                                              ▼
 MCP client ────────▶┌────────────────────┐   ┌──────────────┐   ┌───────────────┐
 (Claude Desktop)    │ mcp_server.py      │──▶│  tools.py    │──▶│  devices.py    │
                     │ (FastMCP)          │   │ call_tool()  │   │ DeviceRegistry │
                     └────────────────────┘   │ schema+errors│   │ (mock devices) │
                                               └──────────────┘   └───────────────┘
```

## Running It

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # add your ANTHROPIC_API_KEY

# 1) CLI agent (interactive)
cd src && python -m appliance_agent.agent

# 2) CLI agent (single command)
python -m appliance_agent.agent "Set the living room AC to 22 degrees"

# 3) MCP server (register with Claude Desktop, etc.)
python -m appliance_agent.mcp_server
```

To register this as an MCP server in Claude Desktop, add the following to `claude_desktop_config.json` (adjust the path to wherever you cloned the repo):

```json
{
  "mcpServers": {
    "appliance-agent": {
      "command": "python",
      "args": ["-m", "appliance_agent.mcp_server"],
      "cwd": "/absolute/path/to/appliance-agent/src"
    }
  }
}
```

## Testing

```bash
pip install -r requirements.txt
python -m pytest tests/ -v
```

The full test suite passes without an API key — the agent-loop tests use a fake client that replays scripted responses instead of calling the real Anthropic API (`tests/test_agent.py`).

## Demo Scenario (default home setup)

| device_id | Appliance | Initial state |
|---|---|---|
| `living-room-ac` | Living room AC | On, 24°C, cooling |
| `bedroom-purifier` | Bedroom air purifier | Off, auto |
| `utility-washer` | Laundry room washer | **Offline** (for demoing error handling) |
| `kitchen-fridge` | Kitchen refrigerator | On, 4°C |

`utility-washer` starts offline on purpose — sending a command like "start the washer" lets you see the agent catch a `DeviceOfflineError` and explain it to the user in natural language right away.

## Ideas for Future Extension

- Add timestamps/versioning to `tool_result` to match real device state streaming (WebSocket)
- Handle parallel `tool_use` calls for controlling multiple devices at once ("turn off all the lights and the AC")
- Persist conversation history to a database to keep context across sessions
- Add a VLM so device state can also be read from an image (e.g. a photo of the washer's display)
