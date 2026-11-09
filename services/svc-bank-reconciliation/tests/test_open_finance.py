from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from supreme_common.auth_context import create_access_token


PREFIX = "/bank-accounts/open-finance"
ITEM_ID = "e062ab2b-9006-45e8-b689-defabba53647"
ACCOUNT_ID = "a658c848-e475-457b-8565-d1fffba127c4"
TRANSACTION_ID = "a8534c85-53ce-4f21-94d7-50e9d2ee4957"
PERIOD = {"date_from": "2026-10-01", "date_to": "2026-10-31"}


@pytest.fixture(autouse=True)
def isolated_pluggy_runtime(tmp_path, monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "synthetic-test-secret-with-at-least-32-characters")
    monkeypatch.setenv("DB_ROOT_DIR", str(tmp_path / "db"))
    monkeypatch.setenv("EVENT_DB_PATH", str(tmp_path / "events.db"))
    monkeypatch.setenv("REDIS_URL", "")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("PLUGGY_CLIENT_ID", raising=False)
    monkeypatch.delenv("PLUGGY_CLIENT_SECRET", raising=False)


def authorization(**changes: object) -> dict[str, str]:
    claims = {
        "sub": "client-1",
        "organization_id": "org-1",
        "company_id": "company-1",
        "role": "client_user",
        "mfa_verified": True,
        **changes,
    }
    return {"Authorization": "Bearer " + create_access_token(claims), "X-Correlation-ID": "pluggy-test"}


class PluggyStub:
    def __init__(self) -> None:
        self.calls: list[httpx.Request] = []
        self.client_user_id = ""
        self.connector = {
            "id": 601,
            "name": "Banco sintético",
            "country": "BR",
            "type": "BUSINESS_BANK",
            "isOpenFinance": True,
            "isSandbox": False,
            "products": ["ACCOUNTS", "TRANSACTIONS"],
        }
        self.item = {
            "id": ITEM_ID,
            "connector": self.connector,
            "status": "UPDATED",
            "executionStatus": "SUCCESS",
            "products": ["ACCOUNTS", "TRANSACTIONS"],
            "consentExpiresAt": "2099-01-01T00:00:00Z",
            "lastUpdatedAt": "2026-10-31T12:00:00Z",
        }
        self.account = {
            "id": ACCOUNT_ID,
            "itemId": ITEM_ID,
            "type": "BANK",
            "name": "Conta Corrente",
            "number": "0001/12345-0",
            "balance": "90071992547409.93",
            "currencyCode": "BRL",
        }
        self.transactions = [
            {
                "id": TRANSACTION_ID,
                "accountId": ACCOUNT_ID,
                "description": "Pagamento sintético",
                "date": "2026-10-15T12:00:00Z",
                "amount": "-212.45",
                "currencyCode": "BRL",
                "status": "POSTED",
                "type": "DEBIT",
                "providerId": "bank-reference",
            }
        ]
        self.failure: tuple[str, int] | None = None

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        path = request.url.path
        if self.failure and path == self.failure[0]:
            return httpx.Response(self.failure[1], json={"message": "private-provider-secret"})
        if path == "/auth":
            return httpx.Response(200, json={"apiKey": "private-api-key"})
        assert request.headers["X-API-KEY"] == "private-api-key"
        assert "authorization" not in request.headers
        assert request.headers["X-Correlation-ID"] == "pluggy-test"
        if path == "/connect_token":
            self.client_user_id = json.loads(request.content)["options"]["clientUserId"]
            return httpx.Response(200, json={"accessToken": "public-connect-token"})
        if path == "/connectors":
            return httpx.Response(200, json={"results": [self.connector], "page": 1, "totalPages": 1})
        if path == "/connectors/601":
            return httpx.Response(200, json=self.connector)
        if path == f"/items/{ITEM_ID}":
            if request.method == "DELETE":
                return httpx.Response(200, json={"count": 1})
            return httpx.Response(200, json={"clientUserId": self.client_user_id, **self.item})
        if path == "/accounts":
            assert request.url.params["itemId"] == ITEM_ID
            assert request.url.params["type"] == "BANK"
            return httpx.Response(200, json={"results": [self.account], "page": 1, "totalPages": 1})
        if path == "/v2/transactions":
            assert request.url.params["accountId"] == ACCOUNT_ID
            assert request.url.params["dateFrom"] == PERIOD["date_from"]
            assert request.url.params["dateTo"] == PERIOD["date_to"]
            return httpx.Response(200, json={"results": self.transactions, "next": None})
        raise AssertionError(f"Unexpected provider request: {request.method} {path}")


