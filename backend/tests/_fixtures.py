"""Shared PIL test fixtures (in-memory PNG data URLs)."""
import base64
import io
from PIL import Image, ImageDraw


def to_dataurl(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def solid_png(color, size=(400, 400)) -> str:
    return to_dataurl(Image.new("RGB", size, color))


def solid_rgba_png(color, size=(400, 400)) -> str:
    return to_dataurl(Image.new("RGBA", size, color))


def transparent_circle_png(size=(200, 200)) -> str:
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse([20, 20, size[0] - 20, size[1] - 20], fill=(255, 0, 0, 160))
    return to_dataurl(img)
