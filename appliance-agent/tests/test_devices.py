import pytest

from appliance_agent.devices import (
    DeviceNotFoundError,
    DeviceOfflineError,
    DeviceRegistry,
    InvalidParameterError,
    UnsupportedOperationError,
)


@pytest.fixture
def home() -> DeviceRegistry:
    return DeviceRegistry.demo_home()


def test_list_devices_returns_all_four(home):
    devices = home.list_devices()
    assert {d["device_id"] for d in devices} == {
        "living-room-ac",
        "bedroom-purifier",
        "utility-washer",
        "kitchen-fridge",
    }


def test_unknown_device_raises(home):
    with pytest.raises(DeviceNotFoundError):
        home.get_status("does-not-exist")


def test_set_temperature_happy_path(home):
    status = home.set_temperature("living-room-ac", 22.0)
    assert status["temperature"] == 22.0


def test_set_temperature_out_of_range_raises(home):
    with pytest.raises(InvalidParameterError):
        home.set_temperature("living-room-ac", 40.0)  # aircon max is 30


def test_set_temperature_unsupported_device_raises(home):
    with pytest.raises(UnsupportedOperationError):
        home.set_temperature("bedroom-purifier", 22.0)  # purifiers have no temperature


def test_offline_device_rejects_commands(home):
    # demo_home() ships the washer offline on purpose to exercise this path
    with pytest.raises(DeviceOfflineError):
        home.start_cycle("utility-washer", "standard")


def test_cannot_set_temperature_while_powered_off(home):
    home.set_power("living-room-ac", False)
    with pytest.raises(InvalidParameterError):
        home.set_temperature("living-room-ac", 22.0)


def test_invalid_mode_raises(home):
    with pytest.raises(InvalidParameterError):
        home.set_mode("living-room-ac", "not-a-real-mode")


def test_start_cycle_happy_path(home):
    home.set_power("utility-washer", True) if home.devices["utility-washer"].online else None
    home.devices["utility-washer"].online = True  # bring it online for this test
    home.set_power("utility-washer", True)
    status = home.start_cycle("utility-washer", "quick")
    assert status["status"] == "running:quick"
