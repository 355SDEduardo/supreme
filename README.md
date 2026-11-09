# Supreme — Plataforma contábil unificada

Quatorze serviços FastAPI independentes, gateway na porta **8080**, interface web,
CLI e biblioteca `supreme-common`. A arquitetura de referência está em
[ARQUITETURA_UNIFICADA_MICROSERVICOS.md](ARQUITETURA_UNIFICADA_MICROSERVICOS.md).

## Iniciar no Windows ou Linux

Requisitos: Python 3.12+ e `uv`; Node.js para os testes JavaScript. Execute na raiz:

```powershell
uv sync
uv run python -m scripts.bootstrap --email admin@seu-escritorio.com --organization meu-escritorio
uv run python -m scripts.dev_runner
```

O bootstrap solicita a senha sem exibi-la, gera segredos em `.env` e preserva
credenciais existentes. Acesse **http://127.0.0.1:8080**, entre, cadastre a chave
MFA no autenticador e confirme o código. Cadastre uma empresa na visão geral e
selecione-a antes de importar documentos ou operar os módulos. `/docs` reúne os
contratos dos serviços disponíveis; o painel informa os serviços indisponíveis.

O orquestrador verifica portas, inicia os 14 processos e o gateway, grava logs em
`data/logs/` e encerra os filhos com `Ctrl+C`. O modo local usa bancos SQLite
separados em `data/db/`; os dados dos motores ficam em
`data/storage/<serviço>/<organização>/<empresa>/`. O barramento local persiste
eventos e confirmações em `data/events/events.db`. Não há dependência de Docker
ou Redis nesse modo.

## Organização e contratos

| Serviço | Porta | Prefixos no gateway |
| --- | ---: | --- |
| `svc-security-iam` | 8001 | `/api/v1/security`, `/api/v1/certificates` |
| `svc-companies` | 8002 | `/api/v1/companies`, `/api/v1/cockpit`, `/api/v1/auth` |
| `svc-obligations` | 8003 | `/api/v1/tasks`, `/api/v1/companies/{id}/obligations` |
| `svc-documents` | 8004 | `/api/v1/documents` |
| `svc-pdf-tools` | 8005 | `/api/v1/pdf` |
| `svc-nfse-engine` | 8006 | `/api/v1/nfse` |
| `svc-nfe-difal` | 8007 | `/api/v1/nfe` |
| `svc-federal-tax-audit` | 8008 | `/api/v1/tax-audit` |
| `svc-bank-reconciliation` | 8009 | `/api/v1/reconciliation`, `/api/v1/bank-accounts` |
| `svc-finance-bpo` | 8010 | `/api/v1/bills` |
| `svc-fiscal-gov` | 8011 | `/api/v1/fiscal` |
| `svc-client-portal` | 8012 | `/api/v1/portal` |
| `svc-analytics-dre` | 8013 | `/api/v1/analytics` |
| `svc-accounting-ai` | 8014 | `/api/v1/ai` |

Cada diretório `services/svc-*/` contém pacote, manifesto, imagem e testes.
`libs/supreme_common/` concentra autenticação, contexto, eventos, persistência de
infraestrutura e validações. `frontend/` reúne o shell e os módulos; `gateway/`
possui proxy e OpenAPI agregado; `cli/` contém a interface de terminal.

Os diretórios originais `audit/`, `nfse/`, `pdf/`, `portalcontabilidades/` e
`st_difal_web/` preservam a referência anterior. Os novos serviços não os
importam em execução. Consulte o [mapa de fontes](docs/migration/source-map.json)
e o [guia de migração](docs/migration/README.md).

## Fluxos integrados

- **NFS-e no portal:** lote temporário inicialmente vazio, isolado por sessão,
  usuário e empresa. Cada importação válida de XML/ZIP substitui a anterior;
  os downloads Excel/CSV/JSON guardam os resultados. Exporte antes de recarregar,
  sair ou trocar de empresa. Não há custódia ou eventos automáticos nesse modo.
  Consulte os [contratos e limites de sessão](services/svc-nfse-engine/README.md).
- **NFS-e integrada (API/CLI sem `workspace`):** XML/ZIP → custódia de documentos → pipeline nacional/ABRASF/municipal
  → snapshot imutável → `NFSeBatchProcessed` → auditoria federal e projeção de
  retenções. Cancelamentos recebidos em lotes posteriores reprojetam o acervo;
  totais e exportações financeiras consideram notas autorizadas. O parâmetro
  `mode=nacional_strict` restringe a entrada ao padrão nacional.
- **Conciliação:** OFX → consulta HTTP de títulos → matching → baixa idempotente
  no financeiro → confirmação local → eventos para DRE e classificação contábil.
  A baixa exige aprovação, direção e soma dos títulos compatíveis com o extrato.
- **DRE:** projeções privadas alimentadas por eventos do financeiro; categorias
  `sales_deductions`, `cogs`, `financial_revenue` e `financial_expense` separam as
  rubricas. Outros pagamentos compõem despesas operacionais. Dados ausentes
  resultam em zero, sem receitas demonstrativas. Exportação PDF chama o serviço
  de ferramentas PDF.

