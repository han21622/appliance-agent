"""Tool-calling agent loop for the smart-appliance assistant.

Talks to the Claude Messages API with `tools=TOOLS` (see tools.py), executes
whichever tool(s) Claude asks for against the mock device layer, feeds the
result back as a `tool_result`, and repeats until Claude returns a final
text answer (stop_reason != "tool_use") or `max_turns` is hit.

The Anthropic client is passed in rather than constructed here, so the loop
itself can be unit-tested with a scripted fake client and no network / API
key — see tests/test_agent.py.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Protocol

from .devices import DeviceRegistry
from .tools import TOOLS, call_tool

# Load the project-root .env (…/appliance-agent/.env) regardless of the
# current working directory, so `.env` only ever needs to exist in one
# place — no matter whether you run this from the repo root or from src/.
try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
except ImportError:
    pass  # python-dotenv not installed — fall back to real env vars only

# Any recent Claude model with tool-use support works; override via env var
# so this doesn't go stale — see https://docs.claude.com/en/docs/about-claude/models
DEFAULT_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-5")

SYSTEM_PROMPT = (
    "당신은 사용자의 집에 있는 가전기기를 제어하는 어시스턴트입니다. "
    "사용자의 자연어 요청을 이해해서 적절한 tool을 호출해 기기를 조회/제어하세요. "
    "기기 ID가 불명확하면 먼저 list_devices로 목록을 확인한 뒤 가장 알맞은 기기를 고르세요. "
    "tool 호출 결과에 ok: false가 포함되어 있으면 이는 정상적으로 처리된 오류이므로, "
    "오류를 사용자에게 이해하기 쉬운 한국어로 설명하고 가능하면 대안을 제안하세요. "
    "모든 tool 호출이 끝나면 사용자에게 무엇을 했는지 간결하게 요약해서 답하세요."
)


class MessagesClient(Protocol):
    """Structural type for whatever object exposes `.messages.create(...)`.

    `anthropic.Anthropic()` satisfies this. Tests pass a small fake instead.
    """

    messages: Any


def _extract_text(content_blocks: list[Any]) -> str:
    parts = [b.text for b in content_blocks if getattr(b, "type", None) == "text"]
    return "\n".join(parts).strip()


def run_agent(
    client: MessagesClient,
    registry: DeviceRegistry,
    user_message: str,
    model: str = DEFAULT_MODEL,
    max_turns: int = 6,
    verbose: bool = True,
) -> str:
    """Run one user turn to completion, returning Claude's final text reply."""
    messages: list[dict[str, Any]] = [{"role": "user", "content": user_message}]

    for _ in range(max_turns):
        response = client.messages.create(
            model=model,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason != "tool_use":
            return _extract_text(response.content)

        tool_results = []
        for block in response.content:
            if getattr(block, "type", None) != "tool_use":
                continue
            if verbose:
                print(f"  [tool_use]    {block.name}({json.dumps(block.input, ensure_ascii=False)})")
            result = call_tool(registry, block.name, block.input)
            if verbose:
                tag = "ok" if result["ok"] else "error"
                print(f"  [tool_result:{tag}] {json.dumps(result, ensure_ascii=False)}")
            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(result, ensure_ascii=False),
                    "is_error": not result["ok"],
                }
            )
        messages.append({"role": "user", "content": tool_results})

    return "(최대 turn 수를 초과해 대화를 끝맺지 못했습니다. max_turns를 늘려보세요.)"


def main() -> None:
    import sys

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY 환경변수가 설정되어 있지 않습니다. .env.example을 참고하세요.")
        raise SystemExit(1)

    import anthropic

    client = anthropic.Anthropic()
    registry = DeviceRegistry.demo_home()

    print("가전제품 제어 에이전트 (종료: exit / quit)")
    print("등록된 기기:", ", ".join(d["device_id"] for d in registry.list_devices()))

    if len(sys.argv) > 1:
        # one-shot mode: python -m appliance_agent.agent "거실 에어컨 24도로 맞춰줘"
        reply = run_agent(client, registry, " ".join(sys.argv[1:]))
        print("\n[assistant]", reply)
        return

    while True:
        try:
            user_message = input("\n[you] ")
        except (EOFError, KeyboardInterrupt):
            break
        if user_message.strip().lower() in {"exit", "quit"}:
            break
        reply = run_agent(client, registry, user_message)
        print("[assistant]", reply)


if __name__ == "__main__":
    main()
