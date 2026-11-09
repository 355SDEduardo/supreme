# Arquitetura do Front-End Único Unificado — Supreme

Este documento detalha a arquitetura do **Front-End Único Unificado (`frontend/`)** da plataforma **Supreme**, onde todos os 14 microsserviços (`services/svc-*/`) operam exclusivamente como servidores de API backend e toda a interface de usuário é concentrada em uma única aplicação web servida pelo **API Gateway / BFF (`gateway/bff_router.py` na porta 8080)**, preservando integralmente a estética do portal principal **Supreme** e todos os elementos funcionais de `portalcontabilidades`, `nfse`, `st_difal_web`, `pdf` e `audit`.

---

## 1. Visão Geral da Arquitetura

1. **Microsserviços 100% Backend-Only (`services/svc-*/`, portas 8001 a 8014):**
   - Nenhum microsserviço monta diretórios estáticos (`StaticFiles`) ou serve páginas HTML (`HTMLResponse`/`FileResponse`).
   - Cada microsserviço expõe exclusivamente contratos REST/JSON e fluxos de exportação sob `/api/v1/<dominio>/*` e `/health`.

2. **API Gateway / BFF Único (`gateway/bff_router.py`, porta 8080):**
   - Roteia todas as chamadas `/api/v1/*` para os 14 microsserviços com propagação de `Authorization: Bearer ...`, `X-Correlation-ID` e contexto de organização/empresa.
   - Gerencia a sessão autenticada no navegador via cookie `HttpOnly` (`supreme_session`) e proteção CSRF (`X-Supreme-CSRF: 1`).
   - Serve a aplicação unificada na raiz `/` (e `/app`) a partir de `frontend/index.html` e os ativos estáticos em `/assets/*` a partir de `frontend/assets/`.

3. **Front-End Único Nativo Sem Iframes (`frontend/`):**
   - [`frontend/index.html`](file:///C:/lucas/incolapse/supreme/frontend/index.html): Casca única contendo login com MFA, barra lateral categorizada, seletor global de empresa e competência, **16 views nativas** e **8 modais**.
   - [`frontend/assets/style.css`](file:///C:/lucas/incolapse/supreme/frontend/assets/style.css): Design System unificado na paleta oficial do portal **Supreme** (`--bg: #f1f5f9`, `--panel: #ffffff`, `--ink: #172b42`, `--muted: #52657a`, `--accent: #166659`, `--sidebar: #132f3c`, `--border: #cbd5e1`).
   - [`frontend/assets/api.js`](file:///C:/lucas/incolapse/supreme/frontend/assets/api.js): Cliente HTTP unificado (`ApiClient`) para os 14 microsserviços com injeção automática de CSRF, correlação e tratamento de sessão.
   - [`frontend/assets/charts.js`](file:///C:/lucas/incolapse/supreme/frontend/assets/charts.js): Motor gráfico Canvas 2D nativo (`MiniCharts`) para projeção de fluxo de caixa, gráficos de rosca e barras horizontais.
   - [`frontend/assets/retencoes.js`](file:///C:/lucas/incolapse/supreme/frontend/assets/retencoes.js): Motor de cálculo e controlador do módulo de retenções tributárias por competência (`Retencoes` / `NfseRetencoes`).
   - [`frontend/assets/app.js`](file:///C:/lucas/incolapse/supreme/frontend/assets/app.js): Controlador unificado CSP-safe (sem scripts inline) de todas as 16 views e 8 modais.
   - `frontend/assets/pluggy.js`: Configuração e teste das credenciais da API Pluggy por empresa.

---

## 2. Mapeamento das 16 Views Nativas e Microsserviços Backend

| View no Front-End Único (`frontend/index.html`) | Microsserviço Backend | Porta | Prefixo no Gateway |
| :--- | :--- | ---: | :--- |
| `#view-cockpit` (Visão Geral & Cockpit) | Agregador Multi-Serviço | 8080 | `/api/v1/*` |
| `#view-companies` (Empresas, Filiais & RBAC) | `svc-companies` | 8002 | `/api/v1/companies` |
| `#view-obligations` (Calendário Fiscal & Obrigações) | `svc-obligations` | 8003 | `/api/v1/obligations` |
| `#view-documents` (GED Contábil & Custódia SHA-256) | `svc-documents` | 8004 | `/api/v1/documents` |
| `#view-bills` (BPO Financeiro, Contas & Aging) | `svc-finance-bpo` | 8010 | `/api/v1/finance` |
| `#view-reconciliation` (Conciliação Bancária OFX) | `svc-bank-reconciliation` | 8009 | `/api/v1/reconciliation` |
| `#view-pluggy` (Configuração da API Pluggy) | `svc-bank-reconciliation` | 8009 | `/api/v1/bank-accounts/open-finance` |
| `#view-analytics` (DRE, Fluxo de Caixa & KPIs) | `svc-analytics-dre` | 8013 | `/api/v1/analytics` |
| `#view-fiscal` (Integrações Fiscais & CND/DCTFWeb) | `svc-fiscal-gov` | 8011 | `/api/v1/fiscal` |
| `#view-ai` (Automação, OCR & IA Contábil) | `svc-accounting-ai` | 8014 | `/api/v1/ai` |
| `#view-portal` (Portal do Cliente, Guias & SLA) | `svc-client-portal` | 8012 | `/api/v1/portal` |
| `#view-security` (Segurança IAM, Cofre A1 & LGPD) | `svc-security-iam` | 8001 | `/api/v1/security` |
| `#view-nfse` (Inteligência NFS-e, Retenções & DANFSE) | `svc-nfse-engine` | 8006 | `/api/v1/nfse` |
| `#view-nfe` (Conferidor NF-e, ST/DIFAL & ZIPs) | `svc-nfe-difal` | 8007 | `/api/v1/nfe` |
| `#view-pdf` (Ferramentas PDF: 6 Utilitários) | `svc-pdf-tools` | 8005 | `/api/v1/pdf` |
| `#view-tax-audit` (Auditoria Tributária Federal: 8 Abas) | `svc-federal-tax-audit` | 8008 | `/api/v1/tax-audit` |

---

## 3. Como Executar e Validar

A view `pluggy` é controlada por `frontend/assets/pluggy.js`. Usa o `ApiClient`
com cookies e CSRF, respeita empresa/MFA/perfil e cancela respostas antigas ao
mudar de contexto. A tela administra credenciais criptografadas por empresa e
consulta conectores; o consentimento bancário permanece nas APIs Pluggy Connect.
Nenhum SDK externo ou alteração na CSP é necessário para essa configuração.

1. Execute o bootstrap e o orquestrador na raiz:
   ```powershell
   uv sync
   uv run python -m scripts.bootstrap --email admin@seu-escritorio.com --organization meu-escritorio
   uv run python -m scripts.dev_runner
   ```
2. Abra **`http://127.0.0.1:8080`** no navegador.
3. Efetue login, conclua o MFA e selecione a empresa e competência na barra superior para operar as views permitidas pelo seu perfil.
