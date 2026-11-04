"""API gateway with explicit route ownership and same-origin application shell."""
from contextlib import asynccontextmanager
from pathlib import Path
import os
import re
import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.background import BackgroundTask
from supreme_common.auth_context import AuthMiddleware, context
from supreme_common.uploads import RequestLimitMiddleware
from scripts.service_catalog import SERVICES

ROOT = Path(__file__).resolve().parents[1]
BY_ROUTE = {route: (slug, port) for slug,route,port in SERVICES}

def target(path):
    """Gateway paths map to native service APIs, without exposing internal routes."""
    parts = path.strip('/').split('/')
    prefix, rest = parts[0], '/'.join(parts[1:])
    if prefix == 'companies' and re.fullmatch(r'[^/]+/obligations', rest):
        return 'obligations', '/companies/' + rest
    if prefix == 'auth' and rest == 'switch-company-context':
        return 'companies', '/auth/' + rest
    aliases = {'certificates': 'security', 'cockpit': 'companies', 'tasks': 'obligations',
               'bank-accounts': 'reconciliation', 'reconciliations': 'reconciliation'}
    route = aliases.get(prefix, prefix)
    if route not in BY_ROUTE:
        raise HTTPException(404, 'Serviço não encontrado.')
    slug, _ = BY_ROUTE[route]
    if prefix == 'pdf' and rest == 'status':
        native = '/api/status'
    elif prefix in {'nfse', 'tax-audit'}:
        native = '/api' + ('/' + rest if rest else '')
    elif prefix == 'ai':
        native = '/api/v1/ai' + ('/' + rest if rest else '')
    elif prefix == 'reconciliation':
        native = '/reconciliations' + ('/' + rest if rest else '')
    else:
        native = '/' + prefix + ('/' + rest if rest else '')
    return slug, native

def service_url(slug):
    port = next(port for name,_,port in SERVICES if name == slug)
    return os.getenv('SVC_' + slug.upper().replace('-','_') + '_URL', f'http://127.0.0.1:{port}').rstrip('/')

def public_path(slug, native):
    route = next(route for name,route,_ in SERVICES if name == slug)
    if native in {'/health', '/api/health', '/api/status'} or native.startswith('/internal/'):
        return None
    if slug in {'nfse-engine','federal-tax-audit'}:
        return '/api/v1/' + route + native.removeprefix('/api')
    if slug == 'accounting-ai':
        return native
    return '/api/v1' + native

def rewrite_refs(value, prefix):
    if isinstance(value, dict):
        return {key: ('#/components/schemas/' + prefix + item.rsplit('/',1)[1] if key == '$ref' and item.startswith('#/components/schemas/') else rewrite_refs(item, prefix)) for key,item in value.items()}
    if isinstance(value, list):
        return [rewrite_refs(item,prefix) for item in value]
    return value

