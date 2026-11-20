from __future__ import annotations

import hashlib
import httpx
import pytest
from fastapi import HTTPException
from supreme_common.auth_context import current_context


def test_storage_roundtrip_integrity_and_tenant_boundary(monkeypatch):
    from supreme_common.object_storage import ObjectStorage
    monkeypatch.setenv('SUPABASE_URL', 'https://synthetic.supabase.co')
    monkeypatch.setenv('SUPABASE_SERVICE_ROLE_KEY', 'synthetic-only')
    objects = {}
    def serve(request):
        key = request.url.path.replace('/authenticated', '')
        if request.method == 'POST':
            objects[key] = request.content
            return httpx.Response(200, json={})
        return httpx.Response(200, content=objects[key])
    marker = current_context.set({'organization_id': 'org-a', 'company_id': 'company-a'})
    try:
        with httpx.Client(transport=httpx.MockTransport(serve)) as client:
            store = ObjectStorage('documents-custody', client=client)
            ref = store.put(b'private document')
            assert hashlib.sha256(b'private document').hexdigest() in ref
            assert store.get(ref) == b'private document'
            current_context.set({'organization_id': 'org-b', 'company_id': 'company-a'})
            with pytest.raises(HTTPException) as exc:
                store.get(ref)
            assert exc.value.status_code == 403
            current_context.set({'organization_id': 'org-a', 'company_id': 'company-a'})
            objects[next(iter(objects))] = b'corrupt'
            with pytest.raises(HTTPException) as exc:
                store.get(ref)
            assert exc.value.status_code == 502
    finally:
        current_context.reset(marker)


def test_storage_errors_do_not_expose_provider_body(monkeypatch):
    from supreme_common.object_storage import ObjectStorage
    monkeypatch.setenv('SUPABASE_URL', 'https://synthetic.supabase.co')
    monkeypatch.setenv('SUPABASE_SERVICE_ROLE_KEY', 'synthetic-only')
    marker = current_context.set({'organization_id': 'org', 'company_id': 'company'})
    try:
        with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(500, text='secret'))) as client:
            with pytest.raises(HTTPException) as exc:
                ObjectStorage('nfse-xml', client=client).put(b'xml')
            assert 'secret' not in str(exc.value)
    finally:
        current_context.reset(marker)


def test_existing_object_is_reused_only_when_bytes_match(monkeypatch):
    from supreme_common.object_storage import ObjectStorage
    monkeypatch.setenv('SUPABASE_URL', 'https://synthetic.supabase.co')
    monkeypatch.setenv('SUPABASE_SERVICE_ROLE_KEY', 'synthetic-only')
    objects = {}

    def serve(request):
        key = request.url.path.replace('/authenticated', '')
        if request.method == 'POST':
            if key in objects:
                return httpx.Response(409)
            objects[key] = request.content
            return httpx.Response(201, json={})
        return httpx.Response(200, content=objects[key])

    marker = current_context.set({'organization_id': 'org-a', 'company_id': 'company-a'})
    try:
        with httpx.Client(transport=httpx.MockTransport(serve)) as client:
            store = ObjectStorage('nfse-xml', client=client)
            first = store.put(b'<xml/>')
            assert store.put(b'<xml/>') == first
            objects[next(iter(objects))] = b'<other/>'
            with pytest.raises(HTTPException) as exc:
                store.put(b'<xml/>')
            assert exc.value.status_code == 502
    finally:
        current_context.reset(marker)


def test_signed_url_stays_inside_the_bucket_and_expires_quickly(monkeypatch):
    from supreme_common.object_storage import ObjectStorage
    monkeypatch.setenv('SUPABASE_URL', 'https://synthetic.supabase.co')
    monkeypatch.setenv('SUPABASE_SERVICE_ROLE_KEY', 'synthetic-only')
    seen = {}

    def serve(request):
        seen['body'] = request.content
        return httpx.Response(200, json={'signedURL': '/object/sign/documents-custody/tenant/file?token=1'})

    marker = current_context.set({'organization_id': 'org-a', 'company_id': 'company-a'})
    try:
        with httpx.Client(transport=httpx.MockTransport(serve)) as client:
            store = ObjectStorage('documents-custody', client=client)
            from supreme_common.object_storage import tenant_prefix
            reference = f'supabase://documents-custody/{tenant_prefix()}/{hashlib.sha256(b"doc").hexdigest()}'
            with pytest.raises(ValueError):
                store.signed_url(reference, 0)
            with pytest.raises(ValueError):
                store.signed_url(reference, 301)
            url = store.signed_url(reference, 60)
            assert url.startswith('https://synthetic.supabase.co/storage/v1/object/sign/documents-custody/')
            assert b'"expiresIn":60' in seen['body'] or b'"expiresIn": 60' in seen['body']
            with httpx.Client(transport=httpx.MockTransport(
                lambda request: httpx.Response(200, json={'signedURL': 'https://evil.example/file'})
            )) as client:
                with pytest.raises(HTTPException) as exc:
                    ObjectStorage('documents-custody', client=client).signed_url(reference, 60)
                assert exc.value.status_code == 502
    finally:
        current_context.reset(marker)


def test_missing_tenant_and_network_failures_stay_generic(monkeypatch):
    from supreme_common.object_storage import ObjectStorage
    monkeypatch.setenv('SUPABASE_URL', 'https://synthetic.supabase.co')
    monkeypatch.setenv('SUPABASE_SERVICE_ROLE_KEY', 'synthetic-only')
    with pytest.raises(HTTPException) as exc:
        ObjectStorage('documents-custody', client=httpx.Client()).put(b'doc')
    assert exc.value.status_code == 401
    marker = current_context.set({'organization_id': 'org-a'})
    try:
        with pytest.raises(HTTPException) as exc:
            ObjectStorage('documents-custody', client=httpx.Client()).put(b'doc')
        assert exc.value.status_code == 403
    finally:
        current_context.reset(marker)
    marker = current_context.set({'organization_id': 'org-a', 'company_id': 'company-a'})
    try:
        def fail(request):
            raise httpx.ConnectError('down')
        with httpx.Client(transport=httpx.MockTransport(fail)) as client:
            with pytest.raises(HTTPException) as exc:
                ObjectStorage('documents-custody', client=client).put(b'doc')
            assert exc.value.status_code == 503
            assert 'down' not in str(exc.value.detail)
    finally:
        current_context.reset(marker)
