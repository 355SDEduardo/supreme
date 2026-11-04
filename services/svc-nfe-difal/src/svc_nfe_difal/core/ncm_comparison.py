from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from svc_nfe_difal.core.models import (
    ComparisonItem,
    ComparisonSummary,
    FiscalInfo,
    NfeData,
    NfeProduct,
)

ANALYZED_CFOP_PREFIXES = ("61", "63", "66", "67", "68", "69")
ESTADUAL_CFOP_PREFIXES = ("51", "53", "54", "56", "57", "58", "59")


def normalize_ncm(value: object) -> str:
    if value is None:
        return ""
    return "".join(char for char in str(value) if char.isascii() and char.isdigit())


def normalize_cfop(value: object) -> str:
    return "" if value is None else str(value).strip()


def should_analyze_cfop(
    value: object, prefixes: tuple[str, ...] | None = None
) -> bool:
    cfop = normalize_cfop(value)
    allowed = prefixes if prefixes is not None else ANALYZED_CFOP_PREFIXES
    return (
        len(cfop) == 4
        and cfop.isascii()
        and cfop.isdigit()
        and (not allowed or cfop.startswith(allowed))
    )


def load_fiscal_catalog(path: Path) -> dict[str, FiscalInfo]:
    if not path.exists():
        return {}
    return load_fiscal_catalog_bytes(path.read_bytes())


def load_fiscal_catalog_bytes(content: bytes) -> dict[str, FiscalInfo]:
    try:
        payload = json.loads(content.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("A base fiscal não contém um JSON UTF-8 válido.") from exc
    if not isinstance(payload, list):
        raise ValueError("A base fiscal deve conter uma lista de itens.")

    catalog: dict[str, FiscalInfo] = {}
    for index, record in enumerate(payload, start=1):
        if not isinstance(record, dict):
            raise ValueError(f"O item {index} da base fiscal não é um objeto JSON.")

        ncm = normalize_ncm(record.get("NCM"))
        if len(ncm) != 8:
            raise ValueError(f"O item {index} possui NCM inválido; informe oito dígitos.")

        info = FiscalInfo(
            status_st=_text(record.get("ST")) or "Não informado",
            posicao=_text(record.get("Posição")),
            subposicao=_text(record.get("Subposição")),
            item=_text(record.get("Subitem")),
            mva=_text(record.get("MVA")),
            cest=normalize_ncm(record.get("CEST")),
        )
        previous = catalog.get(ncm)
        if previous is not None and previous != info:
            raise ValueError(f"O NCM {ncm} possui dados fiscais divergentes na base.")
        catalog[ncm] = info
    return catalog


def compare_nfes(
    nfes: list[NfeData],
    catalog: dict[str, FiscalInfo],
    *,
    cfop_prefixes: tuple[str, ...] | None = None,
) -> tuple[list[ComparisonItem], ComparisonSummary]:
    grouped: dict[str, list[NfeProduct]] = {}
    cfops: dict[str, set[str]] = {}

    for nfe in nfes:
        for product in nfe.produtos:
            product.ncm_cadastrado = None
            product.status_st = ""
            product.mva = ""
            product.cest = ""

            ncm = normalize_ncm(product.ncm)
            cfop = normalize_cfop(product.cfop)
            if not ncm or not should_analyze_cfop(cfop, cfop_prefixes):
                continue
            grouped.setdefault(ncm, []).append(product)
            cfops.setdefault(ncm, set()).add(cfop)

    items: list[ComparisonItem] = []
    for ncm in sorted(grouped):
        info = catalog.get(ncm)
        is_registered = info is not None
        status = info.status_st if info else "NCM não encontrado na base"
        mva = info.mva if info else ""
        cest = info.cest if info else ""

        for product in grouped[ncm]:
            product.ncm_cadastrado = is_registered
            product.status_st = status
            product.mva = mva
            product.cest = cest

        items.append(
            ComparisonItem(
                ncm=ncm,
                posicao=info.posicao if info else "",
                subposicao=info.subposicao if info else "",
                item=info.item if info else "",
                cfops=tuple(sorted(cfops[ncm])),
                ncm_cadastrado=is_registered,
                st=status,
                mva=mva,
                cest=cest,
            )
        )

    registered = sum(item.ncm_cadastrado for item in items)
    return items, ComparisonSummary(
        total_ncms=len(items),
        registered_ncms=registered,
        unregistered_ncms=len(items) - registered,
    )


def catalog_to_json_compatible(catalog: dict[str, FiscalInfo]) -> list[dict[str, Any]]:
    return [
        {
            "NCM": ncm,
            "Posição": info.posicao,
            "Subposição": info.subposicao,
            "Subitem": info.item,
            "ST": info.status_st,
            "MVA": info.mva,
            "CEST": info.cest,
        }
        for ncm, info in sorted(catalog.items())
    ]


def _text(value: object) -> str:
    return "" if value is None else str(value).strip()