@pytest.fixture
def api(tmp_path, monkeypatch):
    from svc_bank_reconciliation.app import create_app
    from svc_bank_reconciliation.pluggy_client import PluggyClient, PluggySettings, get_pluggy

    stub = PluggyStub()
    provider = PluggyClient(
        PluggySettings(client_id="synthetic-client", client_secret="synthetic-secret"),
        transport=httpx.MockTransport(stub),
    )
    app = create_app(database_url=f"sqlite:///{(tmp_path / 'pluggy.db').as_posix()}")
    app.dependency_overrides[get_pluggy] = lambda: provider
    with TestClient(app) as client:
        client.headers.update(authorization())
        yield client, stub, app


def connect(client: TestClient) -> str:
    response = client.post(PREFIX + "/connect-token", json={"connector_id": 601})
    assert response.status_code == 201, response.text
    assert response.json()["access_token"] == "public-connect-token"
    connection_id = response.json()["connection_id"]
    response = client.post(PREFIX + f"/connections/{connection_id}/complete", json={"item_id": ITEM_ID})
    assert response.status_code == 200, response.text
    return connection_id


def test_connection_and_local_statement(api):
    client, stub, _ = api
    connection = connect(client)
    response = client.post(PREFIX + f"/connections/{connection}/sync", json=PERIOD)
    assert response.status_code == 200, response.text
    calls = len(stub.calls)
    accounts = client.get(PREFIX + f"/connections/{connection}/accounts").json()
    assert accounts[0]["balance"] == "90071992547409.93"
    statement = client.get(PREFIX + f"/accounts/{ACCOUNT_ID}/transactions", params=PERIOD)
    assert statement.status_code == 200, statement.text
    assert statement.json()["results"][0]["amount"] == "-212.45"
    assert statement.json()["total"] == 1
    assert len(stub.calls) == calls  # Portal reads the stored snapshot, never the provider.
    assert "private-api-key" not in statement.text
    assert len([r for r in stub.calls if r.url.path == "/auth"]) == 1


@pytest.mark.parametrize("changes", [{"company_id": "other"}, {"organization_id": "other"}])
def test_cross_tenant_connection_is_inaccessible(api, changes):
    client, stub, _ = api
    connection = connect(client)
    calls = len(stub.calls)
    client.headers.update(authorization(**changes))
    assert client.get(PREFIX + f"/connections/{connection}").status_code == 404
    assert client.post(PREFIX + f"/connections/{connection}/sync", json=PERIOD).status_code == 404
    assert client.delete(PREFIX + f"/connections/{connection}").status_code == 404
    assert len(stub.calls) == calls


def test_unrelated_item_cannot_be_registered(api):
    client, stub, _ = api
    issued = client.post(PREFIX + "/connect-token", json={"connector_id": 601}).json()
    stub.item["clientUserId"] = "unrelated-session"
    response = client.post(
        PREFIX + f"/connections/{issued['connection_id']}/complete", json={"item_id": ITEM_ID}
    )
    assert response.status_code == 403


def test_failed_sync_preserves_snapshot(api):
    client, stub, _ = api
    connection = connect(client)
    assert client.post(PREFIX + f"/connections/{connection}/sync", json=PERIOD).status_code == 200
    stub.failure = ("/v2/transactions", 500)
    response = client.post(PREFIX + f"/connections/{connection}/sync", json=PERIOD)
    assert response.status_code == 502
    assert "private-provider-secret" not in response.text
    assert client.get(PREFIX + f"/accounts/{ACCOUNT_ID}/transactions", params=PERIOD).json()["total"] == 1


def test_sync_updates_and_removes_transactions_without_duplicates(api):
    client, stub, _ = api
    connection = connect(client)
    endpoint = PREFIX + f"/connections/{connection}/sync"
    assert client.post(endpoint, json=PERIOD).status_code == 200
    stub.transactions[0]["amount"] = "-10.01"
    assert client.post(endpoint, json=PERIOD).status_code == 200
    assert client.post(endpoint, json=PERIOD).status_code == 200
    statement = client.get(PREFIX + f"/accounts/{ACCOUNT_ID}/transactions", params=PERIOD).json()
    assert statement["total"] == 1 and statement["results"][0]["amount"] == "-10.01"
    stub.transactions = []
    assert client.post(endpoint, json=PERIOD).status_code == 200
    assert client.get(PREFIX + f"/accounts/{ACCOUNT_ID}/transactions", params=PERIOD).json()["total"] == 0


