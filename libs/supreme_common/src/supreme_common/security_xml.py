from io import BytesIO
from pathlib import PurePosixPath
import re
import zipfile
from defusedxml import ElementTree

MAX_XML_DEPTH = 50
MAX_XML_ELEMENTS = 10_000
MAX_XML_BYTES = 10 * 1024 * 1024

def parse_safe_xml(content: bytes):
    if len(content) > MAX_XML_BYTES:
        raise ValueError('XML excede 10 MB.')
    # Strip NULs as well, so UTF-16/32 declarations cannot bypass the lexical guard.
    if re.search(br'<!\s*(?:DOCTYPE|ENTITY)\b', content.replace(b'\x00', b''), re.I):
        raise ValueError('DTD e entidades não são permitidos.')
    try:
        root = ElementTree.fromstring(content, forbid_dtd=True, forbid_entities=True, forbid_external=True)
    except Exception as exc:
        raise ValueError('XML inválido ou inseguro.') from exc
    stack, count = [(root, 1)], 0
    while stack:
        element, depth = stack.pop()
        count += 1
        if depth > MAX_XML_DEPTH or count > MAX_XML_ELEMENTS:
            raise ValueError('XML excede os limites de profundidade ou elementos.')
        stack.extend((child, depth + 1) for child in element)
    return root

def xml_inputs(filename, content, *, max_files=5000, max_total=100 * 1024 * 1024):
    if not filename.lower().endswith('.zip'):
        if not filename.lower().endswith('.xml'):
            raise ValueError('Envie XML ou ZIP.')
        parse_safe_xml(content)
        return [(filename, content)]
    if len(content) > 55 * 1024 * 1024:
        raise ValueError('ZIP excede 55 MB.')
    result, total = [], 0
    try:
        with zipfile.ZipFile(BytesIO(content)) as archive:
            entries = archive.infolist()
            if len(entries) > 10000:
                raise ValueError('ZIP excede 10.000 entradas.')
            for entry in entries:
                path = PurePosixPath(entry.filename.replace('\\', '/'))
                if path.is_absolute() or '..' in path.parts or entry.flag_bits & 1:
                    raise ValueError('ZIP possui caminhos inseguros ou senha.')
                total += entry.file_size
                if total > max_total:
                    raise ValueError('ZIP excede 100 MB descompactados.')
                if entry.is_dir() or path.suffix.lower() != '.xml':
                    continue
                if len(result) >= max_files or entry.file_size > MAX_XML_BYTES:
                    raise ValueError('ZIP excede o limite de XMLs ou tamanho por XML.')
                with archive.open(entry) as stream:
                    raw = stream.read(MAX_XML_BYTES + 1)
                parse_safe_xml(raw)
                result.append((path.name, raw))
    except zipfile.BadZipFile as exc:
        raise ValueError('ZIP inválido.') from exc
    return result
