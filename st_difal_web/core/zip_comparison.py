"""Conciliação de NF-es em RAM, por chave ou identidade secundária inequívoca."""

from __future__ import annotations

import re
from dataclasses import replace
from decimal import Decimal, InvalidOperation
from typing import BinaryIO

from core.models import (
    ParseIssue, ReconciliationDivergence, ReconciliationNote,
    ReconciliationSummary, ZipComparisonResult,
)
from core.nfe_parser import NfeParser
from core.zip_extractor import extract_xmls_from_zip

TOLERANCE = Decimal("0.01")
MAX_COMPARISON_XML_FILES = 5000
MAX_COMPARISON_ZIP_ENTRIES = 10000


def monetary_amount(value: str) -> Decimal:
    """Aceita valores XML e brasileiros; limita valores inválidos a zero."""
    text = value.strip()
    if not text:
        return Decimal(0)
    if "," in text:
        text = text.replace(".", "").replace(",", ".")
    try:
        amount = Decimal(text)
    except InvalidOperation:
        return Decimal(0)
    if not amount.is_finite() or amount.copy_abs() > Decimal("1000000000000000"):
        return Decimal(0)
    return amount


def _valid_key(key: str) -> bool:
    return re.fullmatch(r"[0-9]{44}", key) is not None


def _cnpj(value: str) -> str:
    normalized = re.sub(r"[. /-]", "", value.strip())
    return normalized if re.fullmatch(r"[0-9]{14}", normalized) else ""


def _identity(note: ReconciliationNote) -> tuple[str, str, str] | None:
    cnpj = _cnpj(note.cnpj_emitente)
    serie, numero = note.serie.strip(), note.numero.strip()
    if not re.fullmatch(r"[0-9]{14}", cnpj) or not re.fullmatch(r"[0-9]+", serie) or not re.fullmatch(r"[0-9]+", numero):
        return None
    return cnpj, serie.lstrip("0") or "0", numero.lstrip("0") or "0"


def _load(
    source: BinaryIO | bytes, name: str,
) -> tuple[dict[str, ReconciliationNote], list[ParseIssue], set[str]]:
    extracted = extract_xmls_from_zip(
        source, zip_filename=name,
        max_entries=MAX_COMPARISON_ZIP_ENTRIES,
        max_xml_files=MAX_COMPARISON_XML_FILES,
    )
    issues = list(extracted.issues)
    notes: dict[str, ReconciliationNote] = {}
    parser = NfeParser()
    company_candidates: set[str] | None = None
    unidentified_company: list[str] = []
    for filename, content in extracted.xml_files:
        try:
            data = parser.parse_bytes(content, filename)
            if not data.numero:
                raise ValueError("O XML não contém uma NF-e com número informado.")
            participants = {_cnpj(data.cnpj_emitente), _cnpj(data.cnpj_destinatario)} - {""}
            if not participants:
                unidentified_company.append(filename)
            company_candidates = (
                participants if company_candidates is None
                else company_candidates & participants
            )
            amounts = {}
            for field in ("valor_total", "valor_icms", "valor_icms_st"):
                raw = getattr(data, field)
                amount = monetary_amount(raw)
                amounts[field] = str(amount)
                # Zero declarado é válido; vazio ou conteúdo inválido merece aviso.
                if not raw or (amount == 0 and raw.strip().replace(".", "").replace(",", "").strip("0") != ""):
                    issues.append(ParseIssue(filename, f"{field} ausente ou inválido; considerado zero."))
            note = ReconciliationNote(
                data.chave, data.numero, data.serie, data.data_emissao,
                data.cnpj_emitente, data.nome_emitente, data.cnpj_destinatario,
                data.nome_destinatario, amounts["valor_total"],
                float(monetary_amount(amounts["valor_total"])),
                amounts["valor_icms"], amounts["valor_icms_st"], filename,
            )
            if not _valid_key(note.chave):
                identity = _identity(note)
                if identity is None:
                    raise ValueError("NF-e sem chave válida e sem CNPJ, série e número completos para conciliação.")
                note = replace(note, chave="CHAVE_INCOMPLETA_" + "_".join(identity))
                issues.append(ParseIssue(filename, "Chave ausente ou inválida; usada identidade CNPJ/série/número."))
            if note.chave in notes:
                issues.append(ParseIssue(filename, "NF-e duplicada; mantida a primeira ocorrência do ZIP. Verifique os valores das cópias."))
            else:
                notes[note.chave] = note
        except ValueError as exc:
            issues.append(ParseIssue(filename, str(exc)))
    if not notes:
        raise ValueError(f"O ZIP '{name}' não contém NF-e válida para conciliação (vazio, sem XML ou com XMLs rejeitados).")
    if unidentified_company:
        raise ValueError(
            f"Não foi possível validar a empresa do ZIP '{name}': a NF-e "
            f"'{unidentified_company[0]}' não possui CNPJ válido de emitente ou destinatário."
        )
    if not company_candidates:
        raise ValueError(
            f"As NF-es do ZIP '{name}' não pertencem à mesma empresa: "
            "nenhum CNPJ está presente em todas as notas como emitente ou destinatário."
        )
    return notes, issues, company_candidates


