from __future__ import annotations

import asyncio
import json

import httpx
import pytest
from fastapi import HTTPException
from supreme_common.auth_context import current_context

from svc_bank_reconciliation.pluggy_client import PluggyClient, PluggySettings


@pytest.fixture(autouse=True)
def caller():
    marker = current_context.set({"correlation_id": "synthetic-correlation"})
    yield
    current_context.reset(marker)


def client(handler) -> PluggyClient:
    return PluggyClient(
        PluggySettings(client_id="synthetic", client_secret="synthetic"),
        transport=httpx.MockTransport(handler),
    )


@pytest.mark.asyncio
async def test_cursor_is_decoded_once_and_filters_are_preserved():
    requests = []

    def handler(request):
        if request.url.path == "/auth":
            return httpx.Response(200, json={"apiKey": "private-key"})
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(
                200,
                json={
                    "results": [{"id": "first"}],
                    "next": "?accountId=account&after=a%2Bb%3D%3D",
                },
            )
        assert request.url.params["after"] == "a+b=="
        assert request.url.params["accountId"] == "account"
        assert request.url.params["dateFrom"] == "2026-10-01"
        assert request.url.params["dateTo"] == "2026-10-31"
        return httpx.Response(200, json={"results": [{"id": "second"}], "next": None})

    result = await client(handler).transactions("account", "2026-10-01", "2026-10-31")
    assert [row["id"] for row in result] == ["first", "second"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "cursor",
    [
        "https://evil.test/?after=x",
        "?accountId=other&after=x",
        "?dateFrom=2020-01-01&after=x",
        "?after=",
        "?after=x&after=y",
        "?after=x#fragment",
        123,
    ],
)
async def test_cursor_cannot_change_scope_or_destination(cursor):
    def handler(request):
        if request.url.path == "/auth":
            return httpx.Response(200, json={"apiKey": "private-key"})
        return httpx.Response(200, json={"results": [], "next": cursor})

    with pytest.raises(HTTPException) as caught:
        await client(handler).transactions("account", "2026-10-01", "2026-10-31")
    assert caught.value.status_code == 502


@pytest.mark.asyncio
async def test_repeated_cursor_is_bounded():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(
            200,
            json={"apiKey": "private-key"}
            if request.url.path == "/auth"
            else {
                "results": [],
                "next": "?after=repeated",
            },
        )

    with pytest.raises(HTTPException) as caught:
        await client(handler).transactions("account", "2026-10-01", "2026-10-31")
    assert caught.value.status_code == 502 and len(calls) == 3


@pytest.mark.asyncio
async def test_numbered_pages_are_read_and_limited():
    def handler(request):
        if request.url.path == "/auth":
            return httpx.Response(200, json={"apiKey": "private-key"})
        page = int(request.url.params["page"])
        return httpx.Response(200, json={"results": [{"id": page}], "page": page, "totalPages": 2})

    provider = client(handler)
    assert await provider.list_all("/accounts", {"itemId": "item"}, limit=2) == [{"id": 1}, {"id": 2}]
    with pytest.raises(HTTPException) as caught:
        await provider.list_all("/accounts", {"itemId": "item"}, limit=1)
    assert caught.value.status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,expected", [(400, 502), (401, 503), (403, 503), (404, 404), (429, 429), (500, 502), (302, 502)]
)
async def test_provider_failures_are_sanitized(status, expected):
    def handler(request):
        if request.url.path == "/auth":
            return httpx.Response(200, json={"apiKey": "private-key"})
        return httpx.Response(status, json={"secret": "do-not-expose"}, headers={"Retry-After": "15"})

    with pytest.raises(HTTPException) as caught:
        await client(handler).request("GET", "/accounts")
    assert caught.value.status_code == expected
    assert "do-not-expose" not in caught.value.detail
    if status == 429:
        assert caught.value.headers == {"Retry-After": "15"}


@pytest.mark.asyncio
@pytest.mark.parametrize("error,expected", [(httpx.ReadTimeout, 504), (httpx.ConnectError, 502)])
async def test_network_failures(error, expected):
    def handler(request):
        raise error("private-provider-data", request=request)

    with pytest.raises(HTTPException) as caught:
        await client(handler).request("GET", "/accounts")
    assert caught.value.status_code == expected
    assert "private-provider-data" not in caught.value.detail


@pytest.mark.asyncio
async def test_api_key_is_reused_and_refreshed_once_for_get():
    auth_calls = 0
    expired = False

    def handler(request):
        nonlocal auth_calls
        if request.url.path == "/auth":
            auth_calls += 1
            assert json.loads(request.content) == {"clientId": "synthetic", "clientSecret": "synthetic"}
            return httpx.Response(200, json={"apiKey": f"key-{auth_calls}"})
        if expired and request.headers["X-API-KEY"] == "key-1":
            return httpx.Response(401)
        return httpx.Response(200, json={"results": []})

    provider = client(handler)
    await asyncio.gather(*(provider.request("GET", "/accounts") for _ in range(5)))
    assert auth_calls == 1
    expired = True
    await provider.request("GET", "/accounts")
    assert auth_calls == 2


@pytest.mark.asyncio
async def test_mutations_are_not_retried_on_auth_failure():
    mutations = 0

    def handler(request):
        nonlocal mutations
        if request.url.path == "/auth":
            return httpx.Response(200, json={"apiKey": "private-key"})
        mutations += 1
        return httpx.Response(401)

    with pytest.raises(HTTPException):
        await client(handler).request("POST", "/connect_token", json={})
    assert mutations == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [b"not-json", b"[]", b'{"apiKey":null}'])
async def test_invalid_auth_response(body):
    with pytest.raises(HTTPException) as caught:
        await client(lambda _: httpx.Response(200, content=body)).request("GET", "/accounts")
    assert caught.value.status_code == 502


@pytest.mark.asyncio
async def test_decimal_json_and_response_size_limit(monkeypatch):
    from decimal import Decimal
    from svc_bank_reconciliation import pluggy_client

    def handler(request):
        return httpx.Response(
            200,
            content=(
                b'{"apiKey":"private-key"}'
                if request.url.path == "/auth"
                else b'{"balance":90071992547409.93}'
            ),
        )

    provider = client(handler)
    assert (await provider.request("GET", "/accounts"))["balance"] == Decimal("90071992547409.93")
    monkeypatch.setattr(pluggy_client, "MAX_RESPONSE_BYTES", 5)
    with pytest.raises(HTTPException) as caught:
        await provider.request("GET", "/accounts")
    assert caught.value.status_code == 502
