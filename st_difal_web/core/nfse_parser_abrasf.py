"""ABRASF 1.x/2.x parsing, including multi-service notes."""
from __future__ import annotations

from dataclasses import fields, replace
from decimal import Decimal
import xml.etree.ElementTree as ET

from core.nfse_models import (
    CanonicalNfse, DocumentKind, DocumentStatus, IssWithholdingType,
    NfseAmounts, NfseFamily, NfseFederalWithholding, NfseIdentity, NfseParty, NfseServiceItem,
)
from core.nfse_parser_national import extract_ibs_cbs
from core.nfse_xml import XmlReader, child, find, local_name, subitem


def federal_total(federal: NfseFederalWithholding) -> Decimal:
    social = (federal.csll + federal.pis + federal.cofins if federal.social_contributions_total is None
              else federal.social_contributions_total)
    return federal.irrf + federal.inss_cp + federal.other_withholdings + social


def legacy_party(reader: XmlReader, node: ET.Element | None, field: str) -> NfseParty | None:
    if node is None:
        return None
    return NfseParty(
        reader.identifier(node, ('Cnpj', 'Cpf', 'NIF'), field + '.tax_id'),
        reader.text(node, ('RazaoSocial', 'xNome', 'NomeFantasia'), field + '.name'),
        trade_name=reader.text(node, ('NomeFantasia',), field + '.trade_name'),
        municipal_tax_id=reader.text(node, ('InscricaoMunicipal', 'IM'), field + '.municipal_tax_id'),
        ibge_city_code=reader.text(node, ('CodigoMunicipio', 'cMun', 'Cidade'), field + '.ibge_city_code'),
        state_code=reader.text(node, ('Uf',), field + '.state_code'))


