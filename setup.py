"""
py2app конфиг для сборки PalletPacker.app на macOS.
Запуск: python setup.py py2app
"""
from setuptools import setup

APP = ["main.py"]

DATA_FILES = [
    ("", ["devices.json", "icon.icns"]),
]

OPTIONS = {
    "argv_emulation": False,
    "iconfile": "icon.icns",
    "packages": [
        "pyqtgraph",
        "OpenGL",
        "PySide6",
        "openpyxl",
        "numpy",
    ],
    "includes": [
        "PySide6.QtPrintSupport",
        "PySide6.QtOpenGLWidgets",
        "PySide6.QtOpenGL",
    ],
    "excludes": [
        "tkinter",
        "win32com",
        "pythoncom",
        "pywin32",
        "pywin32-ctypes",
    ],
    "plist": {
        "CFBundleName": "PalletPacker",
        "CFBundleDisplayName": "PalletPacker",
        "CFBundleIdentifier": "com.palletpacker.app",
        "CFBundleVersion": "2.0",
        "CFBundleShortVersionString": "2.0",
        "NSHighResolutionCapable": True,
        "LSMinimumSystemVersion": "10.15",
    },
}

setup(
    app=APP,
    data_files=DATA_FILES,
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)