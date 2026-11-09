const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '../frontend/assets/pluggy.js'), 'utf8');
const configured = {
  configured: true, source: 'company', revision: 1, client_id_masked: '••••demo',
  storage_available: true, sandbox_allowed: true, allow_sandbox: false,
};

function setup(handler = async () => configured) {
  const elements = new Map();
  const listeners = {};
  class Element {
    constructor() { this.value = ''; this.children = []; this.events = {}; this.checked = false; }
    addEventListener(event, callback) { this.events[event] = callback; }
    setAttribute(name, value) { this[name] = value; }
    replaceChildren(...children) { this.children = children; }
    append(...children) { this.children.push(...children); }
    reportValidity() { return true; }
    focus() { this.focused = true; }
    reset() {
      for (const id of ['pluggy-client-id', 'pluggy-client-secret']) get(id).value = '';
      get('pluggy-sandbox').checked = false;
    }
  }
  const get = id => {
    if (!elements.has(id)) elements.set(id, new Element());
    return elements.get(id);
  };
  const calls = [];
  const sandbox = {
    document: { getElementById: get, createElement: () => new Element(), addEventListener: (e, f) => { listeners[e] = f; } },
    window: { confirm: () => true },
    AppState: { activeCompanyId: 'company-a', activeCompanyName: 'Empresa A', currentUser: { role: 'super_admin', mfaVerified: true } },
    ApiClient: { request: async (url, options) => { calls.push({ url, options }); return handler(url, options); } },
    AbortController, DOMException, Intl, setTimeout, clearTimeout,
  };
  vm.runInNewContext(source, sandbox);
  listeners.DOMContentLoaded();
  return { get, calls, sandbox, controller: sandbox.window.PluggyConfiguration };
}
const settle = () => new Promise(resolve => setImmediate(resolve));
const submit = fixture => fixture.get('pluggy-form').events.submit({ preventDefault() {} });

test('credentials are sent once and cleared only after a successful save', async () => {
  let resolveSave;
  const pending = new Promise(resolve => { resolveSave = resolve; });
  const ui = setup(async (_, options) => options.method === 'PUT' ? pending : configured);
  await ui.controller.refresh();
  ui.get('pluggy-client-id').value = 'new-client';
  ui.get('pluggy-client-secret').value = 'synthetic-secret';
  submit(ui); submit(ui);
  assert.equal(ui.calls.filter(call => call.options.method === 'PUT').length, 1);
  assert.equal(ui.get('pluggy-fields').disabled, true);
  assert.equal(ui.get('pluggy-client-secret').value, 'synthetic-secret');
  assert.equal(ui.calls.at(-1).options.body.client_secret, 'synthetic-secret');
  resolveSave({ ...configured, revision: 2 });
  await settle();
  assert.equal(ui.get('pluggy-client-secret').value, '');
  assert.equal(ui.get('pluggy-fields').disabled, false);
  assert.match(ui.get('pluggy-feedback').textContent, /salvas/);
});

test('recoverable errors preserve the form and offer a retry', async () => {
  const ui = setup(async (_, options) => {
    if (options.method === 'PUT') throw new Error('Autenticação da Pluggy indisponível.');
    return configured;
  });
  await ui.controller.refresh();
  ui.get('pluggy-client-secret').value = 'synthetic-secret';
  submit(ui);
  await settle();
  assert.equal(ui.get('pluggy-client-secret').value, 'synthetic-secret');
  assert.equal(ui.get('pluggy-save').disabled, false);
  assert.match(ui.get('pluggy-feedback').textContent, /indisponível/);
});

test('company change cancels requests, clears secrets and ignores late responses', async () => {
  let finish;
  const ui = setup(() => new Promise(resolve => { finish = resolve; }));
  const oldRequest = ui.controller.refresh();
  ui.get('pluggy-client-secret').value = 'synthetic-secret';
  ui.controller.reset();
  ui.sandbox.AppState.activeCompanyId = 'company-b';
  assert.equal(ui.calls[0].options.signal.aborted, true);
  assert.equal(ui.get('pluggy-client-secret').value, '');
  finish(configured);
  await oldRequest;
  assert.equal(ui.get('pluggy-source').textContent, 'Não consultada');
  assert.equal(ui.get('pluggy-fields').disabled, true);
});

test('a late save cannot clear a form entered in another company', async () => {
  let finish;
  const ui = setup(async (_, options) => options.method === 'PUT'
    ? new Promise(resolve => { finish = resolve; }) : configured);
  await ui.controller.refresh();
  ui.get('pluggy-client-secret').value = 'old-secret';
  submit(ui);
  ui.controller.reset();
  ui.sandbox.AppState.activeCompanyId = 'company-b';
  await ui.controller.refresh();
  ui.get('pluggy-client-secret').value = 'new-company-secret';
  finish({ ...configured, revision: 2 });
  await settle();
  assert.equal(ui.get('pluggy-client-secret').value, 'new-company-secret');
});

test('viewer, missing company and unverified MFA cannot submit requests', async () => {
  for (const scenario of ['viewer', 'company', 'mfa']) {
    const ui = setup();
    if (scenario === 'viewer') ui.sandbox.AppState.currentUser.role = 'viewer';
    if (scenario === 'company') ui.sandbox.AppState.activeCompanyId = '';
    if (scenario === 'mfa') ui.sandbox.AppState.currentUser.mfaVerified = false;
    await ui.controller.refresh();
    assert.equal(ui.calls.length, 0);
    assert.equal(ui.get('pluggy-fields').disabled, true);
  }
});

test('test button uses saved configuration and never submits unsaved secrets', async () => {
  const ui = setup(async (_, options) => options.method === 'POST' ? { message: 'Autenticação confirmada.' } : configured);
  await ui.controller.refresh();
  ui.get('pluggy-client-secret').value = 'unsaved-secret';
  await ui.get('pluggy-test').events.click();
  assert.equal(ui.calls.at(-1).options.body, undefined);
  assert.equal(ui.get('pluggy-client-secret').value, 'unsaved-secret');
});

test('connector names render as text and empty lists are explicit', async () => {
  let banks = [{ name: '<img src=x onerror=alert(1)>', type: 'BUSINESS_BANK', isSandbox: true }];
  const ui = setup(async url => url.endsWith('/connectors') ? banks : configured);
  await ui.controller.refresh();
  await ui.get('pluggy-connectors-load').events.click();
  assert.equal(ui.get('pluggy-connectors').children[0].children[0].textContent, banks[0].name);
  banks = [];
  await ui.get('pluggy-connectors-load').events.click();
  assert.equal(ui.get('pluggy-connectors').children.length, 0);
  assert.match(ui.get('pluggy-connectors-summary').textContent, /Nenhum banco/);
});

test('removal requires confirmation and production disables sandbox', async () => {
  const ui = setup(async () => ({ ...configured, allow_sandbox: true, sandbox_allowed: false }));
  await ui.controller.refresh();
  assert.equal(ui.get('pluggy-sandbox').disabled, true);
  assert.equal(ui.get('pluggy-sandbox').checked, false);
  ui.sandbox.window.confirm = () => false;
  ui.get('pluggy-remove').events.click();
  assert.equal(ui.calls.length, 1);
});
