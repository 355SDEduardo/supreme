from __future__ import annotations

import json

import httpx
import pytest
from fastapi.testclient import TestClient
from supreme_common.auth_context import create_access_token

PREFIX = "/bank-accounts/open-finance/configuration"
CREDS = {"client_id": "synthetic-client", "client_secret": "synthetic-secret", "revision": 0}


def headers(**changes: object) -> dict[str, str]:
    claims = {
        "sub": "admin-1",
        "organization_id": "org-1",
        "company_id": "company-1",
        "role": "super_admin",
        "mfa_verified": True,
        **changes,
    }
    return {"Authorization": "Bearer " + create_access_token(claims)}


@pytest.fixture
def api(tmp_path, monkeypatch):
    from svc_bank_reconciliation.app import create_app
    from svc_bank_reconciliation.pluggy_client import PluggyClient

    monkeypatch.delenv("PLUGGY_CLIENT_ID", raising=False)
    monkeypatch.delenv("PLUGGY_CLIENT_SECRET", raising=False)
    monkeypatch.setenv("PLUGGY_ALLOW_SANDBOX", "false")
    monkeypatch.setenv("SUPREME_ENV", "development")
    calls = []

    def provider(request):
        calls.append(request)
        if request.url.path == "/auth":
            payload = json.loads(request.content)
            if payload["clientSecret"] == "invalid-secret":
                return httpx.Response(401, json={"detail": "private-provider-body"})
            return httpx.Response(200, json={"apiKey": "private-provider-api-key"})
        if request.url.path == "/connectors":
            return httpx.Response(200, json={"page": 1, "totalPages": 0, "results": []})
        raise AssertionError(request.url.path)

    original = PluggyClient.__init__

    def init(self, settings, **kwargs):
        original(self, settings, transport=httpx.MockTransport(provider))

    monkeypatch.setattr(PluggyClient, "__init__", init)
    app = create_app(database_url=f"sqlite:///{(tmp_path / 'config.db').as_posix()}")
    with TestClient(app) as client:
        client.headers.update(headers())
        yield client, app, calls


def test_configuration_is_missing_until_saved_and_never_returns_secrets(api):
    client, app, calls = api
    response = client.get(PREFIX)
    assert response.status_code == 200
    assert response.json()["source"] == "none"
    response = client.put(PREFIX, json=CREDS)
    assert response.status_code == 200, response.text
    assert response.json()["configured"] is True
    assert response.json()["source"] == "company"
    assert response.json()["revision"] == 1
    assert calls[0].url.path == "/auth"
    assert "synthetic-secret" not in response.text
    assert "synthetic-client" not in response.text
    assert "private-provider-api-key" not in response.text
    from svc_bank_reconciliation.pluggy_configuration_store import PluggyConfiguration

    with app.state.sessions() as db:
        row = db.query(PluggyConfiguration).one()
        assert b"synthetic" not in row.encrypted_credentials
    assert client.get(PREFIX).json() == response.json()


@pytest.mark.parametrize("role", ["analyst", "bpo_operator", "client_user", "viewer", "service"])
def test_configuration_requires_admin_on_server(api, role):
    client, _, calls = api
    for method, suffix in [("GET", ""), ("PUT", ""), ("POST", "/test"), ("DELETE", "?revision=0")]:
        response = client.request(method, PREFIX + suffix, json=CREDS, headers=headers(role=role))
        assert response.status_code == 403
    assert calls == []


def test_company_and_organization_are_isolated_and_config_used_by_existing_api(api):
    client, _, calls = api
    assert client.put(PREFIX, json=CREDS).status_code == 200
    for changes in [{"company_id": "other"}, {"organization_id": "other"}]:
        assert client.get(PREFIX, headers=headers(**changes)).json()["configured"] is False
        assert (
            client.get(
                PREFIX.replace("/configuration", "/connectors"), headers=headers(**changes)
            ).status_code
            == 503
        )
    assert client.get(PREFIX.replace("/configuration", "/connectors")).status_code == 200
    assert json.loads(calls[-2].content)["clientId"] == CREDS["client_id"]


def test_invalid_replacement_preserves_previous_configuration_and_redacts_errors(api):
    client, _, _ = api
    original = client.put(PREFIX, json=CREDS).json()
    response = client.put(PREFIX, json={"client_secret": "invalid-secret", "revision": 1})
    assert response.status_code == 503
    assert "private-provider-body" not in response.text
    assert client.get(PREFIX).json() == original
    response = client.put(PREFIX, json={"client_secret": {"secret": "do-not-echo"}, "revision": 1})
    assert response.status_code == 422
    assert "do-not-echo" not in response.text


def test_rotation_reuses_id_invalidates_cache_and_prevents_stale_writes(api):
    client, _, calls = api
    client.put(PREFIX, json=CREDS)
    connectors = PREFIX.replace("/configuration", "/connectors")
    assert client.get(connectors).status_code == 200
    assert client.put(PREFIX, json={"revision": 1, "client_secret": "rotated-secret"}).status_code == 200
    assert client.get(connectors).status_code == 200
    assert json.loads(calls[-2].content)["clientSecret"] == "rotated-secret"
    assert client.put(PREFIX, json={"revision": 1, "client_secret": "stale-secret"}).status_code == 409
    assert client.delete(PREFIX + "?revision=1").status_code == 409
    assert client.post(PREFIX + "/test").status_code == 200
    assert client.delete(PREFIX + "?revision=2").status_code == 200
    assert client.get(connectors).status_code == 503


