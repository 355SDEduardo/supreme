// Exercita o JavaScript real com uma fronteira DOM mínima, sem navegador instalado.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const { test } = require("node:test");
const path = require("node:path");
const source = fs.readFileSync(path.join(__dirname, "../static/app.js"), "utf8");

class Element {
  constructor(text = "", dataset = {}) {
    this.textContent = text;
    this.dataset = dataset;
    this.attributes = {};
    this.events = {};
    this.hidden = false;
    const classes = new Set();
    this.classList = { contains: (name) => classes.has(name) || name === this.className, add: (name) => classes.add(name) };
  }
  setAttribute(key, value) { this.attributes[key] = value; }
  getAttribute(key) { return this.attributes[key]; }
  addEventListener(name, listener) { this.events[name] = listener; }
  replaceChildren(child) { this.child = child; }
  querySelector(selector) { return selector === ".sort-button" ? this.child : null; }
  focus() { this.focused = true; }
}

function table(id, entries) {
  const header = new Element("Valor Total", { sortType: "number" });
  const empty = new Element("Nenhuma nota");
  empty.hidden = entries.length > 0;
  const rows = entries.map(([name, amount]) => {
    const row = new Element(`${name} ${amount}`);
    row.cells = [new Element(amount)];
    return row;
  });
  const body = {
    rows: [...rows, empty],
    querySelectorAll: (selector) => selector === "[data-table-empty]" ? [empty] : body.rows.filter((row) => row !== empty),
    append: (row) => { body.rows = body.rows.filter((current) => current !== row); body.rows.push(row); },
  };
  const instance = {
    id, dataset: { tableName: id }, tBodies: [body], tHead: { rows: [{ cells: [header] }] },
    querySelectorAll: () => body.querySelectorAll("rows"), querySelector: () => empty,
  };
  const input = new Element("", { reconciliationFilter: id });
  const count = new Element();
  return { instance, input, count, header, empty, body, rows };
}

test("Filtros ignoram acentos, mostram vazio e preservam a outra tabela", () => {
  const first = table("cliente", [["JOÃO", "R$ 10,00"], ["Maria", "R$ 2,00"]]);
  const second = table("portal", [["Portal", "R$ 100,00"]]);
  const fixtures = [first, second];
  const document = {
    getElementById: (id) => fixtures.find((item) => item.instance.id === id)?.instance || fixtures.find((item) => `${item.instance.id}-count` === id)?.count || new Element(),
    createElement: () => new Element(),
    querySelectorAll: (selector) => fixtures.map((item) => selector === ".sortable-table" ? item.instance : item.input),
  };
  vm.runInNewContext(source.slice(source.indexOf("const tableSortStatus"), source.indexOf("const filters =")), { document, Intl });
  first.input.value = "joao";
  first.input.events.input();
  assert.equal(first.rows[0].hidden, false);
  assert.equal(first.rows[1].hidden, true);
  assert.equal(first.count.textContent, "1 de 2 nota(s)");
  assert.equal(second.rows[0].hidden, false);
  first.input.value = "ausente";
  first.input.events.input();
  assert.equal(first.empty.hidden, false);
  first.input.value = "";
  first.input.events.input();
  assert.equal(first.empty.hidden, true);
  assert(first.rows.every((row) => !row.hidden));
});

test("Ordenação numérica brasileira alterna direção sem reexibir linhas filtradas", () => {
  const fixture = table("cliente", [["A", "R$ 100,00"], ["B", "R$ 2,00"], ["C", "R$ 10,00"]]);
  const document = {
    getElementById: () => new Element(), createElement: () => new Element(),
    querySelectorAll: (selector) => selector === ".sortable-table" ? [fixture.instance] : [],
  };
  vm.runInNewContext(source.slice(source.indexOf("const tableSortStatus"), source.indexOf("const filters =")), { document, Intl });
  fixture.rows[1].hidden = true;
  fixture.header.child.events.click();
  assert.deepEqual(fixture.body.rows.slice(0, 3).map((row) => row.textContent), ["B R$ 2,00", "C R$ 10,00", "A R$ 100,00"]);
  assert.equal(fixture.header.getAttribute("aria-sort"), "ascending");
  assert.equal(fixture.rows[1].hidden, true);
  fixture.header.child.events.click();
  assert.equal(fixture.body.rows[0].textContent, "A R$ 100,00");
  assert.equal(fixture.header.getAttribute("aria-sort"), "descending");
  assert.equal(fixture.body.rows.at(-1), fixture.empty);
});

test("Nova aba funciona por URL e teclado; envio exibe espera e desabilita botão", () => {
  const tabs = [new Element("Importar", { tabTarget: "importacao" }), new Element("Comparar", { tabTarget: "conciliacao-zips" })];
  const panels = tabs.map((tab) => ({ id: tab.dataset.tabTarget }));
  const submit = new Element("Comparar Pacotes ZIP", { pendingLabel: "Cruzando notas dos ZIPs…" });
  const form = new Element();
  form.querySelector = () => submit;
  const document = {
    getElementById: (id) => panels.find((panel) => panel.id === id),
    querySelectorAll: (selector) => ({ "[data-tab-target]": tabs, "[data-tab-panel]": panels, ".async-form": [form] })[selector] || [],
  };
  const window = { location: { href: "http://localhost/?tab=conciliacao-zips" }, history: { replaceState() {} } };
  vm.runInNewContext(source.slice(0, source.indexOf("const tableSortStatus")), { document, window, URL });
  assert.equal(panels[0].hidden, true);
  assert.equal(panels[1].hidden, false);
  assert.equal(tabs[1].getAttribute("aria-selected"), "true");
  tabs[1].events.keydown({ key: "ArrowLeft", preventDefault() {} });
  assert.equal(panels[0].hidden, false);
  assert.equal(tabs[0].focused, true);
  form.events.submit();
  assert.equal(submit.disabled, true);
  assert.equal(submit.getAttribute("aria-busy"), "true");
  assert.equal(submit.textContent, "Cruzando notas dos ZIPs…");
});
