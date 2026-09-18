"""
Кроссплатформенные пути для PalletPacker.

- Windows: всё рядом с программой.
- macOS:   пользовательские данные в ~/Library/Application Support/PalletPacker/,
           ресурсы (devices.json, icon.ico) — внутри .app-бандла.
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


APP_NAME = "PalletPacker"


def app_dir() -> Path:
    """
    Папка для изменяемых пользовательских файлов:
    settings.json, devices.json, order.json.
    """
    if sys.platform == "darwin":
        d = Path.home() / "Library" / "Application Support" / APP_NAME
        d.mkdir(parents=True, exist_ok=True)
        return d

    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).parent


def resource_dir() -> Path:
    """
    Папка с вшитыми ресурсами (icon.ico, стартовый devices.json).
    """
    if getattr(sys, "frozen", False):
        if sys.platform == "darwin":
            rp = os.environ.get("RESOURCEPATH")
            if rp:
                return Path(rp)
            # fallback для py2app
            return Path(sys.executable).parent.parent / "Resources"
        return Path(sys.executable).parent

    return Path(__file__).parent


def ensure_user_files() -> None:
    """
    При первом запуске на macOS копирует devices.json и icon.ico
    из бандла в папку пользовательских данных.
    На Windows ничего не делает.
    """
    if sys.platform != "darwin":
        return

    src = resource_dir()
    dst = app_dir()

    for name in ("devices.json", "icon.ico"):
        target = dst / name
        if target.exists():
            continue
        source = src / name
        if not source.exists():
            continue
        try:
            shutil.copy2(source, target)
        except Exception:
            pass


def is_windows() -> bool:
    return sys.platform.startswith("win")


def is_macos() -> bool:
    return sys.platform == "darwin"