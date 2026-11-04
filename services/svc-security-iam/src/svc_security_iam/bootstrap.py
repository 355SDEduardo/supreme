"""Initialize an administrator in this service's configured database (also Docker)."""
import argparse
import getpass
from supreme_common.auth_context import SAFE_ID, hash_password, secret_key
from supreme_common.database import configure_database
from .app import create_app
from .auth import Identity
from .database import Base

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--email',required=True)
    parser.add_argument('--organization',required=True)
    args=parser.parse_args()
    if not SAFE_ID.fullmatch(args.organization):
        parser.error('Identificador de organização inválido.')
    secret_key()
    app=create_app()
    configure_database(app,Base)
    Base.metadata.create_all(app.state.engine)
    with app.state.sessions() as db:
        if db.query(Identity).filter(Identity.email==args.email.lower()).first():
            parser.error('Usuário já existe; credenciais preservadas.')
        password=getpass.getpass('Senha inicial (mínimo 12 caracteres): ')
        if len(password)<12 or password!=getpass.getpass('Repita a senha: '):
            parser.error('Senha curta ou confirmação incompatível.')
        db.add(Identity(email=args.email.lower(),organization_id=args.organization,
            password_hash=hash_password(password),role='super_admin',company_ids='[]'))
        db.commit()
    app.state.engine.dispose()
    print('Administrador criado. Configure o MFA no primeiro acesso.')

if __name__=='__main__':
    main()
