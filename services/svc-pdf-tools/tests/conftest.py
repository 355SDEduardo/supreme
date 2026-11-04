from pathlib import Path
from tempfile import TemporaryDirectory
import pytest
from reportlab.pdfgen import canvas


def create_dummy_pdf(filename: Path, num_pages: int = 3, title: str = "Test PDF") -> Path:
    filename.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(filename))
    for page in range(1, num_pages + 1):
        c.drawString(100, 750, f"{title} - Page {page}")
        c.drawString(100, 700, f"Content for page {page} of {num_pages}")
        c.showPage()
    c.save()
    return filename


@pytest.fixture
def sample_pdf_files():
    with TemporaryDirectory() as temp_dir:
        dir_path = Path(temp_dir)
        file_a = dir_path / "pdf_a.pdf"
        file_b = dir_path / "pdf_b.pdf"

        create_dummy_pdf(file_a, num_pages=3, title="PDF A")
        create_dummy_pdf(file_b, num_pages=2, title="PDF B")

        yield file_a, file_b