def create_app(*, transport=None):
    @asynccontextmanager
    async def lifespan(app):
        from supreme_common.auth_context import secret_key
        secret_key()
        async with httpx.AsyncClient(timeout=httpx.Timeout(120, connect=5), follow_redirects=False,
                                     trust_env=False, transport=transport) as client:
            app.state.http = client
            yield
    app = FastAPI(title='Supreme Gateway', openapi_url=None, docs_url=None, redoc_url=None, lifespan=lifespan)
    app.add_middleware(RequestLimitMiddleware)
    app.add_middleware(AuthMiddleware, public={
        '/', '/app', '/assets/app.js', '/assets/style.css',
        '/assets/api.js', '/assets/charts.js', '/assets/retencoes.js',
        '/api/v1/security/auth/token'
    })

    @app.middleware('http')
    async def browser_security(request, call_next):
        response = await call_next(request)
        response.headers['Content-Security-Policy'] = ("default-src 'self'; script-src 'self' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; img-src 'self' data: https://fastapi.tiangolo.com; "
            "connect-src 'self'; frame-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'self'; form-action 'self'")
        if os.getenv('SUPREME_ENV') == 'production':
            response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
        return response

    @app.get('/health')
    async def health():
        return {'status': 'ok', 'service': 'supreme-gateway'}

    @app.get('/api/v1/platform/session')
    async def session():
        return {key: value for key,value in context().items() if key in {'sub','organization_id','company_id','role','mfa_verified'}}

    @app.post('/api/v1/platform/logout')
    async def logout():
        response = JSONResponse({'status': 'signed_out'})
        response.delete_cookie('supreme_session', path='/')
        return response

    @app.get('/api/v1/platform/health')
    async def health_all():
        import asyncio
        async def check(slug, route, port):
            try:
                response = await app.state.http.get(service_url(slug) + '/health', timeout=3)
                return {'service': slug, 'route': route, 'port': port, 'available': response.status_code == 200}
            except httpx.HTTPError:
                return {'service': slug, 'route': route, 'port': port, 'available': False}
        return {'services': await asyncio.gather(*(check(*service) for service in SERVICES))}

    @app.get('/api/openapi.json')
    async def openapi():
        import asyncio
        async def schema(slug):
            try:
                response = await app.state.http.get(service_url(slug) + '/openapi.json', timeout=5)
                response.raise_for_status()
                return slug, response.json()
            except (httpx.HTTPError, ValueError):
                return slug, None
        result = {'openapi': '3.1.0', 'info': {'title': 'Supreme APIs', 'version': '1.0.0'},
                  'paths': {}, 'components': {'schemas': {}}, 'x-unavailable-services': []}
        for slug, schema in await asyncio.gather(*(schema(slug) for slug,_,_ in SERVICES)):
            if schema is None:
                result['x-unavailable-services'].append(slug)
                continue
            prefix = slug.replace('-','_') + '_'
            for path, methods in schema.get('paths', {}).items():
                mapped = public_path(slug, path)
                if mapped:
                    result['paths'][mapped] = rewrite_refs(methods, prefix)
            result['components']['schemas'].update({prefix + name: rewrite_refs(value, prefix) for name,value in schema.get('components', {}).get('schemas', {}).items()})
        return result

    @app.get('/docs')
    async def docs():
        return get_swagger_ui_html(openapi_url='/api/openapi.json', title='Supreme APIs')

    @app.api_route('/api/v1/{path:path}', methods=['GET','POST','PUT','PATCH','DELETE','HEAD','OPTIONS'])
    async def proxy(path: str, request: Request):
        slug, native = target(path)
        headers = {key: value for key,value in request.headers.items() if key.lower() in {'content-type','accept','x-correlation-id','x-supreme-csrf'}}
        if request.state.auth:
            headers['Authorization'] = 'Bearer ' + request.state.auth['_token']
            headers['X-Correlation-ID'] = request.state.auth['correlation_id']
        url = service_url(slug) + native
        try:
            outgoing = app.state.http.build_request(request.method, url, params=request.query_params, headers=headers, content=await request.body())
            upstream = await app.state.http.send(outgoing, stream=True)
        except httpx.TimeoutException as exc:
            raise HTTPException(504, 'Tempo de resposta do serviço excedido.') from exc
        except httpx.HTTPError as exc:
            raise HTTPException(503, f'Serviço {slug} indisponível.') from exc
        if native in {'/security/auth/token', '/security/mfa/verify', '/auth/switch-company-context'} and upstream.status_code == 200:
            await upstream.aread()
            data = upstream.json()
            response = JSONResponse(data)
            if token := data.get('access_token'):
                response.set_cookie('supreme_session', token, httponly=True,
                    secure=os.getenv('SUPREME_ENV') == 'production', samesite='strict', max_age=1800, path='/')
            await upstream.aclose()
            return response
        response_headers = {key:value for key,value in upstream.headers.items() if key.lower() in {'content-type','content-disposition','content-length','content-encoding','x-correlation-id'}}
        if upstream.is_stream_consumed:
            response_headers = {key:value for key,value in response_headers.items() if key.lower() not in {'content-encoding','content-length'}}
            return Response(upstream.content, status_code=upstream.status_code, headers=response_headers)
        return StreamingResponse(upstream.aiter_raw(), status_code=upstream.status_code, headers=response_headers,
                                 background=BackgroundTask(upstream.aclose))

    @app.get('/')
    @app.get('/app')
    async def index():
        return FileResponse(ROOT / 'frontend/index.html')

    app.mount('/assets', StaticFiles(directory=ROOT/'frontend/assets', check_dir=False), name='assets')
    return app

app = create_app()
