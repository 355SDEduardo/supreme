"""Inspeção e leitura limitada de XMLs compactados, exclusivamente em memória."""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from struct import Struct
from typing import BinaryIO
from zipfile import ZIP_DEFLATED, ZIP_STORED, BadZipFile, ZipFile, is_zipfile
from zlib import error as ZlibError

from svc_nfse_engine.multilayout.models import ParseIssue

DEFAULT_MAX_ENTRIES = 500
DEFAULT_MAX_XML_BYTES = 5 * 1024 * 1024
DEFAULT_MAX_TOTAL_UNCOMPRESSED = 100 * 1024 * 1024
DEFAULT_MAX_ZIP_BYTES = 55 * 1024 * 1024


@dataclass(frozen=True)
class ZipExtractionResult:
    xml_files: list[tuple[str, bytes]]
    issues: list[ParseIssue]
    total_entries_inspected: int
    total_xmls_found: int


def _safe_name(filename: str) -> str:
    name = filename.replace("\\", "/").rsplit("/", 1)[-1].strip()
    return "".join(char for char in name if char.isprintable())[:180] or "arquivo"


def is_zip_content(source: BinaryIO | bytes) -> bool:
    """Verifica a assinatura ZIP preservando posição e propriedade do fluxo."""
    stream = BytesIO(source) if isinstance(source, bytes) else source
    position = stream.tell()
    try:
        stream.seek(0)
        return is_zipfile(stream)
    finally:
        stream.seek(position)


def _check_directory(stream: BinaryIO, max_entries: int, filename: str) -> None:
    """Conta metadados em buffers pequenos antes de ZipFile criar ZipInfos.

    Não confia apenas no contador do rodapé: percorre também os registros
    centrais, sem ler seus nomes, comentários ou campos extras para memória.
    """
    footer = Struct("<4s4H2IH")
    stream.seek(0, 2)
    size = stream.tell()
    tail_size = min(size, footer.size + 65535)
    stream.seek(size - tail_size)
    tail = stream.read(tail_size)
    offset = tail.rfind(b"PK\x05\x06")
    if offset < 0 or len(tail) - offset < footer.size:
        raise ValueError(f"O diretório do ZIP '{filename}' está corrompido.")
    _, disk, start_disk, disk_entries, total_entries, directory_size, directory_offset, comment_size = footer.unpack_from(tail, offset)
    if disk or start_disk or disk_entries != total_entries:
        raise ValueError(f"O ZIP '{filename}' dividido em volumes não é aceito.")
    if total_entries > max_entries:
        raise ValueError(f"O ZIP '{filename}' contém entradas demais ({total_entries} > {max_entries}).")
    # ZIP64 com diretório estendido é desnecessário para os limites de ingestão.
    if total_entries == 65535 or directory_size == 0xFFFFFFFF or directory_offset == 0xFFFFFFFF:
        raise ValueError(f"O ZIP '{filename}' usa um diretório ZIP64 não suportado.")
    directory_end = size - tail_size + offset
    directory_start = directory_end - directory_size
    if directory_start < 0 or offset + footer.size + comment_size > len(tail):
        raise ValueError(f"O diretório do ZIP '{filename}' está corrompido.")
    stream.seek(directory_start)
    inspected = 0
    lengths = Struct("<3H")
    while stream.tell() < directory_end:
        if directory_end - stream.tell() < 46:
            raise ValueError(f"O diretório do ZIP '{filename}' está corrompido.")
        header = stream.read(46)
        if len(header) != 46 or header[:4] != b"PK\x01\x02":
            raise ValueError(f"O diretório do ZIP '{filename}' está corrompido.")
        inspected += 1
        if inspected > max_entries:
            raise ValueError(f"O ZIP '{filename}' contém entradas demais (> {max_entries}).")
        variable_size = sum(lengths.unpack_from(header, 28))
        if variable_size > directory_end - stream.tell():
            raise ValueError(f"O diretório do ZIP '{filename}' está corrompido.")
        stream.seek(variable_size, 1)
    if inspected != total_entries:
        raise ValueError(f"O contador de entradas do ZIP '{filename}' está corrompido.")


