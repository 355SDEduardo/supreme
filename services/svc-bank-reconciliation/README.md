# svc-bank-reconciliation

Serviço MS-09, porta 8009. Execute na raiz: `uv run --env-file .env uvicorn svc_bank_reconciliation.app:app --port 8009`.

`GET /health` verifica o processo; `/docs` descreve os contratos. Rotas privadas exigem JWT emitido pelo IAM. O banco e armazenamento são privados; consulte a configuração e os fluxos no README da raiz.

Teste isolado: `uv run pytest services/svc-bank-reconciliation/tests -q`.

For isolated execution, configure the SVC_*_URL values from the root .env.example. The root development runner configures discovery automatically.

## Extratos bancários via Pluggy / Open Finance

As APIs abaixo conectam bancos brasileiros via Pluggy Connect e mantêm uma cópia
local dos extratos. A configuração da API está disponível no portal em
**BPO Financeiro & Analytics → Integração Pluggy**. O gateway existente já encaminha as rotas.
Os contratos tipados aparecem em `/docs` do serviço e no OpenAPI agregado.

Escopo: conectores `PERSONAL_BANK`/`BUSINESS_BANK`, `isOpenFinance=true`, contas
`BANK` e produtos `ACCOUNTS` e `TRANSACTIONS`. Não inclui pagamentos, cartões,
investimentos, identidade, importação no financeiro nem baixa/conciliação
automática. Os fluxos OFX existentes continuam independentes.

### Configuração pelo frontend

Selecione uma empresa e abra **Integração Pluggy**. Com MFA verificado e perfil
`super_admin` ou `supervisor`, informe **Client ID** e **Client Secret** obtidos
no Dashboard Pluggy e clique em **Validar e salvar**. A autenticação é verificada
no servidor antes de gravar; uma falha preserva a configuração anterior.

A configuração é privada por organização **e empresa** e tem prioridade sobre
as variáveis de ambiente. Campos vazios preservam as credenciais atuais; trocar
o Client ID exige também informar o segredo. O botão **Testar configuração salva**
faz uma nova autenticação com as credenciais persistidas, sem aplicar o formulário.
**Consultar bancos** lista os conectores compatíveis. Essas ações não conectam
contas nem sincronizam extratos; o consentimento via Pluggy Connect continua
seguindo o fluxo de APIs descrito abaixo.

O Client Secret nunca é retornado e o Client ID aparece apenas mascarado. Ambos
são armazenados com AES-256-GCM na tabela `pluggy_configurations`, com organização
e empresa autenticadas também pela criptografia. É necessária a chave
`MASTER_ENCRYPTION_KEY` (32 bytes em hexadecimal), já criada pelo bootstrap.
Preserve essa chave junto ao backup privado; trocá-la exige recriptografar as
credenciais com a chave anterior. Tokens da Pluggy ficam somente em memória.
O frontend limpa os campos ao salvar, trocar de empresa, sair da tela ou encerrar
a sessão; não os grava no armazenamento do navegador. Use HTTPS fora do host local.

Sandbox é proibido em produção. A remoção só afeta a configuração da empresa e
restaura o uso do ambiente, se configurado. Trocar de aplicação ou remover a
configuração exige desconectar os bancos e aguardar expiração de sessões pendentes;
a rotação do segredo da mesma aplicação permanece permitida. A revisão retornada
pela API impede sobrescrever alterações concorrentes sem recarregar a tela.

Rotas administrativas no prefixo `/api/v1/bank-accounts/open-finance`:

| Método e rota | Comportamento |
| --- | --- |
| `GET /configuration` | Origem, ID mascarado, sandbox, revisão e disponibilidade do armazenamento |
| `PUT /configuration` | Valida e salva `client_id`, `client_secret`, `allow_sandbox` e `revision`; credenciais omitidas são preservadas |
| `POST /configuration/test` | Testa novamente a autenticação da configuração efetiva |
| `DELETE /configuration?revision=N` | Remove a configuração da empresa e usa o ambiente, se disponível |

