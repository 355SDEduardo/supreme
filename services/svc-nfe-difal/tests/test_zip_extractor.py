from __future__ import annotations

import struct
from io import BytesIO
from zipfile import ZIP_BZIP2, ZIP_DEFLATED, ZIP_STORED, ZipFile

import pytest

from svc_nfe_difal.core.zip_extractor import extract_xmls_from_zip, is_zip_content
from .sample_data import SAMPLE_XML


def make_zip(entries: list[tuple[str, bytes]], compression: int = ZIP_DEFLATED) -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w", compression=compression) as archive:
        for name, content in entries:
            archive.writestr(name, content)
    return buffer.getvalue()


def test_extract_valid_zip_and_preserve_caller_stream() -> None:
    payload = make_zip([("nota1.xml", SAMPLE_XML), ("nota2.XML", SAMPLE_XML)])
    stream = BytesIO(payload)
    stream.seek(7)
    assert is_zip_content(stream)
    assert stream.tell() == 7
    result = extract_xmls_from_zip(stream)
    assert result.xml_files == [("nota1.xml", SAMPLE_XML), ("nota2.XML", SAMPLE_XML)]
    assert result.issues == []
    assert result.total_entries_inspected == result.total_xmls_found == 2
    assert stream.tell() == 7
    assert not stream.closed