def test_unknown_resource(api):
    client, _, _ = api
    assert client.get(PREFIX + f"/accounts/{uuid4()}/transactions", params=PERIOD).status_code == 404


@pytest.mark.parametrize(
    "changes,status",
    [
        ({"role": "viewer"}, 403),
        ({"role": "unknown"}, 403),
        ({"mfa_verified": False}, 403),
        ({"company_id": None}, 409),
    ],
)
def test_access_controls_before_provider_calls(api, changes, status):
    client, stub, _ = api
    client.headers.update(authorization(**changes))
    assert client.post(PREFIX + "/connect-token", json={"connector_id": 601}).status_code == status
    assert not stub.calls


def test_authentication_and_csrf(api):
    client, stub, _ = api
    token = client.headers.pop("Authorization")[7:]
    assert client.get(PREFIX + "/connections").status_code == 401
    client.cookies.set("supreme_session", token)
    assert client.post(PREFIX + "/connect-token", json={"connector_id": 601}).status_code == 403
    assert not stub.calls
    response = client.post(
        PREFIX + "/connect-token", json={"connector_id": 601}, headers={"X-Supreme-CSRF": "1"}
    )
    assert response.status_code == 201


@pytest.mark.parametrize(
    "change",
    [
        {"isOpenFinance": False},
        {"isSandbox": True},
        {"country": "US"},
        {"type": "INVESTMENT"},
        {"products": ["ACCOUNTS"]},
    ],
)
def test_only_open_finance_banks(api, change):
    client, stub, _ = api
    stub.connector.update(change)
    assert client.get(PREFIX + "/connectors").json() == []
    assert client.post(PREFIX + "/connect-token", json={"connector_id": 601}).status_code == 422
    assert not any(r.url.path == "/connect_token" for r in stub.calls)


@pytest.mark.parametrize(
    "payload",
    [
        {"connector_id": -1},
        {"connector_id": "601"},
        {"connector_id": 601, "products": ["PAYMENT_DATA"]},
        {"connector_id": 601, "clientUserId": "forged"},
        {"connector_id": 601, "webhookUrl": "https://evil.test"},
    ],
)
def test_connect_input_validation(api, payload):
    client, stub, _ = api
    assert client.post(PREFIX + "/connect-token", json=payload).status_code == 422
    assert not stub.calls


def test_complete_expiration_owner_and_idempotence(api):
    from svc_bank_reconciliation.open_finance_models import OpenFinanceConnection

    client, stub, app = api
    issued = client.post(PREFIX + "/connect-token", json={"connector_id": 601}).json()
    url = PREFIX + f"/connections/{issued['connection_id']}/complete"
    assert (
        client.post(url, json={"item_id": ITEM_ID}, headers=authorization(sub="other-user")).status_code
        == 403
    )
    with app.state.sessions() as db:
        row = db.get(OpenFinanceConnection, issued["connection_id"])
        row.expires_at = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        db.commit()
    assert client.post(url, json={"item_id": ITEM_ID}).status_code == 410
    connection = connect(client)
    calls = len(stub.calls)
    url = PREFIX + f"/connections/{connection}/complete"
    assert client.post(url, json={"item_id": ITEM_ID}).status_code == 200
    assert len(stub.calls) == calls
    assert client.post(url, json={"item_id": str(uuid4())}).status_code == 409


def test_widget_options_and_reconnection_token(api):
    client, stub, _ = api
    connection = connect(client)
    response = client.post(PREFIX + f"/connections/{connection}/connect-token")
    assert response.status_code == 200
    assert response.json()["widget_options"] == {
        "connectorIds": [601],
        "selectedConnectorId": 601,
        "countries": ["BR"],
        "products": ["ACCOUNTS", "TRANSACTIONS"],
        "includeSandbox": False,
        "updateItem": ITEM_ID,
    }
    sent = json.loads(stub.calls[-1].content)
    assert sent["itemId"] == ITEM_ID
    assert sent["options"]["products"] == ["ACCOUNTS", "TRANSACTIONS"]
    assert sent["options"]["avoidDuplicates"] is False
    assert "org-1" not in sent["options"]["clientUserId"]


