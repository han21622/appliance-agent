"""Tests the tool-calling loop mechanics (agent.run_agent) against a
scripted fake Anthropic client — no network call / API key needed.

This is the "검증" (verification) half of "Tool calling ... 워크플로우
설계 및 검증": it proves the loop correctly executes a tool Claude asks
for, feeds the (successful or failed) result back as a tool_result, and
terminates on a final text turn — independent of what any specific model
actually decides to do.
"""

import json

from appliance_agent.agent import run_agent
from appliance_agent.devices import DeviceRegistry


class FakeBlock:
    def __init__(self, type, **kw):
        self.type = type
        for k, v in kw.items():
            setattr(self, k, v)


class FakeResponse:
    def __init__(self, content, stop_reason):
        self.content = content
        self.stop_reason = stop_reason


class FakeMessages:
    """Replays a fixed script of responses; records every `create()` call
    so tests can assert on what the agent loop sent back to the model."""

    def __init__(self, script):
        self._script = list(script)
        self.calls = []

    def create(self, **kwargs):
        # snapshot `messages` — run_agent keeps mutating the same list object
        # after this call returns, so without copying it here every recorded
        # call would alias the same (eventually-final) list.
        snapshot = dict(kwargs)
        snapshot["messages"] = list(kwargs["messages"])
        self.calls.append(snapshot)
        return self._script.pop(0)


class FakeClient:
    def __init__(self, script):
        self.messages = FakeMessages(script)


def test_agent_executes_tool_then_returns_final_text():
    script = [
        FakeResponse(
            content=[
                FakeBlock(
                    "tool_use",
                    id="tool_1",
                    name="set_temperature",
                    input={"device_id": "living-room-ac", "temperature": 22},
                )
            ],
            stop_reason="tool_use",
        ),
        FakeResponse(
            content=[FakeBlock("text", text="거실 에어컨을 22도로 설정했습니다.")],
            stop_reason="end_turn",
        ),
    ]
    client = FakeClient(script)
    registry = DeviceRegistry.demo_home()

    reply = run_agent(client, registry, "거실 에어컨 22도로 맞춰줘", verbose=False)

    assert reply == "거실 에어컨을 22도로 설정했습니다."
    assert registry.get_status("living-room-ac")["temperature"] == 22.0

    # second create() call must carry the tool_result of the first call
    second_call_messages = client.messages.calls[1]["messages"]
    tool_result_msg = second_call_messages[-1]
    assert tool_result_msg["role"] == "user"
    payload = json.loads(tool_result_msg["content"][0]["content"])
    assert payload["ok"] is True


def test_agent_surfaces_handled_error_to_the_model():
    # utility-washer ships offline in demo_home() — exercises the error path
    script = [
        FakeResponse(
            content=[
                FakeBlock(
                    "tool_use",
                    id="tool_1",
                    name="start_cycle",
                    input={"device_id": "utility-washer", "cycle": "standard"},
                )
            ],
            stop_reason="tool_use",
        ),
        FakeResponse(
            content=[FakeBlock("text", text="세탁기가 오프라인 상태라 세탁을 시작할 수 없습니다.")],
            stop_reason="end_turn",
        ),
    ]
    client = FakeClient(script)
    registry = DeviceRegistry.demo_home()

    reply = run_agent(client, registry, "세탁기 돌려줘", verbose=False)

    assert "오프라인" in reply
    second_call_messages = client.messages.calls[1]["messages"]
    tool_result_msg = second_call_messages[-1]["content"][0]
    assert tool_result_msg["is_error"] is True
    payload = json.loads(tool_result_msg["content"])  # type: ignore[arg-type]
    assert payload["error"]["type"] == "DeviceOfflineError"


def test_agent_stops_at_max_turns_instead_of_looping_forever():
    # every response asks for another (identical) tool call — never finishes
    infinite_tool_use = FakeResponse(
        content=[
            FakeBlock("tool_use", id="tool_x", name="list_devices", input={})
        ],
        stop_reason="tool_use",
    )
    client = FakeClient([infinite_tool_use] * 10)
    registry = DeviceRegistry.demo_home()

    reply = run_agent(client, registry, "기기 목록 계속 보여줘", max_turns=3, verbose=False)

    assert "max_turns" in reply
    assert len(client.messages.calls) == 3
