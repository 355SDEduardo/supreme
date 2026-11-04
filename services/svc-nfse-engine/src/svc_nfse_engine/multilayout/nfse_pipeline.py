"""The single batch pipeline used by Flask and the command line."""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
import xml.etree.ElementTree as ET

from svc_nfse_engine.multilayout.nfse_events import NfseEventManager
from svc_nfse_engine.multilayout.nfse_models import DocumentKind, DocumentStatus, FindingSeverity, NfseFamily, NfseFinding, NfseProcessingState
from svc_nfse_engine.multilayout.nfse_parser_abrasf import AbrasfNfseParser, federal_total
from svc_nfse_engine.multilayout.nfse_parser_municipal import HeuristicFallbackParser, MunicipalLegacyParser, PaulistanaNfseParser
from svc_nfse_engine.multilayout.nfse_parser_national import NationalNfseParser
from svc_nfse_engine.multilayout.nfse_resolver import SchemaResolver
from svc_nfse_engine.multilayout.nfse_rules_engine import NfseRulesEngine, effective_iss_withheld
from svc_nfse_engine.multilayout.nfse_security import (
    DEFAULT_MAX_XML_BYTES, MAX_BATCH_XML_FILES, MAX_ZIP_BYTES, MAX_ZIP_TOTAL_BYTES,
    SafeArtifact, compute_sha256, ingest_nfse_zip, safe_parse_xml,
)
from svc_nfse_engine.multilayout.nfse_xml import find, local_name


def document_roots(root: ET.Element) -> list[ET.Element]:
    """Unwrap responses without also ingesting DPS/note children a second time."""
    roots = []

    def visit(node: ET.Element) -> None:
        tag = local_name(node)
        if tag in {'CompNfse', 'NFSe', 'DPS', 'Nfse', 'PEDREGEVT_EVT', 'evento',
                   'CancelarNfseEnvio', 'CancelarNfseResposta', 'NfseCancelamento', 'NfseSubstituicao'} or (
                tag == 'NFe' and find(node, 'ChaveNFe') is not None):
            roots.append(node)
            return
        for item in node:
            visit(item)

    visit(root)
    return roots or [root]


