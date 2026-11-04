/* Consulta de retenções com filtro independente de competência e utilitários de cálculo. */
const Retencoes = (() => {
  let requestId = 0;
  let controller = null;
  const money = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' });
  const fields = ['iss', 'inss', 'pis', 'cofins', 'irrf', 'csll', 'total_declarado', 'total_identificado'];
  const summaryIds = ['Iss', 'Inss', 'Pis', 'Cofins', 'Irrf', 'Csll', 'TotalDeclarado', 'TotalIdentificado'];
  const formatMonth = (value) => value ? `${value.slice(5, 7)}/${value.slice(0, 4)}` : 'Todas as competências';

  function toCents(value) {
    const num = Number(value);
    return Number.isFinite(num) ? Math.round(num * 100) : 0;
  }

  function fromCents(cents) {
    return Number((cents / 100).toFixed(2));
  }

  function computeNotaRetencoes(note = {}) {
    const ret = note.retencoes || {};
    const federal = note.tributos_federais || {};
    const pisCofinsRetidos = [1, 2].includes(federal.tp_retencao_pis_cofins);
    const issRetido = Boolean(ret.iss_retido ?? note.iss_retido ?? [2, 3].includes(note.tipo_retencao_issqn));
    const iss = issRetido ? toCents(ret.iss ?? note.valor_iss ?? note.valor_issqn) : 0;
    const irrf = toCents(ret.irrf ?? note.valor_irrf ?? federal.valor_ret_irrf);
    const inss = toCents(ret.inss ?? note.valor_inss ?? federal.valor_ret_cp_inss);
    const csrfExplicit = toCents(ret.csrf);
    const csrfParts =
      toCents(ret.pis ?? note.valor_pis ?? (pisCofinsRetidos ? federal.valor_pis : 0)) +
      toCents(ret.cofins ?? note.valor_cofins ?? (pisCofinsRetidos ? federal.valor_cofins : 0)) +
      toCents(ret.csll ?? note.valor_csll ?? federal.valor_ret_csll);
    const csrf = csrfExplicit > 0 ? csrfExplicit : csrfParts;
    const known = iss + irrf + inss + csrf;

    const reportedTotal = toCents(
      ret.total_retencoes !== undefined ? ret.total_retencoes : note.valor_total_retencoes
    );
    const inferredTotal =
      (note.valor_servicos ?? note.valor_servico) !== undefined && note.valor_liquido !== undefined
        ? Math.max(0, toCents(note.valor_servicos ?? note.valor_servico) - toCents(note.valor_liquido))
        : 0;
    const total = Math.max(known, reportedTotal, inferredTotal);
    const outros = Math.max(0, total - known);

    return {
      iss: fromCents(iss),
      irrf: fromCents(irrf),
      inss: fromCents(inss),
      csrf: fromCents(csrf),
      outros: fromCents(outros),
      total: fromCents(total),
    };
  }

  function computeRetencoesTotals(notes = [], stats = {}) {
    if (Array.isArray(notes) && notes.length > 0) {
      const acc = { iss: 0, irrf: 0, inss: 0, csrf: 0, outros: 0, total: 0 };
      for (const note of notes) {
        const item = computeNotaRetencoes(note);
        acc.iss += toCents(item.iss);
        acc.irrf += toCents(item.irrf);
        acc.inss += toCents(item.inss);
        acc.csrf += toCents(item.csrf);
        acc.outros += toCents(item.outros);
        acc.total += toCents(item.total);
      }
      return {
        iss: fromCents(acc.iss),
        irrf: fromCents(acc.irrf),
        inss: fromCents(acc.inss),
        csrf: fromCents(acc.csrf),
        outros: fromCents(acc.outros),
        total: fromCents(acc.total),
      };
    }

    const iss = toCents(stats.total_iss_retido);
    const irrf = toCents(stats.total_irrf);
    const inss = toCents(stats.total_inss);
    const csrfExplicit = toCents(stats.total_csrf);
    const csrfParts =
      toCents(stats.total_pis) + toCents(stats.total_cofins) + toCents(stats.total_csll);
    const csrf = csrfExplicit > 0 ? csrfExplicit : csrfParts;
    const known = iss + irrf + inss + csrf;
    const reportedTotal = toCents(stats.valor_total_retencoes);
    const total = Math.max(known, reportedTotal);
    const outros = Math.max(0, total - known);

    return {
      iss: fromCents(iss),
      irrf: fromCents(irrf),
      inss: fromCents(inss),
      csrf: fromCents(csrf),
      outros: fromCents(outros),
      total: fromCents(total),
    };
  }

  function renderReport(report, selected) {
    const select = document.getElementById('retencoesCompetencia');
    const months = new Set(report.competencias);
    // Manter o período selecionado mesmo após excluir a última nota desse mês.
    if (selected) months.add(selected);
    select.replaceChildren(new Option('Todas as competências', ''));
    [...months].sort().reverse().forEach((month) => select.add(new Option(formatMonth(month), month)));
    select.value = selected;

    fields.forEach((field, index) => {
      document.getElementById(`retencoes${summaryIds[index]}`).textContent = money.format(report.totais[field]);
    });
    const difference = document.getElementById('retencoesDifference');
    difference.textContent = `Total declarado: informado nas notas. Tributos identificados: soma de ISS, INSS, PIS, COFINS, IRRF e CSLL retidos. Diferença do período (declarado − identificado): ${money.format(report.totais.diferenca)}.`;

    const period = formatMonth(selected);
    document.getElementById('retencoesCaption').textContent = `Notas com retenções · ${period} · valores em reais (R$)`;
    const tbody = document.getElementById('retencoesTableBody');
    const fragment = document.createDocumentFragment();
    report.notas.forEach((note) => {
      const row = document.createElement('tr');
      const values = [`#${note.numero_nfse}`, formatMonth(note.competencia), note.tomador,
        ...fields.map((field) => money.format(note[field]))];
      values.forEach((value) => {
        const cell = document.createElement('td');
        cell.textContent = value;
        row.appendChild(cell);
      });
      fragment.appendChild(row);
    });
    if (!report.notas.length) {
      const row = document.createElement('tr');
      const cell = document.createElement('td');
      cell.colSpan = 11;
      cell.textContent = report.total_notas_periodo
        ? 'Nenhuma retenção encontrada nesta competência. Selecione outro período ou limpe o filtro.'
        : 'Nenhuma nota neste período. Importe arquivos XML ou selecione outra competência.';
      row.appendChild(cell);
      fragment.appendChild(row);
    }
    tbody.replaceChildren(fragment);
    document.getElementById('retencoesStatus').textContent = `${period}: ${report.total_notas_retencao} nota(s) com retenção de ${report.total_notas_periodo} nota(s) no período.`;
  }

  async function refresh() {
    const select = document.getElementById('retencoesCompetencia');
    if (!select) return;
    const selected = select.value;
    const id = ++requestId;
    controller?.abort();
    const requestController = new AbortController();
    controller = requestController;
    const results = document.getElementById('retencoesResults');
    const status = document.getElementById('retencoesStatus');
    const retry = document.getElementById('btnRetryRetencoes');
    document.getElementById('btnClearRetencoesFilter').disabled = !selected;
    results.hidden = true;
    retry.hidden = true;
    status.textContent = `Carregando retenções · ${formatMonth(selected)}...`;
    const params = new URLSearchParams();
    if (selected) params.set('competencia', selected);
    const timeout = setTimeout(() => requestController.abort(), 15000);
    try {
      const report = await ApiClient.request(`/nfse/retencoes?${params}`, { signal: requestController.signal });
      if (id !== requestId) return;
      renderReport(report, selected);
      results.hidden = false;
    } catch (error) {
      if (id !== requestId) return;
      status.textContent = 'Não foi possível carregar as retenções. Confira a conexão e tente novamente.';
      retry.hidden = false;
    } finally {
      clearTimeout(timeout);
    }
  }

  if (typeof document !== 'undefined' && typeof document.addEventListener === 'function') {
    document.addEventListener('DOMContentLoaded', () => {
      const compEl = document.getElementById('retencoesCompetencia');
      const clearEl = document.getElementById('btnClearRetencoesFilter');
      const retryEl = document.getElementById('btnRetryRetencoes');
      if (compEl) compEl.addEventListener('change', refresh);
      if (clearEl) clearEl.addEventListener('click', () => {
        if (compEl) compEl.value = '';
        refresh();
      });
      if (retryEl) retryEl.addEventListener('click', refresh);
    });
  }

  function reset() {
    requestId += 1;
    controller?.abort();
    const select = document.getElementById('retencoesCompetencia');
    if (select) select.value = '';
    const results = document.getElementById('retencoesResults');
    if (results) results.hidden = true;
  }

  const api = { refresh, reset, computeNotaRetencoes, computeRetencoesTotals };
  if (typeof globalThis !== 'undefined') {
    globalThis.NfseRetencoes = api;
  }
  if (typeof module === 'object' && module.exports) {
    module.exports = api;
  }
  return api;
})();
