"""Tests for Feature 08: Automação e IA Contábil."""
from datetime import date
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


from portalcontabilidades.core.database import Base, get_db
from portalcontabilidades.features.automacao_ia.models import AiExtraction, AiClassificationSuggestion, AiAnomalyAlert
from portalcontabilidades.features.automacao_ia.router import router
from portalcontabilidades.features.automacao_ia.ocr_extractor import extract_structured_invoice_data
from portalcontabilidades.features.automacao_ia.anomaly_detector import detect_payment_anomalies
from portalcontabilidades.features.automacao_ia.classification_suggester import suggest_accounting_classification, register_user_feedback
from portalcontabilidades.features.automacao_ia.executive_summary import generate_consultative_summary, LEGAL_DISCLAIMER

# Test Database setup with StaticPool for in-memory SQLite shared across connections
TEST_DB_URL = "sqlite:///:memory:"
engine = create_engine(
    TEST_DB_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app = FastAPI()
app.include_router(router)
app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(autouse=True)
def setup_database():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client():
    return TestClient(app)


def test_ocr_extraction_high_and_low_confidence(client):
    """Tests OCR parsing of high-quality utility bill vs blurry/unrecognized receipt."""
    # 1. High quality bill text
    high_quality_text = (
        "ENEL DISTRIBUICAO SAO PAULO\n"
        "CNPJ: 61.695.227/0001-93\n"
        "Fatura de Energia Eletrica No: 9845123\n"
        "Data de Vencimento: 25/11/2026\n"
        "Total a Pagar: R$ 845,90\n"
        "Linha Digitavel: 83640000008459000180005020261125000000000000\n"
    )
    resp = client.post(
        "/api/v1/ai/documents/doc-high-01/extract",
        json={"document_id": "doc-high-01", "raw_text": high_quality_text}
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["confidence_score"] >= 80.0
    assert data["requires_manual_review"] is False
    assert data["extracted_data"]["issuer_tax_id"] == "61.695.227/0001-93"
    assert data["extracted_data"]["total_amount"] == 845.90
    assert data["extracted_data"]["due_date"] == "25/11/2026"

    # 2. Blurry / damaged receipt text
    low_quality_text = "Comprovante ilegivel ... borrões ..."
    resp_low = client.post(
        "/api/v1/ai/documents/doc-low-02/extract",
        json={"document_id": "doc-low-02", "raw_text": low_quality_text}
    )
    assert resp_low.status_code == 201
    data_low = resp_low.json()
    assert data_low["confidence_score"] < 70.0
    assert data_low["requires_manual_review"] is True


def test_classification_suggestion_and_human_loop_guard(client):
    """Validates that AI suggestions return confidence score and strictly enforce human review."""
    resp = client.post(
        "/api/v1/ai/transactions/suggest-classification",
        json={
            "company_id": "comp-100",
            "description_or_memo": "Conta de Luz Enel SP",
            "amount": 420.50
        }
    )
    assert resp.status_code == 200
    sugg = resp.json()
    assert sugg["suggested_debit_account"] == "3.1.02.01"  # Despesa Energia
    assert sugg["suggested_credit_account"] == "1.1.01.02"  # Banco
    assert sugg["confidence_score"] >= 90.0
    assert sugg["requires_human_approval"] is True
    assert sugg["decision_status"] == "pending_review"


def test_operator_feedback_and_continuous_learning(client):
    """Validates that human feedback updates suggestion and prioritizes learned rule for future runs."""
    # 1. Create a generic suggestion
    resp_init = client.post(
        "/api/v1/ai/transactions/suggest-classification",
        json={
            "company_id": "comp-aprendizado",
            "description_or_memo": "Fornecedor Tech Alpha Software",
            "amount": 1500.00
        }
    )
    sugg_id = resp_init.json()["id"]

    # 2. Operator reviews and edits to custom account
    resp_feedback = client.post(
        f"/api/v1/ai/suggestions/{sugg_id}/feedback",
        json={
            "decision": "edited",
            "reviewed_by": "user-senior-accountant",
            "counterparty_keyword": "tech alpha",
            "edited_debit_account": "3.1.03.88",
            "edited_credit_account": "1.1.01.02",
            "edited_cost_center": "TI"
        }
    )
    assert resp_feedback.status_code == 200
    fb = resp_feedback.json()
    assert fb["decision_status"] == "edited"
    assert fb["reviewed_by"] == "user-senior-accountant"

    # 3. New transaction from same vendor should now match learned feedback with 99% confidence
    resp_next = client.post(
        "/api/v1/ai/transactions/suggest-classification",
        json={
            "company_id": "comp-aprendizado",
            "description_or_memo": "Mensalidade Tech Alpha Licencas",
            "amount": 1500.00
        }
    )
    assert resp_next.status_code == 200
    next_sugg = resp_next.json()
    assert next_sugg["suggested_debit_account"] == "3.1.03.88"
    assert next_sugg["suggested_cost_center"] == "TI"
    assert next_sugg["confidence_score"] == 99.0


def test_anomaly_detection_duplicate_and_spike(client):
    """Tests duplicate payment risk and expense spike detection."""
    company_id = "comp-anomalies"

    # Historical bills
    hist = [
        {
            "id": "bill-old-01",
            "counterparty_tax_id": "11.222.333/0001-44",
            "amount": 2500.00,
            "due_date": "2026-11-10"
        }
    ]

    # New bill 1: Duplicate risk (same CNPJ, same amount, 5 days apart)
    new_dup_bill = {
        "id": "bill-new-02",
        "counterparty_tax_id": "11.222.333/0001-44",
        "amount": 2500.00,
        "due_date": "2026-11-15"
    }

    # New bill 2: Expense spike (R$ 5,000 when average is R$ 1,000 -> 5x / 400% spike)
    scan_resp = client.post(
        f"/api/v1/ai/companies/{company_id}/scan-anomalies",
        json={
            "company_id": company_id,
            "new_bill": new_dup_bill,
            "historical_bills": hist,
            "historical_average_expense": 500.0
        }
    )
    assert scan_resp.status_code == 200
    alerts = scan_resp.json()
    assert len(alerts) >= 2  # duplicate + spike
    types = [a["anomaly_type"] for a in alerts]
    assert "duplicate_payment_risk" in types
    assert "abnormal_expense_spike" in types

    # Query anomalies endpoint
    list_resp = client.get(f"/api/v1/ai/companies/{company_id}/anomalies")
    assert list_resp.status_code == 200
    assert len(list_resp.json()) >= 2


def test_executive_summary_mandatory_legal_disclaimer(client):
    """Tests that the AI consultative executive summary includes highlights and mandatory CFC disclaimer."""
    resp = client.post(
        "/api/v1/ai/companies/comp-exec-01/generate-executive-summary",
        json={
            "company_id": "comp-exec-01",
            "month": 10,
            "year": 2026,
            "metrics_summary": {
                "gross_revenue": 240000.0,
                "net_result": 48000.0,
                "final_cash_balance": 115000.0
            }
        }
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["competence"] == "10/2026"
    assert "Receita Operacional Bruta" in str(data["key_highlights"])
    assert "Lucro Líquido apurado" in str(data["key_highlights"])
    assert "Aviso Legal" in data["legal_disclaimer"]
    assert "Resolução CFC" in data["legal_disclaimer"]
    assert len(data["sources_analyzed"]) >= 3