def test_environment_fallback_and_production_sandbox_restriction(api, monkeypatch):
    client, _, _ = api
    monkeypatch.setenv("PLUGGY_CLIENT_ID", "environment-client")
    monkeypatch.setenv("PLUGGY_CLIENT_SECRET", "environment-secret")
    assert client.get(PREFIX).json()["source"] == "environment"
    assert client.put(PREFIX, json=CREDS).json()["source"] == "company"
    assert client.delete(PREFIX + "?revision=1").json()["source"] == "environment"
    monkeypatch.setenv("SUPREME_ENV", "production")
    assert client.get(PREFIX).json()["sandbox_allowed"] is False
    assert client.put(PREFIX, json={**CREDS, "allow_sandbox": True}).status_code == 422


def test_missing_encryption_key_does_not_persist_or_send_credentials(api, monkeypatch):
    client, _, calls = api
    monkeypatch.delenv("MASTER_ENCRYPTION_KEY")
    assert client.get(PREFIX).json()["storage_available"] is False
    assert client.put(PREFIX, json=CREDS).status_code == 503
    assert calls == []


def test_gateway_cookie_csrf_and_mfa(api, monkeypatch):
    from gateway.bff_router import create_app

    client, app, _ = api
    assert client.get(PREFIX, headers=headers(mfa_verified=False)).status_code == 403
    assert client.get(PREFIX, headers=headers(company_id=None)).status_code == 409
    monkeypatch.setenv("SVC_BANK_RECONCILIATION_URL", "http://bank-service")
    with TestClient(create_app(transport=httpx.ASGITransport(app=app))) as gateway:
        gateway.cookies.set("supreme_session", headers()["Authorization"][7:])
        endpoint = "/api/v1" + PREFIX
        assert gateway.put(endpoint, json=CREDS).status_code == 403
        response = gateway.put(endpoint, json=CREDS, headers={"X-Supreme-CSRF": "1"})
        assert response.status_code == 200
        assert response.headers["Cache-Control"] == "no-store"


def test_partial_environment_can_be_replaced_from_frontend(api, monkeypatch):
    client, _, _ = api
    monkeypatch.setenv("PLUGGY_CLIENT_ID", "incomplete-client")
    response = client.get(PREFIX)
    assert response.status_code == 200
    assert response.json()["configured"] is False
    assert response.json()["configuration_error"]
    assert client.put(PREFIX, json=CREDS).status_code == 200


def test_sandbox_configuration_can_be_corrected_after_switching_to_production(api, monkeypatch):
    client, _, _ = api
    assert client.put(PREFIX, json={**CREDS, "allow_sandbox": True}).status_code == 200
    monkeypatch.setenv("SUPREME_ENV", "production")
    assert client.get(PREFIX).status_code == 200
    assert client.get(PREFIX.replace("/configuration", "/connectors")).status_code == 503
    assert client.put(PREFIX, json={"revision": 1, "allow_sandbox": False}).status_code == 200


def test_encrypted_credentials_cannot_be_copied_to_another_tenant(api):
    from svc_bank_reconciliation.pluggy_configuration_store import PluggyConfiguration

    client, app, _ = api
    client.put(PREFIX, json=CREDS)
    with app.state.sessions() as db:
        row = db.get(PluggyConfiguration, ("org-1", "company-1"))
        db.add(
            PluggyConfiguration(
                organization_id="org-1",
                company_id="other",
                encrypted_credentials=row.encrypted_credentials,
                updated_at=row.updated_at,
                updated_by=row.updated_by,
            )
        )
        db.commit()
    response = client.get(
        PREFIX.replace("/configuration", "/connectors"), headers=headers(company_id="other")
    )
    assert response.status_code == 503
    assert CREDS["client_secret"] not in response.text


def test_active_connections_prevent_app_replacement_and_removal_but_allow_secret_rotation(api):
    from svc_bank_reconciliation.open_finance_models import OpenFinanceConnection

    client, app, _ = api
    client.put(PREFIX, json=CREDS)
    with app.state.sessions() as db:
        db.add(
            OpenFinanceConnection(
                id="synthetic-connection",
                organization_id="org-1",
                company_id="company-1",
                user_id="admin-1",
                client_user_id="unique-session",
                connector_id=601,
                connector_name="Banco sintético",
                item_id="synthetic-item",
                expires_at="2020-01-01T00:00:00Z",
            )
        )
        db.commit()
    assert (
        client.put(PREFIX, json={**CREDS, "client_id": "different-client", "revision": 1}).status_code == 409
    )
    assert client.delete(PREFIX + "?revision=1").status_code == 409
    assert client.put(PREFIX, json={"client_secret": "new-secret", "revision": 1}).status_code == 200


def test_saved_settings_survive_client_cache_loss_and_reuse_authentication(api):
    client, app, calls = api
    client.put(PREFIX, json=CREDS)
    endpoint = PREFIX.replace("/configuration", "/connectors")
    assert client.get(endpoint).status_code == 200
    assert client.get(endpoint).status_code == 200
    assert len([call for call in calls if call.url.path == "/auth"]) == 2
    app.state.pluggy_clients.clear()
    assert client.get(endpoint).status_code == 200
    assert len([call for call in calls if call.url.path == "/auth"]) == 3