Sem configuração prévia, use `revision: 0`. Os dois campos de credenciais são
obrigatórios na primeira configuração. A revisão não substitui a autenticação:
todas essas rotas exigem perfil administrativo, MFA e contexto da empresa no JWT.

### Configuração alternativa do servidor

Configure no ambiente **do serviço bancário**:

| Variável | Uso |
| --- | --- |
| `PLUGGY_CLIENT_ID` | Identificador da aplicação no Dashboard Pluggy |
| `PLUGGY_CLIENT_SECRET` | Segredo da aplicação; nunca retornar ao navegador |
| `PLUGGY_ALLOW_SANDBOX` | `false` por padrão; `true` somente para testes |

Há um modelo em [.env.pluggy.example](.env.pluggy.example). O runner local carrega
o `.env` da raiz; configure os valores privadamente nesse ambiente, sem versionar.
Reinicie o serviço após trocar o ambiente. Alterações feitas pelo portal são
aplicadas na próxima operação, inclusive entre processos. Sem configuração, as operações remotas
retornam `503`; as leituras locais continuam disponíveis.

A URL é fixa: `https://api.pluggy.ai`. Sandbox usa a mesma API e só permite
conectores que também sejam Open Finance; `SUPREME_ENV=production` proíbe sandbox.
A chave obtida por `/auth` fica somente em memória, é reutilizada por até 7.100
segundos por processo e nunca integra respostas ou registros persistidos.
Somente o Connect Token temporário é entregue ao cliente.

O Compose principal não injeta estas variáveis. Use o complemento deste serviço:

```powershell
docker compose -f docker-compose.yml -f services/svc-bank-reconciliation/docker-compose.pluggy.yml up -d svc-bank-reconciliation
```

### Rotas e fluxo do portal

Prefixo pelo gateway: **`/api/v1/bank-accounts/open-finance`**.
Diretamente na porta 8009, remova apenas `/api/v1`.

Todas as rotas exigem sessão válida, MFA e empresa selecionada. O navegador usa
cookie `HttpOnly`; mutações exigem `X-Supreme-CSRF: 1`. Integrações usam Bearer.
Nas rotas bancárias abaixo, os perfis `super_admin`, `supervisor`, `analyst`, `bpo_operator`, `client_user`
e `service` podem operar. `viewer` só consulta. Organização e empresa vêm do JWT;
não são aceitas como parâmetros de conexão. `X-Correlation-ID` acompanha a chamada
externa, sem encaminhar o JWT Supreme à Pluggy.

| Método e rota relativa | Comportamento |
| --- | --- |
| `GET /connectors` | Bancos habilitados para o escopo Open Finance |
| `POST /connect-token` | Inicia sessão; corpo `{"connector_id":601}` |
| `POST /connections/{id}/complete` | Valida e vincula `{"item_id":"UUID"}` recebido do widget |
| `GET /connections` | Conexões vinculadas da empresa; `offset` e `limit` (máximo 100) |
| `GET /connections/{id}` | Estado local e status atual da Pluggy/consentimento |
| `POST /connections/{id}/connect-token` | Token restrito ao Item existente para reconexão/renovação no widget |
| `POST /connections/{id}/refresh` | Solicita nova coleta no banco; `202` não significa extrato pronto |
| `POST /connections/{id}/sync` | Copia contas e transações já coletadas pela Pluggy para o banco local |
| `GET /connections/{id}/accounts` | Contas do último extrato sincronizado |
| `GET /accounts/{id}/transactions` | Extrato local com `date_from`, `date_to`, `offset` e `limit` (até 500) |
| `DELETE /connections/{id}` | Exclui o Item remoto e marca a conexão desconectada; repetível |

Para integrar a interface:

