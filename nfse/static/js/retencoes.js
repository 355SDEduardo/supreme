/* Consulta de retenções com filtro independente de competência. */
const Retencoes = (() => {
  let requestId = 0;
  let controller = null;
  const money = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' });
  const fields = ['iss', 'inss', 'pis', 'cofins', 'irrf', 'csll', 'total_declarado', 'total_identificado'];
  const summaryIds = ['Iss', 'Inss', 'Pis', 'Cofins', 'Irrf', 'Csll', 'TotalDeclarado', 'TotalIdentificado'];
  const formatMonth = (value) => value ? `${value.slice(5, 7)}/${value.slice(0, 4)}` : 'Todas as competências';

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
      const response = await fetch(`/api/retencoes?${params}`, { signal: requestController.signal });
      if (!response.ok) throw new Error('Falha ao consultar retenções');
      const report = await response.json();
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

  document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('retencoesCompetencia').addEventListener('change', refresh);
    document.getElementById('btnClearRetencoesFilter').addEventListener('click', () => {
      document.getElementById('retencoesCompetencia').value = '';
      refresh();
    });
    document.getElementById('btnRetryRetencoes').addEventListener('click', refresh);
  });

  return { refresh };
})();
