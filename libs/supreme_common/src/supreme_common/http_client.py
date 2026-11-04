import os
import httpx
from fastapi import HTTPException
from .auth_context import context

async def service_request(service, method, path, **kwargs):
    claims = context()
    name = 'SVC_' + service.upper().replace('-', '_') + '_URL'
    url = os.environ[name]
    headers = {'Authorization': 'Bearer ' + claims['_token'], 'X-Correlation-ID': claims['correlation_id']}
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=False, trust_env=False) as client:
            response = await client.request(method, url + path, headers=headers, **kwargs)
    except httpx.HTTPError as exc:
        raise HTTPException(503, f'Serviço {service} indisponível.') from exc
    if response.status_code >= 400:
        raise HTTPException(response.status_code, f'Serviço {service}: operação recusada.')
    return response
