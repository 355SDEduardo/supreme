"""JWT validation and request tenant context, applied independently in every service."""
from contextvars import ContextVar
from contextlib import contextmanager
from datetime import timedelta
import base64
import hashlib
import hmac
import os
import re
import secrets
import time
import uuid
import jwt
from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

current_context = ContextVar('supreme_context', default=None)
SAFE_ID = re.compile(r'^[a-zA-Z0-9_-]{1,100}$')

def secret_key():
    key = os.environ.get('SECRET_KEY', '')
    if len(key) < 32:
        raise RuntimeError('Configure SECRET_KEY com pelo menos 32 caracteres (scripts/bootstrap.py).')
    return key

def hash_password(password):
    salt = secrets.token_bytes(16)
    key = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 600_000)
    return base64.b64encode(salt + key).decode()

def verify_password(password, hashed):
    try:
        data = base64.b64decode(hashed, validate=True)
        return len(data) == 48 and hmac.compare_digest(data[16:], hashlib.pbkdf2_hmac('sha256', password.encode(), data[:16], 600_000))
    except (ValueError, TypeError):
        return False

def create_access_token(data, expires_delta: timedelta | None = None):
    claims = dict(data)
    now = int(time.time())
    claims.update(iat=now, exp=now + int((expires_delta or timedelta(minutes=30)).total_seconds()),
                  iss='supreme-iam', aud='supreme', jti=str(uuid.uuid4()))
    claims['sub'] = str(claims.get('sub') or claims.get('user_id', ''))
    claims.setdefault('session_id', str(uuid.uuid4()))
    return jwt.encode(claims, secret_key(), algorithm='HS256')

def decode_access_token(token):
    try:
        claims = jwt.decode(token, secret_key(), algorithms=['HS256'], audience='supreme', issuer='supreme-iam',
                            options={'require': ['exp', 'iat', 'sub', 'organization_id', 'jti']})
        for field in ('sub', 'organization_id'):
            if not SAFE_ID.fullmatch(claims[field]):
                return None
        if claims.get('company_id') and not SAFE_ID.fullmatch(claims['company_id']):
            return None
        return claims
    except (jwt.PyJWTError, TypeError, ValueError, KeyError):
        return None

def context():
    claims = current_context.get()
    if not claims:
        raise HTTPException(401, 'Autenticação necessária.')
    return claims

def tenant_path(root):
    from pathlib import Path
    claims = context()
    company = claims.get('company_id')
    if not company:
        raise HTTPException(409, 'Selecione uma empresa.')
    path = Path(root) / claims['organization_id'] / company
    path.mkdir(parents=True, exist_ok=True)
    return path

def require_role(*roles):
    if context().get('role') not in roles:
        raise HTTPException(403, 'Perfil sem permissão para esta operação.')

@contextmanager
def delegated_company(company_id):
    """Use only after verifying the company against the caller's organization."""
    require_role('super_admin','supervisor')
    if not SAFE_ID.fullmatch(company_id):
        raise HTTPException(422,'Identificador de empresa inválido.')
    claims = {**context(), 'company_id':company_id}
    claims['_token'] = create_access_token({k:v for k,v in claims.items() if not k.startswith('_')})
    marker = current_context.set(claims)
    try:
        yield
    finally:
        current_context.reset(marker)