def extract_xmls_from_zip(
    source: BinaryIO | bytes,
    *,
    zip_filename: str = "arquivo.zip",
    max_entries: int = DEFAULT_MAX_ENTRIES,
    max_xml_files: int | None = None,
    max_xml_bytes: int = DEFAULT_MAX_XML_BYTES,
    max_total_bytes: int = DEFAULT_MAX_TOTAL_UNCOMPRESSED,
    max_zip_bytes: int = DEFAULT_MAX_ZIP_BYTES,
) -> ZipExtractionResult:
    """Retorna XMLs e rejeições; violações globais geram ValueError.

    O fluxo deve permitir seek/tell. Sua posição é restaurada e ele não é
    fechado. Nenhum caminho do ZIP é utilizado para escrever em disco.
    """
    if min(max_entries, max_xml_bytes, max_zip_bytes) <= 0 or max_total_bytes < 0:
        raise ValueError("Os limites do ZIP devem ser positivos (total pode ser zero).")
    if max_xml_files is not None and max_xml_files <= 0:
        raise ValueError("O limite de arquivos XML deve ser positivo.")
    stream = BytesIO(source) if isinstance(source, bytes) else source
    position = stream.tell()
    filename = _safe_name(zip_filename)
    xml_files: list[tuple[str, bytes]] = []
    issues: list[ParseIssue] = []
    try:
        stream.seek(0, 2)
        if stream.tell() > max_zip_bytes:
            raise ValueError(
                f"O tamanho compactado do ZIP '{filename}' excede o limite de {max_zip_bytes} bytes."
            )
        if not is_zip_content(stream):
            raise ValueError(f"O arquivo '{filename}' não é um ZIP válido ou está corrompido.")
        _check_directory(stream, max_entries, filename)
        stream.seek(0)
        with ZipFile(stream) as archive:
            entries = archive.infolist()
            if len(entries) > max_entries:
                raise ValueError(
                    f"O ZIP '{filename}' contém entradas demais ({len(entries)} > {max_entries})."
                )
            if max_xml_files is not None:
                xml_count = sum(
                    not info.is_dir()
                    and Path(info.filename.replace("\\", "/").rsplit("/", 1)[-1].strip()).suffix.casefold() == ".xml"
                    for info in entries
                )
                if xml_count > max_xml_files:
                    raise ValueError(
                        f"O ZIP '{filename}' excede o limite de {max_xml_files} arquivos XML "
                        f"({xml_count} encontrados)."
                    )
            if sum(info.file_size for info in entries) > max_total_bytes:
                raise ValueError(
                    f"O tamanho descompactado total declarado no ZIP '{filename}' "
                    f"excede o limite de {max_total_bytes} bytes."
                )
            total_read = 0
            for info in entries:
                if info.is_dir():
                    continue
                basename = info.filename.replace("\\", "/").rsplit("/", 1)[-1].strip()
                if Path(basename).suffix.casefold() != ".xml":
                    continue
                clean_name = _safe_name(basename)
                if info.flag_bits & 1:
                    issues.append(ParseIssue(clean_name, "XML compactado com senha não é aceito."))
                    continue
                if info.file_size > max_xml_bytes:
                    issues.append(ParseIssue(
                        clean_name, f"XML excede o limite individual de {max_xml_bytes} bytes."
                    ))
                    continue
                # DEFLATE limita a saída do descompressor; outros codecs podem
                # alocar buffers internos maiores que o limite solicitado.
                if info.compress_type not in {ZIP_STORED, ZIP_DEFLATED}:
                    issues.append(ParseIssue(clean_name, "Método de compressão do XML não é aceito. Use ZIP padrão (DEFLATE)."))
                    continue
                try:
                    read_limit = min(max_xml_bytes, max_total_bytes - total_read) + 1
                    with archive.open(info) as entry:
                        content = entry.read(read_limit)
                except (BadZipFile, EOFError, OSError, RuntimeError, NotImplementedError, ZlibError):
                    issues.append(ParseIssue(clean_name, "XML compactado corrompido ou com compressão inválida."))
                    continue
                total_read += len(content)
                if total_read > max_total_bytes:
                    raise ValueError(
                        f"O volume total de dados descompactados do ZIP '{filename}' "
                        f"excede o limite de {max_total_bytes} bytes."
                    )
                if len(content) > max_xml_bytes:
                    issues.append(ParseIssue(
                        clean_name, f"XML excedeu o limite de leitura de {max_xml_bytes} bytes."
                    ))
                    continue
                xml_files.append((clean_name, content))
        return ZipExtractionResult(xml_files, issues, len(entries), len(xml_files))
    except BadZipFile as exc:
        raise ValueError(f"O arquivo ZIP '{filename}' está corrompido.") from exc
    finally:
        stream.seek(position)
