"""Paulistana and explicitly flagged municipal fallback adapters."""
from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
import xml.etree.ElementTree as ET

from core.nfse_models import (
    CanonicalNfse, DocumentKind, DocumentStatus, FindingSeverity, IssWithholdingType,
    NfseAmounts, NfseFamily, NfseFederalWithholding, NfseFinding, NfseIdentity, NfseParty, NfseServiceItem,
)
from core.nfse_parser_abrasf import AbrasfNfseParser, federal_total, legacy_party
from core.nfse_xml import XmlReader, find, subitem


class PaulistanaNfseParser:
    def parse(self, root: ET.Element, raw_sha256: str, filename: str) -> CanonicalNfse:
        return _parse_flat(root, raw_sha256, filename, paulistana=True)


class HeuristicFallbackParser:
    def parse(self, root: ET.Element, raw_sha256: str, filename: str) -> CanonicalNfse:
        if find(root, 'infNFe') is not None or find(root, 'ValorServicos', 'vServ', 'ValorTotal', 'vNFSe') is None:
            raise ValueError('XML não reconhecido como documento de serviços NFS-e.')
        document = _parse_flat(root, raw_sha256, filename, paulistana=False)
        finding = NfseFinding('SCHEMA_UNKNOWN_HEURISTIC_PARSED', FindingSeverity.WARNING,
            'Schema municipal não catalogado', 'Extração heurística: conferir os campos com o XML original.',
            'Schema oficial registrado', root.tag, legal_basis='Auditoria documental')
        return replace(document, findings=(finding,))


class MunicipalLegacyParser:
    def __init__(self, family: NfseFamily = NfseFamily.OUTROS):
        self.family = family

    def parse(self, root: ET.Element, raw_sha256: str, filename: str) -> CanonicalNfse:
        if find(root, 'InfNfse') is not None:
            return AbrasfNfseParser(self.family).parse(root, raw_sha256, filename)
        return replace(HeuristicFallbackParser().parse(root, raw_sha256, filename), family=self.family)


