"""MCP server exposing the same appliance-control tools over the Model
Context Protocol, so any MCP client (Claude Desktop, Claude Code, etc.) can
drive the demo home directly — not just the CLI agent in agent.py.

Both entry points call the *same* `call_tool()` dispatch from tools.py, so
there is exactly one place validation/error-formatting logic lives.

Run:
    python -m appliance_agent.mcp_server

Then point an MCP client at it (stdio transport). Example Claude Desktop
config entry:
    {
      "mcpServers": {
        "appliance-agent": {
          "command": "python",
          "args": ["-m", "appliance_agent.mcp_server"],
          "cwd": "/absolute/path/to/appliance-agent/src"
        }
      }
    }
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from .devices import DeviceRegistry
from .tools import call_tool

mcp = FastMCP("appliance-agent")

# one shared in-memory "home" for the life of the server process
_registry = DeviceRegistry.demo_home()


@mcp.tool()
def list_devices() -> dict:
    """집 안에 등록된 모든 가전기기 목록과 기본 상태를 조회합니다."""
    return call_tool(_registry, "list_devices", {})


@mcp.tool()
def get_device_status(device_id: str) -> dict:
    """특정 가전기기의 상세 상태(전원, 온도, 모드, 동작 상태)를 조회합니다."""
    return call_tool(_registry, "get_device_status", {"device_id": device_id})


@mcp.tool()
def set_power(device_id: str, power: bool) -> dict:
    """가전기기의 전원을 켜거나 끕니다."""
    return call_tool(_registry, "set_power", {"device_id": device_id, "power": power})


@mcp.tool()
def set_temperature(device_id: str, temperature: float) -> dict:
    """에어컨 또는 냉장고의 목표 온도를 설정합니다 (허용 범위를 벗어나면 오류 반환)."""
    return call_tool(_registry, "set_temperature", {"device_id": device_id, "temperature": temperature})


@mcp.tool()
def set_mode(device_id: str, mode: str) -> dict:
    """에어컨(cooling/heating/dehumidify/fan) 또는 공기청정기(auto/sleep/turbo) 모드를 설정합니다."""
    return call_tool(_registry, "set_mode", {"device_id": device_id, "mode": mode})


@mcp.tool()
def start_cycle(device_id: str, cycle: str) -> dict:
    """세탁기의 세탁 코스를 시작합니다 (standard/quick/heavy/wool)."""
    return call_tool(_registry, "start_cycle", {"device_id": device_id, "cycle": cycle})


if __name__ == "__main__":
    mcp.run()
