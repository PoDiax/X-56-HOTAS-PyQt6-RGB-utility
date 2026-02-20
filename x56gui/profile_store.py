from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from .effects import EFFECT_MODES, EFFECT_OFF
from .protocol import SUPPORTED_PRODUCTS


@dataclass(frozen=True)
class DeviceDefaultProfile:
    enabled: bool = False
    name: str = "Default"
    red: int = 255
    green: int = 255
    blue: int = 255
    effect_enabled: bool = False
    effect_mode: str = EFFECT_OFF
    effect_speed: int = 3
    effect_brightness: int = 100

    def to_json(self) -> dict[str, object]:
        return {
            "enabled": self.enabled,
            "name": self.name,
            "red": self.red,
            "green": self.green,
            "blue": self.blue,
            "effect_enabled": self.effect_enabled,
            "effect_mode": self.effect_mode,
            "effect_speed": self.effect_speed,
            "effect_brightness": self.effect_brightness,
        }

    @staticmethod
    def from_json(data: dict[str, object]) -> DeviceDefaultProfile:
        return DeviceDefaultProfile(
            enabled=bool(data.get("enabled", False)),
            name=str(data.get("name", "Default")),
            red=_clamp_rgb(data.get("red", 255)),
            green=_clamp_rgb(data.get("green", 255)),
            blue=_clamp_rgb(data.get("blue", 255)),
            effect_enabled=bool(data.get("effect_enabled", False)),
            effect_mode=_effect_mode(data.get("effect_mode", EFFECT_OFF)),
            effect_speed=_clamp_int(data.get("effect_speed", 3), 1, 20, 3),
            effect_brightness=_clamp_int(data.get("effect_brightness", 100), 5, 100, 100),
        )


class ProfileStore:
    def __init__(self) -> None:
        self._path = self._resolve_path()
        self._profiles: dict[str, DeviceDefaultProfile] = {}
        self._load()

    @staticmethod
    def _resolve_path() -> Path:
        config_home = Path.home() / ".config" / "x56gui"
        config_home.mkdir(parents=True, exist_ok=True)
        return config_home / "profiles.json"

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

            loaded: dict[str, DeviceDefaultProfile] = {}
            for key, value in profiles_raw.items():
                if not isinstance(key, str):
                    continue
                if not isinstance(value, dict):
                    continue
                loaded[key] = DeviceDefaultProfile.from_json(value)
            self._profiles = loaded
        except (OSError, json.JSONDecodeError, ValueError):
            self._profiles = {}

    def _save(self) -> None:
        payload = {
            "profiles": {k: v.to_json() for k, v in self._profiles.items()}
        }
        self._path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    @staticmethod
    def _key(product_id: int) -> str:
        return f"{product_id:04x}"

    def get(self, product_id: int) -> DeviceDefaultProfile:
        key = self._key(product_id)
        return self._profiles.get(key, DeviceDefaultProfile())

    def set(self, product_id: int, profile: DeviceDefaultProfile) -> None:
        self._profiles[self._key(product_id)] = profile
        self._save()

    def get_known_products(self) -> list[int]:
        return sorted(SUPPORTED_PRODUCTS.keys())


def _clamp_rgb(value: Any) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = 255
    return max(0, min(255, parsed))


def _clamp_int(value: Any, min_value: int, max_value: int, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(min_value, min(max_value, parsed))


def _effect_mode(value: object) -> str:
    mode = str(value).lower()
    if mode in EFFECT_MODES:
        return mode
    return EFFECT_OFF
