"""National NFSe/DPS adapter with scoped declared and assessed totals."""
from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
import xml.etree.ElementTree as ET

from svc_nfse_engine.multilayout.nfse_models import (
    CanonicalNfse, DocumentKind, DocumentStatus, IssWithholdingType, FindingSeverity, NfseFinding,
    NfseAmounts, NfseFamily, NfseFederalWithholding, NfseIbsCbs,
    NfseIdentity, NfseParty, NfseServiceItem,
)
from svc_nfse_engine.multilayout.nfse_xml import XmlReader, child, find, local_name, subitem


def national_party(reader: XmlReader, node: ET.Element | None, field: str) -> NfseParty | None:
    if node is None:
        return None
    option = reader.text(node, ('opSimpNac',), field + '.simple_option')
    return NfseParty(
        tax_id=reader.identifier(node, ('CNPJ', 'CPF', 'NIF'), field + '.tax_id'),
        name=reader.text(node, ('xNome',), field + '.name'),
        municipal_tax_id=reader.text(node, ('IM',), field + '.municipal_tax_id'),
        ibge_city_code=reader.text(node, ('cMun',), field + '.ibge_city_code'),
        city_name=reader.text(node, ('xMun',), field + '.city_name'),
        state_code=reader.text(node, ('UF',), field + '.state_code'),
        is_simple_national=True if option in {'2', '3'} else False if option == '1' else None,
        is_mei=option == '2' if option in {'1', '2', '3'} else None,
        tax_regime=reader.text(node, ('regEspTrib',), field + '.tax_regime'))


def extract_ibs_cbs(reader: XmlReader, node: ET.Element | None, version: str,
                    declared: ET.Element | None = None) -> NfseIbsCbs | None:
    if node is None:
        return None
    tags = {'tax_base': ('vBC',), 'ibs_state_rate': ('pIBSUF',), 'ibs_state_amount': ('vIBSUF',),
            'ibs_city_rate': ('pIBSMun',), 'ibs_city_amount': ('vIBSMun',),
            'cbs_rate': ('pCBS',), 'cbs_amount': ('vCBS',), 'total_ibs': ('vTotIBS', 'vIBSTot', 'vIBS'),
            'total_cbs': ('vTotCBS', 'vCBS'), 'total_nf': ('vTotNF',)}
    classification = declared if declared is not None else node
    return NfseIbsCbs(layout_version=version,
        cst=reader.text(classification, ('CST',), 'ibs_cbs.cst'),
        c_class_trib=reader.text(classification, ('cClassTrib',), 'ibs_cbs.c_class_trib'),
        ind_op=reader.text(classification, ('cIndOp', 'indOp'), 'ibs_cbs.ind_op'),
        ibs_state_effective_rate=reader.number(node, ('pAliqEfetUF',), 'ibs_cbs.ibs_state_effective_rate', optional=True),
        ibs_city_effective_rate=reader.number(node, ('pAliqEfetMun',), 'ibs_cbs.ibs_city_effective_rate', optional=True),
        cbs_effective_rate=reader.number(node, ('pAliqEfetCBS',), 'ibs_cbs.cbs_effective_rate', optional=True),
        has_complex_adjustments=find(node, 'gDif', 'gDevTrib', 'gCredPres', 'gTribRegular', 'gEstornoCred') is not None,
        **{name: reader.number(node, options, 'ibs_cbs.' + name) for name, options in tags.items()})