def process_nfse_batch(inputs: Iterable[tuple[str, bytes]], *,
                       max_total_bytes: int = MAX_ZIP_TOTAL_BYTES,
                       max_xml_files: int = MAX_BATCH_XML_FILES) -> NfseProcessingState:
    state = NfseProcessingState()
    resolver = SchemaResolver()
    events = NfseEventManager()
    rules = NfseRulesEngine()
    consumed_bytes = 0
    seen_hashes: set[str] = set()
    documents_by_key = {}
    event_list = []

    def issue(filename: str, message: str, digest: str = '') -> None:
        state.issues.append({'filename': filename, 'message': message, 'sha256': digest})

    for filename, content in inputs:
        suffix = Path(filename).suffix.casefold()
        try:
            if suffix == '.zip':
                artifacts, zip_issues = ingest_nfse_zip(content, filename,
                    max_total_bytes=max_total_bytes - consumed_bytes,
                    max_xml_files=max(1, max_xml_files - state.total_processed))
                for message in zip_issues:
                    issue(filename, message)
            elif suffix == '.xml':
                try:
                    artifacts = [safe_parse_xml(content, filename)]
                except ValueError as exc:
                    artifacts = [SafeArtifact(content, compute_sha256(content), len(content), '',
                                              False, None, str(exc), filename)]
            else:
                issue(filename, 'Extensão diferente de .xml ou .zip.')
                continue
        except (OSError, ValueError) as exc:
            issue(filename, str(exc))
            continue
        for artifact in artifacts:
            state.total_processed += 1
            consumed_bytes += artifact.size_bytes
            if state.total_processed > max_xml_files or consumed_bytes > max_total_bytes:
                raise ValueError('Lote NFS-e excede o limite de XMLs ou de 100 MB descompactados.')
            state.original_artifacts[artifact.sha256] = artifact.raw_bytes
            if not artifact.is_well_formed:
                issue(artifact.filename, artifact.error_message or 'XML malformado.', artifact.sha256)
                continue
            if artifact.sha256 in seen_hashes:
                state.logs.append(f'{artifact.filename}: artefato duplicado ignorado ({artifact.sha256}).')
                continue
            seen_hashes.add(artifact.sha256)
            for root in document_roots(artifact.root_element):
                try:
                    metadata = resolver.resolve(root)
                    if metadata.document_kind == DocumentKind.EVENT:
                        event_list.append(events.parse_event_xml(root, artifact.sha256))
                        continue
                    if metadata.document_kind == DocumentKind.RESPONSE:
                        issue(artifact.filename, 'Envelope sem NFS-e/DPS/evento suportado.', artifact.sha256)
                        continue
                    if metadata.family == NfseFamily.NATIONAL:
                        parser = NationalNfseParser()
                    elif metadata.family in {NfseFamily.ABRASF_1, NfseFamily.ABRASF_2}:
                        parser = AbrasfNfseParser(metadata.family)
                    elif metadata.family == NfseFamily.PAULISTANA:
                        parser = PaulistanaNfseParser()
                    elif metadata.family == NfseFamily.OUTROS:
                        parser = HeuristicFallbackParser()
                    else:
                        parser = MunicipalLegacyParser(metadata.family)
                    doc = parser.parse(root, artifact.sha256, artifact.filename)
                    if metadata.ambiguous:
                        doc = replace(doc, findings=doc.findings + (NfseFinding('SCHEMA_AMBIGUOUS',
                            FindingSeverity.WARNING, 'Schema ambíguo', 'Desempate por prioridade do catálogo.',
                            'Schema único', metadata.schema_id),))
                    key = doc.identity.access_key or doc.identity.xml_id or artifact.sha256
                    if key in documents_by_key:
                        previous = documents_by_key[key]
                        if previous.to_dict() != doc.to_dict():
                            issue(artifact.filename, f'Documentos diferentes com a mesma chave: {key}. Primeiro preservado.', artifact.sha256)
                        continue
                    documents_by_key[key] = doc
                    state.documents.append(doc)
                    # Record confirmed cancellation/substitution contained in ABRASF CompNfse.
                    embedded = find(root, 'NfseCancelamento', 'NfseSubstituicao')
                    if embedded is not None and find(embedded, 'Confirmacao') is not None:
                        evt = events.parse_event_xml(embedded, artifact.sha256, target_access_key=doc.identity.access_key)
                        event_list.append(replace(evt, target_access_key=doc.identity.access_key))
                except (ValueError, ArithmeticError) as exc:
                    issue(artifact.filename, str(exc), artifact.sha256)
    keys = {d.identity.access_key for d in state.documents if d.identity.access_key}
    for event in event_list:
        if not event.target_access_key and event.target_number:
            candidates = [d for d in state.documents if d.identity.nfse_number == event.target_number
                and (not event.target_provider_tax_id or d.provider.tax_id == event.target_provider_tax_id)
                and (not event.target_city_ibge or event.target_city_ibge in {
                    d.provider.ibge_city_code, d.issuer.ibge_city_code if d.issuer else ''})]
            if len(candidates) == 1:
                event = replace(event, target_access_key=candidates[0].identity.access_key)
        events.register_event(event, keys)
    for key in keys:
        events.reconcile_orphans(key)
    state.events = [e for items in events.events_by_target.values() for e in items]
    state.orphan_events = events.orphan_events
    state.documents = [rules.enrich_document(events.project_status(d)) for d in state.documents]
    state.total_valid = len(state.documents)
    state.total_with_findings = sum(any(f.severity != FindingSeverity.INFO for f in d.findings) for d in state.documents)
    active = [d for d in state.documents if d.kind == DocumentKind.NFSE and d.status == DocumentStatus.AUTHORIZED]
    state.total_gross_amount = sum((d.amounts.gross_service for d in active), Decimal('0.00'))
    state.total_iss_amount = sum((d.amounts.iss_amount for d in active), Decimal('0.00'))
    state.total_iss_withheld = sum((effective_iss_withheld(d) for d in active), Decimal('0.00'))
    state.total_federal_withheld = sum((federal_total(d.federal_withholding) for d in active), Decimal('0.00'))
    state.total_withheld_amount = state.total_iss_withheld + state.total_federal_withheld
    state.total_net_amount = sum((d.amounts.net_amount_calculated for d in active), Decimal('0.00'))
    state.logs.append(f'{state.total_processed} XML(s); {len(state.documents)} documento(s); '
                      f'{len(state.events)} evento(s); {len(state.issues)} ocorrência(s) de leitura.')
    return state


def path_inputs(paths: Iterable[Path]) -> Iterable[tuple[str, bytes]]:
    for path in paths:
        limit = MAX_ZIP_BYTES if path.suffix.casefold() == '.zip' else DEFAULT_MAX_XML_BYTES
        with path.open('rb') as stream:
            content = stream.read(limit + 1)
        if len(content) > limit:
            raise ValueError(f'{path.name}: arquivo excede limite de {limit} bytes.')
        yield path.name, content
