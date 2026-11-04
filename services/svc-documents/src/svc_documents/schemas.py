"""Pydantic schemas for Feature 02: Gestão Inteligente de Documentos."""
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class DocumentResponse(BaseModel):
    id: str
    company_id: str
    competence: str
    department: str
    file_name: str
    file_size_bytes: int
    file_hash_sha256: str
    version: int
    is_latest: bool
    status: str
    ocr_status: str
    receipt_code: Optional[str] = None
    created_at: datetime


class DocumentReceiptResponse(BaseModel):
    receipt_code: str
    document_id: str
    file_name: str
    file_hash_sha256: str
    file_size_bytes: int
    uploaded_by: Optional[str]
    ip_address: str
    user_agent: Optional[str]
    timestamp_utc: datetime


class DocumentChecklistItemResponse(BaseModel):
    id: str
    title: str
    department: str
    is_required: bool
    is_fulfilled: bool
    fulfilled_by_document_id: Optional[str]


class DocumentChecklistResponse(BaseModel):
    id: str
    company_id: str
    competence: str
    title: str
    completion_percentage: int
    items: List[DocumentChecklistItemResponse]


class RequestChecklistInput(BaseModel):
    company_id: str
    competence: str = Field(..., json_schema_extra={"example": "2026-09"})
    channels: List[str] = ["portal", "whatsapp", "email"]
