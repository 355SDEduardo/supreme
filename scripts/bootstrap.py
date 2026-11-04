"""Generate local secrets and create an explicit initial IAM administrator."""
import argparse
import getpass
import os
from pathlib import Path
import secrets

ROOT = Path(__file__).resolve().parents[1]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--email')
    parser.add_argument('--organization')
    parser.add_argument('--secrets-only',action='store_true')
    args = parser.parse_args()
    from dotenv import load_dotenv
    env = ROOT / '.env'
    if not env.exists():
        with env.open('x', encoding='utf-8') as output:
            output.write('SUPREME_ENV=development\nSECRET_KEY=' + secrets.token_hex(32) +
                         '\nMASTER_ENCRYPTION_KEY=' + secrets.token_hex(32) + '\n')
    load_dotenv(env)
    from scripts.service_catalog import SERVICES
    from scripts.generate_compose import DOMAINS
    missing = {}
    for key in ['POSTGRES_PASSWORD'] + ['DB_'+slug.upper().replace('-','_')+'_PASSWORD' for slug,_,_ in SERVICES if slug in DOMAINS]:
        if not os.getenv(key):
            missing[key] = secrets.token_hex(32)
    if missing:
        with env.open('a',encoding='utf-8') as output:
            output.write('\n' + ''.join(f'{key}={value}\n' for key,value in missing.items()))
        os.environ.update(missing)
    if args.secrets_only:
        print('Segredos locais preparados em .env; valores existentes preservados.')
        return
    if not args.email or not args.organization:
        parser.error('Informe --email e --organization para criar o administrador.')
    from supreme_common.auth_context import SAFE_ID, hash_password
    from svc_security_iam.app import create_app
    from svc_security_iam.auth import Identity
    from svc_security_iam.database import Base
    from supreme_common.database import configure_database
    if not SAFE_ID.fullmatch(args.organization):
        parser.error('Use organização alfanumérica, com hífen ou sublinhado.')
    app = create_app()
    configure_database(app, Base)
    Base.metadata.create_all(app.state.engine)
    with app.state.sessions() as db:
        if db.query(Identity).filter(Identity.email == args.email.lower()).first():
            parser.error('Usuário já existe; nenhuma credencial foi alterada.')
        password = getpass.getpass('Senha inicial (mínimo 12 caracteres): ')
        if len(password) < 12:
            parser.error('A senha deve ter pelo menos 12 caracteres.')
        if password != getpass.getpass('Repita a senha: '):
            parser.error('As senhas não coincidem.')
        db.add(Identity(email=args.email.lower(), organization_id=args.organization,
                        password_hash=hash_password(password), role='super_admin', company_ids='[]'))
        db.commit()
    print('Administrador criado. Inicie o ambiente e configure o MFA no portal.')

if __name__ == '__main__':
    main()
