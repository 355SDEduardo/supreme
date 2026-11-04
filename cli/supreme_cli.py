"""Unified CLI: gateway operations plus compatible offline NF-e batch commands."""
import argparse
from contextlib import ExitStack
import getpass
import json
import os
from pathlib import Path
import sys
import httpx

def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == 'nfe':
        from .nfe_compat import main as nfe_main
        previous = sys.argv
        try:
            sys.argv = ['supreme nfe', *argv[1:]]
            return nfe_main()
        finally:
            sys.argv = previous
    parser = argparse.ArgumentParser(prog='supreme', description='Supreme: audit, nfse, nfe, pdf e APIs')
    parser.add_argument('--url', default=os.getenv('SUPREME_GATEWAY_URL', 'http://127.0.0.1:8080'))
    commands = parser.add_subparsers(dest='command', required=True)
    login = commands.add_parser('login')
    login.add_argument('--email', required=True)
    login.add_argument('--totp')
    audit = commands.add_parser('audit')
    audit.add_argument('--action', choices=['summary','segregate','crosscheck-pis','crosscheck-irpj','missing-notes','darfs','simulate','full'], default='summary')
    audit.add_argument('--json', action='store_true')
    audit.add_argument('--presuncao', type=float, default=32)
    audit.add_argument('--multa', type=float, default=75)
    audit.add_argument('--selic', type=float, default=9.5)
    audit.add_argument('--output', type=Path)
    nfse = commands.add_parser('nfse')
    nfse.add_argument('files', nargs='*', type=Path)
    nfse.add_argument('--mode', choices=['nacional_strict','multi_layout_audit'], default='multi_layout_audit')
    nfse.add_argument('--samples', action='store_true')
    nfse.add_argument('--export', choices=['json','excel','csv'])
    nfse.add_argument('--output', type=Path)
    pdf = commands.add_parser('pdf')
    pdf.add_argument('operation', choices=['merge','split','organize','rotate','repair','number'])
    pdf.add_argument('files', nargs='+', type=Path)
    pdf.add_argument('--output', required=True, type=Path)
    pdf.add_argument('--field', action='append', default=[], help='Campo multipart chave=valor; repetível')
    request = commands.add_parser('request')
    request.add_argument('path')
    request.add_argument('--method', default='GET', choices=['GET','POST','PATCH','PUT','DELETE'])
    request.add_argument('--body', type=Path)
    request.add_argument('--output', type=Path)
    args = parser.parse_args(argv)
    if getattr(args,'output',None) and any(args.output.resolve() == path.resolve() for path in getattr(args,'files',[])):
        parser.error('O arquivo de saída não pode substituir um arquivo de entrada.')
    token = os.getenv('SUPREME_TOKEN', '')
    headers = {'Authorization': 'Bearer ' + token} if token else {}
    try:
        with httpx.Client(base_url=args.url, headers=headers, timeout=120, trust_env=False) as client, ExitStack() as stack:
            if args.command == 'login':
                response = client.post('/api/v1/security/auth/token',json={'email':args.email,'password':getpass.getpass('Senha: '),'totp':args.totp})
            elif args.command == 'audit':
                paths = {'summary':'audit','full':'audit','segregate':'documents','crosscheck-pis':'crosscheck/monthly','crosscheck-irpj':'crosscheck/quarterly','missing-notes':'audit','darfs':'darfs'}
                response = client.post('/api/v1/tax-audit/simulate',json={'presuncao_pct':args.presuncao,'multa_oficio_pct':args.multa,'taxa_selic_pct':args.selic}) if args.action == 'simulate' else client.get('/api/v1/tax-audit/'+paths[args.action])
            elif args.command == 'nfse':
                if args.export:
                    if args.export != 'json' and not args.output:
                        parser.error('--output é obrigatório para exportações binárias.')
                    response = client.get('/api/v1/nfse/export/'+args.export)
                elif args.samples:
                    response = client.post('/api/v1/nfse/load-samples')
                else:
                    if not args.files:
                        parser.error('Informe XMLs/ZIPs, --samples ou --export.')
                    uploads = [('files',(path.name,stack.enter_context(path.open('rb')))) for path in args.files]
                    response = client.post('/api/v1/nfse/upload',params={'mode':args.mode},files=uploads)
            elif args.command == 'pdf':
                field = 'files' if args.operation == 'merge' else 'file'
                uploads = [(field,(path.name,stack.enter_context(path.open('rb')),'application/pdf')) for path in args.files]
                data = dict(item.split('=',1) for item in args.field)
                response = client.post('/api/v1/pdf/'+args.operation,files=uploads,data=data)
            else:
                if not args.path.startswith('/api/v1/'):
                    parser.error('Use um caminho iniciado por /api/v1/.')
                response = client.request(args.method,args.path,json=json.loads(args.body.read_text(encoding='utf-8')) if args.body else None)
            response.raise_for_status()
            if getattr(args,'output',None):
                args.output.write_bytes(response.content)
                print('Resultado salvo em '+str(args.output),file=sys.stderr)
            else:
                print(json.dumps(response.json(),ensure_ascii=False,indent=2))
        return 0
    except (httpx.HTTPError, OSError, ValueError) as exc:
        print('Erro: '+str(exc),file=sys.stderr)
        return 1

if __name__ == '__main__':
    raise SystemExit(main())