1. Liste os conectores e envie a escolha a `POST /connect-token`.
2. Guarde `connection_id` e inicialize o Pluggy Connect com `connectToken` igual
   a `access_token` e todas as propriedades de `widget_options` retornadas.
   Essas opções fixam o banco e os produtos; não envie senhas bancárias ao Supreme.
3. Recebido o Item pelo widget, envie seu UUID a `/connections/{id}/complete`
   na mesma sessão de usuário/empresa, em até 30 minutos. A operação pode ser
   repetida com o mesmo Item. O servidor consulta a Pluggy e confere `clientUserId`,
   banco, produtos e contexto; confiar apenas no callback não autoriza acesso.
4. Consulte o status. Aguarde `provider_status=UPDATED` e
   `execution_status=SUCCESS`, com consentimento vigente. Em estados que exigem
   ação do usuário, use o token de reconexão e `widget_options.updateItem`.
5. Sincronize o período desejado. Depois use apenas as consultas locais para
   renderizar o extrato. Para atualizar dados do banco, solicite `/refresh`,
   acompanhe o status com intervalo/backoff e então execute `/sync` novamente.

Exemplo de corpo para `/sync`:

```json
{"date_from":"2026-10-01","date_to":"2026-10-31"}
```

Não há receptor de webhooks nem agendamento automático nesta entrega. O consumidor
deve coordenar status e sincronização explicitamente e persistir o identificador
da sessão/Item para repetir `/complete` se uma requisição falhar. Um callback
perdido não registra uma conexão automaticamente. A expiração da sessão inicial
exige iniciar uma nova conexão. `avoidDuplicates=false` evita reutilização global
de Items entre empresas; a confirmação local é idempotente por sessão/Item.

### Semântica dos extratos e validações

Cada sincronização substitui atomicamente **a última janela local da conexão**,
incluindo todas as suas contas. Não acumula um histórico ilimitado de janelas.
Correções, remoções e mudanças `PENDING` → `POSTED` da janela são refletidas sem
duplicação. Uma falha de rede, página inválida, resultado parcial ou mudança do
Item durante a coleta preserva integralmente a cópia anterior.

Períodos têm até 366 dias inclusivos. Limites por operação: 100 contas, 20.000
transações, 40 páginas por conta, 8 MiB por resposta e 80 segundos para a coleta.
Se necessário, reduza o período. O cursor de `/v2/transactions` é decodificado
sem permitir troca de conta, filtros ou destino HTTP. Contas, transações, IDs,
moedas, sinais, datas e valores do fornecedor são validados antes de persistir.

As respostas informam `synced_at`, `source_updated_at` e a janela disponível.
Uma leitura fora da janela retorna `409`, em vez de sugerir que não houve
movimentação. Datas de filtro seguem os dias UTC retornados pela Pluggy; a data
completa da transação é preservada. Valores são `Decimal` e saem como strings
decimais. `balance` da conta é o saldo informado na coleta, **não** um saldo de
abertura/fechamento calculado para o período. `PENDING` é apresentado explicitamente
e não significa lançamento liquidado. O serviço não inventa saldos históricos.

Ao desconectar, não há novas consultas/sincronizações da conexão; suas cópias
locais ficam inacessíveis por estas APIs. Elas permanecem no banco privado para
retenção operacional e backup. A exclusão remota não é anunciada como exclusão
do histórico local nem como comprovante regulatório de revogação.

Erros: `401` sessão ausente; `403` perfil/contexto; `404` recurso inacessível;
`409` estado, janela ou concorrência; `410` sessão expirada/conexão desconectada;
`422` entrada/escopo/limites; `429` limite Pluggy com `Retry-After`; `502` resposta
inválida/falha externa; `503` configuração/autorização externa; `504` timeout.
Erros externos não reproduzem corpos que possam conter segredos ou dados pessoais.

### Migração e implantação

