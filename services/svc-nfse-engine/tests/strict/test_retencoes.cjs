// Testes de comportamento do módulo com DOM mínimo, sem dependências externas.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { test } = require('node:test');

const root = path.resolve(__dirname, '../../../../frontend');
const html = fs.readFileSync(path.join(root, 'index.html'), 'utf8');
const script = fs.readFileSync(path.join(root, 'assets/retencoes.js'), 'utf8');

class Element {
  constructor(tag = '') {
    this.tag = tag;
    this.children = [];
    this.events = {};
    this.value = '';
    this.textContent = '';
  }
  set innerHTML(value) { throw new Error('O módulo não deve interpretar dados como HTML'); }
  appendChild(child) {
    this.children.push(...(child.tag === 'fragment' ? child.children : [child]));
  }
  replaceChildren(...children) {
    this.children = [];
    children.forEach((child) => this.appendChild(child));
  }
  add(option) { this.appendChild(option); }
  addEventListener(event, listener) { this.events[event] = listener; }
}

function setup(fetch) {
  const elements = Object.fromEntries([...html.matchAll(/id="([^"]+)"/g)]
    .map((match) => [match[1], new Element()]));
  const timers = new Map();
  let nextTimer = 0;
  const document = new Element();
  document.getElementById = (id) => elements[id];
  document.createElement = (tag) => new Element(tag);
  document.createDocumentFragment = () => new Element('fragment');
  const context = vm.createContext({
    document, fetch, Intl, URLSearchParams, AbortController,
    ApiClient: { request: async (endpoint, options) => {
      const result = await fetch(`/api/v1${endpoint}`, options);
      if (!result.ok) throw new Error('Falha ao consultar retenções');
      return result.json();
    } },
    Option: class extends Element {
      constructor(label, value) { super('option'); this.textContent = label; this.value = value; }
    },
    setTimeout: (callback) => { timers.set(++nextTimer, callback); return nextTimer; },
    clearTimeout: (id) => timers.delete(id),
  });
  vm.runInContext(script, context);
  document.events.DOMContentLoaded();
  return { elements, timers, refresh: () => vm.runInContext('Retencoes.refresh()', context) };
}

function report(month = '2026-01', total = '10.25') {
  const totals = { iss: total, inss: '0.00', pis: '0.00', cofins: '0.00', irrf: '0.00',
    csll: '0.00', total_declarado: total, total_identificado: total, diferenca: '0.00' };
  return { competencias: ['2026-02', '2026-01'], totais: totals,
    total_notas_periodo: 2, total_notas_retencao: 1,
    notas: [{ numero_nfse: 42, competencia: month, tomador: '<img src=x onerror=alert(1)>', ...totals }] };
}
const response = (data) => ({ ok: true, json: async () => data });

test('filtro envia competência e apresenta os valores sem interpretar HTML', async () => {
  let url;
  const { elements: el, timers } = setup(async (value) => { url = value; return response(report()); });
  el.retencoesCompetencia.value = '2026-01';
  await el.retencoesCompetencia.events.change();
  assert.equal(url, '/api/v1/nfse/retencoes?competencia=2026-01');
  assert.match(el.retencoesStatus.textContent, /01\/2026: 1 nota\(s\) com retenção de 2/);
  assert.match(el.retencoesIss.textContent, /10,25/);
  assert.equal(el.retencoesTableBody.children[0].children[2].textContent, '<img src=x onerror=alert(1)>');
  assert.equal(el.retencoesResults.hidden, false);
  assert.equal(timers.size, 0);
});

test('limpar filtro restaura todas as competências e desabilita o botão', async () => {
  const requests = [];
  const { elements: el } = setup(async (url) => { requests.push(url); return response(report()); });
  el.retencoesCompetencia.value = '2026-01';
  await el.retencoesCompetencia.events.change();
  await el.btnClearRetencoesFilter.events.click();
  // O handler dispara a atualização assíncrona; aguardar a fila de microtarefas.
  await new Promise(setImmediate);
  assert.equal(requests[1], '/api/v1/nfse/retencoes?');
  assert.equal(el.retencoesCompetencia.value, '');
  assert.equal(el.btnClearRetencoesFilter.disabled, true);
  assert.match(el.retencoesStatus.textContent, /Todas as competências/);
});

test('erro oculta totais antigos e permite nova tentativa com o mesmo filtro', async () => {
  let fail = false;
  const { elements: el, refresh } = setup(async () => fail ? { ok: false } : response(report()));
  el.retencoesCompetencia.value = '2026-01';
  await refresh();
  fail = true;
  await refresh();
  assert.equal(el.retencoesResults.hidden, true);
  assert.equal(el.btnRetryRetencoes.hidden, false);
  assert.match(el.retencoesStatus.textContent, /Não foi possível/);
  assert.equal(el.retencoesCompetencia.value, '2026-01');
  fail = false;
  await el.btnRetryRetencoes.events.click();
  assert.equal(el.retencoesResults.hidden, false);
  assert.equal(el.btnRetryRetencoes.hidden, true);
});

test('resposta antiga não substitui a competência mais recente', async () => {
  const pending = [];
  const { elements: el, refresh } = setup((url, options) => new Promise((resolve) => {
    pending.push({ resolve, signal: options.signal });
  }));
  el.retencoesCompetencia.value = '2026-01';
  const first = refresh();
  el.retencoesCompetencia.value = '2026-02';
  const second = refresh();
  assert.equal(pending[0].signal.aborted, true);
  pending[1].resolve(response(report('2026-02', '20.00')));
  await second;
  pending[0].resolve(response(report()));
  await first;
  assert.equal(el.retencoesCompetencia.value, '2026-02');
  assert.match(el.retencoesTotalDeclarado.textContent, /20,00/);
  assert.match(el.retencoesStatus.textContent, /02\/2026/);
});

test('período vazio mantém seleção mesmo após exclusão da última nota', async () => {
  const empty = report();
  empty.competencias = [];
  empty.notas = [];
  empty.total_notas_periodo = 0;
  empty.total_notas_retencao = 0;
  Object.keys(empty.totais).forEach((field) => { empty.totais[field] = '0.00'; });
  const { elements: el, refresh } = setup(async () => response(empty));
  el.retencoesCompetencia.value = '2026-01';
  await refresh();
  assert.equal(el.retencoesCompetencia.value, '2026-01');
  assert.ok(el.retencoesCompetencia.children.some((option) => option.value === '2026-01'));
  assert.match(el.retencoesTableBody.children[0].children[0].textContent, /Nenhuma nota neste período/);
  assert.match(el.retencoesTotalDeclarado.textContent, /0,00/);
});

test('tempo limite de rede oferece recuperação', async () => {
  const { elements: el, refresh, timers } = setup((url, { signal }) => new Promise((resolve, reject) => {
    signal.addEventListener('abort', () => reject(new Error('Tempo limite')));
  }));
  const pending = refresh();
  [...timers.values()][0]();
  await pending;
  assert.equal(el.btnRetryRetencoes.hidden, false);
  assert.equal(el.retencoesResults.hidden, true);
  assert.equal(timers.size, 0);
});