@pytest.mark.parametrize(
    "change",
    [
        {"status": "UPDATING"},
        {"status": "PARTIAL_SUCCESS"},
        {"executionStatus": "ERROR"},
        {"consentExpiresAt": "2020-01-01T00:00:00Z"},
        {"statusDetail": {"transactions": {"status": "ERROR"}}},
    ],
)
def test_incomplete_or_expired_consent_is_not_a_statement(api, change):
    client, stub, _ = api
    connection = connect(client)
    stub.item.update(change)
    assert client.post(PREFIX + f"/connections/{connection}/sync", json=PERIOD).status_code == 409
    assert not any(r.url.path == "/v2/transactions" for r in stub.calls)
    assert client.get(PREFIX + f"/connections/{connection}/accounts").status_code == 409


@pytest.mark.parametrize(
    "change",
    [
        {"accountId": str(uuid4())},
        {"amount": "NaN"},
        {"amount": "Infinity"},
        {"amount": "10.01"},
        {"status": "UNKNOWN"},
        {"date": "2026-11-01T00:00:00Z"},
        {"date": "2026-10-15T12:00:00"},
        {"currencyCode": "invalid"},
    ],
)
def test_invalid_provider_data_never_replaces_local_statement(api, change):
    client, stub, _ = api
    connection = connect(client)
    endpoint = PREFIX + f"/connections/{connection}/sync"
    assert client.post(endpoint, json=PERIOD).status_code == 200
    stub.transactions[0].update(change)
    assert client.post(endpoint, json=PERIOD).status_code == 502
    result = client.get(PREFIX + f"/accounts/{ACCOUNT_ID}/transactions", params=PERIOD).json()
    assert result["results"][0]["amount"] == "-212.45"


def test_wrong_account_and_extra_products_rejected(api):
    client, stub, _ = api
    connection = connect(client)
    stub.account["itemId"] = str(uuid4())
    assert client.post(PREFIX + f"/connections/{connection}/sync", json=PERIOD).status_code == 502
    stub.item["products"].append("PAYMENT_DATA")
    assert client.post(PREFIX + f"/connections/{connection}/sync", json=PERIOD).status_code == 422


@pytest.mark.parametrize(
    "period",
    [
        {"date_from": "2026-10-31", "date_to": "2026-10-01"},
        {"date_from": "2020-01-01", "date_to": "2026-10-01"},
        {"date_from": "invalid", "date_to": "2026-10-01"},
    ],
)
def test_period_validation(api, period):
    client, stub, _ = api
    connection = connect(client)
    calls = len(stub.calls)
    assert client.post(PREFIX + f"/connections/{connection}/sync", json=period).status_code == 422
    assert len(stub.calls) == calls


def test_local_pagination_coverage_and_tenant_isolation(api):
    client, stub, _ = api
    connection = connect(client)
    stub.transactions.append({**stub.transactions[0], "id": str(uuid4()), "status": "PENDING"})
    assert client.post(PREFIX + f"/connections/{connection}/sync", json=PERIOD).status_code == 200
    url = PREFIX + f"/accounts/{ACCOUNT_ID}/transactions"
    result = client.get(url, params={**PERIOD, "limit": 1, "offset": 1}).json()
    assert result["total"] == 2 and len(result["results"]) == 1
    assert client.get(url, params={**PERIOD, "date_from": "2026-09-30"}).status_code == 409
    assert client.get(url, params={**PERIOD, "limit": 501}).status_code == 422
    assert client.get(url, params=PERIOD, headers=authorization(company_id="other")).status_code == 404
    assert client.get(url, params=PERIOD, headers=authorization(organization_id="other")).status_code == 404


def test_disconnect_is_remote_and_idempotent(api):
    client, stub, _ = api
    connection = connect(client)
    assert client.post(PREFIX + f"/connections/{connection}/sync", json=PERIOD).status_code == 200
    endpoint = PREFIX + f"/connections/{connection}"
    stub.failure = (f"/items/{ITEM_ID}", 500)
    assert client.delete(endpoint).status_code == 502
    assert client.get(endpoint + "/accounts").status_code == 200
    stub.failure = None
    assert client.delete(endpoint).status_code == 204
    calls = len(stub.calls)
    assert client.delete(endpoint).status_code == 204
    assert len(stub.calls) == calls
    assert client.get(endpoint + "/accounts").status_code == 410
    assert client.get(PREFIX + f"/accounts/{ACCOUNT_ID}/transactions", params=PERIOD).status_code == 410
    assert client.get(endpoint).json()["status"] == "disconnected"
    assert len([r for r in stub.calls if r.method == "DELETE"]) == 1


