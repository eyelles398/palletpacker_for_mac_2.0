"""
Генерирует icon.ico для приложения — паллета с коробками.
Запуск: python make_icon.py
"""
from PIL import Image, ImageDraw


def make_icon(path="icon.ico", sizes=(16, 32, 48, 64, 128, 256)):
    images = []
    for s in sizes:
        img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)

        # зелёный скруглённый фон
        r = max(2, s // 7)
        d.rounded_rectangle(
            [0, 0, s - 1, s - 1],
            radius=r,
            fill=(46, 125, 50, 255),
        )

        # деревянная паллета
        pal_top = int(s * 0.78)
        pal_bot = int(s * 0.93)
        d.rectangle(
            [int(s * 0.08), pal_top, int(s * 0.92), pal_bot],
            fill=(139, 69, 19, 255),
        )
        # «доски» паллеты
        d.line(
            [int(s * 0.08), (pal_top + pal_bot) // 2,
             int(s * 0.92), (pal_top + pal_bot) // 2],
            fill=(90, 45, 10, 255), width=max(1, s // 48),
        )

        # три коробки
        box = int(s * 0.26)
        outline = max(1, s // 48)
        positions = [
            (0.14, 0.50),
            (0.50, 0.50),
            (0.32, 0.22),
        ]
        for px, py in positions:
            x1 = int(s * px)
            y1 = int(s * py)
            d.rectangle(
                [x1, y1, x1 + box, y1 + box],
                fill=(255, 193, 7, 255),
                outline=(120, 80, 0, 255),
                width=outline,
            )
            # крышка коробки (полоска)
            d.line(
                [x1, y1 + box // 3, x1 + box, y1 + box // 3],
                fill=(120, 80, 0, 255), width=max(1, s // 64),
            )

        images.append(img)

    images[0].save(path, format="ICO", sizes=[(s, s) for s in sizes])
    print(f"Иконка сохранена: {path}")


if __name__ == "__main__":
    make_icon()