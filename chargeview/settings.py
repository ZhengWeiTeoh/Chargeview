import json
import os
import tempfile
from pathlib import Path

CONFIG = Path(os.environ["LOCALAPPDATA"]) / "DeskCharge" / "settings.json"


BATTERY_CACHE = CONFIG.with_name("battery.json")


def load(path=CONFIG):
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def save(data, path=CONFIG):
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as temp:
            json.dump(data, temp, indent=2)
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def keyboard_battery(devices, config, stop):
    profile = config.get("keyboard")
    candidates = [(path, name, caps) for path, name, caps in devices
                  if "crush" in name.casefold() or "vid_320f&pid_5088" in path.casefold()]
    if not profile:
        status = "Battery protocol not configured" if candidates else "Keyboard disconnected"
        return None, status, "WOBKEY Crush80"
    from chargeview.hardware.windows_hid import feature, query_input
    match = next(((path, name, caps) for path, name, caps in devices
                  if path.lower() == profile["path"].lower()), None)
    if match is None:
        return None, "Calibrated interface disconnected", "Calibrated HID protocol"
    path, _, caps = match
    signature = bytes.fromhex(profile.get("signature", ""))
    data = (query_input(path, bytes.fromhex(profile["request"]), stop, signature)
            if profile.get("request") else feature(path, profile["report"], caps.feature))
    if not data:
        return None, "No battery response", "Calibrated HID protocol"
    if not data.startswith(signature):
        return None, "Unexpected battery response", "Calibrated HID protocol"
    index = profile["offset"]
    value = data[index] if 0 <= index < len(data) else 255
    if value > 100:
        return None, "Battery value unavailable", "Calibrated HID protocol"
    return value, "Connected", "Calibrated HID protocol"


