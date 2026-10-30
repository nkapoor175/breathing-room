
from fastapi.testclient import TestClient

from imagine.fake_imagine import MAX_IMAGE_BYTES, app


def test_rejects_non_image_upload():
    with TestClient(app) as client:
        response = client.post(
            "/twin/from-photo",
            files={"file": ("test.txt", b"hello", "text/plain")},
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "Upload an image file."


def test_rejects_empty_image():
    with TestClient(app) as client:
        response = client.post(
            "/twin/from-photo",
            files={"file": ("empty.png", b"", "image/png")},
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "The uploaded image is empty."


def test_rejects_oversized_upload():
    contents = b"x" * (MAX_IMAGE_BYTES + 1)

    with TestClient(app) as client:
        response = client.post(
            "/twin/from-photo",
            files={"file": ("large.png", contents, "image/png")},
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "Image must be 10 MB or smaller."


def test_rejects_invalid_image_data():
    with TestClient(app) as client:
        response = client.post(
            "/twin/from-photo",
            files={
                "file": ("fake.png", b"this is not an image", "image/png")
            },
        )

    assert response.status_code == 400
    assert response.json()["detail"] == (
        "The uploaded file is not a valid image."
    )


from io import BytesIO

from PIL import Image


def test_valid_image_returns_503_without_nebius_key(monkeypatch):
    monkeypatch.delenv("NEBIUS_API_KEY", raising=False)

    image_buffer = BytesIO()
    Image.new("RGB", (20, 20), "white").save(
        image_buffer, format="PNG"
    )

    with TestClient(app) as client:
        response = client.post(
            "/twin/from-photo",
            files={
                "file": (
                    "valid.png",
                    image_buffer.getvalue(),
                    "image/png",
                )
            },
        )

    assert response.status_code == 503
    assert "Nebius API key" in response.json()["detail"]
