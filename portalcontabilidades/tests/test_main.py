"""End-to-End integration test for root main.py application."""


def test_root_endpoint(client):
    """Tests root discovery endpoint and confirms all 10 modules are operational."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "operational"
    assert len(data["features_loaded"]) == 10
    folder_names = [f["folder"] for f in data["features_loaded"]]
    assert "10-seguranca-lgpd-e-certificados" in folder_names
    assert "09-gestao-multiempresa" in folder_names
    assert "01-central-de-obrigacoes-tarefas-e-prazos" in folder_names
    assert "02-gestao-inteligente-de-documentos" in folder_names
    assert "03-conciliacao-bancaria-automatica" in folder_names
    assert "04-contas-a-pagar-e-receber" in folder_names
    assert "05-integracoes-fiscais-e-governamentais" in folder_names
    assert "06-portal-do-cliente-e-comunicacao" in folder_names
    assert "07-fluxo-de-caixa-dre-e-dashboards" in folder_names
    assert "08-automacao-e-ia-contabil" in folder_names


def test_health_check(client):
    """Tests liveness probe."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_openapi_schema_generation(client):
    """Tests OpenAPI /docs JSON schema generation including routes across all 10 features."""
    response = client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    assert "paths" in schema
    assert len(schema["paths"]) >= 40
    # Spot-check critical endpoints from distinct modules
    assert "/security/mfa/setup" in schema["paths"]
    assert "/companies" in schema["paths"]
    assert "/tasks/{task_id}/status" in schema["paths"]
    assert "/documents/upload" in schema["paths"]
    assert "/bank-accounts/{account_id}/statements/import-ofx" in schema["paths"]
    assert "/bills/payable" in schema["paths"]
    assert "/fiscal/transmissions/enqueue" in schema["paths"]
    assert "/portal/tickets" in schema["paths"]
    assert "/analytics/companies/{company_id}/dre" in schema["paths"]
    assert "/api/v1/ai/transactions/suggest-classification" in schema["paths"]
