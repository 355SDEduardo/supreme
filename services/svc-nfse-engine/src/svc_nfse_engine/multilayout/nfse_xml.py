"""Namespace-independent, scoped extraction with exact source paths."""
from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import xml.etree.ElementTree as ET

from svc_nfse_engine.multilayout.nfse_models import NfseProvenance


def local_name(element: ET.Element) -> str:
    return element.tag.rsplit('}', 1)[-1]


def find(element: ET.Element | None, *tags: str) -> ET.Element | None:
    if element is None:
        return None
    for tag in tags:
        for node in element.iter():
            if local_name(node).casefold() == tag.casefold():
                return node
    return None


def child(element: ET.Element | None, tag: str) -> ET.Element | None:
    if element is not None:
        return next((n for n in element if local_name(n) == tag), None)
    return None


def decimal_value(text: str) -> Decimal:
    normalized = text.strip()
    if ',' in normalized:
        normalized = normalized.replace('.', '').replace(',', '.')
    if len(normalized) > 80:
        raise ValueError('Valor decimal excede o limite de caracteres.')
    try:
        value = Decimal(normalized)
        if not value.is_finite() or len(value.as_tuple().digits) > 20 or abs(value.as_tuple().exponent) > 12 or abs(value) > Decimal('1e16'):
            raise ValueError('Valor decimal fora dos limites.')
        return value
    except InvalidOperation as exc:
        raise ValueError(f'Valor decimal inválido: {text[:80]!r}') from exc


def tax_id(text: str) -> str:
    return re.sub(r'[.\s/\-]', '', text).upper()


def subitem(text: str) -> str:
    digits = text.replace('.', '').strip().zfill(4)
    return f'{digits[:2]}.{digits[2:4]}' if text else ''


class XmlReader:
    def __init__(self, root: ET.Element, schema: str):
        self.schema = schema
        self.records: list[NfseProvenance] = []
        self.paths: dict[int, str] = {}
        self._index(root, '/' + root.tag)

    def _index(self, node: ET.Element, path: str) -> None:
        self.paths[id(node)] = path
        counts: dict[str, int] = {}
        for item in node:
            counts[item.tag] = counts.get(item.tag, 0) + 1
            self._index(item, f'{path}/{item.tag}[{counts[item.tag]}]')

    def record(self, node: ET.Element, field: str, raw: str, value: object, rule: str) -> None:
        if field:
            self.records.append(NfseProvenance(field, self.paths[id(node)], raw,
                                               str(value), self.schema, rule))

    def text(self, scope: ET.Element | None, tags: tuple[str, ...], field: str = '',
             default: str = '') -> str:
        node = find(scope, *tags)
        if node is None or node.text is None:
            return default
        raw = node.text
        value = raw.strip()
        self.record(node, field, raw, value, 'strip')
        return value

    def identifier(self, scope: ET.Element | None, tags: tuple[str, ...], field: str) -> str:
        node = find(scope, *tags)
        if node is None or not node.text:
            return ''
        value = tax_id(node.text)
        self.record(node, field, node.text, value, 'identifier_text')
        return value

    def number(self, scope: ET.Element | None, tags: tuple[str, ...], field: str,
               *, optional: bool = False, rate: bool = False) -> Decimal | None:
        node = find(scope, *tags)
        if node is None or not (node.text or '').strip():
            return None if optional else Decimal('0.00')
        value = decimal_value(node.text)
        rule = 'to_decimal'
        if rate and Decimal('0') < value <= Decimal('0.10'):
            value *= 100
            rule = 'fraction_to_percent'
        self.record(node, field, node.text, value, rule)
        return value

    def timestamp(self, scope: ET.Element | None, tags: tuple[str, ...], field: str) -> datetime | None:
        text = self.text(scope, tags, field)
        return datetime.fromisoformat(text) if text else None

    def day(self, scope: ET.Element | None, tags: tuple[str, ...], field: str) -> date | None:
        text = self.text(scope, tags, field)
        return date.fromisoformat(text[:10]) if text else None
