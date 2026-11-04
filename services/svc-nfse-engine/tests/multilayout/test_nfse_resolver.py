import xml.etree.ElementTree as ET

import pytest

from svc_nfse_engine.multilayout.nfse_models import DocumentKind, NfseFamily
from svc_nfse_engine.multilayout.nfse_resolver import SchemaResolver, SchemaRegistry, SchemaMetadata
from .nfse_samples import national, abrasf, paulistana, event


@pytest.mark.parametrize(('content', 'family', 'kind'), [
    (national(), NfseFamily.NATIONAL, DocumentKind.NFSE),
    (b'<DPS><infDPS/></DPS>', NfseFamily.NATIONAL, DocumentKind.DPS),
    (event(), NfseFamily.NATIONAL, DocumentKind.EVENT),
    (abrasf(), NfseFamily.ABRASF_2, DocumentKind.NFSE),
    (abrasf(version='1.00'), NfseFamily.ABRASF_1, DocumentKind.NFSE),
    (paulistana(), NfseFamily.PAULISTANA, DocumentKind.NFSE),
    (b'<Municipal/>', NfseFamily.OUTROS, DocumentKind.UNKNOWN),
    (abrasf(namespace='http://www.ginfes.com.br'), NfseFamily.GINFES, DocumentKind.NFSE)])
def test_structural_discovery(content, family, kind):
    metadata = SchemaResolver().resolve(ET.fromstring(content))
    assert metadata.family == family
    assert metadata.document_kind == kind


@pytest.mark.parametrize('version', ['2.01', '2.02', '2.03', '2.04'])
def test_version_is_preserved(version):
    assert SchemaResolver().resolve(ET.fromstring(abrasf(version=version))).version == version


def test_registry_priority_and_ambiguity():
    registry = SchemaRegistry()
    registry.register(SchemaMetadata('CUSTOM', NfseFamily.NATIONAL, DocumentKind.NFSE,
        '1.01', 'http://www.sped.fazenda.gov.br/nfse', 'NFSe', priority=1))
    result = SchemaResolver(registry).resolve(ET.fromstring(national()))
    assert result.schema_id == 'CUSTOM'
    assert result.ambiguous