class AbrasfNfseParser:
    def __init__(self, family: NfseFamily = NfseFamily.ABRASF_2):
        self.family = family

    def parse(self, root: ET.Element, raw_sha256: str, filename: str) -> CanonicalNfse:
        reader = XmlReader(root, self.family.value + '_' + root.get('versao', ''))
        info = find(root, 'InfNfse')
        if info is None:
            raise ValueError('XML ABRASF sem InfNfse.')
        declaration = find(info, 'InfDeclaracaoPrestacaoServico')
        if declaration is None:
            declaration = info
        provider_node = find(info, 'PrestadorServico')
        if provider_node is None:
            provider_node = find(declaration, 'Prestador')
        provider = legacy_party(reader, provider_node, 'provider')
        if provider is None:
            raise ValueError('NFS-e sem identificação do prestador.')
        simple = reader.text(declaration, ('OptanteSimplesNacional',), 'provider.is_simple_national')
        provider = replace(provider, is_simple_national=True if simple == '1' else False if simple == '2' else None,
                           tax_regime=reader.text(declaration, ('RegimeEspecialTributacao',), 'provider.tax_regime'))
        customer = legacy_party(reader, find(declaration, 'Tomador', 'TomadorServico'), 'customer')
        intermediary = legacy_party(reader, find(declaration, 'Intermediario'), 'intermediary')
        issuer = legacy_party(reader, find(info, 'OrgaoGerador'), 'issuer')
        service_nodes = [n for n in declaration.iter() if local_name(n) == 'Servico']
        if not service_nodes:
            raise ValueError('NFS-e sem serviço declarado.')
        services = []
        federal_values = {name: Decimal('0.00') for name in ('irrf', 'inss_cp', 'csll', 'pis', 'cofins', 'other_withholdings')}
        gross = deductions = discount_incond = discount_cond = iss_declared = retained_declared = Decimal('0.00')
        retention_codes = set()
        declared_rates = []
        for index, service in enumerate(service_nodes, 1):
            values = child(service, 'Valores')
            if values is None:
                values = service
            prefix = f'services.{index}.'
            amount = reader.number(values, ('ValorServicos',), prefix + 'gross_amount')
            gross += amount
            deductions += reader.number(values, ('ValorDeducoes',), prefix + 'deductions')
            discount_incond += reader.number(values, ('DescontoIncondicionado',), prefix + 'unconditional_discount')
            discount_cond += reader.number(values, ('DescontoCondicionado',), prefix + 'conditional_discount')
            iss_declared += reader.number(values, ('ValorIss',), prefix + 'iss_amount')
            retained_declared += reader.number(values, ('ValorIssRetido',), prefix + 'iss_withheld_amount')
            retention_codes.add(reader.text(service, ('IssRetido',), prefix + 'retention'))
            rate = reader.number(values, ('Aliquota',), prefix + 'iss_rate_declared', optional=True, rate=True)
            if rate is not None:
                declared_rates.append(rate)
            for name, tag in (('irrf', 'ValorIr'), ('inss_cp', 'ValorInss'), ('csll', 'ValorCsll'),
                              ('pis', 'ValorPis'), ('cofins', 'ValorCofins'), ('other_withholdings', 'OutrasRetencoes')):
                federal_values[name] += reader.number(values, (tag,), prefix + 'federal_withholding.' + name)
            services.append(NfseServiceItem(index,
                lc116_subitem=subitem(reader.text(service, ('ItemListaServico',), prefix + 'lc116_subitem')),
                municipal_tax_code=reader.text(service, ('CodigoTributacaoMunicipio',), prefix + 'municipal_tax_code'),
                description=reader.text(service, ('Discriminacao',), prefix + 'description'),
                gross_amount=amount,
                execution_city_ibge=reader.text(service, ('MunicipioPrestacaoServico', 'CodigoMunicipio'), prefix + 'execution_city_ibge'),
                incidence_city_ibge=reader.text(service, ('MunicipioIncidencia',), prefix + 'incidence_city_ibge')))
        federal = NfseFederalWithholding(**federal_values)
        retention = (IssWithholdingType.RETIDO_TOMADOR if retention_codes == {'1'}
                     else IssWithholdingType.NAO_RETIDO if retention_codes == {'2'}
                     else IssWithholdingType.NAO_INFORMADO)
        assessed = child(info, 'ValoresNfse')
        if assessed is None:
            assessed = find(info, 'Valores')
        assessed_iss = reader.number(assessed, ('ValorIss',), 'amounts.iss_amount', optional=True)
        iss = iss_declared if assessed_iss is None else assessed_iss
        withheld = retained_declared
        if retention == IssWithholdingType.RETIDO_TOMADOR and not withheld:
            withheld = iss
        total_retained = federal_total(federal) + withheld
        net = reader.number(assessed, ('ValorLiquidoNfse',), 'amounts.net_amount_declared', optional=True)
        rate = reader.number(assessed, ('Aliquota',), 'amounts.iss_rate_applied', optional=True, rate=True)
        base = reader.number(assessed, ('BaseCalculo',), 'amounts.iss_base', optional=True)
        amounts = NfseAmounts(gross, discount_incond, discount_cond, deductions,
            gross - deductions - discount_incond if base is None else base,
            declared_rates[0] if len(set(declared_rates)) == 1 else None,
            rate, iss, withheld, total_retained,
            gross - discount_incond - discount_cond - total_retained if net is None else net)
        issued = reader.timestamp(info, ('DataEmissao',), 'identity.nfse_issued_at')
        competence = reader.day(declaration, ('Competencia',), 'identity.competence_date')
        number = reader.text(info, ('Numero',), 'identity.nfse_number')
        key = reader.text(info, ('ChaveAcesso',), 'identity.access_key')
        if not key:
            city = issuer.ibge_city_code if issuer else provider.ibge_city_code
            key = 'ABRASF_' + '_'.join((city, issued.strftime('%Y%m%d') if issued else '', provider.tax_id, number))
        identity = NfseIdentity(key, info.get('Id', ''), number,
            reader.text(info, ('Serie',), 'identity.series'),
            competence_date=competence or (issued.date().replace(day=1) if issued else None), nfse_issued_at=issued)
        ibs = extract_ibs_cbs(reader, find(info, 'IBSCBS'), root.get('versao', ''))
        self.provenance_records = reader.records
        return CanonicalNfse(raw_sha256, filename, self.family, DocumentKind.NFSE,
            DocumentStatus.AUTHORIZED, identity, issuer, provider, customer, intermediary,
            tuple(services), amounts, federal, retention, ibs, tuple(reader.records))
