from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StatementError(ValueError):
    """A safe, actionable validation message, without document contents."""


class Candidate(BaseModel):
    id: str
    source_id: str
    format: Literal['pdf', 'csv', 'xlsx', 'ofx']
    location: str
    date: date
    amount: Decimal = Field(ge=0, max_digits=18, decimal_places=2, allow_inf_nan=False)
    type: Literal['entrada', 'saida']
    description: str = Field(min_length=1, max_length=4000)
    reference: str = ''
    reference_kind: Literal['fitid', 'document', 'none'] = 'none'
    quality: dict[str, int]
    currency: str = 'BRL'


class ParsedSource(BaseModel):
    id: str
    filename: str
    sha256: str
    format: Literal['pdf', 'csv', 'xlsx', 'ofx']
    bank_code: str = ''
    agency: str = ''
    account: str = ''
    excluded_balances: int = 0
    currency: str = 'BRL'
    rows: list[Candidate] = Field(default_factory=list)


class Group(BaseModel):
    id: str
    date: date
    amount: Decimal
    type: Literal['entrada', 'saida']
    candidates: list[Candidate]
    field_sources: dict[str, str]
    issues: list[str] = Field(default_factory=list)
    selected_description_id: str | None = None
    selection_reason: str | None = None
    ai_model: str | None = None
    ai_response_id: str | None = None


class ImportPayload(BaseModel):
    bank_code: str
    agency: str
    account: str
    date_from: date
    date_to: date
    sources: list[ParsedSource]
    groups: list[Group]


class Selection(BaseModel):
    model_config = ConfigDict(extra='forbid')
    group_id: str
    candidate_id: str
    reason: str = Field(min_length=1, max_length=500)


class Selections(BaseModel):
    model_config = ConfigDict(extra='forbid')
    selections: list[Selection]
