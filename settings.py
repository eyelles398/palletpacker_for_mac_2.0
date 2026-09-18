"""
Сохранение/загрузка пользовательских настроек окна в settings.json.

Храним:
- размер и позицию главного окна;
- размеры сплиттеров (горизонтальный и правый вертикальный);
- параметры паллеты (Д/Ш/В, макс. вес, тара, макс. свес);
- состояние чекбоксов;
- последняя использованная папка для диалогов.
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path


def _app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).parent


SETTINGS_FILE = _app_dir() / "settings.json"

DEFAULTS: dict = {
    "window": {"width": 1400, "height": 850, "x": None, "y": None},
    "splitters": {
        "main": [480, 920],
        "right": [250, 600],
    },
    "pallet": {
        "L": 1200, "W": 800, "H": 1500,
        "max_weight": 1000, "tare_weight": 25,
        "max_overhang_mm": 0,
    },
    "flags": {
        "use_tare": False,
        "full_support": False,
        "side_on_floor": False,
        "group_by_model": False,
        "show_labels": True,
    },
    "last_dir": "",
}


def _merge(base: dict, other: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (other or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def load_settings() -> dict:
    if not SETTINGS_FILE.exists():
        return copy.deepcopy(DEFAULTS)
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return copy.deepcopy(DEFAULTS)
    return _merge(DEFAULTS, data)


def save_settings(data: dict) -> None:
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        # сохранение настроек не должно ломать приложение
        pass