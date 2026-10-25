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
