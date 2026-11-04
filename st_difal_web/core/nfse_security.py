"""Bounded, non-destructive XML and ZIP ingestion."""
from __future__ import annotations

import codecs
import hashlib
import re
from dataclasses import dataclass
from io import StringIO
import xml.etree.ElementTree as ET
from zipfile import ZipFile
from io import BytesIO

from core.zip_extractor import extract_xmls_from_zip

DEFAULT_MAX_XML_BYTES = 10 * 1024 * 1024
MAX_XML_DEPTH = 50
MAX_XML_ELEMENTS = 10000
MAX_ZIP_TOTAL_BYTES = 100 * 1024 * 1024
MAX_ZIP_BYTES = 55 * 1024 * 1024
MAX_BATCH_XML_FILES = 5000


@dataclass(frozen=True)
class SafeArtifact:
    raw_bytes: bytes
    sha256: str
    size_bytes: int
    detected_encoding: str
    is_well_formed: bool
    root_element: ET.Element | None
    error_message: str | None = None
    filename: str = ""


def compute_sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def detect_encoding_and_strip_bom(raw_bytes: bytes) -> tuple[bytes, str]:
    for bom, encoding in ((codecs.BOM_UTF32_LE, "utf-32-le"),
                          (codecs.BOM_UTF32_BE, "utf-32-be"),
                          (codecs.BOM_UTF8, "utf-8"),
                          (codecs.BOM_UTF16_LE, "utf-16-le"),
                          (codecs.BOM_UTF16_BE, "utf-16-be")):
        if raw_bytes.startswith(bom):
            return raw_bytes[len(bom):], encoding
    for signature, encoding in ((b'\x00\x00\x00<', 'utf-32-be'),
                                (b'<\x00\x00\x00', 'utf-32-le'),
                                (b'\x00<', 'utf-16-be'),
                                (b'<\x00', 'utf-16-le')):
        if raw_bytes.startswith(signature):
            return raw_bytes, encoding
    match = re.search(br'<\?xml[^>]+encoding=["\']([^"\']+)["\']', raw_bytes[:512])
    return raw_bytes, match[1].decode('ascii') if match else 'utf-8'


def inspect_xml_security(raw_bytes: bytes, max_bytes: int = DEFAULT_MAX_XML_BYTES) -> None:
    if len(raw_bytes) > max_bytes:
        raise ValueError(f"XML excede o tamanho máximo permitido ({max_bytes} bytes).")
    if not raw_bytes.strip():
        raise ValueError("O conteúdo XML está vazio.")
    upper = raw_bytes.replace(b'\x00', b'').upper()
    if b'<!DOCTYPE' in upper or b'<!ENTITY' in upper:
        raise ValueError("DTD/ENTITY não permitidas (risco XXE).")


def safe_parse_xml(raw_bytes: bytes, filename: str = "", *,
                   max_bytes: int = DEFAULT_MAX_XML_BYTES) -> SafeArtifact:
    digest = compute_sha256(raw_bytes)
    inspect_xml_security(raw_bytes, max_bytes)
    encoding = ""
    try:
        content, encoding = detect_encoding_and_strip_bom(raw_bytes)
        try:
            decoded = content.decode(encoding)
        except UnicodeDecodeError:
            if encoding.lower().startswith(('utf-16', 'utf-32')):
                raise
            encoding = 'latin-1'
            decoded = content.decode(encoding)
        # Encoding aliases (e.g. UTF-7) must not hide markup from the raw-byte scan.
        upper_text = decoded.upper()
        if '<!DOCTYPE' in upper_text or '<!ENTITY' in upper_text:
            raise ValueError('DTD/ENTITY não permitidas (risco XXE).')
        depth = count = 0
        iterator = ET.iterparse(StringIO(decoded), events=('start', 'end'))
        for event, _element in iterator:
            if event == 'start':
                depth += 1
                count += 1
                if depth > MAX_XML_DEPTH or count > MAX_XML_ELEMENTS:
                    raise ValueError("XML excede limite de profundidade (50) ou elementos (10000).")
            else:
                depth -= 1
        return SafeArtifact(raw_bytes, digest, len(raw_bytes), encoding, True,
                            iterator.root, filename=filename)
    except (ET.ParseError, UnicodeError, LookupError, ValueError) as exc:
        return SafeArtifact(raw_bytes, digest, len(raw_bytes), encoding, False,
                            None, str(exc), filename)


def ingest_nfse_zip(zip_bytes: bytes, filename: str = 'pacote.zip', *,
                    max_total_bytes: int = MAX_ZIP_TOTAL_BYTES,
                    max_xml_files: int = MAX_BATCH_XML_FILES) -> tuple[list[SafeArtifact], list[str]]:
    extracted = extract_xmls_from_zip(
        zip_bytes, zip_filename=filename, max_entries=MAX_BATCH_XML_FILES,
        max_xml_files=max_xml_files, max_xml_bytes=DEFAULT_MAX_XML_BYTES,
        max_total_bytes=max_total_bytes, max_zip_bytes=MAX_ZIP_BYTES)
    issues = [f"{issue.filename}: {issue.message}" for issue in extracted.issues]
    with ZipFile(BytesIO(zip_bytes)) as archive:
        for info in archive.infolist():
            if not info.is_dir() and not info.filename.lower().endswith('.xml'):
                issues.append(f"{info.filename}: arquivo não XML ignorado.")
    artifacts = []
    for name, content in extracted.xml_files:
        try:
            artifacts.append(safe_parse_xml(content, f'{filename}/{name}'))
        except ValueError as exc:
            artifacts.append(SafeArtifact(content, compute_sha256(content), len(content), '',
                                          False, None, str(exc), f'{filename}/{name}'))
    if not artifacts and not issues:
        issues.append('O ZIP não contém arquivos XML.')
    return artifacts, issues
