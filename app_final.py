"""Reshapyx: a small image processing API."""

from fastapi import FastAPI

VERSION = "0.1.0"
app = FastAPI(title="Reshapyx", version=VERSION)
