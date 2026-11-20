"""Private, immutable, tenant-scoped Supabase objects. No credentials reach clients."""
from __future__ import annotations

from hashlib import sha256
import os
import re
from urllib.parse import urlsplit

import httpx
from fastapi import HTTPException
from .auth_context import context

BUCKET_LIMITS = {'documents-custody': 50 * 1024**2, 'nfse-xml': 10 * 1024**2,
                 'tax-audit-workspaces': 50 * 1024**2}


def enabled() -> bool:
    return os.getenv('SUPREME_STORAGE_MODE', 'local') == 'supabase'


def tenant_prefix() -> str:
    claims = context()
    parts = [claims.get('organization_id'), claims.get('company_id')]
    if not all(parts):
        raise HTTPException(403, 'Contexto de organização e empresa obrigatório.')
    return '/'.join(sha256(str(part).encode()).hexdigest() for part in parts)


class ObjectStorage:
    def __init__(self, bucket: str, *, client: httpx.Client | None = None):
        if bucket not in BUCKET_LIMITS:
            raise ValueError('Bucket não autorizado.')
        self.bucket, self.client = bucket, client
        self.base = os.getenv('SUPABASE_URL', '').rstrip('/')
        self.key = os.getenv('SUPABASE_SERVICE_ROLE_KEY', '')
        parsed = urlsplit(self.base)
        if parsed.scheme != 'https' or not parsed.netloc or parsed.path or parsed.query or not self.key:
            raise HTTPException(503, 'Configure o Storage privado no backend.')

    def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        headers = {'Authorization': 'Bearer ' + self.key, 'apikey': self.key}
        headers.update(kwargs.pop('headers', {}))
        try:
            if self.client is not None:
                return self.client.request(method, self.base + '/storage/v1' + path,
                                           headers=headers, timeout=30, **kwargs)
            with httpx.Client(timeout=30, follow_redirects=False) as client:
                return client.request(method, self.base + '/storage/v1' + path, headers=headers, **kwargs)
        except httpx.HTTPError:
            raise HTTPException(503, 'Storage indisponível; tente novamente.') from None

    def _key(self, reference: str) -> str:
        prefix = f'supabase://{self.bucket}/{tenant_prefix()}/'
        if not reference.startswith(prefix) or not re.fullmatch('[a-f0-9]{64}', reference[len(prefix):]):
            raise HTTPException(403, 'Objeto fora do contexto autorizado.')
        return reference.removeprefix(f'supabase://{self.bucket}/')

    def put(self, content: bytes) -> str:
        if len(content) > BUCKET_LIMITS[self.bucket]:
            raise HTTPException(413, 'Arquivo excede o limite do bucket.')
        digest = sha256(content).hexdigest()
        key = tenant_prefix() + '/' + digest
        reference = f'supabase://{self.bucket}/{key}'
        response = self._request('POST', f'/object/{self.bucket}/{key}', content=content,
                                 headers={'Content-Type': 'application/octet-stream', 'x-upsert': 'false'})
        if response.status_code not in {200, 201}:
            # The provider may return 400 or 409 for an existing immutable object.
            # Verify the stored bytes before accepting a retry; never overwrite.
            if response.status_code not in {400, 409} or self.get(reference) != content:
                raise HTTPException(502, 'Falha ao preservar objeto no Storage.')
        return reference

    def get(self, reference: str) -> bytes:
        key = self._key(reference)
        response = self._request('GET', f'/object/authenticated/{self.bucket}/{key}')
        if response.status_code != 200:
            raise HTTPException(502, 'Objeto indisponível no Storage.')
        content = response.content
        if len(content) > BUCKET_LIMITS[self.bucket] or sha256(content).hexdigest() != key.rsplit('/', 1)[1]:
            raise HTTPException(502, 'Integridade do objeto inválida.')
        return content

    def signed_url(self, reference: str, expires: int = 60) -> str:
        key = self._key(reference)
        if not 1 <= expires <= 300:
            raise ValueError('Validade permitida: 1 a 300 segundos.')
        response = self._request('POST', f'/object/sign/{self.bucket}/{key}', json={'expiresIn': expires})
        if response.status_code != 200:
            raise HTTPException(502, 'Falha ao autorizar download.')
        try:
            path = response.json()['signedURL']
            if not isinstance(path, str) or not path.startswith('/object/sign/' + self.bucket + '/'):
                raise ValueError()
        except (KeyError, ValueError, TypeError):
            raise HTTPException(502, 'Resposta inválida do Storage.') from None
        return self.base + '/storage/v1' + path
