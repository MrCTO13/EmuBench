"""Draw the original EmuBench cartridge icon. Run with Python and Pillow."""
from pathlib import Path

from PIL import Image, ImageDraw


ASSETS = Path(__file__).resolve().parents[2] / "emubench" / "assets"
SIZES = (16, 24, 32, 48, 64, 128, 256, 512, 1024)
INK = "#14243b"
BLUE = "#2053af"
GOLD = "#ffdf83"


def cartridge(size):
    # All dimensions use the same 128-unit grid. Small icons omit shallow mold lines.
    scale = max(2, size * 2 // 128)
    surface = Image.new("RGBA", (128 * scale, 128 * scale))
    pen = ImageDraw.Draw(surface)

    def polygon(points, color):
        pen.polygon([(int(x * scale), int(y * scale)) for x, y in points], fill=color)

    def rect(bounds, color, radius=0):
        pen.rounded_rectangle(tuple(int(v * scale) for v in bounds), radius=radius * scale, fill=color)

    # A notched cartridge, with the narrow side and underside visible.
    polygon([(9, 19), (16, 12), (91, 12), (99, 20), (112, 20), (119, 27),
             (119, 109), (112, 117), (15, 117), (9, 111)], INK)
    polygon([(12, 20), (17, 15), (90, 15), (98, 23), (111, 23), (115, 27),
             (115, 106), (110, 111), (16, 111), (12, 107)], BLUE)
    polygon([(12, 20), (17, 15), (90, 15), (97, 22), (93, 22), (88, 18),
             (19, 18), (15, 22), (15, 105), (12, 107)], "#6499e6")
    polygon([(110, 109), (115, 104), (115, 28), (112, 25), (112, 102),
             (108, 106), (17, 106), (17, 109)], "#163b82")

    if size >= 48:
        for y in (21, 24):
            rect((38, y, 84, y + .9), "#13428c")
            rect((38, y + 1, 84, y + 1.6), "#5384d0")

    # A screen-printed, two-stripe label with a square-cut E.
    rect((20, 31, 106, 92), INK, 3)
    rect((23, 34, 103, 89), "#132e60", 1)
    polygon([(77, 34), (91, 34), (62, 89), (48, 89)], "#1d437c")
    polygon([(96, 34), (100, 34), (71, 89), (67, 89)], "#244d87")
    polygon([(40, 44), (88, 44), (83, 54), (53, 54), (53, 59),
             (76, 59), (71, 68), (53, 68), (53, 73), (80, 73),
             (75, 82), (40, 82)], GOLD)
    if size >= 48:
        rect((24, 97, 26, 99), INK, 1)
        rect((99, 97, 101, 99), INK, 1)

    rect((38, 102, 88, 115), INK, 1)
    rect((41, 105, 85, 114), "#9d784a")
    width = 6 if size <= 32 else 3
    for x in range(42, 85, width + 2):
        rect((x, 105, min(x + width, 85), 113), "#efbd68")

    return surface.resize((size, size), Image.Resampling.LANCZOS)


def main():
    ASSETS.mkdir(exist_ok=True, parents=True)
    icons = {size: cartridge(size) for size in SIZES}
    icons[128].save(ASSETS / "emubench.png", optimize=True)
    windows = [n for n in SIZES if n <= 256]
    icons[256].save(ASSETS / "emubench.ico", sizes=[(n, n) for n in windows],
                    append_images=[icons[n] for n in windows if n < 256])
    icons[1024].save(ASSETS / "emubench.icns", append_images=list(icons.values()))


if __name__ == "__main__":
    main()
