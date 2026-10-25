import logging
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from PIL import Image

import app_final
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


@pytest.mark.parametrize("source_format", ["PNG", "JPEG", "WEBP"])
@pytest.mark.parametrize("target_format", ["png", "jpeg", "webp"])
def test_convert(client, source_format, target_format):
    response = client.post(
        "/images/convert",
        params={"format": target_format},
        files={"file": ("image", image_bytes(source_format))},
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == f"image/{target_format}"
    assert "attachment" in response.headers["content-disposition"]
    with Image.open(BytesIO(response.content)) as image:
        image.load()
        assert image.format == target_format.upper()
        assert image.size == (120, 80)


def test_jpeg_flattens_transparency_on_white(client):
    response = client.post(
        "/images/convert?format=jpeg",
        files={"file": ("image.png", image_bytes(mode="RGBA", color=(255, 0, 0, 0)))},
    )
    assert response.status_code == 200
    with Image.open(BytesIO(response.content)) as image:
        assert image.mode == "RGB"
        assert image.getpixel((0, 0)) == (255, 255, 255)


def test_unsupported_output_format(client):
    response = client.post(
        "/images/convert?format=gif", files={"file": ("image.png", image_bytes())}
    )
    assert response.status_code == 422


@pytest.mark.parametrize("route", ["info", "resize?width=60&height=60", "convert?format=png"])
def test_upload_limit(client, monkeypatch, route):
    monkeypatch.setattr(app_final, "MAX_UPLOAD_BYTES", 10)
    response = client.post(
        f"/images/{route}", files={"file": ("image.png", image_bytes())}
    )
    assert response.status_code == 413


def test_exact_upload_limit(client, monkeypatch):
    data = image_bytes()
    monkeypatch.setattr(app_final, "MAX_UPLOAD_BYTES", len(data))
    response = client.post("/images/info", files={"file": ("image.png", data)})
    assert response.status_code == 200


def test_pixel_limit(client, monkeypatch):
    monkeypatch.setattr(app_final, "MAX_IMAGE_PIXELS", 100)
    response = client.post("/images/info", files={"file": ("image.png", image_bytes())})
    assert response.status_code == 413


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


@pytest.mark.parametrize("value", ["0", "-1", "not-a-number"])
def test_invalid_environment_setting(monkeypatch, value):
    monkeypatch.setenv("MAX_UPLOAD_MB", value)
    with pytest.raises(ValueError):
        app_final.positive_env("MAX_UPLOAD_MB", 10)


def test_environment_setting(monkeypatch):
    monkeypatch.setenv("MAX_UPLOAD_MB", "3")
    assert app_final.positive_env("MAX_UPLOAD_MB", 10) == 3


def test_request_logging(client, caplog):
    with caplog.at_level(logging.INFO, logger="uvicorn.error"):
        client.get("/health")
    assert "GET /health status=200" in caplog.text


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


@pytest.mark.parametrize("target", ["png", "webp"])
def test_conversion_preserves_alpha(client, target):
    response = client.post(
        f"/images/convert?format={target}",
        files={"file": ("image.png", image_bytes(mode="RGBA", color=(255, 0, 0, 128)))},
    )
    assert response.status_code == 200
    with Image.open(BytesIO(response.content)) as image:
        assert image.getpixel((0, 0))[3] == 128


def test_resize_preserves_alpha(client):
    response = client.post(
        "/images/resize?width=60&height=60",
        files={"file": ("image.png", image_bytes(mode="RGBA", color=(255, 0, 0, 128)))},
    )
    assert response.status_code == 200
    with Image.open(BytesIO(response.content)) as image:
        assert image.getpixel((0, 0))[3] == 128


def test_openapi_describes_image_downloads(client):
    paths = client.get("/openapi.json").json()["paths"]
    resize = paths["/images/resize"]["post"]["responses"]["200"]["content"]
    assert resize["image/png"]["schema"]["format"] == "binary"
    convert = paths["/images/convert"]["post"]["responses"]["200"]["content"]
    assert set(convert) == {"image/png", "image/jpeg", "image/webp"}