def test_unconfigured_provider_is_explicit_and_local_routes_still_work(api):
    from svc_bank_reconciliation.pluggy_client import get_pluggy

    client, _, app = api
    app.dependency_overrides.pop(get_pluggy)
    assert client.get(PREFIX + "/connections").status_code == 200
    response = client.post(PREFIX + "/connect-token", json={"connector_id": 601})
    assert response.status_code == 503
    assert "PLUGGY_CLIENT_ID" in response.json()["detail"]


def test_gateway_routes_and_cookie_flow(api, monkeypatch):
    from gateway.bff_router import create_app, public_path

    _, _, app = api
    monkeypatch.setenv("SVC_BANK_RECONCILIATION_URL", "http://bank-service")
    with TestClient(create_app(transport=httpx.ASGITransport(app=app))) as gateway:
        gateway.cookies.set("supreme_session", authorization()["Authorization"][7:])
        headers = {"X-Supreme-CSRF": "1", "X-Correlation-ID": "pluggy-test"}
        response = gateway.post(
            "/api/v1" + PREFIX + "/connect-token", json={"connector_id": 601}, headers=headers
        )
        assert response.status_code == 201, response.text
        path = PREFIX + f"/connections/{response.json()['connection_id']}/complete"
        response = gateway.post("/api/v1" + path, json={"item_id": ITEM_ID}, headers=headers)
        assert response.status_code == 200, response.text
        assert response.headers["Cache-Control"] == "no-store"
        assert (
            public_path("bank-reconciliation", PREFIX + "/connect-token")
            == "/api/v1" + PREFIX + "/connect-token"
        )


def test_optimistic_concurrency_prevents_stale_snapshot_write(api):
    from sqlalchemy.orm.exc import StaleDataError
    from svc_bank_reconciliation.open_finance_models import OpenFinanceConnection

    client, _, app = api
    connection = connect(client)
    with app.state.sessions() as first, app.state.sessions() as second:
        stale = first.get(OpenFinanceConnection, connection)
        fresh = second.get(OpenFinanceConnection, connection)
        fresh.disconnected_at = datetime.now(timezone.utc).isoformat()
        second.commit()
        stale.synced_at = datetime.now(timezone.utc).isoformat()
        with pytest.raises(StaleDataError):
            first.commit()


def test_additive_migration_preserves_existing_accounts(tmp_path):
    from sqlalchemy import create_engine, inspect, text
    from svc_bank_reconciliation.database import Base
    from svc_bank_reconciliation.migrate_open_finance import TABLES, missing_tables, upgrade

    engine = create_engine(f"sqlite:///{(tmp_path / 'migration.db').as_posix()}")
    names = {t.name for t in TABLES}
    Base.metadata.create_all(engine, tables=[t for t in Base.metadata.sorted_tables if t.name not in names])
    with engine.begin() as db:
        db.execute(
            text(
                "INSERT INTO bank_accounts (id, company_id, bank_code, bank_name, agency_number, "
                "account_number, current_balance) VALUES ('existing', 'company', '001', "
                "'Sintético', '1', '1', 123.45)"
            )
        )
    original_columns = inspect(engine).get_columns("bank_accounts")
    assert set(missing_tables(engine)) == names
    assert set(upgrade(engine)) == names
    assert upgrade(engine) == []
    assert missing_tables(engine) == []
    assert [c["name"] for c in inspect(engine).get_columns("bank_accounts")] == [
        c["name"] for c in original_columns
    ]
    with engine.connect() as db:
        assert (
            db.execute(text("SELECT bank_name FROM bank_accounts WHERE id='existing'")).scalar()
            == "Sintético"
        )
    engine.dispose()


def test_openapi_exposes_typed_statement_contract(api):
    client, _, _ = api
    schema = client.get("/openapi.json").json()
    operation = schema["paths"][PREFIX + "/accounts/{account_id}/transactions"]["get"]
    assert operation["responses"]["200"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "/TransactionPage"
    )
    assert "amount" in schema["components"]["schemas"]["Transaction"]["properties"]
