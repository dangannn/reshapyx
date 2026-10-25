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
