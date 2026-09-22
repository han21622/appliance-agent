"""Tool schema definitions + dispatch layer shared by both entry points:

- agent.py       -> passes TOOLS to the Claude Messages API (tool use / function calling)
- mcp_server.py  -> exposes the same underlying functions as MCP tools

Keeping one dispatch function (`call_tool`) behind both entry points means
the appliance domain logic, validation, and error formatting are written
and tested exactly once.
"""

from __future__ import annotations

from typing import Any

from .devices import DeviceError, DeviceRegistry

# --- Claude tool-use schemas ------------------------------------------------
# https://docs.claude.com/en/docs/build-with-claude/tool-use — each tool needs
# name / description / input_schema (JSON Schema). Keeping descriptions
# specific is what makes the model pick the right tool and fill arguments
# correctly instead of guessing.

TOOLS: list[dict[str, Any]] = [
    {
        "name": "list_devices",
        "description": "집 안에 등록된 모든 가전기기 목록과 기본 상태(전원, 온라인 여부)를 조회합니다.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_device_status",
        "description": "특정 가전기기의 상세 상태(전원, 온도, 모드, 동작 상태)를 조회합니다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "device_id": {"type": "string", "description": "기기 ID (예: living-room-ac)"}
            },
            "required": ["device_id"],
        },
    },
    {
        "name": "set_power",
        "description": "가전기기의 전원을 켜거나 끕니다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "device_id": {"type": "string"},
                "power": {"type": "boolean", "description": "true=켜기, false=끄기"},
            },
            "required": ["device_id", "power"],
        },
    },
    {
        "name": "set_temperature",
        "description": "에어컨 또는 냉장고의 목표 온도를 설정합니다. 기기 타입별 허용 범위를 벗어나면 오류가 반환됩니다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "device_id": {"type": "string"},
                "temperature": {"type": "number"},
            },
            "required": ["device_id", "temperature"],
        },
    },
    {
        "name": "set_mode",
        "description": "에어컨(cooling/heating/dehumidify/fan) 또는 공기청정기(auto/sleep/turbo)의 동작 모드를 설정합니다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "device_id": {"type": "string"},
                "mode": {"type": "string"},
            },
            "required": ["device_id", "mode"],
        },
    },
    {
        "name": "start_cycle",
        "description": "세탁기의 세탁 코스를 시작합니다 (standard/quick/heavy/wool).",
        "input_schema": {
            "type": "object",
            "properties": {
                "device_id": {"type": "string"},
                "cycle": {"type": "string"},
            },
            "required": ["device_id", "cycle"],
        },
    },
]


def call_tool(registry: DeviceRegistry, name: str, tool_input: dict[str, Any]) -> dict[str, Any]:
    """Dispatch one tool call to the device registry.

    Always returns a JSON-serializable dict with an explicit ``ok`` field —
    this is the "출력 스키마" the agent loop and the model both rely on:
    on success ``{"ok": true, "result": {...}}``, on a handled domain error
    ``{"ok": false, "error": {"type": ..., "message": ...}}``. The model
    sees the error text and can retry, ask the user for clarification, or
    explain the failure — instead of the process crashing.
    """
    try:
        if name == "list_devices":
            result = registry.list_devices()
        elif name == "get_device_status":
            result = registry.get_status(tool_input["device_id"])
        elif name == "set_power":
            result = registry.set_power(tool_input["device_id"], bool(tool_input["power"]))
        elif name == "set_temperature":
            result = registry.set_temperature(tool_input["device_id"], float(tool_input["temperature"]))
        elif name == "set_mode":
            result = registry.set_mode(tool_input["device_id"], tool_input["mode"])
        elif name == "start_cycle":
            result = registry.start_cycle(tool_input["device_id"], tool_input["cycle"])
        else:
            return {"ok": False, "error": {"type": "UnknownTool", "message": f"알 수 없는 tool: {name}"}}
        return {"ok": True, "result": result}
    except DeviceError as e:
        return {"ok": False, "error": {"type": type(e).__name__, "message": str(e)}}
    except (KeyError, TypeError, ValueError) as e:
        # malformed tool_input from the model — treat as a handled error too
        return {"ok": False, "error": {"type": "BadToolInput", "message": str(e)}}