class NationalNfseParser:
    def parse(self, root: ET.Element, raw_sha256: str, filename: str) -> CanonicalNfse:
        kind = DocumentKind.DPS if local_name(root) == 'DPS' else DocumentKind.NFSE
        reader = XmlReader(root, 'NAT_' + kind.value + '_' + root.get('versao', '1.01'))
        nf = child(root, 'infNFSe')
        dps = find(root, 'infDPS')
        if dps is None or (kind == DocumentKind.NFSE and nf is None):
            raise ValueError('NFS-e nacional sem infNFSe/DPS/infDPS obrigatório.')
        provider = national_party(reader, child(dps, 'prest'), 'provider')
        if provider is None:
            raise ValueError('DPS sem prestador (prest).')
        issued = reader.timestamp(nf, ('dhProc',), 'identity.nfse_issued_at')
        declared_issued = reader.timestamp(dps, ('dhEmi',), 'identity.dps_issued_at')
        competence = reader.day(dps, ('dCompet',), 'identity.competence_date')
        if competence is None and declared_issued:
            competence = declared_issued.date().replace(day=1)
        identity_node = nf if nf is not None else dps
        xml_id = identity_node.get('Id', '')
        access_key = xml_id.removeprefix('NFS') if kind == DocumentKind.NFSE else ''
        reader.record(identity_node, 'identity.xml_id', xml_id, xml_id, 'attribute_Id')
        reader.record(identity_node, 'identity.access_key', xml_id, access_key, 'strip_NFS_prefix')
        declared_values = child(dps, 'valores')
        assessed_values = child(nf, 'valores')
        federal_node = find(declared_values, 'tribFed')
        federal = NfseFederalWithholding(**{name: reader.number(federal_node, (tag,), 'federal_withholding.' + name)
            for name, tag in (('irrf', 'vRetIRRF'), ('inss_cp', 'vRetCP'), ('csll', 'vRetCSLL'),
                              ('pis', 'vPis'), ('cofins', 'vCofins'), ('other_withholdings', 'vOutRet'))})
        social_code = reader.text(find(federal_node, 'piscofins'), ('tpRetPisCofins',),
                                  'federal_withholding.social_retention_type')
        # vPis/vCofins are own tax debits; NT007's vRetCSLL is an aggregate,
        # not a second retention to add to those own debits.
        raw_pis, raw_cofins = federal.pis, federal.cofins
        if social_code in {'0', '3', '4', '5', '6', '7', '8', '9'}:
            federal = replace(federal, social_contributions_total=federal.csll,
                              csll=Decimal('0.00'), pis=Decimal('0.00'), cofins=Decimal('0.00'))
        elif social_code != '1':
            federal = replace(federal, pis=Decimal('0.00'), cofins=Decimal('0.00'))
        federal = replace(federal, pis_own=raw_pis, cofins_own=raw_cofins, social_retention_type=social_code)
        normalized_fields = {'federal_withholding.pis': federal.pis, 'federal_withholding.cofins': federal.cofins,
                             'federal_withholding.csll': federal.csll}
        reader.records = [replace(record, normalized_value=str(normalized_fields[record.canonical_field]),
                                  transformation_rule='retention_domain_' + (social_code or 'unknown'))
                          if record.canonical_field in normalized_fields else record for record in reader.records]
        for field_name, tag in (('pis_own', 'vPis'), ('cofins_own', 'vCofins')):
            reader.number(federal_node, (tag,), 'federal_withholding.' + field_name)
        if federal.social_contributions_total is not None:
            reader.number(federal_node, ('vRetCSLL',), 'federal_withholding.social_contributions_total')
        retention_code = reader.text(find(declared_values, 'tribMun'), ('tpRetISSQN',), 'iss_withholding_type')
        try:
            retention = IssWithholdingType(retention_code)
        except ValueError:
            retention = IssWithholdingType.NAO_INFORMADO
        amounts = NfseAmounts(
            gross_service=reader.number(declared_values, ('vServ',), 'amounts.gross_service'),
            unconditional_discount=reader.number(declared_values, ('vDescIncond',), 'amounts.unconditional_discount'),
            conditional_discount=reader.number(declared_values, ('vDescCond',), 'amounts.conditional_discount'),
            deductions=reader.number(declared_values, ('vDR', 'vDeduc'), 'amounts.deductions'),
            iss_base=reader.number(assessed_values, ('vBC',), 'amounts.iss_base'),
            iss_rate_declared=reader.number(find(declared_values, 'tribMun'), ('pAliq',), 'amounts.iss_rate_declared', optional=True),
            iss_rate_applied=reader.number(assessed_values, ('pAliqAplic',), 'amounts.iss_rate_applied', optional=True),
            iss_amount=reader.number(assessed_values, ('vISSQN',), 'amounts.iss_amount'),
            total_withheld=reader.number(assessed_values, ('vTotalRet',), 'amounts.total_withheld'),
            net_amount_declared=reader.number(assessed_values, ('vLiq',), 'amounts.net_amount_declared'))
        if retention in {IssWithholdingType.RETIDO_TOMADOR, IssWithholdingType.RETIDO_INTERMEDIARIO}:
            amounts = replace(amounts, iss_withheld_amount=amounts.iss_amount)
        service = child(dps, 'serv')
        code = reader.text(service, ('cTribNac',), 'services.1.national_tax_code')
        services = (NfseServiceItem(
            national_tax_code=code, lc116_subitem=subitem(code[:4]),
            municipal_tax_code=reader.text(service, ('cTribMun',), 'services.1.municipal_tax_code'),
            nbs_code=reader.text(service, ('cNBS',), 'services.1.nbs_code'),
            description=reader.text(service, ('xDescServ',), 'services.1.description'),
            gross_amount=amounts.gross_service,
            execution_city_ibge=reader.text(service, ('cLocPrestacao',), 'services.1.execution_city_ibge'),
            incidence_city_ibge=reader.text(nf, ('cLocIncid',), 'services.1.incidence_city_ibge')),)
        assessed_ibs = child(nf, 'IBSCBS')
        declared_ibs = child(dps, 'IBSCBS')
        ibs = extract_ibs_cbs(reader, assessed_ibs if assessed_ibs is not None else declared_ibs,
                              root.get('versao', ''), declared_ibs)
        identity = NfseIdentity(access_key, xml_id,
            reader.text(nf, ('nNFSe',), 'identity.nfse_number'),
            reader.text(nf, ('serie',), 'identity.series'),
            reader.text(dps, ('nDPS',), 'identity.dps_number'),
            reader.text(dps, ('serie',), 'identity.dps_series'), competence, issued, declared_issued)
        customer = national_party(reader, child(dps, 'toma'), 'customer')
        intermediary = national_party(reader, child(dps, 'interm'), 'intermediary')
        issuer = national_party(reader, child(nf, 'emit'), 'issuer')
        self.provenance_records = reader.records
        extraction_findings = ()
        if not social_code and (raw_pis or raw_cofins):
            extraction_findings = (NfseFinding('FEDERAL_RETENTION_TYPE_MISSING', FindingSeverity.WARNING,
                'Tipo de retenção PIS/COFINS ausente', 'Débitos próprios de PIS/COFINS não foram tratados como retenção sem indicador.',
                'tpRetPisCofins', 'Ausente', legal_basis='Leiaute nacional; NT007'),)
        return CanonicalNfse(raw_sha256, filename, NfseFamily.NATIONAL, kind,
            DocumentStatus.UNKNOWN if kind == DocumentKind.DPS else DocumentStatus.AUTHORIZED,
            identity, issuer, provider, customer, intermediary, services, amounts, federal,
            retention, ibs, tuple(reader.records), extraction_findings)
