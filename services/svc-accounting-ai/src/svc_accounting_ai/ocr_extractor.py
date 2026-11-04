"""Intelligent OCR and structured metadata extractor for Brazilian utility bills and invoices."""
import re
from typing import Dict, Any


def extract_structured_invoice_data(text_content: str) -> Dict[str, Any]:
    """Extracts structured metadata from OCR text: CNPJ, due date, total amount, barcode, and withholdings.
    Calculates overall confidence score based on core accounting fields.
    """
    confidence_points = 0

    # 1. CNPJ Extraction
    cnpj_match = re.search(r"(\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2})", text_content)
    if not cnpj_match:
        cnpj_match = re.search(r"\b(\d{14})\b", text_content)
    cnpj = cnpj_match.group(1) if cnpj_match else None
    if cnpj:
        confidence_points += 25

    # 2. Total Amount Extraction
    amount_match = re.search(r"(?:total|valor a pagar|total a pagar|valor da nota)[:\s]*r?\$?\s*([\d\.,]+)", text_content, re.IGNORECASE)
    total_amount = None
    if amount_match:
        try:
            val_str = amount_match.group(1).replace(".", "").replace(",", ".")
            total_amount = float(val_str)
            confidence_points += 25
        except Exception:
            pass

    # 3. Due Date Extraction
    due_match = re.search(r"(?:vencimento|venc|data de vencimento)[:\s]*(\d{2}/\d{2}/\d{4})", text_content, re.IGNORECASE)
    due_date = due_match.group(1) if due_match else None
    if due_date:
        confidence_points += 20

    # 4. Barcode / Linha Digitável (44 digits FEBRABAN barcode, 47 digits boleto, 48 digits concessionária)
    barcode_match = re.search(r"(\d{5}[\.\s]?\d{5}[\.\s]?\d{5}[\.\s]?\d{6}[\.\s]?\d{5}[\.\s]?\d{6}[\.\s]?\d[\.\s]?\d{14}|\d{44,48})", text_content)
    barcode = barcode_match.group(1) if barcode_match else None
    if barcode:
        confidence_points += 20

    # 5. Document Number
    doc_match = re.search(r"(?:n[oº°\.]|n[úu]mero|fatura|nf-e|nota fiscal)\s*[:]?\s*([a-z0-9\.-]+)", text_content, re.IGNORECASE)
    doc_number = doc_match.group(1) if doc_match else None
    if doc_number:
        confidence_points += 10

    # 6. Withholdings (Retenções)
    withholdings = {}
    irrf = re.search(r"irrf[:\s]*r?\$?\s*([\d\.,]+)", text_content, re.IGNORECASE)
    if irrf:
        withholdings["irrf"] = irrf.group(1)
    iss = re.search(r"iss[:\s]*r?\$?\s*([\d\.,]+)", text_content, re.IGNORECASE)
    if iss:
        withholdings["iss"] = iss.group(1)

    score_pct = min(100, max(30, confidence_points))

    return {
        "issuer_tax_id": cnpj,
        "document_number": doc_number,
        "due_date": due_date,
        "total_amount": total_amount,
        "barcode_line": barcode,
        "withholdings": withholdings,
        "confidence_score": score_pct,
        "requires_manual_review": score_pct < 70
    }
