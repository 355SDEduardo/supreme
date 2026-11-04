"""Immutable status projections and order-independent event reconciliation."""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
import xml.etree.ElementTree as ET

from svc_nfse_engine.multilayout.nfse_models import CanonicalNfse, DocumentStatus, NfseEvent
from svc_nfse_engine.multilayout.nfse_xml import XmlReader, find, local_name


@dataclass(frozen=True)
class SubstitutionLink:
    original_key: str
    substitute_key: str
    event_datetime: datetime
    reason: str


def event_order(event: NfseEvent) -> tuple[datetime, int, str]:
    stamp = event.event_datetime
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp.astimezone(timezone.utc), event.sequence_number, event.event_id


class NfseEventManager:
    def __init__(self) -> None:
        self.events_by_target: dict[str, list[NfseEvent]] = {}
        self.orphan_events: list[NfseEvent] = []
        self.substitution_graph: dict[str, SubstitutionLink] = {}
        self._event_ids: set[tuple[str, str]] = set()

    def register_event(self, event: NfseEvent, known_keys: set[str]) -> None:
        identity = (event.event_id, event.target_access_key)
        if identity in self._event_ids:
            return
        self._event_ids.add(identity)
        self.events_by_target.setdefault(event.target_access_key, []).append(event)
        if event.target_access_key not in known_keys:
            self.orphan_events.append(event)
        events = sorted(self.events_by_target[event.target_access_key], key=event_order)
        substitutions = [e for e in events if e.confirmed and e.substituting_access_key]
        if substitutions:
            latest = substitutions[-1]
            self.substitution_graph[event.target_access_key] = SubstitutionLink(
                event.target_access_key, latest.substituting_access_key,
                latest.event_datetime, latest.reason)

    def parse_event_xml(self, root: ET.Element, raw_sha256: str, *, target_access_key: str = '') -> NfseEvent:
        reader = XmlReader(root, 'EVENT')
        node = find(root, 'infEvento', 'infPedReg', 'InfPedidoCancelamento')
        if node is None:
            node = root
        code = reader.text(root, ('tpEvento',), '')
        if not code:
            code = next((local_name(n) for n in root.iter()
                         if local_name(n).startswith(('e101', 'e105'))), '')
        event_type = {'e101101': 'CANCELAMENTO', 'e101103': 'SUBSTITUICAO',
                      '101101': 'CANCELAMENTO', '101103': 'SUBSTITUICAO'}.get(code)
        if not event_type:
            event_type = 'SUBSTITUICAO' if 'Substitu' in local_name(root) else 'CANCELAMENTO' if 'Cancel' in local_name(root) else code or 'MANIFESTACAO'
        key = reader.text(root, ('chNFSe', 'ChaveAcesso'), '').removeprefix('NFS') or target_access_key
        number = reader.text(root, ('Numero', 'NumeroNfse'), '')
        if not key and not number:
            raise ValueError('Evento sem chave ou identificação da NFS-e alvo.')
        stamp = reader.timestamp(root, ('dhRegEvento', 'dhEvento', 'dhPedReg', 'DataHora'), '')
        if stamp is None:
            raise ValueError('Evento sem data/hora de registro.')
        sequence = reader.text(root, ('nSeqEvento', 'nPedRegEvento'), '', '1')
        # A cancellation request alone is not proof of acceptance by the municipality.
        confirmed = local_name(root) != 'CancelarNfseEnvio'
        return NfseEvent(node.get('Id', '') or raw_sha256, key, event_type, int(sequence), stamp,
            reader.text(root, ('xJust', 'Motivo', 'CodigoCancelamento'), ''),
            reader.identifier(find(root, 'autor'), ('CNPJ', 'CPF'), ''),
            reader.text(root, ('chSubst', 'ChaveNfseSubstituta'), '').removeprefix('NFS'), raw_sha256,
            number, reader.text(root, ('CodigoMunicipio',), ''),
            reader.identifier(root, ('Cnpj', 'Cpf'), ''), confirmed)

    def project_status(self, document: CanonicalNfse) -> CanonicalNfse:
        status = document.status
        for event in sorted(self.events_by_target.get(document.identity.access_key, []), key=event_order):
            if not event.confirmed:
                continue
            if 'SUBST' in event.event_type.upper():
                status = DocumentStatus.SUBSTITUTED
            elif 'CANCEL' in event.event_type.upper():
                status = DocumentStatus.CANCELLED
        return replace(document, status=status)

    def reconcile_orphans(self, newly_ingested_key: str) -> list[NfseEvent]:
        found = [e for e in self.orphan_events if e.target_access_key == newly_ingested_key]
        self.orphan_events = [e for e in self.orphan_events if e not in found]
        return found

    def get_effective_document_chain(self, root_key: str) -> list[str]:
        chain = []
        current = root_key
        while current not in chain:
            chain.append(current)
            link = self.substitution_graph.get(current)
            if link is None:
                break
            current = link.substitute_key
        return chain
