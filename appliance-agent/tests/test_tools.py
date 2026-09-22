from appliance_agent.devices import DeviceRegistry
from appliance_agent.tools import TOOLS, call_tool


def test_all_tools_have_required_schema_fields():
    for tool in TOOLS:
        assert {"name", "description", "input_schema"} <= tool.keys()
        assert tool["input_schema"]["type"] == "object"


def test_call_tool_success_shape():
    registry = DeviceRegistry.demo_home()
    result = call_tool(registry, "get_device_status", {"device_id": "living-room-ac"})
    assert result["ok"] is True
    assert result["result"]["device_id"] == "living-room-ac"


def test_call_tool_domain_error_shape():
    registry = DeviceRegistry.demo_home()
    result = call_tool(registry, "set_temperature", {"device_id": "living-room-ac", "temperature": 99})
    assert result["ok"] is False
    assert result["error"]["type"] == "InvalidParameterError"


def test_call_tool_missing_argument_is_handled_not_raised():
    registry = DeviceRegistry.demo_home()
    result = call_tool(registry, "set_temperature", {"device_id": "living-room-ac"})  # no temperature
    assert result["ok"] is False
    assert result["error"]["type"] == "BadToolInput"


def test_call_tool_unknown_tool_name():
    registry = DeviceRegistry.demo_home()
    result = call_tool(registry, "not_a_real_tool", {})
    assert result["ok"] is False
    assert result["error"]["type"] == "UnknownTool"
