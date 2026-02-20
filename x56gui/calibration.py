from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .usb_backend import DeviceInfo

CHANNELS = ("R", "G", "B")

CALIBRATION_COLORS: dict[str, tuple[int, int, int]] = {
    "Red": (255, 0, 0),
    "Green": (0, 255, 0),
    "Blue": (0, 0, 255),
    "Orange": (190, 20, 0),
    "Purple": (180, 0, 200),
    "Pink": (190, 4, 18),
    "White": (255, 255, 255),
}


@dataclass(frozen=True)
class ColorOffset:
    red: int = 0
    green: int = 0
    blue: int = 0

    def to_json(self) -> dict[str, int]:
        return {
            "red": self.red,
            "green": self.green,
            "blue": self.blue,
        }

    @staticmethod
    def from_json(data: dict[str, object]) -> ColorOffset:
        return ColorOffset(
            red=_to_int(data.get("red", 0), 0),
            green=_to_int(data.get("green", 0), 0),
            blue=_to_int(data.get("blue", 0), 0),
        )


@dataclass(frozen=True)
class ColorCalibration:
    order: tuple[str, str, str] = ("R", "G", "B")
    gain_r: float = 1.0
    gain_g: float = 1.0
    gain_b: float = 1.0
    target_offsets: dict[str, ColorOffset] | None = None

    def apply(self, red: int, green: int, blue: int, target_name: str | None = None) -> tuple[int, int, int]:
        calibrated = [red, green, blue]

        offsets = self.target_offsets or {}
        if offsets:
            selected_target = target_name or self.closest_target_name(red, green, blue)
            offset = offsets.get(selected_target)
            if offset is not None:
                calibrated[0] = max(0, min(255, calibrated[0] + offset.red))
                calibrated[1] = max(0, min(255, calibrated[1] + offset.green))
                calibrated[2] = max(0, min(255, calibrated[2] + offset.blue))

        return calibrated[0], calibrated[1], calibrated[2]

    @staticmethod
    def closest_target_name(red: int, green: int, blue: int) -> str:
        best_name = "White"
        best_distance = float("inf")
        for name, rgb in CALIBRATION_COLORS.items():
            distance = math.sqrt((red - rgb[0]) ** 2 + (green - rgb[1]) ** 2 + (blue - rgb[2]) ** 2)
            if distance < best_distance:
                best_name = name
                best_distance = distance
        return best_name

    def offset_for(self, target_name: str) -> ColorOffset:
        offsets = self.target_offsets or {}
        return offsets.get(target_name, ColorOffset())

    def with_offset(self, target_name: str, offset: ColorOffset) -> ColorCalibration:
        offsets = dict(self.target_offsets or {})
        offsets[target_name] = offset
        return ColorCalibration(
            order=self.order,
            gain_r=self.gain_r,
            gain_g=self.gain_g,
            gain_b=self.gain_b,
            target_offsets=offsets,
        )

    def to_json(self) -> dict[str, object]:
        offsets = self.target_offsets or {}
        return {
            "order": list(self.order),
            "gain_r": self.gain_r,
            "gain_g": self.gain_g,
            "gain_b": self.gain_b,
            "target_offsets": {k: v.to_json() for k, v in offsets.items()},
        }

    @staticmethod
    def from_json(data: dict[str, object]) -> ColorCalibration:
        order_raw = data.get("order", ["R", "G", "B"])
        if not isinstance(order_raw, list) or len(order_raw) != 3:
            order = ("R", "G", "B")
        else:
            parsed = [str(x).upper() for x in order_raw]
            if any(item not in CHANNELS for item in parsed):
                order = ("R", "G", "B")
            else:
                order = (parsed[0], parsed[1], parsed[2])

        return ColorCalibration(
            order=order,
            gain_r=float(data.get("gain_r", 1.0)),
            gain_g=float(data.get("gain_g", 1.0)),
            gain_b=float(data.get("gain_b", 1.0)),
            target_offsets=_parse_offsets(data.get("target_offsets")),
        )


def _to_int(value: object, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _parse_offsets(raw: object) -> dict[str, ColorOffset]:
    if not isinstance(raw, dict):
        return {}
    parsed: dict[str, ColorOffset] = {}
    for key, value in raw.items():
        if not isinstance(key, str) or not isinstance(value, dict):
            continue
        if key not in CALIBRATION_COLORS:
            continue
        parsed[key] = ColorOffset.from_json(value)
    return parsed


class CalibrationStore:
    def __init__(self) -> None:
        self._path = self._resolve_path()
        self._profiles: dict[str, ColorCalibration] = {}
        self._load()

    @staticmethod
    def _resolve_path() -> Path:
        config_home = Path.home() / ".config" / "x56gui"
        config_home.mkdir(parents=True, exist_ok=True)
        return config_home / "calibration.json"

    @staticmethod
    def key_for_device(device: DeviceInfo) -> str:
        return f"{device.product_id:04x}"

    @staticmethod
    def _legacy_key_for_device(device: DeviceInfo) -> str:
        return f"{device.product_id:04x}:{device.bus}:{device.address}"

    def _load(self) -> None:
        try:
            if not self._path.exists():
                return
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                return
            profiles_raw = raw.get("profiles", {})
            if not isinstance(profiles_raw, dict):
                return

            loaded: dict[str, ColorCalibration] = {}
            for key, value in profiles_raw.items():
                if isinstance(key, str) and isinstance(value, dict):
                    loaded[key] = ColorCalibration.from_json(value)
            self._profiles = loaded
        except (OSError, json.JSONDecodeError, ValueError):
            self._profiles = {}

    def _save(self) -> None:
        payload = {
            "profiles": {k: v.to_json() for k, v in self._profiles.items()}
        }
        self._path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def get_for_device(self, device: DeviceInfo) -> ColorCalibration | None:
        key = self.key_for_device(device)
        direct = self._profiles.get(key)
        if direct is not None:
            return direct

        legacy_key = self._legacy_key_for_device(device)
        legacy = self._profiles.get(legacy_key)
        if legacy is not None:
            self._profiles[key] = legacy
            self._save()
            return legacy
        return None

    def set_for_device(self, device: DeviceInfo, calibration: ColorCalibration) -> None:
        key = self.key_for_device(device)
        self._profiles[key] = calibration

        legacy_key = self._legacy_key_for_device(device)
        if legacy_key in self._profiles:
            del self._profiles[legacy_key]

        self._save()

    def reset_for_device(self, device: DeviceInfo) -> None:
        key = self.key_for_device(device)
        legacy_key = self._legacy_key_for_device(device)
        changed = False
        if key in self._profiles:
            del self._profiles[key]
            changed = True
        if legacy_key in self._profiles:
            del self._profiles[legacy_key]
            changed = True
        if changed:
            self._save()