async def enforce_request_context(request: Request):
    """Check identifiers after routing/body parsing, before business side effects."""
    if request.url.path in {'/health', '/api/health', '/api/status', '/security/auth/token', '/security/auth/mfa-login'}:
        return
    claims = context()
    if not claims.get('mfa_verified') and not request.url.path.startswith(('/security/mfa/', '/security/auth/')):
        raise HTTPException(403, 'Configure e verifique o MFA antes de acessar dados operacionais.')
    if request.app.title not in {'svc-companies', 'svc-security-iam'} and not claims.get('company_id'):
        raise HTTPException(409, 'Selecione uma empresa antes de acessar dados operacionais.')
    if request.method not in {'GET','HEAD','OPTIONS'}:
        if request.url.path.startswith(('/companies','/cockpit','/certificates')):
            require_role('super_admin','supervisor')
    if request.url.path.startswith('/analytics'):
        require_role('super_admin','supervisor','analyst','service')
    expected = {'organization_id': claims['organization_id'], 'company_id': claims.get('company_id')}
    values = dict(request.query_params)
    values.update(request.path_params)
    content_type = request.headers.get('content-type', '')
    if 'application/json' in content_type:
        try:
            body = await request.json()
        except ValueError:
            body = {}
        if isinstance(body, dict):
            values.update(body)
    elif 'multipart/form-data' in content_type or 'application/x-www-form-urlencoded' in content_type:
        values.update(await request.form())
    for key, value in expected.items():
        if values.get(key) and values[key] != value:
            raise HTTPException(403, 'Contexto de empresa/organização incompatível com a sessão.')
    for key in ('user_id', 'actor_user_id', 'uploaded_by', 'approved_by', 'reconciled_by', 'created_by', 'created_by_user_id', 'approver_user_id', 'sender_id'):
        if values.get(key) and values[key] != claims['sub']:
            raise HTTPException(403, 'Identidade do operador incompatível com a sessão.')
    if values.get('user_role') and values['user_role'] != claims.get('role'):
        raise HTTPException(403, 'Perfil informado não corresponde à sessão.')
    is_authorized_batch = request.app.title in {'svc-companies','svc-obligations'} and claims.get('role') in {'super_admin','supervisor'}
    if values.get('company_ids') and not is_authorized_batch and any(c != claims.get('company_id') for c in values['company_ids']):
        raise HTTPException(403, 'Operação em lote requer o contexto das empresas selecionadas.')

class AuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, public=()):
        super().__init__(app)
        self.public = {'/health', '/api/health', '/api/status', '/docs', '/docs/oauth2-redirect', '/openapi.json', '/redoc', *public}

    async def dispatch(self, request, call_next):
        correlation = request.headers.get('x-correlation-id', '')
        if not SAFE_ID.fullmatch(correlation):
            correlation = str(uuid.uuid4())
        bearer = request.headers.get('authorization', '')
        token = bearer[7:] if bearer.startswith('Bearer ') else request.cookies.get('supreme_session', '')
        claims = decode_access_token(token) if token else None
        if request.url.path.endswith('/security/auth/token'):
            claims = None
        if request.url.path not in self.public and not claims:
            return JSONResponse({'detail': 'Token ausente, inválido ou expirado.'}, 401, headers={'X-Correlation-ID': correlation})
        if claims and claims.get('role') == 'viewer' and request.method not in {'GET', 'HEAD', 'OPTIONS'} and not request.url.path.endswith('/platform/logout'):
            return JSONResponse({'detail': 'Perfil somente leitura.'}, 403)
        if token and not bearer and request.method not in {'GET', 'HEAD', 'OPTIONS'}:
            if request.headers.get('x-supreme-csrf') != '1':
                return JSONResponse({'detail': 'Cabeçalho CSRF obrigatório.'}, 403)
            origin = request.headers.get('origin')
            if origin and origin != str(request.base_url).rstrip('/'):
                return JSONResponse({'detail': 'Origem não autorizada.'}, 403)
        if claims:
            claims = {**claims, 'correlation_id': correlation, '_token': token}
        marker = current_context.set(claims)
        request.state.auth = claims
        try:
            response = await call_next(request)
            if claims and request.url.path not in self.public and request.app.title != 'Supreme Gateway':
                from .events import publish
                publish('AuditLogRecorded', {'action': request.method + ' ' + request.url.path,
                    'status_code': response.status_code, 'ip_address': request.client.host if request.client else 'internal'})
        finally:
            current_context.reset(marker)
        response.headers.update({'X-Correlation-ID': correlation, 'X-Content-Type-Options': 'nosniff',
                                 'X-Frame-Options': 'SAMEORIGIN', 'Referrer-Policy': 'no-referrer', 'Cache-Control': 'no-store'})
        return response
