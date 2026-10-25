from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app_final import app


def test_health():
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_version():
    with TestClient(app) as client:
        response = client.get("/version")
    assert response.status_code == 200
    assert response.json() == {"version": "0.1.0"}


@pytest.fixture
def client():
    with TestClient(app) as client:
        yield client


def image_bytes(image_format="PNG", size=(120, 80), mode="RGB", color="red"):
    with Image.new(mode, size, color) as image:
        buffer = BytesIO()
        image.save(buffer, format=image_format)
        return buffer.getvalue()


@pytest.mark.parametrize("image_format", ["PNG", "JPEG", "WEBP"])
def test_info(client, image_format):
    data = image_bytes(image_format)
    response = client.post("/images/info", files={"file": ("image", data)})
    assert response.status_code == 200
    assert response.json() == {
        "format": image_format,
        "width": 120,
        "height": 80,
        "mode": "RGB",
        "size_bytes": len(data),
    }


@pytest.mark.parametrize("data", [b"", b"not an image", image_bytes()[:40]])
def test_invalid_image(client, data):
    response = client.post("/images/info", files={"file": ("fake.png", data)})
    assert response.status_code == 422


def test_unsupported_format(client):
    response = client.post(
        "/images/info", files={"file": ("image.bmp", image_bytes("BMP"))}
    )
    assert response.status_code == 422


def test_animation_rejected(client):
    buffer = BytesIO()
    with (
        Image.new("RGB", (10, 10), "red") as first,
        Image.new("RGB", (10, 10), "blue") as second,
    ):
        first.save(buffer, format="PNG", save_all=True, append_images=[second])
    response = client.post(
        "/images/info", files={"file": ("animated.png", buffer.getvalue())}
    )
    assert response.status_code == 422


@pytest.mark.parametrize(
    "size,bounds,want",
    [
        ((120, 80), (60, 60), (60, 40)),
        ((80, 120), (60, 60), (40, 60)),
        ((20, 10), (60, 60), (20, 10)),
    ],
)
def test_resize(client, size, bounds, want):
    response = client.post(
        "/images/resize",
        params={"width": bounds[0], "height": bounds[1]},
        files={"file": ("image.png", image_bytes(size=size))},
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    with Image.open(BytesIO(response.content)) as image:
        assert image.size == want
        assert image.format == "PNG"


@pytest.mark.parametrize("width", [0, -1, 4097])
def test_invalid_resize_bounds(client, width):
    response = client.post(
        "/images/resize",
        params={"width": width, "height": 60},
        files={"file": ("image.png", image_bytes())},
    )
    assert response.status_code == 422


def test_resize_applies_exif_orientation(client):
    buffer = BytesIO()
    with Image.new("RGB", (120, 80), "red") as image:
        exif = Image.Exif()
        exif[274] = 6
        image.save(buffer, format="JPEG", exif=exif)
    response = client.post(
        "/images/resize?width=60&height=60", files={"file": ("photo.jpg", buffer.getvalue())}
    )
    assert response.status_code == 200
    with Image.open(BytesIO(response.content)) as image:
        assert image.size == (40, 60)
        assert image.getexif().get(274, 1) == 1


def test_resize_cmyk_jpeg(client):
    response = client.post(
        "/images/resize?width=60&height=60",
        files={"file": ("print.jpg", image_bytes("JPEG", mode="CMYK"))},
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    with Image.open(BytesIO(response.content)) as image:
        image.load()
        assert image.format == "PNG"
        assert image.size == (60, 40)
        assert image.mode == "RGBA"


def test_resize_preserves_alpha(client):
    response = client.post(
        "/images/resize?width=60&height=60",
        files={"file": ("image.png", image_bytes(mode="RGBA", color=(255, 0, 0, 128)))},
    )
    assert response.status_code == 200
    with Image.open(BytesIO(response.content)) as image:
        assert image.getpixel((0, 0))[3] == 128