def _parse_flat(root: ET.Element, digest: str, filename: str, *, paulistana: bool) -> CanonicalNfse:
    family = NfseFamily.PAULISTANA if paulistana else NfseFamily.OUTROS
    reader = XmlReader(root, family.value)
    if paulistana:
        option = reader.text(root, ('OpcaoSimples',), 'provider.simple_option')
        provider = NfseParty(
            reader.identifier(find(root, 'CPFCNPJPrestador'), ('CNPJ', 'CPF'), 'provider.tax_id'),
            reader.text(root, ('RazaoSocialPrestador',), 'provider.name'),
            municipal_tax_id=reader.text(find(root, 'ChaveNFe'), ('InscricaoPrestador',), 'provider.municipal_tax_id'),
            ibge_city_code=reader.text(find(root, 'EnderecoPrestador'), ('Cidade',), 'provider.ibge_city_code', '3550308'),
            is_simple_national=True if option == '1' else False if option == '0' else None)
        customer = NfseParty(
            reader.identifier(find(root, 'CPFCNPJTomador'), ('CNPJ', 'CPF'), 'customer.tax_id'),
            reader.text(root, ('RazaoSocialTomador',), 'customer.name'))
    else:
        provider = legacy_party(reader, find(root, 'Prestador', 'prest', 'PrestadorServico'), 'provider') or NfseParty('', '')
        customer = legacy_party(reader, find(root, 'Tomador', 'toma', 'TomadorServico'), 'customer')
    issued = reader.timestamp(root, ('DataEmissao', 'dhProc', 'dhEmi', 'dtEmissao'), 'identity.nfse_issued_at')
    number = reader.text(root, ('NumeroNFe', 'nNFSe', 'NumeroNota', 'Numero'), 'identity.nfse_number')
    verification = reader.text(root, ('CodigoVerificacao',), 'identity.verification')
    key = ('3550308' + provider.municipal_tax_id + number + verification) if paulistana else reader.text(root, ('ChaveAcesso', 'chNFSe'), 'identity.access_key')
    key = key or f'SYNTH_{provider.tax_id}_{number}_{digest}'
    retention_code = reader.text(root, ('ISSRetido', 'tpRetISSQN'), 'iss_withholding_type').casefold()
    retention = IssWithholdingType.RETIDO_TOMADOR if retention_code in {'true', 's', 'sim', '1'} else IssWithholdingType.NAO_RETIDO if retention_code in {'false', 'n', 'nao', 'não', '2'} else IssWithholdingType.NAO_INFORMADO
    if not paulistana and find(root, 'ISSRetido') is None and find(root, 'tpRetISSQN') is not None:
        try:
            retention = IssWithholdingType(retention_code)
        except ValueError:
            retention = IssWithholdingType.NAO_INFORMADO
    federal = NfseFederalWithholding(**{name: reader.number(root, tags, 'federal_withholding.' + name)
        for name, tags in (('irrf', ('ValorIR', 'vRetIRRF')), ('inss_cp', ('ValorINSS', 'vRetCP')),
            ('csll', ('ValorCSLL', 'vRetCSLL')), ('pis', ('ValorPIS', 'vPis')),
            ('cofins', ('ValorCOFINS', 'vCofins')), ('other_withholdings', ('OutrasRetencoes',)))})
    gross = reader.number(root, ('ValorServicos', 'vServ', 'ValorTotal', 'vNFSe'), 'amounts.gross_service')
    deductions = reader.number(root, ('ValorDeducoes',), 'amounts.deductions')
    uncond = reader.number(root, ('DescontoIncondicionado', 'vDescIncond'), 'amounts.unconditional_discount')
    cond = reader.number(root, ('DescontoCondicionado', 'vDescCond'), 'amounts.conditional_discount')
    iss = reader.number(root, ('ValorISS', 'vISSQN'), 'amounts.iss_amount')
    withheld = reader.number(root, ('ValorISSRetido',), 'amounts.iss_withheld_amount')
    if retention in {IssWithholdingType.RETIDO_TOMADOR, IssWithholdingType.RETIDO_INTERMEDIARIO} and not withheld:
        withheld = iss
    total_retained = federal_total(federal) + withheld
    net = reader.number(root, ('ValorLiquido', 'ValorLiquidoNfse', 'vLiq'), 'amounts.net_amount_declared', optional=True)
    rate = reader.number(root, ('AliquotaServicos', 'Aliquota', 'pAliqAplic'), 'amounts.iss_rate_applied', optional=True, rate=True)
    base = reader.number(root, ('BaseCalculo', 'vBC'), 'amounts.iss_base', optional=True)
    amounts = NfseAmounts(gross, uncond, cond, deductions, gross - deductions - uncond if base is None else base,
                          rate, rate, iss, withheld, total_retained,
                          gross - uncond - cond - total_retained if net is None else net)
    services = (NfseServiceItem(
        lc116_subitem=subitem(reader.text(root, ('ItemListaServico',), 'services.1.lc116_subitem')),
        municipal_tax_code=reader.text(root, ('CodigoServico', 'CodigoTributacaoMunicipio'), 'services.1.municipal_tax_code'),
        description=reader.text(root, ('Discriminacao', 'xDescServ'), 'services.1.description'), gross_amount=gross,
        execution_city_ibge=reader.text(root, ('MunicipioPrestacaoServico',), 'services.1.execution_city_ibge'),
        incidence_city_ibge=reader.text(root, ('MunicipioIncidencia',), 'services.1.incidence_city_ibge')),)
    identity = NfseIdentity(key, root.get('Id', ''), number, reader.text(root, ('SerieRPS', 'Serie'), 'identity.series'),
        competence_date=reader.day(root, ('Competencia', 'dCompet'), 'identity.competence_date') or (issued.date().replace(day=1) if issued else None), nfse_issued_at=issued)
    return CanonicalNfse(digest, filename, family, DocumentKind.NFSE, DocumentStatus.AUTHORIZED,
                         identity, None, provider, customer, None, services, amounts, federal, retention,
                         None, tuple(reader.records))
