"""Mock smart-appliance device layer.

This simulates a small fleet of home appliances (air conditioner, washing
machine, refrigerator, air purifier) with an in-memory state store. It
exists so the agent/tool-calling layer above it has something real to call,
validate against, and fail against — without needing an actual device or
cloud API.

Kept dependency-free (stdlib only) so it's trivial to read, test, and swap
for a real device API later.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

DeviceType = Literal["aircon", "washer", "fridge", "purifier"]


class DeviceError(Exception):
    """Base class for all device-layer errors the agent must handle."""


class DeviceNotFoundError(DeviceError):
    def __init__(self, device_id: str):
        super().__init__(f"'{device_id}' 라는 기기를 찾을 수 없습니다.")
        self.device_id = device_id


class DeviceOfflineError(DeviceError):
    def __init__(self, device_id: str):
        super().__init__(f"'{device_id}' 기기가 오프라인 상태라 명령을 수행할 수 없습니다.")
        self.device_id = device_id


class InvalidParameterError(DeviceError):
    def __init__(self, message: str):
        super().__init__(message)


class UnsupportedOperationError(DeviceError):
    def __init__(self, device_id: str, operation: str, device_type: str):
        super().__init__(
            f"'{device_id}'({device_type})는 '{operation}' 동작을 지원하지 않습니다."
        )


# valid ranges / options per device type — used for parameter validation
TEMPERATURE_RANGES: dict[DeviceType, tuple[float, float]] = {
    "aircon": (18.0, 30.0),
    "fridge": (1.0, 7.0),
}
MODE_OPTIONS: dict[DeviceType, tuple[str, ...]] = {
    "aircon": ("cooling", "heating", "dehumidify", "fan"),
    "purifier": ("auto", "sleep", "turbo"),
}
WASH_CYCLES: tuple[str, ...] = ("standard", "quick", "heavy", "wool")


@dataclass
class Device:
    device_id: str
    name: str
    type: DeviceType
    power: bool = False
    online: bool = True
    temperature: float | None = None
    mode: str | None = None
    status: str = "idle"  # idle | running | error


@dataclass
class DeviceRegistry:
    """In-memory fleet of devices. One instance = one 'home'."""

    devices: dict[str, Device] = field(default_factory=dict)

    @classmethod
    def demo_home(cls) -> "DeviceRegistry":
        """A small fixed fleet used for the CLI demo and tests."""
        devices = {
            "living-room-ac": Device("living-room-ac", "거실 에어컨", "aircon", power=True, temperature=24.0, mode="cooling"),
            "bedroom-purifier": Device("bedroom-purifier", "안방 공기청정기", "purifier", power=False, mode="auto"),
            "utility-washer": Device("utility-washer", "세탁실 세탁기", "washer", power=False),
            "kitchen-fridge": Device("kitchen-fridge", "주방 냉장고", "fridge", power=True, temperature=4.0, online=True),
        }
        # simulate one flaky/offline device to exercise error handling
        devices["utility-washer"].online = False
        return cls(devices=devices)

    def _get(self, device_id: str) -> Device:
        if device_id not in self.devices:
            raise DeviceNotFoundError(device_id)
        return self.devices[device_id]

    def list_devices(self) -> list[dict]:
        return [
            {
                "device_id": d.device_id,
                "name": d.name,
                "type": d.type,
                "power": d.power,
                "online": d.online,
                "status": d.status,
            }
            for d in self.devices.values()
        ]

    def get_status(self, device_id: str) -> dict:
        d = self._get(device_id)
        return {
            "device_id": d.device_id,
            "name": d.name,
            "type": d.type,
            "power": d.power,
            "online": d.online,
            "temperature": d.temperature,
            "mode": d.mode,
            "status": d.status,
        }

    def set_power(self, device_id: str, power: bool) -> dict:
        d = self._get(device_id)
        if not d.online:
            raise DeviceOfflineError(device_id)
        d.power = power
        d.status = "idle" if power else "off"
        return self.get_status(device_id)

    def set_temperature(self, device_id: str, temperature: float) -> dict:
        d = self._get(device_id)
        if not d.online:
            raise DeviceOfflineError(device_id)
        if d.type not in TEMPERATURE_RANGES:
            raise UnsupportedOperationError(device_id, "set_temperature", d.type)
        lo, hi = TEMPERATURE_RANGES[d.type]
        if not (lo <= temperature <= hi):
            raise InvalidParameterError(
                f"{d.name}({d.type})의 온도 설정 범위는 {lo}~{hi}도입니다. 요청값: {temperature}"
            )
        if not d.power:
            raise InvalidParameterError(f"{d.name}이(가) 꺼져 있습니다. 먼저 전원을 켜주세요.")
        d.temperature = temperature
        return self.get_status(device_id)

    def set_mode(self, device_id: str, mode: str) -> dict:
        d = self._get(device_id)
        if not d.online:
            raise DeviceOfflineError(device_id)
        if d.type not in MODE_OPTIONS:
            raise UnsupportedOperationError(device_id, "set_mode", d.type)
        if mode not in MODE_OPTIONS[d.type]:
            raise InvalidParameterError(
                f"{d.name}({d.type})의 지원 모드: {', '.join(MODE_OPTIONS[d.type])}. 요청값: {mode}"
            )
        d.mode = mode
        return self.get_status(device_id)

    def start_cycle(self, device_id: str, cycle: str) -> dict:
        d = self._get(device_id)
        if not d.online:
            raise DeviceOfflineError(device_id)
        if d.type != "washer":
            raise UnsupportedOperationError(device_id, "start_cycle", d.type)
        if cycle not in WASH_CYCLES:
            raise InvalidParameterError(f"지원하는 세탁 코스: {', '.join(WASH_CYCLES)}. 요청값: {cycle}")
        if not d.power:
            raise InvalidParameterError(f"{d.name}이(가) 꺼져 있습니다. 먼저 전원을 켜주세요.")
        d.status = f"running:{cycle}"
        return self.get_status(device_id)