As rotas privadas validam JWT, organização, empresa, identidade e perfil. O
gateway usa cookie `HttpOnly` para o navegador; mutações por cookie exigem
`X-Supreme-CSRF: 1`. Integrações usam `Authorization: Bearer ...` e propagam
`X-Correlation-ID`. O log registra ações e status, sem copiar corpos de documentos.

Para configurar Open Finance, selecione uma empresa e abra **BPO Financeiro &
Analytics → Integração Pluggy**. Administradores e supervisores podem validar e
salvar credenciais, testar a autenticação e consultar os bancos disponíveis.
Consulte [configuração, proteção das credenciais e migração do banco bancário](services/svc-bank-reconciliation/README.md#configuração-pelo-frontend).
O cadastro da API não conecta contas nem importa extratos automaticamente.

## CLI

```powershell
uv run supreme login --email admin@seu-escritorio.com --totp 123456
# Use SUPREME_TOKEN com um token de contexto de empresa; não o versione.
uv run supreme request /api/v1/auth/switch-company-context --method POST --body contexto.json
uv run supreme audit --action full --json --output auditoria.json
uv run supreme nfse lote.zip --mode multi_layout_audit
uv run supreme nfse --export excel --output nfse.xlsx
uv run supreme pdf merge a.pdf b.pdf --output unificado.pdf
uv run supreme nfe --comparar-zips cliente.zip portal.zip --excel comparacao.xlsx
```

`supreme nfe` preserva as opções do processamento local anterior, inclusive
operações, filtros, exportações e visualização CSV. Os outros comandos usam o
gateway. `uv run python -m cli.supreme_cli ...` é equivalente. A senha de login
é solicitada no terminal; a saída da autenticação contém o token para uso explícito.

## Containers

```powershell
uv run python -m scripts.bootstrap --secrets-only
docker compose build
docker compose run --rm svc-security-iam python -m svc_security_iam.bootstrap --email admin@seu-escritorio.com --organization meu-escritorio
docker compose up -d
```

O Compose inclui Redis Streams e PostgreSQL, dez bancos/usuários com senhas
distintas e volumes privados. Somente o gateway publica porta no host.
O bootstrap local e o bootstrap do container usam bancos diferentes. Os extras
`supreme-common[redis,postgres]` são instalados nas imagens. Para ativar esses
componentes fora do Docker, instale os extras e configure `REDIS_URL` e o
`DATABASE_URL` específico de cada processo. Não compartilhe uma mesma URL de
banco entre serviços.

O journal de eventos e as outboxes persistem antes da entrega; consumidores
confirmam após sucesso e repetem falhas. Faça backup dos bancos privados, dos
volumes de custódia **e** do journal. Não remova volumes para atualizar imagens.
Antes de expor a plataforma fora do host, configure TLS no proxy de borda e
`SUPREME_ENV=production`, para cookies seguros e HSTS.

## Testes e limites de validação

```powershell
uv run python -m scripts.test_all -q
uv run pytest services/svc-documents/tests -q
uv run pytest tests/test_integration.py -q
```

Os testes usam dados sintéticos, bancos temporários e transporte ASGI para
exercitar os serviços pelas APIs. O runner também executa os testes Node das
interfaces preservadas e do módulo NFS-e adaptado. A validação de containers,
Redis e PostgreSQL requer esses componentes instalados; os testes locais não
substituem esse ensaio de infraestrutura.

Os resultados e as limitações desta migração estão no
[registro de validação](docs/migration/VALIDACAO.md), incluindo a restrição de
rede que impediu uma instalação limpa pelo PyPI nesta sessão.

## Configuração externa e dados existentes

Consulte [.env.example](.env.example). Certificados inválidos são rejeitados;
upload de PFX válido exige raízes confiáveis em `ICP_BRASIL_CA_DIR`. Revogação
CRL/OCSP e integração oficial de assinatura/transmissão devem ser configuradas
antes do uso fiscal operacional. CND e reenvio ao fisco retornam `501` enquanto
não houver adaptador oficial; a DCTFWeb retorna uma **prévia**, sem fabricar DARF
ou recibo de transmissão. Conectores externos de mensagens e OCR de imagens
também dependem de configuração e implementação específicas do fornecedor.

Importe documentos antigos pelas APIs no contexto da empresa correta; não copie
todo o acervo para uma empresa padrão. A auditoria recebe `Consolidado_NFSe.json`
por evento ou `POST /api/v1/tax-audit/nfse/import`. Informe a cobertura temporal
do livro em `PUT /api/v1/tax-audit/ledger/period` antes de interpretar a segregação
de notas posteriores ao fechamento. PDFs seguem os nomes de demonstrativos
descritos no documento de arquitetura.

`.gitignore` e `.dockerignore` excluem documentos reais, `.txt`, `.pdf`, bancos,
certificados, ambientes, segredos e dados gerados. Não execute push de acervos
fiscais. Os esquemas novos são inicializados em bancos vazios; qualquer
alteração posterior de esquema exige migração e backup antes da implantação.
