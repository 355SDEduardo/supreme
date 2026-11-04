from pathlib import Path
from tempfile import TemporaryDirectory
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_root_endpoint():
    response = client.get("/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "PDF Tools" in response.text
    assert 'id="merge-form"' in response.text
    assert 'id="number-form"' in response.text
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "default-src 'self'" in response.headers["content-security-policy"]


def test_status_endpoint():
    response = client.get("/api/status")
    assert response.status_code == 200
    assert response.json()["status"] == "online"


def test_frontend_static_assets():
    css_response = client.get("/static/styles.css")
    js_response = client.get("/static/app.js")

    assert css_response.status_code == 200
    assert css_response.headers["content-type"].startswith("text/css")
    assert "--cobalt: #2563eb" in css_response.text
    assert js_response.status_code == 200
    assert js_response.headers["content-type"].startswith("text/javascript")
    assert 'fetch("/api/status"' in js_response.text


def test_merge_api(sample_pdf_files):
    file_a, file_b = sample_pdf_files
    with open(file_a, "rb") as f1, open(file_b, "rb") as f2:
        files = [
            ("files", (file_a.name, f1, "application/pdf")),
            ("files", (file_b.name, f2, "application/pdf")),
        ]
        response = client.post("/pdf/merge", files=files)
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/pdf"


def test_split_api(sample_pdf_files):
    file_a, _ = sample_pdf_files
    with open(file_a, "rb") as f1:
        files = {"file": (file_a.name, f1, "application/pdf")}
        data = {"mode": "every_page"}
        response = client.post("/pdf/split", files=files, data=data)
        assert response.status_code == 200
        assert response.headers["content-type"] in ["application/pdf", "application/zip"]


def test_organize_api(sample_pdf_files):
    file_a, _ = sample_pdf_files
    with open(file_a, "rb") as f1:
        files = [("files", (file_a.name, f1, "application/pdf"))]
        data = {"mode": "reorder", "page_order_str": "3,1,2"}
        response = client.post("/pdf/organize", files=files, data=data)
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/pdf"


def test_rotate_api(sample_pdf_files):
    file_a, _ = sample_pdf_files
    with open(file_a, "rb") as f1:
        files = {"file": (file_a.name, f1, "application/pdf")}
        data = {"angle": "90", "pages_str": "1,3"}
        response = client.post("/pdf/rotate", files=files, data=data)
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/pdf"


def test_repair_api(sample_pdf_files):
    file_a, _ = sample_pdf_files
    with open(file_a, "rb") as f1:
        files = {"file": (file_a.name, f1, "application/pdf")}
        response = client.post("/pdf/repair", files=files)
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/pdf"


def test_number_api(sample_pdf_files):
    file_a, _ = sample_pdf_files
    with open(file_a, "rb") as f1:
        files = {"file": (file_a.name, f1, "application/pdf")}
        data = {
            "position": "bottom-center",
            "first_number": 1,
            "template": "Página {current} de {total}",
        }
        response = client.post("/pdf/number", files=files, data=data)
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/pdf"