def _totals(notes: list[ReconciliationNote]) -> dict[str, int | float]:
    return {
        "quantidade": len(notes),
        **{field: float(sum((monetary_amount(getattr(note, field)) for note in notes), Decimal(0)))
           for field in ("valor_total", "valor_icms", "valor_icms_st")},
    }


def compare_nfe_zips(
    cliente_stream: BinaryIO | bytes, portal_stream: BinaryIO | bytes, *,
    nome_cliente: str = "cliente.zip", nome_portal: str = "portal.zip",
) -> ZipComparisonResult:
    cliente, issues_cliente, companies_cliente = _load(cliente_stream, nome_cliente)
    portal, issues_portal, companies_portal = _load(portal_stream, nome_portal)
    companies = companies_cliente & companies_portal
    if not companies:
        raise ValueError(
            "Os ZIPs do cliente e do portal não pertencem à mesma empresa: "
            "nenhum CNPJ está presente em todas as notas dos dois pacotes como emitente ou destinatário."
        )
    result = ZipComparisonResult(
        issues_cliente=issues_cliente, issues_portal=issues_portal,
        nome_arquivo_cliente=nome_cliente, nome_arquivo_portal=nome_portal,
        cnpjs_empresa=sorted(companies),
    )
    pairs = [(key, key) for key in sorted(cliente.keys() & portal.keys())]
    remaining_cliente = set(cliente) - set(portal)
    remaining_portal = set(portal) - set(cliente)
    # Indexar todas as notas evita um fallback falso quando já existe outra
    # chave válida com a mesma identidade secundária em qualquer pacote.
    identities_cliente: dict[tuple[str, str, str], list[str]] = {}
    identities_portal: dict[tuple[str, str, str], list[str]] = {}
    for notes, index in ((cliente, identities_cliente), (portal, identities_portal)):
        for key, note in notes.items():
            identity = _identity(note)
            if identity is not None:
                index.setdefault(identity, []).append(key)
    for identity in sorted(identities_cliente.keys() & identities_portal.keys()):
        ck, pk = identities_cliente[identity], identities_portal[identity]
        if len(ck) != 1 or len(pk) != 1:
            for keys, remaining, notes, issues in (
                (ck, remaining_cliente, cliente, issues_cliente),
                (pk, remaining_portal, portal, issues_portal),
            ):
                for key in keys:
                    if key in remaining and not _valid_key(key):
                        issues.append(ParseIssue(notes[key].filename, "Identidade secundária ambígua; nota não conciliada automaticamente."))
            continue
        ckey, pkey = ck[0], pk[0]
        if ckey in remaining_cliente and pkey in remaining_portal and not (_valid_key(ckey) and _valid_key(pkey)):
            pairs.append((ckey, pkey))
            remaining_cliente.remove(ckey)
            remaining_portal.remove(pkey)
    result.apenas_cliente = [cliente[key] for key in sorted(remaining_cliente)]
    result.apenas_portal = [portal[key] for key in sorted(remaining_portal)]
    for ck, pk in sorted(pairs):
        cn, pn = cliente[ck], portal[pk]
        result.em_ambos.append(cn)
        result.em_ambos_portal.append(pn)
        fields = tuple(field for field in ("valor_total", "valor_icms", "valor_icms_st")
                       if abs(monetary_amount(getattr(cn, field)) - monetary_amount(getattr(pn, field))) > TOLERANCE)
        if fields:
            result.divergencias.append(ReconciliationDivergence(
                cn.chave, cn.numero, cn.serie, cn.valor_total_float, pn.valor_total_float,
                float(abs(monetary_amount(cn.valor_total) - monetary_amount(pn.valor_total))),
                cn, pn, fields,
            ))
    groups = {
        "cliente": list(cliente.values()), "portal": list(portal.values()),
        "apenas_cliente": result.apenas_cliente, "apenas_portal": result.apenas_portal,
        "em_ambos": result.em_ambos, "em_ambos_portal": result.em_ambos_portal,
        "divergencias": [item.nota_cliente for item in result.divergencias],
        "divergencias_portal": [item.nota_portal for item in result.divergencias],
    }
    totals = {key: _totals(notes) for key, notes in groups.items()}
    result.resumo = ReconciliationSummary(
        len(cliente), len(portal), len(result.apenas_cliente), len(result.apenas_portal),
        len(result.em_ambos), len(result.divergencias),
        totals["cliente"]["valor_total"], totals["portal"]["valor_total"],
        totals["apenas_cliente"]["valor_total"], totals["apenas_portal"]["valor_total"],
        totals["em_ambos"]["valor_total"], totals,
    )
    return result
