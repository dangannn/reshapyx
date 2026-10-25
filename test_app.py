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