def test_subfolders_traversal_and_non_xml_are_safe(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    payload = make_zip([
        ("subpasta/", b""),
        ("../../nota1.xml", SAMPLE_XML),
        (r"..\outra\nota2.xml", SAMPLE_XML),
        ("/absoluto/nota3.xml", SAMPLE_XML),
        ("leia-me.txt", b"ignore"),
        ("foto.jpg", b"ignore"),
        ("interno.zip", b"ignore"),
    ])
    result = extract_xmls_from_zip(payload)
    assert [name for name, _ in result.xml_files] == ["nota1.xml", "nota2.xml", "nota3.xml"]
    assert result.total_entries_inspected == 7
    assert result.issues == []
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("payload", [b"", b"isto nao e um ZIP", b"PK\x03\x04corrompido"])
def test_invalid_zip(payload: bytes) -> None:
    assert not is_zip_content(payload)
    with pytest.raises(ValueError, match="ZIP válido"):
        extract_xmls_from_zip(payload, zip_filename="lote.zip")


def test_entry_limit_counts_directories_and_ignored_files() -> None:
    payload = make_zip([("pasta/", b""), ("leia-me.txt", b""), ("nota.xml", b"x")])
    with pytest.raises(ValueError, match="entradas demais"):
        extract_xmls_from_zip(payload, max_entries=2)


def test_declared_total_limit_includes_non_xml() -> None:
    payload = make_zip([("nota.xml", b"a"), ("imagem.jpg", b"b" * 10)])
    with pytest.raises(ValueError, match="descompactado total"):
        extract_xmls_from_zip(payload, max_total_bytes=10)


def test_oversized_xml_is_an_issue_and_other_xml_survives() -> None:
    payload = make_zip([("grande.xml", b"x" * 11), ("menor.xml", b"y" * 10)])
    result = extract_xmls_from_zip(payload, max_xml_bytes=10)
    assert result.xml_files == [("menor.xml", b"y" * 10)]
    assert result.issues[0].filename == "grande.xml"
    assert "limite individual" in result.issues[0].message


def test_encrypted_entry_is_rejected_without_opening() -> None:
    payload = bytearray(make_zip([("senha.xml", b"x")]))
    local = payload.index(b"PK\x03\x04")
    central = payload.index(b"PK\x01\x02")
    for offset in (local + 6, central + 8):
        flags = struct.unpack_from("<H", payload, offset)[0]
        struct.pack_into("<H", payload, offset, flags | 1)
    result = extract_xmls_from_zip(bytes(payload))
    assert result.xml_files == []
    assert "senha" in result.issues[0].message


def test_corrupt_entry_is_an_issue_and_batch_continues() -> None:
    payload = bytearray(make_zip([("ruim.xml", b"original"), ("boa.xml", SAMPLE_XML)], ZIP_STORED))
    offset = payload.index(b"original")
    payload[offset] ^= 1
    result = extract_xmls_from_zip(bytes(payload))
    assert result.xml_files == [("boa.xml", SAMPLE_XML)]
    assert result.issues[0].filename == "ruim.xml"
    assert "corrompido" in result.issues[0].message


def test_compressed_size_checked_before_zip_validation() -> None:
    payload = make_zip([("nota.xml", b"x")])
    with pytest.raises(ValueError, match="compactado"):
        extract_xmls_from_zip(payload, max_zip_bytes=len(payload) - 1)


def test_empty_zip_is_valid() -> None:
    result = extract_xmls_from_zip(make_zip([]))
    assert result.xml_files == result.issues == []
    assert result.total_entries_inspected == result.total_xmls_found == 0


def test_xml_file_limit_is_separate_from_directory_and_non_xml_entries():
    payload = make_zip([
        ("pasta.xml/", b""), ("leia-me.txt", b""),
        ("nota.xml", SAMPLE_XML), ("nota.XML ", SAMPLE_XML),
    ])
    result = extract_xmls_from_zip(payload, max_xml_files=2)
    assert result.total_entries_inspected == 4
    assert len(result.xml_files) == 2


def test_xml_limit_is_checked_before_decompressing_or_ignoring_bad_xml(monkeypatch):
    payload = make_zip([("a.xml", b"corrompido"), ("b.xml", b"corrompido")])
    def forbid_open(*args, **kwargs):
        raise AssertionError("O limite deve ser validado antes da descompressão")
    monkeypatch.setattr(ZipFile, "open", forbid_open)
    with pytest.raises(ValueError, match="1 arquivos XML"):
        extract_xmls_from_zip(payload, max_xml_files=1)


@pytest.mark.parametrize("limit", [0, -1])
def test_xml_file_limit_must_be_positive(limit):
    with pytest.raises(ValueError, match="deve ser positivo"):
        extract_xmls_from_zip(make_zip([]), max_xml_files=limit)


def test_actual_reads_are_bounded_even_with_false_metadata(monkeypatch) -> None:
    payload = make_zip([("nota.xml", b"x")])
    reads = []

    class Entry(BytesIO):
        def read(self, size=-1):
            reads.append(size)
            return super().read(size)

    monkeypatch.setattr(ZipFile, "open", lambda *args, **kwargs: Entry(b"y" * 20))
    result = extract_xmls_from_zip(payload, max_xml_bytes=10)
    assert reads == [11]
    assert result.xml_files == []
    assert "limite de leitura" in result.issues[0].message


def test_actual_total_read_budget_is_enforced(monkeypatch) -> None:
    payload = make_zip([("a.xml", b"x"), ("b.xml", b"x")])
    monkeypatch.setattr(ZipFile, "open", lambda *args, **kwargs: BytesIO(b"y" * 6))
    with pytest.raises(ValueError, match="volume total"):
        extract_xmls_from_zip(payload, max_xml_bytes=10, max_total_bytes=10)


def test_unsupported_compression_is_rejected_before_reading() -> None:
    result = extract_xmls_from_zip(make_zip([("nota.xml", SAMPLE_XML)], ZIP_BZIP2))
    assert result.xml_files == []
    assert "Método de compressão" in result.issues[0].message


def test_many_entries_are_rejected_before_zipinfo_allocation(monkeypatch) -> None:
    payload = make_zip([(f"{index}.txt", b"") for index in range(501)])

    def forbid_archive(*args, **kwargs):
        raise AssertionError("ZipFile não deve alocar o diretório excessivo")

    monkeypatch.setattr("svc_nfe_difal.core.zip_extractor.ZipFile", forbid_archive)
    with pytest.raises(ValueError, match="entradas demais"):
        extract_xmls_from_zip(payload)


def test_forged_entry_counter_cannot_bypass_early_limit(monkeypatch) -> None:
    payload = bytearray(make_zip([("a.xml", b"x"), ("b.xml", b"x")]))
    footer = payload.rindex(b"PK\x05\x06")
    struct.pack_into("<HH", payload, footer + 8, 0, 0)

    def forbid_archive(*args, **kwargs):
        raise AssertionError("ZipFile não deve abrir um diretório acima do limite")

    monkeypatch.setattr("svc_nfe_difal.core.zip_extractor.ZipFile", forbid_archive)
    with pytest.raises(ValueError, match="entradas demais"):
        extract_xmls_from_zip(bytes(payload), max_entries=1)


def test_zip_with_comment_and_prepended_bytes() -> None:
    buffer = BytesIO()
    with ZipFile(buffer, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("nota.xml", SAMPLE_XML)
        archive.comment = b"lote com comentario"
    result = extract_xmls_from_zip(b"prefixo" + buffer.getvalue())
    assert result.xml_files == [("nota.xml", SAMPLE_XML)]


def test_small_zip64_local_entry_remains_supported() -> None:
    buffer = BytesIO()
    with ZipFile(buffer, "w", compression=ZIP_DEFLATED) as archive:
        with archive.open("nota.xml", "w", force_zip64=True) as entry:
            entry.write(SAMPLE_XML)
    assert extract_xmls_from_zip(buffer.getvalue()).xml_files == [("nota.xml", SAMPLE_XML)]
