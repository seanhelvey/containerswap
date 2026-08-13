"""Generate the PNG app icons from a simple drawing.

Run after changing the brand colour: `uv run python scripts/make_icons.py`
Kept as a script rather than a build step so there is still no frontend toolchain.
"""

from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent.parent / "static" / "icons"
GREEN = (27, 94, 63)
WHITE = (255, 255, 255)


def draw_icon(size: int, *, maskable: bool = False) -> Image.Image:
    img = Image.new("RGB", (size, size), GREEN)
    draw = ImageDraw.Draw(img)
    s = size / 64.0
    # Maskable icons need their art inside the safe zone (the middle 80%).
    inset = size * 0.1 if maskable else 0

    def box(x0, y0, x1, y1):
        scale = (size - 2 * inset) / size
        return [
            inset + x0 * s * scale,
            inset + y0 * s * scale,
            inset + x1 * s * scale,
            inset + y1 * s * scale,
        ]

    draw.rectangle(box(26, 12, 38, 18), fill=WHITE)  # lid
    draw.rounded_rectangle(box(20, 22, 44, 52), radius=6 * s, fill=WHITE)  # jar
    draw.rectangle(box(23, 34, 41, 38), fill=GREEN)  # label bands
    draw.rectangle(box(23, 41, 41, 45), fill=GREEN)
    return img


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    draw_icon(192).save(OUT / "icon-192.png", optimize=True)
    draw_icon(512).save(OUT / "icon-512.png", optimize=True)
    draw_icon(512, maskable=True).save(OUT / "icon-maskable.png", optimize=True)
    print(f"wrote icons to {OUT}")


if __name__ == "__main__":
    main()
