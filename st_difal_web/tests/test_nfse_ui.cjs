const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { test } = require('node:test');
const source = fs.readFileSync(path.join(__dirname, '../static/app.js'), 'utf8');

class Element {
  constructor(dataset = {}) { this.dataset = dataset; this.events = {}; this.attributes = {}; this.textContent = ''; this.classes = new Set(); this.classList = { add: n => this.classes.add(n), remove: n => this.classes.delete(n) }; }
  addEventListener(name, handler) { this.events[name] = handler; }
  setAttribute(name, value) { this.attributes[name] = value; }
  focus() { this.focused = true; }
}

test('NFS-e tab supports direct URL, keyboard navigation, unknown-tab fallback and submit busy state', () => {
  const tabs = ['importacao', 'auditoria-nfse'].map(tabTarget => new Element({ tabTarget }));
  const panels = tabs.map(tab => ({ id: tab.dataset.tabTarget }));
  const button = new Element({ pendingLabel: 'Auditando notas fiscais…' });
  const form = new Element(); form.querySelector = () => button;
  const document = { getElementById: id => panels.find(panel => panel.id === id), querySelectorAll: selector => ({ '[data-tab-target]': tabs, '[data-tab-panel]': panels, '.async-form': [form] })[selector] || [] };
  const window = { location: { href: 'http://localhost/?tab=auditoria-nfse' }, history: { replaceState() {} } };
  const block = source.slice(0, source.indexOf('const tableSortStatus'));
  vm.runInNewContext(block, { document, window, URL });
  assert.equal(panels[1].hidden, false);
  assert.equal(tabs[1].attributes['aria-selected'], 'true');
  tabs[1].events.keydown({ key: 'Home', preventDefault() {} });
  assert.equal(panels[0].hidden, false);
  assert.equal(tabs[0].focused, true);
  form.events.submit();
  assert.equal(button.disabled, true);
  assert.equal(button.textContent, 'Auditando notas fiscais…');
  window.location.href = 'http://localhost/?tab=unknown';
  vm.runInNewContext(block, { document, window, URL });
  assert.equal(panels[0].hidden, false);
});

test('Drag and drop and file selection display count and do not submit automatically', () => {
  const zone = new Element(); const input = new Element(); const count = new Element();
  input.files = [];
  const document = { getElementById: id => ({ 'drop-zone-nfse': zone, 'arquivos_nfse': input, 'nfse-file-count': count })[id] };
  vm.runInNewContext(source.slice(source.indexOf('// NFS-e upload:')), { document });
  let prevented = false;
  zone.events.dragover({ preventDefault() { prevented = true; } });
  assert.equal(prevented, true);
  assert.equal(zone.classes.has('nfse-dragging'), true);
  const files = [{ name: 'nota.xml' }, { name: 'lote.zip' }];
  zone.events.drop({ preventDefault() {}, dataTransfer: { files } });
  assert.equal(zone.classes.has('nfse-dragging'), false);
  assert.equal(input.files, files);
  assert.equal(count.textContent, '2 arquivo(s) selecionado(s).');
  input.files = [];
  input.events.change();
  assert.equal(count.textContent, '0 arquivo(s) selecionado(s).');
});

test('NFS-e table filter uses accent-insensitive search and empty state', () => {
  const input = new Element({ reconciliationFilter: 'nfse-notes' });
  const count = new Element(); const empty = new Element();
  const rows = [new Element(), new Element()];
  rows[0].textContent = '0001 Prestação JOÃO'; rows[1].textContent = '0002 Maria';
  const table = { id: 'nfse-notes', querySelectorAll: () => rows, querySelector: () => empty };
  const document = { getElementById: id => id === 'nfse-notes' ? table : count, querySelectorAll: () => [input] };
  const normalizer = source.slice(source.indexOf('function normalizedText'), source.indexOf('function localizedNumber'));
  const block = source.slice(source.indexOf('document.querySelectorAll("[data-reconciliation-filter]")'), source.indexOf('const filters ='));
  vm.runInNewContext(normalizer + block, { document });
  input.value = 'joao'; input.events.input();
  assert.equal(rows[0].hidden, false); assert.equal(rows[1].hidden, true);
  assert.equal(count.textContent, '1 de 2 nota(s)');
  input.value = 'ausente'; input.events.input(); assert.equal(empty.hidden, false);
});
