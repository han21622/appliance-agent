# 가전제품 제어 AI Agent — Tool Calling + MCP 데모

Claude Tool Use(function calling)와 Model Context Protocol(MCP)을 이용해, 자연어 명령으로 가전기기(에어컨/세탁기/냉장고/공기청정기)를 제어하는 미니 AI Agent입니다. 판교 AI Intern 공고의 "LLM/VLM API를 활용한 제품 기능 프로토타이핑"과 "Tool calling, MCP 등을 활용한 AI Agent 워크플로우 설계 및 검증" 두 항목을 실제로 구현해보기 위해 만들었습니다.

## 문제 정의

LLM이 가전제품을 제어하려면 자연어 명령을 실제 기기 동작으로 안전하게 매핑해야 합니다. 이 과정에는 세 가지가 필요합니다: (1) 모델이 어떤 도구를, 어떤 인자로 호출할지 스스로 판단할 수 있는 tool 스키마 설계, (2) 잘못된 입력(범위 밖 온도, 존재하지 않는 기기, 오프라인 기기 등)을 시스템이 죽지 않고 처리해 모델에게 되돌려주는 예외 처리, (3) 같은 도구 세트를 여러 클라이언트(커스텀 에이전트, Claude Desktop 같은 MCP 클라이언트)에서 재사용할 수 있는 구조. 이 프로젝트는 이 세 가지를 작은 스코프로 구현하고 자동화된 테스트로 검증합니다.

## 본인의 역할

개인 프로젝트로 전체 설계·구현·테스트를 수행했습니다. 도메인 계층(가전기기 상태 시뮬레이션), tool 스키마·dispatch 계층, Claude tool-use 기반 에이전트 루프, MCP 서버, 그리고 pytest 기반 검증(성공/실패 경로 모두)까지 전부 직접 작성했습니다.

## AI 활용 부분

- **Tool 스키마 설계**: `list_devices`, `get_device_status`, `set_power`, `set_temperature`, `set_mode`, `start_cycle` 6개 tool을 JSON Schema로 정의하고, Claude Messages API의 `tools` 파라미터로 전달합니다 (`src/appliance_agent/tools.py`).
- **출력 스키마 정의**: 모든 tool 호출 결과를 `{"ok": true, "result": {...}}` 또는 `{"ok": false, "error": {"type": ..., "message": ...}}` 형태로 통일해서, 모델이 성공/실패를 항상 같은 구조로 파싱할 수 있게 했습니다.
- **예외 처리**: 존재하지 않는 기기, 오프라인 기기, 허용 범위를 벗어난 온도, 잘못된 모드/코스 값 등을 도메인 계층에서 커스텀 예외로 던지고, dispatch 계층에서 잡아 위 출력 스키마로 변환합니다. 예외가 발생해도 프로세스가 죽지 않고, 모델이 오류를 이해해서 사용자에게 설명하거나 대안을 제안할 수 있습니다.
- **AI Agent 워크플로우**: `agent.py`의 `run_agent()`가 tool_use → tool 실행 → tool_result 반환 → (반복) → 최종 답변까지의 루프를 구현합니다.
- **MCP 서버**: 동일한 tool 세트를 `mcp_server.py`에서 MCP 서버로도 노출해, Claude Desktop 등 어떤 MCP 클라이언트에서도 바로 이 "가전제품 홈"을 제어할 수 있습니다. 에이전트 루프와 MCP 서버가 도메인 로직과 예외 처리를 중복 구현하지 않도록, 둘 다 같은 `call_tool()` dispatch 함수를 통해서만 기기에 접근합니다.

## 결과 (검증)

pytest 17개 테스트로 다음을 검증했습니다: 도메인 계층의 정상/오류 경로 9종(범위 밖 온도, 미지원 동작, 오프라인 기기 등), tool dispatch의 출력 스키마 일관성 5종, 그리고 에이전트 루프 자체의 정확성 3종 — 실제 네트워크 호출 없이 스크립트로 만든 fake Claude 클라이언트로 "tool 호출 → 상태 변경 → 다음 턴에 결과 전달" 흐름과 "max_turns 초과 시 무한루프 대신 안전하게 종료"까지 확인했습니다. MCP 서버는 6개 tool이 올바른 입력 스키마로 등록되는 것을 직접 확인했습니다.

```
$ python -m pytest tests/ -v
======================== 17 passed in 0.03s ========================
```

## 아키텍처

```
                 ┌────────────────────┐
 자연어 명령 ───▶│  agent.py (CLI)     │──┐
                 │  Claude tool-use    │  │
                 └────────────────────┘  │
                                          ▼
 MCP 클라이언트 ─▶┌────────────────────┐   ┌──────────────┐   ┌──────────────┐
 (Claude Desktop) │ mcp_server.py      │──▶│  tools.py    │──▶│ devices.py   │
                  │ (FastMCP)          │   │ call_tool()  │   │ DeviceRegistry│
                  └────────────────────┘   │ 스키마+예외처리│   │ (mock 가전) │
                                            └──────────────┘   └──────────────┘
```

## 실행 방법

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # ANTHROPIC_API_KEY 입력

# 1) CLI 에이전트 (대화형)
cd src && python -m appliance_agent.agent

# 2) CLI 에이전트 (한 번만 실행)
python -m appliance_agent.agent "거실 에어컨 22도로 맞춰줘"

# 3) MCP 서버 (Claude Desktop 등에 등록해서 사용)
python -m appliance_agent.mcp_server
```

Claude Desktop에 MCP 서버로 등록하려면 `claude_desktop_config.json`에 아래처럼 추가하세요 (경로는 실제 클론 위치로 수정):

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

## 테스트

```bash
pip install -r requirements.txt
python -m pytest tests/ -v
```

API 키 없이도 전체 테스트가 통과합니다 — 에이전트 루프 테스트는 실제 Anthropic API 대신 스크립트로 응답을 재생하는 fake client를 사용합니다 (`tests/test_agent.py`).

## 데모 시나리오 (기본 홈 구성)

| device_id | 기기 | 초기 상태 |
|---|---|---|
| `living-room-ac` | 거실 에어컨 | 켜짐, 24도, cooling |
| `bedroom-purifier` | 안방 공기청정기 | 꺼짐, auto |
| `utility-washer` | 세탁실 세탁기 | **오프라인** (오류 처리 데모용) |
| `kitchen-fridge` | 주방 냉장고 | 켜짐, 4도 |

`utility-washer`는 일부러 오프라인 상태로 시작합니다 — "세탁기 돌려줘" 같은 명령을 보내면 에이전트가 `DeviceOfflineError`를 받아 사용자에게 자연어로 설명하는 흐름을 바로 확인할 수 있습니다.

## 향후 확장 아이디어

- 실제 기기 상태 스트리밍(웹소켓)에 맞춰 tool_result에 타임스탬프/버전 추가
- 다중 기기 동시 제어("집 안 조명이랑 에어컨 다 꺼줘") 시 병렬 tool_use 처리
- 대화 히스토리를 DB에 저장해 세션 간 컨텍스트 유지
- VLM을 붙여 기기 상태를 이미지(예: 세탁기 표시창 사진)로도 인식
