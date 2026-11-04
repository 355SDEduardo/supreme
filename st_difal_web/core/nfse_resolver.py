"""Structural schema discovery; municipalities never override XML signatures."""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date
import xml.etree.ElementTree as ET

from core.nfse_models import DocumentKind, NfseFamily
from core.nfse_xml import child, find, local_name


@dataclass(frozen=True)
class SchemaMetadata:
    schema_id: str
    family: NfseFamily
    document_kind: DocumentKind
    version: str
    namespace_uri: str
    root_tag: str
    provider: str = ''
    ibge_code: str | None = None
    effective_from: date | None = None
    effective_to: date | None = None
    priority: int = 100
    ambiguous: bool = False


class SchemaRegistry:
    def __init__(self) -> None:
        self._schemas: list[SchemaMetadata] = []
        for tag, kind in (('NFSe', DocumentKind.NFSE), ('DPS', DocumentKind.DPS),
                          ('PEDREGEVT_EVT', DocumentKind.EVENT)):
            self.register(SchemaMetadata(f'NAT_{kind.value}_V101', NfseFamily.NATIONAL,
                kind, '1.01', 'http://www.sped.fazenda.gov.br/nfse', tag, priority=10))
        for version in ('1.00', '2.01', '2.02', '2.03', '2.04'):
            self.register(SchemaMetadata('ABRASF_V' + version.replace('.', ''),
                NfseFamily.ABRASF_1 if version == '1.00' else NfseFamily.ABRASF_2,
                DocumentKind.NFSE, version, '', 'CompNfse', priority=20))
        self.register(SchemaMetadata('PAULISTANA_NFSE', NfseFamily.PAULISTANA,
            DocumentKind.NFSE, '1.0', '', 'NFe', ibge_code='3550308', priority=40))

    def register(self, metadata: SchemaMetadata) -> None:
        self._schemas.append(metadata)
        self._schemas.sort(key=lambda item: item.priority)


class SchemaResolver:
    def __init__(self, registry: SchemaRegistry | None = None):
        self.registry = registry or SchemaRegistry()

    @staticmethod
    def _extract_qname(element: ET.Element) -> tuple[str, str]:
        return (element.tag[1:].split('}', 1)[0] if element.tag.startswith('{') else '',
                local_name(element))

    def resolve(self, root: ET.Element, *, competence_date: date | None = None) -> SchemaMetadata:
        uri, tag = self._extract_qname(root)
        version = root.get('versao') or root.get('versaoDados') or ''
        if not version:
            version = next((n.get('versao') for n in root.iter() if n.get('versao')), '')
        city_node = find(root, 'cLocEmi', 'CodigoMunicipio', 'cMun')
        city = city_node.text.strip() if city_node is not None and city_node.text else ''
        matches = [s for s in self.registry._schemas if s.root_tag == tag
            and (not s.namespace_uri or s.namespace_uri == uri)
            and (not version or s.version == version)
            and (not s.ibge_code or not city or s.ibge_code == city)
            and (not competence_date or
                 ((not s.effective_from or competence_date >= s.effective_from) and
                  (not s.effective_to or competence_date <= s.effective_to)))]
        # Explicit signature still required for documents sharing NF-e's root name.
        if matches and tag not in {'CompNfse', 'NFe'}:
            return replace(matches[0], ambiguous=len(matches) > 1)
        if tag == 'NFSe' and child(root, 'infNFSe') is not None:
            family, kind = NfseFamily.NATIONAL, DocumentKind.NFSE
            version = version or '1.01'
        elif tag == 'DPS' and child(root, 'infDPS') is not None:
            family, kind = NfseFamily.NATIONAL, DocumentKind.DPS
            version = version or '1.01'
        elif tag in {'PEDREGEVT_EVT', 'evento', 'infEvento', 'CancelarNfseEnvio',
                     'CancelarNfseResposta', 'NfseCancelamento', 'NfseSubstituicao'}:
            family, kind = NfseFamily.NATIONAL if 'sped' in uri else NfseFamily.ABRASF_2, DocumentKind.EVENT
        elif tag == 'NFe' and find(root, 'ChaveNFe', 'CPFCNPJPrestador') is not None:
            family, kind, version = NfseFamily.PAULISTANA, DocumentKind.NFSE, version or '1.0'
        elif tag in {'CompNfse', 'Nfse'} and find(root, 'InfNfse') is not None:
            family = NfseFamily.ABRASF_2 if version.startswith('2.') or find(root, 'DeclaracaoPrestacaoServico') is not None else NfseFamily.ABRASF_1
            kind = DocumentKind.NFSE
            version = version or ('2.04' if family == NfseFamily.ABRASF_2 else '1.00')
        elif tag in {'Envelope', 'ConsultarNfseResposta', 'ConsultarLoteRpsResposta',
                     'GerarNfseResposta', 'RetornoEnvioLoteRPS', 'PedidoEnvioLoteRPS'}:
            family, kind = NfseFamily.OUTROS, DocumentKind.RESPONSE
        else:
            family, kind = NfseFamily.OUTROS, DocumentKind.UNKNOWN
        provider = next((f for token, f in (('betha', NfseFamily.BETHA), ('dsf', NfseFamily.DSF),
                        ('issnet', NfseFamily.ISSNET), ('ginfes', NfseFamily.GINFES), ('ipm', NfseFamily.IPM))
                        if token in uri.lower()), None)
        if provider and family in {NfseFamily.ABRASF_1, NfseFamily.ABRASF_2, NfseFamily.OUTROS}:
            family = provider
        return SchemaMetadata(f'{family.value}_{kind.value}_{version}', family, kind,
                              version, uri, tag, provider=provider.value if provider else '')
