"""
Генерирует icon.icns для macOS.
Требует macOS (использует iconutil из Xcode CLT).
Запуск: python make_icns.py
"""
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw


def draw_icon(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    r = max(2, size // 7)
    d.rounded_rectangle([0, 0, size - 1, size - 1],
                        radius=r, fill=(46, 125, 50, 255))

    pal_top = int(size * 0.78)
    pal_bot = int(size * 0.93)
    d.rectangle([int(size * 0.08), pal_top,
                 int(size * 0.92), pal_bot],
                fill=(139, 69, 19, 255))
    d.line([int(size * 0.08), (pal_top + pal_bot) // 2,
            int(size * 0.92), (pal_top + pal_bot) // 2],
           fill=(90, 45, 10, 255), width=max(1, size // 48))

    box = int(size * 0.26)
    outline = max(1, size // 48)
    for px, py in [(0.14, 0.50), (0.50, 0.50), (0.32, 0.22)]:
        x1, y1 = int(size * px), int(size * py)
        d.rectangle([x1, y1, x1 + box, y1 + box],
                    fill=(255, 193, 7, 255),
                    outline=(120, 80, 0, 255), width=outline)
        d.line([x1, y1 + box // 3, x1 + box, y1 + box // 3],
               fill=(120, 80, 0, 255), width=max(1, size // 64))
    return img


def make_icns(path: str = "icon.icns") -> None:
    if sys.platform != "darwin":
        print("make_icns.py работает только на macOS.")
        sys.exit(1)

    iconset = Path("icon.iconset")
    if iconset.exists():
        shutil.rmtree(iconset)
    iconset.mkdir()

    sizes = {
        "icon_16x16.png":      16,
        "icon_16x16@2x.png":   32,
        "icon_32x32.png":      32,
        "icon_32x32@2x.png":   64,
        "icon_128x128.png":    128,
        "icon_128x128@2x.png": 256,
        "icon_256x256.png":    256,
        "icon_256x256@2x.png": 512,
        "icon_512x512.png":    512,
        "icon_512x512@2x.png": 1024,
    }
    for name, size in sizes.items():
        draw_icon(size).save(iconset / name, "PNG")

    subprocess.run(
        ["iconutil", "-c", "icns", str(iconset), "-o", path],
        check=True,
    )
    shutil.rmtree(iconset)
    print(f"Иконка сохранена: {path}")


if __name__ == "__main__":
    make_icns()