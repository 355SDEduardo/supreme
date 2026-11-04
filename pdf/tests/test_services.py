from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from pypdf import PdfReader

from app.services.merge_pdf import merge_pdfs, merge_selected_pages
from app.services.number_pdf import add_page_numbers
from app.services.organize_pdf import delete_pages, duplicate_page, organize_pdf, reorder_pages, reverse_pdf
from app.services.repair_pdf import repair_pdf
from app.services.rotate_pdf import rotate_pdf
from app.services.split_pdf import extract_page_range, split_by_page_count, split_by_ranges, split_by_size, split_every_page
from app.utils.page_ranges import parse_page_range_string
from app.validators.pdf_validator import has_pdf_signature, validate_pdf
from tests.conftest import create_dummy_pdf


def test_has_pdf_signature(sample_pdf_files):
    file_a, _ = sample_pdf_files
    assert has_pdf_signature(file_a) is True


def test_validate_pdf(sample_pdf_files):
    file_a, _ = sample_pdf_files
    validate_pdf(file_a)  # Should not raise


def test_parse_page_range_string():
    assert parse_page_range_string("1-3, 5", 5) == [1, 2, 3, 5]


def test_merge_pdfs(sample_pdf_files):
    file_a, file_b = sample_pdf_files
    with TemporaryDirectory() as temp_dir:
        output_file = Path(temp_dir) / "merged.pdf"
        result = merge_pdfs([file_a, file_b], output_file)
        assert result.exists()

        reader = PdfReader(result)
        assert len(reader.pages) == 5  # 3 + 2 pages


def test_merge_selected_pages(sample_pdf_files):
    file_a, file_b = sample_pdf_files
    with TemporaryDirectory() as temp_dir:
        output_file = Path(temp_dir) / "merged_selected.pdf"
        result = merge_selected_pages(
            [(file_a, [0, 2]), (file_b, [1])],
            output_file,
        )
        assert result.exists()

        reader = PdfReader(result)
        assert len(reader.pages) == 3


def test_split_every_page(sample_pdf_files):
    file_a, _ = sample_pdf_files
    with TemporaryDirectory() as temp_dir:
        out_dir = Path(temp_dir) / "split_out"
        generated = split_every_page(file_a, out_dir)
        assert len(generated) == 3
        for path in generated:
            assert path.exists()
            assert len(PdfReader(path).pages) == 1


def test_extract_page_range(sample_pdf_files):
    file_a, _ = sample_pdf_files
    with TemporaryDirectory() as temp_dir:
        output_file = Path(temp_dir) / "range.pdf"
        result = extract_page_range(file_a, output_file, 1, 2)
        assert result.exists()
        assert len(PdfReader(result).pages) == 2


def test_split_by_ranges(sample_pdf_files):
    file_a, _ = sample_pdf_files
    with TemporaryDirectory() as temp_dir:
        out_dir = Path(temp_dir) / "split_ranges"
        generated = split_by_ranges(file_a, [(1, 2), (3, 3)], out_dir)
        assert len(generated) == 2


def test_split_by_page_count(sample_pdf_files):
    file_a, _ = sample_pdf_files
    with TemporaryDirectory() as temp_dir:
        out_dir = Path(temp_dir) / "split_count"
        generated = split_by_page_count(file_a, 2, out_dir)
        assert len(generated) == 2  # 3 pages split by 2 => 2 files (2 pages + 1 page)


def test_split_by_size(sample_pdf_files):
    file_a, _ = sample_pdf_files
    with TemporaryDirectory() as temp_dir:
        out_dir = Path(temp_dir) / "split_size"
        generated = split_by_size(file_a, 0.01, out_dir)  # very small threshold
        assert len(generated) >= 1


def test_reorder_pages(sample_pdf_files):
    file_a, _ = sample_pdf_files
    with TemporaryDirectory() as temp_dir:
        output_file = Path(temp_dir) / "reordered.pdf"
        result = reorder_pages(file_a, output_file, [3, 1, 2])
        assert result.exists()
        assert len(PdfReader(result).pages) == 3


def test_delete_pages(sample_pdf_files):
    file_a, _ = sample_pdf_files
    with TemporaryDirectory() as temp_dir:
        output_file = Path(temp_dir) / "deleted.pdf"
        result = delete_pages(file_a, output_file, [2])
        assert result.exists()
        assert len(PdfReader(result).pages) == 2


def test_duplicate_page(sample_pdf_files):
    file_a, _ = sample_pdf_files
    with TemporaryDirectory() as temp_dir:
        output_file = Path(temp_dir) / "duplicated.pdf"
        result = duplicate_page(file_a, output_file, 1, copies=2)
        assert result.exists()
        assert len(PdfReader(result).pages) == 5  # 3 + 2 copies


def test_reverse_pdf(sample_pdf_files):
    file_a, _ = sample_pdf_files
    with TemporaryDirectory() as temp_dir:
        output_file = Path(temp_dir) / "reversed.pdf"
        result = reverse_pdf(file_a, output_file)
        assert result.exists()
        assert len(PdfReader(result).pages) == 3


def test_organize_pdf(sample_pdf_files):
    file_a, file_b = sample_pdf_files
    with TemporaryDirectory() as temp_dir:
        output_file = Path(temp_dir) / "organized.pdf"
        input_files = {"docA": file_a, "docB": file_b}
        page_items = [
            {"source": "docA", "page": 3, "rotation": 0},
            {"source": "docB", "page": 1, "rotation": 90},
        ]
        result = organize_pdf(input_files, page_items, output_file)
        assert result.exists()
        assert len(PdfReader(result).pages) == 2


def test_rotate_pdf(sample_pdf_files):
    file_a, _ = sample_pdf_files
    with TemporaryDirectory() as temp_dir:
        output_file = Path(temp_dir) / "rotated.pdf"
        result = rotate_pdf(file_a, output_file, 90, pages=[1, 3])
        assert result.exists()
        reader = PdfReader(result)
        assert len(reader.pages) == 3


def test_repair_pdf(sample_pdf_files):
    file_a, _ = sample_pdf_files
    with TemporaryDirectory() as temp_dir:
        output_file = Path(temp_dir) / "repaired.pdf"
        result = repair_pdf(file_a, output_file)
        assert result.exists()


def test_add_page_numbers(sample_pdf_files):
    file_a, _ = sample_pdf_files
    with TemporaryDirectory() as temp_dir:
        output_file = Path(temp_dir) / "numbered.pdf"
        result = add_page_numbers(
            file_a,
            output_file,
            position="bottom-center",
            first_number=1,
            template="Página {current} de {total}",
        )
        assert result.exists()
        assert len(PdfReader(result).pages) == 3
