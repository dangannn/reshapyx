"""Reshapyx: a small image processing API."""

from io import BytesIO
from typing import Annotated, Literal

from fastapi import FastAPI, File, HTTPException, Query, Response, UploadFile
from PIL import Image, ImageOps, UnidentifiedImageError

VERSION = "0.1.0"
SUPPORTED_FORMATS = ("PNG", "JPEG", "WEBP")
app = FastAPI(title="Reshapyx", version=VERSION)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/version")
def version():
    return {"version": VERSION}


def read_image(file: UploadFile) -> tuple[Image.Image, str, int]:
    data = file.file.read()
    try:
        with Image.open(BytesIO(data), formats=SUPPORTED_FORMATS) as source:
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
