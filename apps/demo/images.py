import io
from collections.abc import Callable

from PIL import Image, ImageDraw, ImageFont

Box = tuple[int, int, int, int]
Painter = Callable[[ImageDraw.ImageDraw, int, tuple[str, str]], None]

INK = "#111827"
GLASS = "#0b1220"
WHITE = "#ffffff"


FONT_CANDIDATES = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
    "DejaVuSans-Bold.ttf",
)


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for candidate in FONT_CANDIDATES:
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def _gradient(size: tuple[int, int], top: str, bottom: str) -> Image.Image:
    width, height = size
    start, end = _rgb(top), _rgb(bottom)
    image = Image.new("RGB", size)
    draw = ImageDraw.Draw(image)
    for y in range(height):
        ratio = y / max(height - 1, 1)
        draw.line(
            [(0, y), (width, y)],
            fill=tuple(int(start[i] + (end[i] - start[i]) * ratio) for i in range(3)),
        )
    return image


def _rgb(color: str) -> tuple[int, ...]:
    return tuple(int(color[index : index + 2], 16) for index in (1, 3, 5))


def _screen(draw: ImageDraw.ImageDraw, box: Box, colors: tuple[str, str], radius: int) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=colors[0])
    left, top, right, bottom = box
    inset = radius // 2 + 4
    draw.polygon(
        [
            (left + inset, bottom - inset),
            (right - inset, top + (bottom - top) * 2 // 5),
            (right - inset, bottom - inset),
        ],
        fill=colors[1],
    )


def phone(draw: ImageDraw.ImageDraw, size: int, colors: tuple[str, str]) -> None:
    body = (size * 32 // 100, size * 12 // 100, size * 68 // 100, size * 82 // 100)
    draw.rounded_rectangle(body, radius=size // 14, fill=INK)
    inner = (body[0] + 14, body[1] + 14, body[2] - 14, body[3] - 14)
    _screen(draw, inner, colors, size // 18)
    draw.rounded_rectangle(
        (size // 2 - 30, body[1] + 24, size // 2 + 30, body[1] + 40), radius=8, fill=INK
    )


def tablet(draw: ImageDraw.ImageDraw, size: int, colors: tuple[str, str]) -> None:
    body = (size * 20 // 100, size * 18 // 100, size * 80 // 100, size * 78 // 100)
    draw.rounded_rectangle(body, radius=size // 20, fill=INK)
    _screen(draw, (body[0] + 20, body[1] + 20, body[2] - 20, body[3] - 20), colors, size // 30)


def laptop(draw: ImageDraw.ImageDraw, size: int, colors: tuple[str, str]) -> None:
    lid = (size * 18 // 100, size * 20 // 100, size * 82 // 100, size * 62 // 100)
    draw.rounded_rectangle(lid, radius=18, fill=INK)
    _screen(draw, (lid[0] + 16, lid[1] + 16, lid[2] - 16, lid[3] - 16), colors, 8)
    draw.polygon(
        [
            (size * 10 // 100, size * 68 // 100),
            (size * 90 // 100, size * 68 // 100),
            (size * 84 // 100, size * 62 // 100),
            (size * 16 // 100, size * 62 // 100),
        ],
        fill="#374151",
    )


def earbuds(draw: ImageDraw.ImageDraw, size: int, colors: tuple[str, str]) -> None:
    draw.rounded_rectangle(
        (size * 30 // 100, size * 45 // 100, size * 70 // 100, size * 75 // 100),
        radius=60,
        fill=WHITE,
    )
    for left in (size * 30 // 100, size * 52 // 100):
        draw.ellipse(
            (left, size * 18 // 100, left + size // 6, size * 18 // 100 + size // 6), fill=WHITE
        )
        draw.rounded_rectangle(
            (left + 36, size * 30 // 100, left + 66, size * 48 // 100), radius=14, fill=WHITE
        )
    draw.line(
        (size * 30 // 100, size * 56 // 100, size * 70 // 100, size * 56 // 100),
        fill=colors[0],
        width=6,
    )


def headphone(draw: ImageDraw.ImageDraw, size: int, colors: tuple[str, str]) -> None:
    draw.arc(
        (size * 22 // 100, size * 15 // 100, size * 78 // 100, size * 75 // 100),
        180,
        360,
        fill=INK,
        width=34,
    )
    for left in (size * 16 // 100, size * 66 // 100):
        draw.rounded_rectangle(
            (left, size * 42 // 100, left + size // 6, size * 72 // 100), radius=40, fill=INK
        )
        draw.rounded_rectangle(
            (left + 20, size * 47 // 100, left + size // 6 - 20, size * 67 // 100),
            radius=30,
            fill=colors[0],
        )


def speaker(draw: ImageDraw.ImageDraw, size: int, colors: tuple[str, str]) -> None:
    draw.rounded_rectangle(
        (size * 20 // 100, size * 34 // 100, size * 80 // 100, size * 66 // 100),
        radius=size // 6,
        fill=INK,
    )
    for center in (size * 34 // 100, size * 66 // 100):
        draw.ellipse((center - 50, size // 2 - 50, center + 50, size // 2 + 50), fill=colors[0])
        draw.ellipse((center - 20, size // 2 - 20, center + 20, size // 2 + 20), fill=INK)


def watch(draw: ImageDraw.ImageDraw, size: int, colors: tuple[str, str]) -> None:
    draw.rounded_rectangle(
        (size * 40 // 100, size * 8 // 100, size * 60 // 100, size * 92 // 100),
        radius=30,
        fill="#1f2937",
    )
    draw.rounded_rectangle(
        (size * 30 // 100, size * 28 // 100, size * 70 // 100, size * 72 // 100),
        radius=60,
        fill=INK,
    )
    _screen(
        draw, (size * 34 // 100, size * 32 // 100, size * 66 // 100, size * 68 // 100), colors, 50
    )


def band(draw: ImageDraw.ImageDraw, size: int, colors: tuple[str, str]) -> None:
    draw.rounded_rectangle(
        (size * 43 // 100, size * 8 // 100, size * 57 // 100, size * 92 // 100),
        radius=30,
        fill="#1f2937",
    )
    draw.rounded_rectangle(
        (size * 38 // 100, size * 30 // 100, size * 62 // 100, size * 70 // 100),
        radius=50,
        fill=INK,
    )
    _screen(
        draw, (size * 41 // 100, size * 34 // 100, size * 59 // 100, size * 66 // 100), colors, 40
    )


def charger(draw: ImageDraw.ImageDraw, size: int, colors: tuple[str, str]) -> None:
    draw.rounded_rectangle(
        (size * 33 // 100, size * 35 // 100, size * 67 // 100, size * 75 // 100),
        radius=40,
        fill=WHITE,
    )
    for left in (size * 40 // 100, size * 54 // 100):
        draw.rectangle((left, size * 20 // 100, left + 18, size * 35 // 100), fill="#9ca3af")
    draw.rounded_rectangle(
        (size * 44 // 100, size * 58 // 100, size * 56 // 100, size * 64 // 100),
        radius=6,
        fill=colors[0],
    )


def powerbank(draw: ImageDraw.ImageDraw, size: int, colors: tuple[str, str]) -> None:
    draw.rounded_rectangle(
        (size * 28 // 100, size * 18 // 100, size * 72 // 100, size * 82 // 100),
        radius=50,
        fill=INK,
    )
    for row in range(4):
        top = size * 60 // 100 - row * 30
        draw.rounded_rectangle(
            (size * 44 // 100, top, size * 56 // 100, top + 18), radius=6, fill=colors[1]
        )


def cable(draw: ImageDraw.ImageDraw, size: int, colors: tuple[str, str]) -> None:
    draw.arc(
        (size * 20 // 100, size * 20 // 100, size * 80 // 100, size * 80 // 100),
        30,
        330,
        fill=INK,
        width=24,
    )
    draw.rounded_rectangle(
        (size * 70 // 100, size * 30 // 100, size * 84 // 100, size * 42 // 100),
        radius=10,
        fill="#9ca3af",
    )
    draw.rounded_rectangle(
        (size * 70 // 100, size * 58 // 100, size * 84 // 100, size * 70 // 100),
        radius=10,
        fill=colors[0],
    )


def case(draw: ImageDraw.ImageDraw, size: int, colors: tuple[str, str]) -> None:
    draw.rounded_rectangle(
        (size * 32 // 100, size * 12 // 100, size * 68 // 100, size * 88 // 100),
        radius=size // 12,
        fill=colors[0],
    )
    draw.rounded_rectangle(
        (size * 38 // 100, size * 18 // 100, size * 52 // 100, size * 36 // 100),
        radius=24,
        fill=INK,
    )


def controller(draw: ImageDraw.ImageDraw, size: int, _colors: tuple[str, str]) -> None:
    draw.rounded_rectangle(
        (size * 18 // 100, size * 34 // 100, size * 82 // 100, size * 66 // 100),
        radius=size // 7,
        fill=INK,
    )
    draw.ellipse(
        (size * 30 // 100, size * 42 // 100, size * 40 // 100, size * 52 // 100), fill="#4b5563"
    )
    for dx, dy, color in (
        (0, -30, "#22c55e"),
        (30, 0, "#ef4444"),
        (-30, 0, "#3b82f6"),
        (0, 30, "#eab308"),
    ):
        center = (size * 66 // 100 + dx, size * 48 // 100 + dy)
        draw.ellipse((center[0] - 14, center[1] - 14, center[0] + 14, center[1] + 14), fill=color)


def console(draw: ImageDraw.ImageDraw, size: int, colors: tuple[str, str]) -> None:
    draw.rounded_rectangle(
        (size * 12 // 100, size * 32 // 100, size * 26 // 100, size * 68 // 100),
        radius=30,
        fill="#ef4444",
    )
    draw.rounded_rectangle(
        (size * 74 // 100, size * 32 // 100, size * 88 // 100, size * 68 // 100),
        radius=30,
        fill="#3b82f6",
    )
    draw.rounded_rectangle(
        (size * 26 // 100, size * 30 // 100, size * 74 // 100, size * 70 // 100),
        radius=14,
        fill=INK,
    )
    _screen(
        draw, (size * 29 // 100, size * 33 // 100, size * 71 // 100, size * 67 // 100), colors, 8
    )


PAINTERS: dict[str, Painter] = {
    "phone": phone,
    "tablet": tablet,
    "laptop": laptop,
    "earbuds": earbuds,
    "headphone": headphone,
    "speaker": speaker,
    "watch": watch,
    "band": band,
    "charger": charger,
    "powerbank": powerbank,
    "cable": cable,
    "case": case,
    "controller": controller,
    "console": console,
}


def product_image(shape: str, brand: str, colors: tuple[str, str], *, size: int = 900) -> bytes:
    image = _gradient((size, size), "#f8fafc", "#e2e8f0")
    draw = ImageDraw.Draw(image)
    draw.ellipse((size // 8, size // 6, size * 7 // 8, size * 23 // 24), fill=_tint(colors[1]))
    PAINTERS[shape](draw, size, colors)
    draw.text(
        (size // 2, size * 94 // 100),
        brand.upper(),
        fill="#475569",
        font=_font(size // 22),
        anchor="ms",
    )
    return _jpeg(image)


def category_image(shape: str, name: str, colors: tuple[str, str], *, size: int = 700) -> bytes:
    image = _gradient((size, size), *colors)
    draw = ImageDraw.Draw(image)
    PAINTERS[shape](draw, size, ("#ffffff", "#e2e8f0"))
    draw.text((size // 2, size * 95 // 100), name, fill=WHITE, font=_font(size // 14), anchor="ms")
    return _jpeg(image)


def banner_image(title: str, subtitle: str, shape: str, colors: tuple[str, str]) -> bytes:
    width, height = 1800, 640
    image = _gradient((width, height), *colors)
    draw = ImageDraw.Draw(image)
    draw.text((110, 250), title, fill=WHITE, font=_font(84), anchor="ls")
    draw.text((110, 340), subtitle, fill=WHITE, font=_font(44), anchor="ls")
    device = Image.new("RGBA", (height, height), (0, 0, 0, 0))
    PAINTERS[shape](ImageDraw.Draw(device), height, ("#ffffff", "#cbd5e1"))
    image.paste(device, (width - height - 80, 0), device)
    return _jpeg(image)


def _tint(color: str) -> tuple[int, ...]:
    return tuple(int(channel + (255 - channel) * 0.65) for channel in _rgb(color))


def _jpeg(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=88, optimize=True)
    return buffer.getvalue()
