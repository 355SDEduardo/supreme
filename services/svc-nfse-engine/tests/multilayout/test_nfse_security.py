import hashlib

import pytest

from svc_nfse_engine.multilayout.nfse_security import compute_sha256, detect_encoding_and_strip_bom, ingest_nfse_zip, safe_parse_xml
from .nfse_samples import national, zipped


def test_exact_original_bytes_hash_and_bom():
    content = b'\xef\xbb\xbf' + national()
    artifact = safe_parse_xml(content, 'nota.xml')
    assert artifact.is_well_formed
    assert artifact.raw_bytes == content
    assert artifact.sha256 == hashlib.sha256(content).hexdigest() == compute_sha256(content)
    assert detect_encoding_and_strip_bom(content) == (national(), 'utf-8')


@pytest.mark.parametrize('encoding', ['utf-8', 'utf-16', 'utf-16-le', 'utf-16-be', 'utf-32', 'utf-32-le', 'utf-32-be'])
def test_xxe_and_entity_expansion_blocked_in_multibyte_encodings(encoding):
    content = '<!DOCTYPE x [<!ENTITY xxe SYSTEM "file:///secrets">]><x>&xxe;</x>'.encode(encoding)
    with pytest.raises(ValueError, match='DTD/ENTITY'):
        safe_parse_xml(content)


@pytest.mark.parametrize('encoding', ['utf-8', 'utf-16', 'utf-16-le', 'utf-16-be', 'utf-32', 'latin-1'])
def test_encoding_detection_and_fallback(encoding):
    content = ('<?xml version="1.0" encoding="' + encoding + '"?><x>ação</x>').encode(encoding)
    artifact = safe_parse_xml(content)
    assert artifact.is_well_formed, artifact.error_message
    assert artifact.root_element.text == 'ação'


def test_wrong_declared_encoding_falls_back_without_repair():
    content = '<?xml version="1.0" encoding="UTF-8"?><x>ação</x>'.encode('latin-1')
    artifact = safe_parse_xml(content)
    assert artifact.is_well_formed
    assert artifact.detected_encoding == 'latin-1'
    assert artifact.raw_bytes == content


@pytest.mark.parametrize('encoding', ['utf-16-le', 'utf-16-be', 'utf-32-le', 'utf-32-be'])
def test_multibyte_without_declaration_or_bom(encoding):
    artifact = safe_parse_xml('<x>ação</x>'.encode(encoding))
    assert artifact.is_well_formed, artifact.error_message
    assert artifact.root_element.text == 'ação'


def test_nonstandard_encoding_cannot_hide_dtd_from_raw_scan():
    content = b'<?xml version="1.0" encoding="utf-7"?>+ADwAIQ-DOCTYPE x [ +ADwAIQ-ENTITY a "secret"> ]><x>&a;</x>'
    artifact = safe_parse_xml(content)
    assert not artifact.is_well_formed
    assert 'DTD/ENTITY' in artifact.error_message


@pytest.mark.parametrize('content', [b'<x>A & B</x>', b'<x>', b'<x>\x01</x>', b'<x>\x00</x>'])
def test_malformed_xml_is_quarantined_without_silent_repair(content):
    artifact = safe_parse_xml(content)
    assert not artifact.is_well_formed
    assert artifact.raw_bytes == content
    assert artifact.sha256 == compute_sha256(content)


@pytest.mark.parametrize('content', [b'<a>' * 51 + b'</a>' * 51, b'<a>' + b'<b/>' * 10000 + b'</a>'], ids=['depth', 'elements'])
def test_tree_limits(content):
    artifact = safe_parse_xml(content)
    assert not artifact.is_well_formed
    assert 'limite' in artifact.error_message


def test_empty_oversized_and_bad_zip():
    with pytest.raises(ValueError, match='vazio'):
        safe_parse_xml(b'')
    with pytest.raises(ValueError, match='tamanho'):
        safe_parse_xml(b'<x/>', max_bytes=3)
    with pytest.raises(ValueError):
        ingest_nfse_zip(b'bad')
    with pytest.raises(ValueError, match='descompactado'):
        ingest_nfse_zip(zipped([('nota.xml', national())]), max_total_bytes=10)


def test_zip_rejections_do_not_drop_valid_artifacts():
    artifacts, issues = ingest_nfse_zip(zipped([('../nota.xml', national()), ('bad.xml', b'<x>'),
        ('xxe.xml', b'<!DOCTYPE x><x/>'), ('extra.txt', b'ignored')]))
    assert len(artifacts) == 3
    assert artifacts[0].is_well_formed
    assert not artifacts[1].is_well_formed and not artifacts[2].is_well_formed
    assert any('extra.txt' in message for message in issues)
