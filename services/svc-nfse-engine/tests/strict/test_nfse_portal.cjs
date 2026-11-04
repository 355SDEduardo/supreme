const assert = require('node:assert/strict');
const { test } = require('node:test');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.resolve(__dirname, '../../../../frontend/assets');
const retentions = require(path.join(root, 'retencoes.js'));

test('cliente usa uma única sessão temporária para consultas concorrentes e download', async () => {
  const calls = [];
  const window = {
    location: { origin: 'http://localhost' },
    crypto: { randomUUID: () => 'correlation' },
    addEventListener() {},
    fetch: async (url, options) => {
      calls.push({ url, options });
      return { ok: true, status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => ({ workspace: 'session-' + calls.filter(c => c.url.endsWith('/workspaces')).length }),
        blob: async () => new Blob(['export']) };
    },
  };
  const document = { body: { appendChild() {} }, createElement: () => ({ click() {}, remove() {} }) };
  vm.runInNewContext(fs.readFileSync(path.join(root, 'api.js'), 'utf8'),
    { window, document, Headers, FormData, Request, URL, setTimeout });
  const api = window.ApiClient;
  await Promise.all([api.request('/nfse/notes'), api.request('/nfse/dashboard/stats')]);
  assert.equal(calls.filter(c => c.url.endsWith('/workspaces')).length, 1);
  assert.ok(calls.slice(1).every(c => c.url.includes('workspace=session-1')));
  await api.download('/nfse/export/json');
  assert.match(calls.at(-1).url, /export\/json\?workspace=session-1$/);
  assert.equal(calls[0].options.headers['X-Supreme-CSRF'], '1');
  await api.resetNfseWorkspace();
  assert.equal(calls.at(-1).options.method, 'DELETE');
  await api.request('/nfse/notes');
  assert.match(calls.at(-1).url, /workspace=session-2$/);
});

test('painel apresenta a lista e os campos reais retornados pelo serviço', async () => {
  const elements = new Map();
  const element = id => {
    if (!elements.has(id)) elements.set(id, { textContent: '', innerHTML: '', style: {}, value: '',
      classList: { remove() {}, toggle() {} }, setAttribute() {} });
    return elements.get(id);
  };
  const note = { numero_nfse: 42, chave_nfse: 'key', status: 100,
    data_emissao_dps: '2026-01-01T10:00:00', data_competencia: '2026-01-01',
    emitente: { razao_social: 'Prestador sintético', documento_formatado: '00.111.222/0001-33' },
    tomador: { razao_social: 'Tomador sintético' }, valor_servico: 1000, valor_liquido: 900,
    valor_total_retencoes: 100, tipo_retencao_issqn: 2, valor_issqn: 50,
    tributos_federais: { valor_ret_irrf: 50 }, auditoria: { status_conciliacao: 'CONCILIADO' } };
  const calls = [];
  const context = vm.createContext({
    document: { addEventListener() {}, getElementById: element, querySelectorAll: () => [] },
    window: { NfseRetencoes: retentions }, Intl, URL, FormData, Blob,
    ApiClient: { nfseGeneration: 0, request: async endpoint => {
      calls.push(endpoint);
      if (endpoint === '/nfse/dashboard/stats') return { total_notas: 1, faturamento_bruto: 1000, faturamento_liquido: 900 };
      if (endpoint === '/nfse/notes?limit=5000') return [note];
      throw new Error('Rota incorreta: ' + endpoint);
    } },
  });
  vm.runInContext(fs.readFileSync(path.join(root, 'app.js'), 'utf8'), context);
  vm.runInContext("AppState.activeCompanyId = 'synthetic'; showToast = message => { throw new Error(message); };", context);
  await vm.runInContext('loadNfseDashboardData()', context);
  assert.equal(calls.length, 2);
  assert.match(element('notesTableBody').innerHTML, /Prestador sintético/);
  assert.match(element('notesTableBody').innerHTML, /1\.000,00/);
  assert.match(element('kpiValorBruto').textContent, /1\.000,00/);
  assert.match(element('kpiISS').textContent, /50,00/);
  assert.match(element('kpiIRRF').textContent, /50,00/);
  assert.match(element('filterPrestador').innerHTML, /Prestador sintético/);
});
