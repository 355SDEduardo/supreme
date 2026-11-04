from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from svc_nfe_difal.core.ncm_comparison import load_fiscal_catalog_bytes, normalize_ncm


@dataclass(frozen=True)
class FiscalRegistration:
    ncm: str = ""
    position: str = ""
    subposition: str = ""
    subitem: str = ""
    state: str = ""
    internal_rate: str = ""
    reduced_base: str = ""
    deferral: str = ""
    fcp: str = ""
    exemption: str = ""
    non_incidence: str = ""
    st: str = ""
    mva: str = ""
    cest: str = ""
    suspension: str = ""

    def to_json_dict(self) -> dict[str, str]:
        return {
            "NCM": self.ncm,
            "Posição": self.position,
            "Subposição": self.subposition,
            "Subitem": self.subitem,
            "Estado": self.state,
            "Alíquota Interna": self.internal_rate,
            "Base Reduzida": self.reduced_base,
            "Diferimento": self.deferral,
            "FCP": self.fcp,
            "Isenção": self.exemption,
            "Não Incidência": self.non_incidence,
            "ST": self.st,
            "MVA": self.mva,
            "CEST": self.cest,
            "Suspensão": self.suspension,
        }


class FiscalRegistrationService:
    REQUIRED_FIELDS = (
        "NCM",
        "Posição",
        "Subposição",
        "Subitem",
        "Estado",
        "Alíquota Interna",
        "Base Reduzida",
        "Diferimento",
        "FCP",
        "Isenção",
        "Não Incidência",
        "ST",
        "Suspensão",
    )
    OPTIONAL_FIELDS = ("MVA", "CEST")
    _lock = threading.RLock()

    def ensure_file(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            self._atomic_write(path, b"[]\n")

    def add(self, path: Path, item: FiscalRegistration) -> int:
        normalized = self._normalize_registration(item)
        with self._lock:
            self.ensure_file(path)
            records = self._read_records(path.read_bytes())
            existing_ncms = {normalize_ncm(record["NCM"]) for record in records}
            if normalized.ncm in existing_ncms:
                raise ValueError(f"O NCM {normalized.ncm} já está cadastrado na base fiscal.")

            records.append(normalized.to_json_dict())
            payload = (
                json.dumps(records, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
            )
            self._read_records(payload)
            self._atomic_write(path, payload)
            return len(records)

    def replace(self, path: Path, content: bytes) -> int:
        with self._lock:
            records = self._read_records(content)
            payload = (
                json.dumps(records, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
            )
            self._atomic_write(path, payload)
            return len(records)

    def _read_records(self, content: bytes) -> list[dict[str, Any]]:
        try:
            payload = json.loads(content.decode("utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("A base fiscal não contém um JSON UTF-8 válido.") from exc
        if not isinstance(payload, list):
            raise ValueError("A base fiscal deve conter uma lista de itens.")

        seen: set[str] = set()
        for index, record in enumerate(payload, start=1):
            if not isinstance(record, dict):
                raise ValueError(f"O item {index} da base fiscal não é um objeto JSON.")
            for field_name in self.REQUIRED_FIELDS:
                if field_name not in record or not isinstance(record[field_name], str):
                    raise ValueError(
                        f"O item {index} não possui o campo de texto obrigatório '{field_name}'."
                    )
            for field_name in self.OPTIONAL_FIELDS:
                if field_name in record and not isinstance(record[field_name], str):
                    raise ValueError(
                        f"O campo '{field_name}' do item {index} deve ser um texto."
                    )
                record.setdefault(field_name, "")

            ncm = normalize_ncm(record["NCM"])
            if len(ncm) != 8:
                raise ValueError(f"O item {index} possui NCM inválido; informe oito dígitos.")
            if ncm in seen:
                raise ValueError(f"O NCM {ncm} está duplicado na base fiscal.")
            seen.add(ncm)
            record["NCM"] = ncm

        load_fiscal_catalog_bytes(
            json.dumps(payload, ensure_ascii=False).encode("utf-8")
        )
        return payload

    def _normalize_registration(self, item: FiscalRegistration) -> FiscalRegistration:
        ncm = normalize_ncm(item.ncm)
        if len(ncm) != 8:
            raise ValueError("O NCM deve conter exatamente oito dígitos.")
        return FiscalRegistration(
            ncm=ncm,
            position=_text(item.position),
            subposition=_text(item.subposition),
            subitem=_text(item.subitem),
            state=_required(item.state, "Estado"),
            internal_rate=_required(item.internal_rate, "Alíquota Interna"),
            reduced_base=_required(item.reduced_base, "Base Reduzida"),
            deferral=_required(item.deferral, "Diferimento"),
            fcp=_required(item.fcp, "FCP"),
            exemption=_required(item.exemption, "Isenção"),
            non_incidence=_required(item.non_incidence, "Não Incidência"),
            st=_required(item.st, "ST"),
            mva=_normalize_mva(item.mva),
            cest=_normalize_cest(item.cest),
            suspension=_required(item.suspension, "Suspensão"),
        )

    @staticmethod
    def _atomic_write(path: Path, payload: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path: Path | None = None
        try:
            with NamedTemporaryFile("wb", dir=path.parent, delete=False) as temporary:
                temporary.write(payload)
                temporary.flush()
                os.fsync(temporary.fileno())
                temp_path = Path(temporary.name)
            temp_path.replace(path)
        finally:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)


def _normalize_mva(value: str) -> str:
    text = _text(value)
    if not text:
        return ""
    try:
        number = Decimal(text.removesuffix("%").strip().replace(",", "."))
    except InvalidOperation as exc:
        raise ValueError("A MVA deve ser um percentual numérico válido.") from exc
    if not number.is_finite() or number < 0:
        raise ValueError("A MVA deve ser um percentual maior ou igual a zero.")
    formatted = format(number.normalize(), "f").replace(".", ",")
    return f"{formatted}%"


def _normalize_cest(value: str) -> str:
    text = _text(value)
    if not text:
        return ""
    digits = normalize_ncm(text)
    invalid = [char for char in text if char not in "0123456789. -"]
    if len(digits) != 7 or invalid:
        raise ValueError("O CEST deve conter exatamente sete dígitos.")
    return digits


def _required(value: str, field_name: str) -> str:
    text = _text(value)
    if not text:
        raise ValueError(f"Informe o campo '{field_name}'.")
    return text


def _text(value: object) -> str:
    return "" if value is None else str(value).strip()