São adicionadas apenas `open_finance_connections`, `open_finance_accounts`,
`open_finance_transactions` e `pluggy_configurations`, no banco privado deste serviço. Não há alteração
de colunas nem migração de extratos OFX. Antes de atualizar um banco existente,
pare o serviço e faça backup. Execute no ambiente que aponta para esse banco:

```powershell
uv run --env-file .env python -m svc_bank_reconciliation.migrate_open_finance
uv run --env-file .env python -m svc_bank_reconciliation.migrate_open_finance --check
```

Em containers, execute o mesmo módulo com `docker compose run --rm
svc-bank-reconciliation python -m svc_bank_reconciliation.migrate_open_finance`
antes de iniciar a nova versão. `DATABASE_URL` deve apontar exclusivamente para
o banco bancário. Sem ela, a ferramenta usa o banco existente em `DB_ROOT_DIR`.
O comando é idempotente; `--check` retorna código 1 se faltarem tabelas.
Bancos novos também recebem as tabelas no ciclo normal de inicialização.
Rollback de aplicação: retorne à versão anterior e preserve as tabelas novas;
não exclua os dados. Não foi executada migração em banco real nesta implementação.

### Validação e referências

```powershell
uv run pytest services/svc-bank-reconciliation/tests -q
uv run pytest -c pyproject.toml services/svc-bank-reconciliation/tests tests/test_integration.py -q
uv run pytest tests/test_pluggy_frontend.py -q
```

Os testes usam dados sintéticos, SQLite temporário e `httpx.MockTransport`,
incluindo gateway/CSRF, isolamento, precisão decimal, expiração, paginação,
atualização/remoção de transações, falhas, concorrência e migração preservando OFX.
Os testes de configuração também cobrem criptografia vinculada à empresa,
permissões administrativas, erros sem segredos, rotação, fallback por ambiente
e correção de sandbox ao migrar para produção. O teste de frontend executa oito
cenários JavaScript, incluindo respostas atrasadas após troca de empresa,
limpeza de credenciais, falhas recuperáveis, envios duplicados e conteúdo externo.
Na validação da configuração pelo frontend, passaram 17 testes específicos da API.
Na cópia preparada para publicação, passaram 392 testes Python e 25 subtestes,
incluindo o executor dos oito cenários JavaScript do Pluggy. Houve uma falha
preexistente em `test_source_map_references_existing_sources_and_destinations`:
o mapa de migração exige amostras em `nfse/data/samples/` que não estão versionadas.
Os 14 testes JavaScript dos demais módulos e a sintaxe do frontend passaram em
execução separada. Ruff passou nos arquivos Python alterados; a formatação dos
novos módulos e testes foi verificada. A inspeção visual ficou pendente por
ausência de navegador disponível.
Eles não comprovam conexão bancária real, cobertura de uma instituição, assinatura
Pluggy, homologação, Redis/PostgreSQL ou implantação em containers. Antes de uso
real, valide com credenciais da aplicação e consentimento em conector Open Finance.

Contrato externo implementado exclusivamente a partir da documentação oficial:

- [Autenticação](https://docs.pluggy.ai/pt/reference/authentication) e
  [Connect Token](https://docs.pluggy.ai/pt/reference/auth/connect-token-create).
- [Conectores](https://docs.pluggy.ai/pt/reference/connector/connectors-list),
  [consulta de Item](https://docs.pluggy.ai/pt/reference/items/items-retrieve),
  [atualização](https://docs.pluggy.ai/pt/reference/items/items-update) e
  [exclusão](https://docs.pluggy.ai/pt/reference/items/items-delete).
- [Contas](https://docs.pluggy.ai/pt/reference/account/accounts-list),
  [transações por cursor](https://docs.pluggy.ai/pt/reference/transaction/transactions-list-by-cursor)
  e [campos das transações](https://docs.pluggy.ai/pt/docs/products/transactions).
- [Opções e limites do callback do widget](https://docs.pluggy.ai/pt/docs/connect-widget/environments).
