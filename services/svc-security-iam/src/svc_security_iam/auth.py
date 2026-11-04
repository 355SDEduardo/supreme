from datetime import datetime, timezone
import time
import uuid
import pyotp
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import Column, String, Integer, Boolean
from sqlalchemy.orm import Session
from supreme_common.auth_context import context, create_access_token, hash_password, verify_password, require_role
from .database import Base, get_db
from .crypto_vault import encrypt_string, decrypt_string

class Identity(Base):
    __tablename__ = 'iam_users'
    id = Column(String(100), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(100), nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(30), nullable=False, default='analyst')
    company_ids = Column(String, nullable=False, default='[]')
    active = Column(Boolean, default=True)
    mfa_secret_encrypted = Column(String, nullable=True)
    mfa_enabled = Column(Boolean, default=False)
    last_totp_counter = Column(Integer, default=-1)
    failed_attempts = Column(Integer, default=0)
    locked_until = Column(Integer, default=0)

class Login(BaseModel):
    email: str
    password: str = Field(min_length=1, max_length=1024)
    totp: str | None = None

class UserCreate(BaseModel):
    email: str
    password: str = Field(min_length=12, max_length=1024)
    role: str = 'analyst'
    company_ids: list[str] = []

auth_router = APIRouter(prefix='/security/auth', tags=['IAM'])

def token_for(user):
    import json
    return create_access_token({'sub': user.id, 'organization_id': user.organization_id,
        'role': user.role, 'company_ids': json.loads(user.company_ids), 'company_id': None,
        'mfa_verified': bool(user.mfa_enabled)})

@auth_router.post('/token')
def login(payload: Login, db: Session = Depends(get_db)):
    # This is the only unscoped read: credentials establish the tenant context.
    user = db.query(Identity).filter(Identity.email == payload.email.lower()).first()
    if not user or not user.active or user.locked_until > time.time():
        raise HTTPException(401, 'Credenciais inválidas ou acesso temporariamente bloqueado.')
    if not verify_password(payload.password, user.password_hash):
        user.failed_attempts += 1
        if user.failed_attempts >= 5:
            user.locked_until = int(time.time()) + 300
        db.commit()
        raise HTTPException(401, 'Credenciais inválidas ou acesso temporariamente bloqueado.')
    if user.mfa_enabled:
        if not payload.totp:
            raise HTTPException(401, 'Código MFA obrigatório.')
        validate_totp(user, payload.totp, db)
    user.failed_attempts = 0
    db.commit()
    return {'access_token': token_for(user), 'token_type': 'bearer', 'expires_in': 1800,
            'mfa_setup_required': not user.mfa_enabled}

def validate_totp(user, token, db):
    if not user.mfa_secret_encrypted:
        raise HTTPException(400, 'MFA não configurado.')
    totp = pyotp.TOTP(decrypt_string(user.mfa_secret_encrypted))
    now_counter = int(time.time()) // 30
    for counter in range(now_counter - 1, now_counter + 2):
        if counter > user.last_totp_counter and totp.at(counter * 30) == token:
            from sqlalchemy import update
            changed = db.connection().execute(update(Identity.__table__).where(
                Identity.__table__.c.id == user.id,
                Identity.__table__.c.organization_id == user.organization_id,
                Identity.__table__.c.last_totp_counter < counter).values(last_totp_counter=counter))
            if changed.rowcount != 1:
                raise HTTPException(400, 'Código MFA já utilizado.')
            user.last_totp_counter = counter
            return
    user.failed_attempts += 1
    if user.failed_attempts >= 5:
        user.locked_until = int(time.time()) + 300
    db.commit()
    raise HTTPException(400, 'Código MFA inválido, expirado ou reutilizado.')

@auth_router.post('/users', status_code=201)
def create_user(payload: UserCreate, db: Session = Depends(get_db)):
    import json
    require_role('super_admin')
    if payload.role not in {'super_admin', 'supervisor', 'analyst', 'bpo_operator', 'client_user', 'viewer'}:
        raise HTTPException(422, 'Perfil inválido.')
    if db.query(Identity).filter(Identity.email == payload.email.lower()).first():
        raise HTTPException(409, 'Usuário já cadastrado.')
    user = Identity(email=payload.email.lower(), password_hash=hash_password(payload.password),
                    organization_id=context()['organization_id'], role=payload.role,
                    company_ids=json.dumps(payload.company_ids))
    db.add(user)
    db.commit()
    return {'id': user.id, 'email': user.email, 'role': user.role}

@auth_router.get('/users/{identity_id}')
def user_details(identity_id: str, db: Session = Depends(get_db)):
    require_role('super_admin','supervisor')
    user=db.query(Identity).filter(Identity.id==identity_id,Identity.active.is_(True)).first()
    if not user:
        raise HTTPException(404,'Usuário não encontrado nesta organização.')
    return {'id':user.id,'email':user.email,'role':user.role,'organization_id':user.organization_id}

mfa_router = APIRouter(prefix='/security/mfa', tags=['MFA'])

@mfa_router.post('/setup')
def setup(db: Session = Depends(get_db)):
    user = db.query(Identity).filter(Identity.id == context()['sub']).first()
    if not user:
        raise HTTPException(404, 'Usuário não encontrado.')
    if user.mfa_enabled:
        raise HTTPException(409, 'MFA já habilitado.')
    secret = pyotp.random_base32()
    user.mfa_secret_encrypted = encrypt_string(secret)
    db.commit()
    return {'secret': secret, 'manual_code': secret,
            'otpauth_url': pyotp.TOTP(secret).provisioning_uri(user.email, issuer_name='Supreme')}

class MfaToken(BaseModel):
    token: str = Field(pattern=r'^\d{6}$')

@mfa_router.post('/verify')
def verify(payload: MfaToken, db: Session = Depends(get_db)):
    user = db.query(Identity).filter(Identity.id == context()['sub']).with_for_update().first()
    if not user:
        raise HTTPException(404, 'Usuário não encontrado.')
    validate_totp(user, payload.token, db)
    user.mfa_enabled = True
    db.commit()
    return {'verified': True, 'access_token': token_for(user), 'token_type': 'bearer'}
