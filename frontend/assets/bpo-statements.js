/* Bank statement imports: display facts as decimal strings and never render source text as HTML. */
(() => {
  const base = '/bills/statements';
  const state = { generation: 0, controller: null, busy: false, preview: null, ledgerOffset: 0 };
  const el = id => document.getElementById(id);
  const company = () => typeof AppState !== 'undefined' && AppState.activeCompanyId;
  const writable = () => typeof AppState !== 'undefined' && AppState.currentUser.role !== 'viewer';
  const dateLabel = value => String(value).split('-').reverse().join('/');
  const amountLabel = value => {
    const [integer, fraction = '00'] = String(value).split('.');
    return `R$ ${integer.replace(/\B(?=(\d{3})+(?!\d))/g, '.')},${fraction.padEnd(2, '0')}`;
  };
  function message(text) { el('bpo-statement-status').textContent = text; }
  function controls() {
    const data = state.preview;
    el('bpo-upload').disabled = state.busy || !company() || !writable();
    el('bpo-imports').disabled = state.busy;
    el('bpo-reload').disabled = state.busy || !company();
    el('bpo-analyze').disabled = state.busy || !writable() || !data || data.status === 'registered' || data.issues.length > 0 || !data.pending_descriptions;
    el('bpo-register').disabled = state.busy || !writable() || !data || data.status === 'registered' || data.issues.length > 0 || data.pending_descriptions > 0;
    el('bpo-preview-prev').disabled = state.busy || !data || data.offset === 0;
    el('bpo-preview-next').disabled = state.busy || !data || data.offset + data.limit >= data.total;
  }
  function cell(row, text) {
    const td = document.createElement('td');
    td.textContent = text;
    row.append(td);
    return td;
  }
  function render(data) {
    state.preview = data;
    const tbody = el('bpo-preview-body');
    tbody.replaceChildren();
    for (const group of data.results) {
      const row = document.createElement('tr');
      const selected = group.candidates.find(c => c.id === group.selected_description_id);
      cell(row, dateLabel(group.date));
      cell(row, selected ? selected.description : 'Aguardando seleção da descrição pela IA');
      cell(row, group.type === 'entrada' ? 'Entrada' : 'Saída');
      cell(row, amountLabel(group.amount)).className = 'text-right mono';
      const details = document.createElement('details');
      const summary = document.createElement('summary');
      summary.textContent = `${group.candidates.length} fonte(s)${group.issues.length ? ' — revisar' : ''}`;
      details.append(summary);
      const list = document.createElement('ul');
      for (const candidate of group.candidates) {
        const item = document.createElement('li');
        const source = data.sources.find(s => s.id === candidate.source_id);
        const fields = Object.entries(group.field_sources).filter(([, id]) => id === candidate.id).map(([key]) => ({date:'data', amount:'valor', type:'tipo'}[key])).join(', ');
        item.textContent = `${source?.filename || candidate.format} — ${candidate.location}: ${candidate.description}. ${fields ? `Fonte de ${fields}.` : ''}`;
        list.append(item);
      }
      for (const text of [...group.issues, ...(group.selection_reason ? [group.selection_reason] : [])]) {
        const item = document.createElement('li'); item.textContent = text; list.append(item);
      }
      details.append(list); cell(row, '').append(details); tbody.append(row);
    }
    el('bpo-source-summary').replaceChildren();
    for (const source of data.sources) {
      const item = document.createElement('li');
      item.textContent = `${source.filename}: ${source.transactions} movimentos; ${source.excluded_balances} linhas de saldo excluídas${source.currency !== 'BRL' ? `; moeda declarada ${source.currency}, valor exige outra fonte` : ''}.`;
      el('bpo-source-summary').append(item);
    }
    el('bpo-preview-page').textContent = `${data.total ? data.offset + 1 : 0}–${Math.min(data.offset + data.results.length, data.total)} de ${data.total}`;
    message(data.issues.length ? `Registro bloqueado: ${data.issues.join(' ')}` : `${data.total} transações. ${data.pending_descriptions} descrições aguardando IA. Estado: ${data.status === 'registered' ? 'registrado' : 'prévia'}.`);
    controls();
  }
  async function guarded(work) {
    if (state.busy || !company()) return;
    const generation = state.generation;
    const controller = new AbortController();
    state.controller = controller; state.busy = true; controls();
    try {
      await work(async (path, options = {}) => {
        const result = await ApiClient.request(base + path, {...options, signal: controller.signal});
        if (generation !== state.generation) throw new DOMException('Contexto alterado', 'AbortError');
        return result;
      });
    } catch (error) {
      if (generation === state.generation) message(error.name === 'AbortError' ? 'Análise interrompida. Retome a importação para consultar o último lote concluído.' : error.message);
    } finally {
      if (generation === state.generation) { state.busy = false; state.controller = null; el('bpo-stop').disabled = true; controls(); }
    }
  }
  async function ledger(request) {
    const data = await request(`/transactions?offset=${state.ledgerOffset}&limit=100`);
    el('bpo-ledger-body').replaceChildren();
    for (const item of data.results) {
      const row = document.createElement('tr');
      cell(row, item.account_key); cell(row, dateLabel(item.date)); cell(row, item.description);
      cell(row, item.type === 'entrada' ? 'Entrada' : 'Saída'); cell(row, amountLabel(item.amount)).className = 'text-right mono';
      el('bpo-ledger-body').append(row);
    }
    el('bpo-ledger-page').textContent = `${data.total ? data.offset + 1 : 0}–${data.offset + data.results.length} de ${data.total}`;
    el('bpo-ledger-prev').disabled = data.offset === 0;
    el('bpo-ledger-next').disabled = data.offset + data.limit >= data.total;
  }
  async function refresh() {
    return guarded(async request => {
      const imports = await request('/imports?limit=100');
      el('bpo-imports').replaceChildren(new Option('Escolha uma importação', ''));
      for (const item of imports) el('bpo-imports').append(new Option(`${item.account_key} — ${item.created_at.slice(0, 10)} — ${item.status}`, item.id));
      if (state.preview) el('bpo-imports').value = state.preview.id;
      await ledger(request);
      if (!state.preview) message('Envie os arquivos complementares da mesma conta ou retome uma importação.');
    });
  }
  function reset() {
    state.generation += 1; state.controller?.abort(); state.controller = null; state.busy = false;
    state.preview = null; state.ledgerOffset = 0;
    if (!el('bpo-statement-form')) return;
    el('bpo-statement-form').reset();
    const year = String(new Date().getFullYear());
    el('bpo-date-from').value = `${year}-01-01`; el('bpo-date-to').value = `${year}-12-31`;
    for (const id of ['bpo-preview-body','bpo-ledger-body','bpo-source-summary','bpo-preview-page','bpo-ledger-page']) el(id).replaceChildren();
    el('bpo-imports').replaceChildren(new Option('Escolha uma importação', ''));
    el('bpo-stop').disabled = true;
    message('Selecione uma empresa e envie os extratos da conta informada.'); controls();
  }
  document.addEventListener('DOMContentLoaded', () => {
    reset();
    el('bpo-statement-form').addEventListener('submit', event => {
      event.preventDefault();
      const files = [...el('bpo-files').files];
      if (!files.length || files.length > 12 || files.some(f => f.size > 10 * 1024 * 1024)) { message('Envie de 1 a 12 arquivos, com até 10 MiB cada.'); return; }
      const body = new FormData(event.currentTarget);
      void guarded(async request => { message('Extraindo e cruzando as fontes…'); render(await request('/imports', {method:'POST', body})); });
    });
    el('bpo-imports').addEventListener('change', event => {
      const id = event.target.value; if (id) void guarded(async request => render(await request(`/imports/${encodeURIComponent(id)}`)));
    });
    el('bpo-reload').addEventListener('click', refresh);
    el('bpo-analyze').addEventListener('click', () => void guarded(async request => {
      el('bpo-stop').disabled = false;
      while (state.preview?.pending_descriptions) {
        message(`Comparando descrições pela API de IA: ${state.preview.pending_descriptions} pendentes…`);
        render(await request(`/imports/${state.preview.id}/descriptions`, {method:'POST'}));
      }
    }));
    el('bpo-stop').addEventListener('click', () => state.controller?.abort());
    el('bpo-register').addEventListener('click', () => void guarded(async request => {
      const id = state.preview.id;
      const result = await request(`/imports/${id}/register`, {method:'POST'});
      render(await request(`/imports/${id}`)); await ledger(request);
      message(`Registro concluído: ${result.registered} transações. A repetição do mesmo lote não duplica registros.`);
    }));
    for (const [name, direction] of [['prev',-1],['next',1]]) {
      el(`bpo-preview-${name}`).addEventListener('click', () => void guarded(async request => {
        const offset = Math.max(0, state.preview.offset + direction * 100);
        render(await request(`/imports/${state.preview.id}?offset=${offset}&limit=100`));
      }));
      el(`bpo-ledger-${name}`).addEventListener('click', () => void guarded(async request => {
        state.ledgerOffset = Math.max(0, state.ledgerOffset + direction * 100); await ledger(request);
      }));
    }
  });
  window.BpoStatements = {reset, refresh, amountLabel};
})();
