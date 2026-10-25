"""Reshapyx: a small image processing API."""

import logging
import os
from contextlib import asynccontextmanager
from io import BytesIO
from time import perf_counter
from typing import Annotated, Literal

from fastapi import FastAPI, File, HTTPException, Query, Response, UploadFile
from PIL import Image, ImageOps, UnidentifiedImageError

VERSION = "0.1.0"
SUPPORTED_FORMATS = ("PNG", "JPEG", "WEBP")
logger = logging.getLogger("uvicorn.error")


def positive_env(name: str, default: int) -> int:
    value = int(os.getenv(name, str(default)))
    if value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


MAX_UPLOAD_BYTES = positive_env("MAX_UPLOAD_MB", 10) * 1024 * 1024
MAX_IMAGE_PIXELS = positive_env("MAX_IMAGE_PIXELS", 20_000_000)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(
        "Reshapyx %s started; upload limit=%s bytes, pixel limit=%s",
        VERSION,
        MAX_UPLOAD_BYTES,
        MAX_IMAGE_PIXELS,
    )
    yield
    logger.info("Reshapyx stopped")


app = FastAPI(title="Reshapyx", version=VERSION, lifespan=lifespan)


@app.middleware("http")
async def log_request(request, call_next):
    started = perf_counter()
    response = await call_next(request)
    logger.info(
        "%s %s status=%s duration_ms=%.1f",
        request.method,
        request.url.path,
        response.status_code,
        (perf_counter() - started) * 1000,
    )
    return response


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/version")
def version():
    return {"version": VERSION}


def read_image(file: UploadFile) -> tuple[Image.Image, str, int]:
    data = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "Image file exceeds the upload limit")
    try:
        with Image.open(BytesIO(data), formats=SUPPORTED_FORMATS) as source:
            if source.width * source.height > MAX_IMAGE_PIXELS:
                raise HTTPException(413, "Image exceeds the pixel limit")
            if getattr(source, "is_animated", False):
                raise HTTPException(422, "Animated images are not supported")
            source.load()
            return source.copy(), source.format, len(data)
    except Image.DecompressionBombError as exc:
        raise HTTPException(413, "Image exceeds the decoder safety limit") from exc
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise HTTPException(422, "Upload a valid PNG, JPEG or WebP image") from exc


@app.post("/images/info")
def image_info(file: Annotated[UploadFile, File()]):
    image, image_format, size_bytes = read_image(file)
    with image:
        return {
            "format": image_format,
            "width": image.width,
            "height": image.height,
            "mode": image.mode,
            "size_bytes": size_bytes,
        }


def image_response(image: Image.Image, image_format: str) -> Response:
    buffer = BytesIO()
    image.save(buffer, format=image_format)
    extension = {"PNG": "png", "JPEG": "jpg", "WEBP": "webp"}[image_format]
    media_type = {"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp"}
    return Response(
        content=buffer.getvalue(),
        media_type=media_type[image_format],
        headers={"Content-Disposition": f'attachment; filename="reshapyx.{extension}"'},
    )


@app.post(
    "/images/resize",
    response_class=Response,
    responses={200: {"content": {"image/png": {"schema": {"type": "string", "format": "binary"}}}}},
)
def resize_image(
    file: Annotated[UploadFile, File()],
    width: Annotated[int, Query(ge=1, le=4096)],
    height: Annotated[int, Query(ge=1, le=4096)],
):
    """Fit inside width x height without cropping or enlarging; return PNG."""
    image, _, _ = read_image(file)
    with image, ImageOps.exif_transpose(image) as oriented:
        oriented.thumbnail((width, height), Image.Resampling.LANCZOS)
        with oriented.convert("RGBA") as rgba:
            return image_response(rgba, "PNG")


@app.post(
    "/images/convert",
    response_class=Response,
    responses={
        200: {
            "content": {
                media_type: {"schema": {"type": "string", "format": "binary"}}
                for media_type in ("image/png", "image/jpeg", "image/webp")
            }
        }
    },
)
def convert_image(
    file: Annotated[UploadFile, File()],
    format: Annotated[Literal["png", "jpeg", "webp"], Query()],
):
    """Convert an image; transparent pixels become white in JPEG."""
    image, _, _ = read_image(file)
    with image, ImageOps.exif_transpose(image) as oriented:
        if format == "jpeg":
            with oriented.convert("RGBA") as rgba:
                with Image.new("RGB", rgba.size, "white") as background:
                    background.paste(rgba, mask=rgba.getchannel("A"))
                    return image_response(background, "JPEG")
        with oriented.convert("RGBA") as rgba:
            return image_response(rgba, format.upper())
