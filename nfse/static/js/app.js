/**
 * NFS-e Nacional Intelligence Suite - Frontend Application Logic
 * Integrates Chart.js, REST API, Drag-and-Drop Upload, Filter Engine, and Modal DANFSE Viewer
 */

// Estado da Aplicação
const AppState = {
  notes: [],
  stats: null,
  charts: {},
  currentNote: null,
  filters: {
    search: '',
    retencao: '',
    status_conciliacao: '',
    municipio: '',
  },
};

// Formatação Monetária e Numérica PT-BR
const Formatters = {
  currency: (val) => {
    const num = typeof val === 'number' ? val : parseFloat(val) || 0;
    return new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(num);
  },
  percent: (val) => {
    const num = typeof val === 'number' ? val : parseFloat(val) || 0;
    return `${num.toFixed(2)}%`;
  },
  date: (val) => {
    if (!val) return '-';
    try {
      const d = new Date(val);
      return d.toLocaleDateString('pt-BR', { timeZone: 'UTC' });
    } catch {
      return val;
    }
  },
  datetime: (val) => {
    if (!val) return '-';
    try {
      const d = new Date(val);
      return d.toLocaleString('pt-BR');
    } catch {
      return val;
    }
  },
};

// Toast Notifications
function showToast(message, type = 'success') {
  const container = document.getElementById('toastContainer');
  if (!container) return;

  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.innerHTML = `
    <span>${type === 'success' ? '✓' : type === 'error' ? '⚠' : 'ℹ'}</span>
    <div>${message}</div>
  `;
  container.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateX(100%)';
    setTimeout(() => toast.remove(), 300);
  }, 4000);
}

// Inicialização Principal
document.addEventListener('DOMContentLoaded', () => {
  initEventListeners();
  loadDashboardData();
});

// Configuração de Listeners
function initEventListeners() {
  // Upload Drag & Drop
  const dropzone = document.getElementById('uploadHero');
  const fileInput = document.getElementById('fileInput');

  if (dropzone && fileInput) {
    dropzone.addEventListener('click', () => fileInput.click());

    ['dragenter', 'dragover'].forEach((eventName) => {
      dropzone.addEventListener(eventName, (e) => {
        e.preventDefault();
        dropzone.classList.add('drag-over');
      });
    });

    ['dragleave', 'drop'].forEach((eventName) => {
      dropzone.addEventListener(eventName, (e) => {
        e.preventDefault();
        dropzone.classList.remove('drag-over');
      });
    });

    dropzone.addEventListener('drop', (e) => {
      const files = e.dataTransfer.files;
      if (files && files.length > 0) {
        handleFileUpload(files);
      }
    });

    fileInput.addEventListener('change', (e) => {
      if (e.target.files && e.target.files.length > 0) {
        handleFileUpload(e.target.files);
      }
    });
  }

  // Ações do Cabeçalho
  const btnSamples = document.getElementById('btnLoadSamples');
  if (btnSamples) btnSamples.addEventListener('click', loadSampleData);

  const btnExcel = document.getElementById('btnExportExcel');
  if (btnExcel) btnExcel.addEventListener('click', () => window.open('/api/export/excel', '_blank'));

  const btnCsv = document.getElementById('btnExportCsv');
  if (btnCsv) btnCsv.addEventListener('click', () => window.open('/api/export/csv', '_blank'));

  const btnJson = document.getElementById('btnExportJson');
  if (btnJson) btnJson.addEventListener('click', () => window.open('/api/export/json', '_blank'));

  const btnClear = document.getElementById('btnClearDb');
  if (btnClear) btnClear.addEventListener('click', clearDatabase);

  // Filtros de Tabela
  const searchInput = document.getElementById('searchInput');
  if (searchInput) {
    let timeout = null;
    searchInput.addEventListener('input', (e) => {
      clearTimeout(timeout);
      timeout = setTimeout(() => {
        AppState.filters.search = e.target.value;
        loadNotesTable();
      }, 250);
    });
  }

  const selectRetencao = document.getElementById('filterRetencao');
  if (selectRetencao) {
    selectRetencao.addEventListener('change', (e) => {
      AppState.filters.retencao = e.target.value;
      loadNotesTable();
    });
  }

  const selectStatus = document.getElementById('filterStatus');
  if (selectStatus) {
    selectStatus.addEventListener('change', (e) => {
      AppState.filters.status_conciliacao = e.target.value;
      loadNotesTable();
    });
  }

  // Modal Close & Tabs
  const modalClose = document.getElementById('modalCloseBtn');
  const modalOverlay = document.getElementById('modalOverlay');
  if (modalClose && modalOverlay) {
    modalClose.addEventListener('click', closeModal);
    modalOverlay.addEventListener('click', (e) => {
      if (e.target === modalOverlay) closeModal();
    });
  }

  document.querySelectorAll('.tab-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.tab-btn').forEach((b) => b.classList.remove('active'));
      document.querySelectorAll('.tab-content').forEach((c) => c.classList.remove('active'));

      btn.classList.add('active');
      const tabTarget = btn.getAttribute('data-tab');
      const targetContent = document.getElementById(`tab-${tabTarget}`);
      if (targetContent) targetContent.classList.add('active');
    });
  });

  // Theme Toggle
  const themeToggle = document.getElementById('themeToggleBtn');
  if (themeToggle) {
    themeToggle.addEventListener('click', () => {
      const current = document.documentElement.getAttribute('data-theme') || 'dark';
      const next = current === 'dark' ? 'light' : 'dark';
      document.documentElement.setAttribute('data-theme', next);
      themeToggle.textContent = next === 'dark' ? '🌙' : '☀️';
      updateChartsTheme();
    });
  }
}

// Upload de Arquivos
async function handleFileUpload(fileList) {
  const formData = new FormData();
  let count = 0;
  for (let i = 0; i < fileList.length; i++) {
    const file = fileList[i];
    if (file.name.toLowerCase().endsWith('.xml') || file.name.toLowerCase().endsWith('.zip')) {
      formData.append('files', file);
      count++;
    }
  }

  if (count === 0) {
    showToast('Selecione arquivos .xml ou .zip de NFS-e!', 'error');
    return;
  }

  showToast(`Enviando ${count} arquivo(s) para extração...`, 'info');

  try {
    const res = await fetch('/api/upload', {
      method: 'POST',
      body: formData,
    });
    const result = await res.json();

    if (result.success) {
      showToast(`${result.processed_count} nota(s) processada(s) e armazenadas em .json!`, 'success');
      if (result.error_count > 0) {
        showToast(`${result.error_count} erro(s) durante o parsing.`, 'error');
      }
      loadDashboardData();
    } else {
      showToast('Falha no upload de arquivos.', 'error');
    }
  } catch (err) {
    showToast(`Erro na requisição: ${err.message}`, 'error');
  }
}

// Carregar Amostras dos Casos Documentados
async function loadSampleData() {
  showToast('Carregando amostras oficiais (Docs 1, 16, 18, 20)...', 'info');
  try {
    const res = await fetch('/api/load-samples', { method: 'POST' });
    const data = await res.json();
    if (data.success) {
      showToast(data.message, 'success');
      loadDashboardData();
    }
  } catch (err) {
    showToast(`Erro ao carregar amostras: ${err.message}`, 'error');
  }
}

// Limpar Base
async function clearDatabase() {
  if (!confirm('Deseja realmente limpar todas as notas fiscais e arquivos salvos?')) return;

  try {
    const res = await fetch('/api/notes', { method: 'DELETE' });
    const data = await res.json();
    if (data.success) {
      showToast('Base de dados e arquivos JSON limpos.', 'info');
      loadDashboardData();
    }
  } catch (err) {
    showToast(`Erro ao limpar base: ${err.message}`, 'error');
  }
}

// Carregar Dados e Atualizar Dashboard
async function loadDashboardData() {
  // Atualizar o módulo após upload, carga de amostras e exclusão de notas.
  Retencoes.refresh();
  try {
    // 1. Carregar Stats
    const statsRes = await fetch('/api/dashboard/stats');
    AppState.stats = await statsRes.json();
    renderKPIs(AppState.stats);
    renderCharts(AppState.stats);

    // 2. Carregar Tabela de Notas
    await loadNotesTable();
  } catch (err) {
    console.error('Erro ao carregar dados do dashboard:', err);
  }
}

// Renderizar KPIs
function renderKPIs(stats) {
  if (!stats) return;

  document.getElementById('kpiBruto').textContent = Formatters.currency(stats.faturamento_bruto);
  document.getElementById('kpiLiquido').textContent = Formatters.currency(stats.faturamento_liquido);
  document.getElementById('kpiRetencoes').textContent = Formatters.currency(stats.total_retencoes);
  
  const pctRet = stats.faturamento_bruto > 0 
    ? ((stats.total_retencoes / stats.faturamento_bruto) * 100).toFixed(1)
    : '0.0';
  document.getElementById('kpiRetencoesPct').textContent = `${pctRet}% da receita`;

  document.getElementById('kpiIssProprio').textContent = Formatters.currency(stats.iss_proprio);
  document.getElementById('kpiIssRetido').textContent = Formatters.currency(stats.iss_retido);
  document.getElementById('kpiInss').textContent = Formatters.currency(stats.inss_retido);
  document.getElementById('kpiPisCofins').textContent = Formatters.currency(stats.pis_cofins_total);

  document.getElementById('kpiConformidade').textContent = `${stats.taxa_conformidade}%`;
  document.getElementById('kpiNotasCount').textContent = `${stats.total_notas} notas cadastradas`;
}

// Renderizar Gráficos (Chart.js)
function renderCharts(stats) {
  if (!window.Chart || !stats) return;

  // 1. Evolução Temporal de Faturamento
  const ctxTimeline = document.getElementById('chartTimeline')?.getContext('2d');
  if (ctxTimeline) {
    if (AppState.charts.timeline) AppState.charts.timeline.destroy();

    const labels = stats.timeline.map((t) => t.competencia);
    const brutos = stats.timeline.map((t) => t.bruto);
    const liquidos = stats.timeline.map((t) => t.liquido);
    const retencoes = stats.timeline.map((t) => t.retencoes);

    AppState.charts.timeline = new Chart(ctxTimeline, {
      type: 'bar',
      data: {
        labels: labels.length ? labels : ['Sem dados'],
        datasets: [
          {
            label: 'Faturamento Bruto (vServ)',
            data: brutos.length ? brutos : [0],
            backgroundColor: 'rgba(59, 130, 246, 0.7)',
            borderColor: '#3b82f6',
            borderWidth: 1,
            borderRadius: 6,
          },
          {
            label: 'Faturamento Líquido (vLiq)',
            data: liquidos.length ? liquidos : [0],
            backgroundColor: 'rgba(16, 185, 129, 0.7)',
            borderColor: '#10b981',
            borderWidth: 1,
            borderRadius: 6,
          },
          {
            label: 'Total Retenções',
            data: retencoes.length ? retencoes : [0],
            backgroundColor: 'rgba(245, 158, 11, 0.7)',
            borderColor: '#f59e0b',
            borderWidth: 1,
            borderRadius: 6,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            position: 'top',
            labels: { color: '#94a3b8', font: { family: 'Outfit' } },
          },
          tooltip: {
            callbacks: {
              label: (ctx) => `${ctx.dataset.label}: ${Formatters.currency(ctx.parsed.y)}`,
            },
          },
        },
        scales: {
          x: {
            grid: { color: 'rgba(255, 255, 255, 0.05)' },
            ticks: { color: '#94a3b8' },
          },
          y: {
            grid: { color: 'rgba(255, 255, 255, 0.05)' },
            ticks: {
              color: '#94a3b8',
              callback: (v) => Formatters.currency(v),
            },
          },
        },
      },
    });
  }

  // 2. Composição das Retenções (Donut)
  const ctxRetencoes = document.getElementById('chartRetencoes')?.getContext('2d');
  if (ctxRetencoes) {
    if (AppState.charts.retencoes) AppState.charts.retencoes.destroy();

    const retLabels = Object.keys(stats.composicao_retencoes);
    const retValues = Object.values(stats.composicao_retencoes);
    const hasData = retValues.some((v) => v > 0);

    AppState.charts.retencoes = new Chart(ctxRetencoes, {
      type: 'doughnut',
      data: {
        labels: retLabels,
        datasets: [
          {
            data: hasData ? retValues : [1],
            backgroundColor: hasData
              ? ['#06b6d4', '#10b981', '#f59e0b', '#8b5cf6']
              : ['rgba(255, 255, 255, 0.05)'],
            borderColor: 'rgba(17, 24, 39, 0.8)',
            borderWidth: 2,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        cutout: '70%',
        plugins: {
          legend: {
            position: 'bottom',
            labels: { color: '#94a3b8', boxWidth: 12 },
          },
          tooltip: {
            callbacks: {
              label: (ctx) => `${ctx.label}: ${Formatters.currency(ctx.parsed)}`,
            },
          },
        },
      },
    });
  }

  // 3. Top Tomadores
  const ctxTomadores = document.getElementById('chartTomadores')?.getContext('2d');
  if (ctxTomadores) {
    if (AppState.charts.tomadores) AppState.charts.tomadores.destroy();

    const topToma = stats.top_tomadores.slice(0, 5);
    const names = topToma.map((t) => (t.nome.length > 22 ? t.nome.substring(0, 22) + '...' : t.nome));
    const vals = topToma.map((t) => t.total_faturado);

    AppState.charts.tomadores = new Chart(ctxTomadores, {
      type: 'bar',
      data: {
        labels: names.length ? names : ['Nenhum tomador'],
        datasets: [
          {
            label: 'Volume Faturado',
            data: vals.length ? vals : [0],
            backgroundColor: 'rgba(6, 182, 212, 0.65)',
            borderColor: '#06b6d4',
            borderWidth: 1,
            borderRadius: 4,
          },
        ],
      },
      options: {
        indexAxis: 'y',
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: (ctx) => `Faturado: ${Formatters.currency(ctx.parsed.x)}`,
            },
          },
        },
        scales: {
          x: {
            grid: { color: 'rgba(255, 255, 255, 0.05)' },
            ticks: {
              color: '#94a3b8',
              callback: (v) => Formatters.currency(v),
            },
          },
          y: {
            grid: { display: false },
            ticks: { color: '#94a3b8' },
          },
        },
      },
    });
  }

  // 4. Distribuição por Município
  const ctxMunicipios = document.getElementById('chartMunicipios')?.getContext('2d');
  if (ctxMunicipios) {
    if (AppState.charts.municipios) AppState.charts.municipios.destroy();

    const muns = stats.por_municipio.slice(0, 5);
    const mNames = muns.map((m) => m.municipio);
    const mVals = muns.map((m) => m.valor);

    AppState.charts.municipios = new Chart(ctxMunicipios, {
      type: 'bar',
      data: {
        labels: mNames.length ? mNames : ['Sem municípios'],
        datasets: [
          {
            label: 'Faturamento por Localidade',
            data: mVals.length ? mVals : [0],
            backgroundColor: 'rgba(99, 102, 241, 0.65)',
            borderColor: '#6366f1',
            borderWidth: 1,
            borderRadius: 4,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: (ctx) => `Total: ${Formatters.currency(ctx.parsed.y)}`,
            },
          },
        },
        scales: {
          x: {
            grid: { display: false },
            ticks: { color: '#94a3b8' },
          },
          y: {
            grid: { color: 'rgba(255, 255, 255, 0.05)' },
            ticks: {
              color: '#94a3b8',
              callback: (v) => Formatters.currency(v),
            },
          },
        },
      },
    });
  }
}

function updateChartsTheme() {
  if (AppState.stats) {
    renderCharts(AppState.stats);
  }
}

// Carregar Tabela com Filtros
async function loadNotesTable() {
  const tbody = document.getElementById('notesTableBody');
  const emptyState = document.getElementById('emptyState');
  if (!tbody) return;

  const params = new URLSearchParams();
  if (AppState.filters.search) params.append('search', AppState.filters.search);
  if (AppState.filters.retencao) params.append('retencao', AppState.filters.retencao);
  if (AppState.filters.status_conciliacao) params.append('status_conciliacao', AppState.filters.status_conciliacao);

  try {
    const res = await fetch(`/api/notes?${params.toString()}`);
    AppState.notes = await res.json();

    if (AppState.notes.length === 0) {
      tbody.innerHTML = '';
      if (emptyState) emptyState.style.display = 'flex';
      return;
    }

    if (emptyState) emptyState.style.display = 'none';

    tbody.innerHTML = AppState.notes
      .map((note) => {
        const tomaName = note.tomador.razao_social || note.tomador.cnpj || 'Tomador não informado';
        const docFmt = note.tomador.documento_formatado || '-';
        const retencaoBadge = note.iss_retido_pelo_tomador
          ? '<span class="badge-status alerta">ISS Retido</span>'
          : '<span class="badge-status">Próprio</span>';

        const statusClass =
          note.auditoria.status_conciliacao === 'CONCILIADO'
            ? 'conciliado'
            : note.auditoria.status_conciliacao === 'ALERTA'
            ? 'alerta'
            : 'inconsistente';

        return `
        <tr>
          <td>
            <div style="font-weight: 700; color: #fff;">#${note.numero_nfse}</div>
            <div style="display: flex; align-items: center; gap: 4px; margin-top: 2px;">
              <span class="cell-chave" title="${note.chave_nfse}">${note.chave_nfse}</span>
              <button class="copy-btn" onclick="copyToClipboard('${note.chave_nfse}')" title="Copiar chave">📋</button>
            </div>
          </td>
          <td>
            <div>${Formatters.date(note.data_competencia)}</div>
            <div style="font-size: 0.72rem; color: #64748b;">${Formatters.datetime(note.data_hora_processamento)}</div>
          </td>
          <td>
            <div class="participant-cell">
              <span class="participant-name" title="${tomaName}">${tomaName}</span>
              <span class="participant-doc">${docFmt}</span>
            </div>
          </td>
          <td>
            <div>${note.local_prestacao || note.local_incidencia || '-'}</div>
            <div style="font-size: 0.72rem; color: #64748b;">${note.codigo_tributacao_nacional || ''}</div>
          </td>
          <td class="val-money">${Formatters.currency(note.valor_servico)}</td>
          <td class="val-money ${note.valor_total_retencoes > 0 ? 'val-amber' : ''}">
            ${Formatters.currency(note.valor_total_retencoes)}
            <div style="margin-top: 2px;">${retencaoBadge}</div>
          </td>
          <td class="val-money val-green">${Formatters.currency(note.valor_liquido)}</td>
          <td>
            <span class="badge-status ${statusClass}">${note.auditoria.status_conciliacao}</span>
          </td>
          <td>
            <div class="table-actions">
              <button class="table-btn" onclick="openNoteDetail('${note.chave_nfse}')" title="Visualizar Detalhes e DANFSE">
                🔍 Ver
              </button>
              <button class="table-btn" onclick="downloadSingleJson('${note.chave_nfse}')" title="Baixar JSON">
                { }
              </button>
              <button class="table-btn delete" onclick="deleteNote('${note.chave_nfse}')" title="Remover">
                ✕
              </button>
            </div>
          </td>
        </tr>
      `;
      })
      .join('');
  } catch (err) {
    console.error('Erro ao listar notas:', err);
  }
}

// Abrir Modal com Detalhes da Nota e Espelho DANFSE
async function openNoteDetail(chave) {
  try {
    const res = await fetch(`/api/notes/${chave}`);
    if (!res.ok) throw new Error('Nota não encontrada');
    const note = await res.json();
    AppState.currentNote = note;

    document.getElementById('modalTitle').textContent = `NFS-e Nº ${note.numero_nfse} - ${note.tomador.razao_social || ''}`;

    // 1. Renderizar Aba DANFSE
    renderDanfseTab(note);

    // 2. Renderizar Aba Tributação & Retenções
    renderTributosTab(note);

    // 3. Renderizar Aba Complementares & PIX
    renderComplementaresTab(note);

    // 4. Renderizar Aba Auditoria & Assinatura
    renderAuditoriaTab(note);

    // 5. Renderizar Aba JSON
    document.getElementById('jsonViewer').textContent = JSON.stringify(note, null, 2);

    // Abrir Modal
    document.getElementById('modalOverlay').classList.add('active');
  } catch (err) {
    showToast(`Erro ao abrir detalhes: ${err.message}`, 'error');
  }
}

// Renderizar Espelho DANFSE
function renderDanfseTab(n) {
  const container = document.getElementById('tab-danfse');
  if (!container) return;

  const emitEnd = n.emitente.endereco ? `${n.emitente.endereco.logradouro}, ${n.emitente.endereco.numero} - ${n.emitente.endereco.bairro}, ${n.local_emissao}/${n.emitente.endereco.uf || ''}` : '-';
  const tomaEnd = n.tomador.endereco ? `${n.tomador.endereco.logradouro}, ${n.tomador.endereco.numero} ${n.tomador.endereco.complemento || ''} - ${n.tomador.endereco.bairro}` : '-';

  container.innerHTML = `
    <div class="danfse-container">
      <div class="danfse-header">
        <div class="danfse-header-title">
          <h4>DOCUMENTO AUXILIAR DA NOTA FISCAL DE SERVIÇOS ELETRÔNICA (DANFSE)</h4>
          <p>Padrão Nacional RFB / SPED - Versão ${n.versao_leiaute}</p>
        </div>
        <div style="text-align: right;">
          <div style="font-size: 1.1rem; font-weight: 800; color: #0f172a;">NFS-e Nº ${n.numero_nfse}</div>
          <div style="font-size: 0.75rem; color: #64748b;">DPS Nº ${n.numero_dps} | Série ${n.serie_dps}</div>
          <div style="font-size: 0.72rem; color: #0284c7; font-weight: 600;">Status: ${n.status_descricao}</div>
        </div>
      </div>

      <div class="danfse-box" style="margin-bottom: 1rem;">
        <div class="danfse-row"><span class="label">Chave de Acesso da NFS-e:</span> <span class="value" style="font-family: monospace;">${n.chave_nfse}</span></div>
        <div class="danfse-row"><span class="label">Data/Hora de Processamento:</span> <span class="value">${Formatters.datetime(n.data_hora_processamento)}</span></div>
        <div class="danfse-row"><span class="label">Data de Competência do Fato Gerador:</span> <span class="value">${Formatters.date(n.data_competencia)}</span></div>
        <div class="danfse-row"><span class="label">Local de Incidência do ISS:</span> <span class="value">${n.local_incidencia} (IBGE: ${n.codigo_municipio_incidencia})</span></div>
      </div>

      <div class="danfse-grid-2">
        <div class="danfse-box">
          <div class="danfse-box-title">PRESTADOR DE SERVIÇOS (EMITENTE)</div>
          <div class="danfse-row"><span class="label">Razão Social:</span> <span class="value">${n.emitente.razao_social || '-'}</span></div>
          <div class="danfse-row"><span class="label">CNPJ:</span> <span class="value">${n.emitente.documento_formatado}</span></div>
          <div class="danfse-row"><span class="label">Endereço:</span> <span class="value">${emitEnd}</span></div>
          <div class="danfse-row"><span class="label">E-mail:</span> <span class="value">${n.emitente.email || '-'}</span></div>
          <div class="danfse-row"><span class="label">Regime Tributário:</span> <span class="value">${n.optante_simples_descricao}</span></div>
        </div>

        <div class="danfse-box">
          <div class="danfse-box-title">TOMADOR DE SERVIÇOS (CLIENTE)</div>
          <div class="danfse-row"><span class="label">Razão Social / Nome:</span> <span class="value">${n.tomador.razao_social || '-'}</span></div>
          <div class="danfse-row"><span class="label">CNPJ / CPF:</span> <span class="value">${n.tomador.documento_formatado}</span></div>
          <div class="danfse-row"><span class="label">Endereço:</span> <span class="value">${tomaEnd}</span></div>
          <div class="danfse-row"><span class="label">Município:</span> <span class="value">${n.local_prestacao}</span></div>
        </div>
      </div>

      <div class="danfse-box" style="margin-bottom: 1rem;">
        <div class="danfse-box-title">DISCRIMINAÇÃO DOS SERVIÇOS PRESTADOS</div>
        <div style="padding: 0.5rem 0; line-height: 1.6; color: #1e293b; white-space: pre-line;">${n.descricao_servico}</div>
        <div style="margin-top: 0.5rem; border-top: 1px dashed #cbd5e1; padding-top: 0.4rem; font-size: 0.75rem; color: #475569;">
          <strong>Tributação Nacional:</strong> ${n.codigo_tributacao_nacional} - ${n.tributacao_nacional_desc} | 
          <strong>NBS:</strong> ${n.codigo_nbs || 'N/A'} - ${n.nbs_desc || 'Não declarada'}
        </div>
      </div>

      <div class="danfse-box">
        <div class="danfse-box-title">DETALHAMENTO DE VALORES E TRIBUTOS</div>
        <div class="danfse-row"><span class="label">Valor Bruto do Serviço (vServ):</span> <span class="value">${Formatters.currency(n.valor_servico)}</span></div>
        <div class="danfse-row"><span class="label">Base de Cálculo do ISSQN:</span> <span class="value">${Formatters.currency(n.base_calculo)}</span></div>
        <div class="danfse-row"><span class="label">Alíquota Aplicada de ISS:</span> <span class="value">${Formatters.percent(n.aliquota_aplicada)}</span></div>
        <div class="danfse-row"><span class="label">Valor do ISSQN Apurado:</span> <span class="value">${Formatters.currency(n.valor_issqn)}</span></div>
        <div class="danfse-row"><span class="label">Tipo de Retenção do ISS:</span> <span class="value">${n.iss_retido_pelo_tomador ? 'RETIDO NA FONTE PELO TOMADOR' : 'NÃO RETIDO (RECOLHIMENTO PELO PRESTADOR)'}</span></div>
        <div class="danfse-row"><span class="label">Retenção Previdenciária INSS (CP):</span> <span class="value">${Formatters.currency(n.tributos_federais.valor_ret_cp_inss)}</span></div>
        <div class="danfse-row"><span class="label">Total de Retenções na Fonte:</span> <span class="value" style="color: #dc2626;">- ${Formatters.currency(n.valor_total_retencoes)}</span></div>
      </div>

      <div class="danfse-total-bar">
        <span>VALOR LÍQUIDO A RECEBER (vLiq):</span>
        <span style="font-size: 1.3rem;">${Formatters.currency(n.valor_liquido)}</span>
      </div>
    </div>
  `;
}

// Renderizar Aba de Tributos
function renderTributosTab(n) {
  const container = document.getElementById('tab-tributos');
  if (!container) return;

  const tf = n.tributos_federais;

  container.innerHTML = `
    <div style="display: flex; flex-direction: column; gap: 1.25rem;">
      <div class="danfse-box">
        <div class="danfse-box-title">TRIBUTAÇÃO MUNICIPAL (ISSQN)</div>
        <div class="danfse-row"><span class="label">Município de Incidência:</span> <span class="value">${n.local_incidencia} (Cód IBGE ${n.codigo_municipio_incidencia})</span></div>
        <div class="danfse-row"><span class="label">Base de Cálculo ISS:</span> <span class="value">${Formatters.currency(n.base_calculo)}</span></div>
        <div class="danfse-row"><span class="label">Alíquota Efetiva:</span> <span class="value">${Formatters.percent(n.aliquota_aplicada)}</span></div>
        <div class="danfse-row"><span class="label">Valor do ISS:</span> <span class="value">${Formatters.currency(n.valor_issqn)}</span></div>
        <div class="danfse-row"><span class="label">Responsabilidade do Recolhimento:</span> <span class="value">${n.iss_retido_pelo_tomador ? 'Tomador (Retenção na Fonte)' : 'Prestador (Guia Municipal)'}</span></div>
      </div>

      <div class="danfse-box">
        <div class="danfse-box-title">TRIBUTAÇÃO FEDERAL (PIS, COFINS, INSS, IRRF, CSLL)</div>
        <div class="danfse-row"><span class="label">CST PIS/COFINS:</span> <span class="value">${tf.cst || 'N/A'}</span></div>
        <div class="danfse-row"><span class="label">Base de Cálculo PIS/COFINS:</span> <span class="value">${Formatters.currency(tf.base_calculo)}</span></div>
        <div class="danfse-row"><span class="label">Alíquota PIS:</span> <span class="value">${Formatters.percent(tf.aliq_pis)} (Valor: ${Formatters.currency(tf.valor_pis)})</span></div>
        <div class="danfse-row"><span class="label">Alíquota COFINS:</span> <span class="value">${Formatters.percent(tf.aliq_cofins)} (Valor: ${Formatters.currency(tf.valor_cofins)})</span></div>
        <div class="danfse-row"><span class="label">Retenção de PIS/COFINS:</span> <span class="value">${tf.tp_retencao_pis_cofins === 2 ? 'Com Retenção' : 'Sem Retenção'}</span></div>
        <div class="danfse-row"><span class="label">Retenção Previdenciária INSS (CP):</span> <span class="value" style="font-weight: 700; color: #d97706;">${Formatters.currency(tf.valor_ret_cp_inss)}</span></div>
      </div>

      <div class="danfse-box">
        <div class="danfse-box-title">CARGA TRIBUTÁRIA APROXIMADA (LEI 12.741/2012 - IBPT)</div>
        <div class="danfse-row"><span class="label">Tributos Federais Estimados:</span> <span class="value">${Formatters.percent(n.perc_trib_federal)}</span></div>
        <div class="danfse-row"><span class="label">Tributos Estaduais Estimados:</span> <span class="value">${Formatters.percent(n.perc_trib_estadual)}</span></div>
        <div class="danfse-row"><span class="label">Tributos Municipais Estimados:</span> <span class="value">${Formatters.percent(n.perc_trib_municipal)}</span></div>
      </div>
    </div>
  `;
}

// Renderizar Aba de Complementares e PIX
function renderComplementaresTab(n) {
  const container = document.getElementById('tab-complementares');
  if (!container) return;

  const c = n.dados_complementares_extraidos;

  container.innerHTML = `
    <div style="display: flex; flex-direction: column; gap: 1.25rem;">
      <div class="danfse-box">
        <div class="danfse-box-title">DADOS EXTRAÍDOS AUTOMATICAMENTE VIA REGEX</div>
        <div class="danfse-row"><span class="label">Chave PIX Identificada:</span> <span class="value" style="color: #059669; font-weight: 700;">${c.chave_pix || 'Nenhuma detectada'}</span></div>
        <div class="danfse-row"><span class="label">Tipo da Chave PIX:</span> <span class="value">${c.tipo_pix || '-'}</span></div>
        <div class="danfse-row"><span class="label">Instituição Bancária:</span> <span class="value">${c.banco_nome || '-'}</span></div>
        <div class="danfse-row"><span class="label">Agência e Conta Corrente:</span> <span class="value">Ag: ${c.agencia || '-'} | C/C: ${c.conta_corrente || '-'}</span></div>
        <div class="danfse-row"><span class="label">Contrato Informado:</span> <span class="value">${c.numero_contrato || '-'}</span></div>
        <div class="danfse-row"><span class="label">Número do Pedido / PO:</span> <span class="value">${c.numero_pedido || '-'}</span></div>
        <div class="danfse-row"><span class="label">Medição:</span> <span class="value">${c.numero_medicao || '-'}</span></div>
      </div>

      <div class="danfse-box">
        <div class="danfse-box-title">DEDUÇÕES DE BENEFÍCIOS INFORMADAS (BASE INSS)</div>
        <div class="danfse-row"><span class="label">Dedução Vale-Transporte:</span> <span class="value">${c.deducao_vt ? Formatters.currency(c.deducao_vt) : '-'}</span></div>
        <div class="danfse-row"><span class="label">Dedução Vale-Refeição/Alimentação:</span> <span class="value">${c.deducao_vr ? Formatters.currency(c.deducao_vr) : '-'}</span></div>
        <div class="danfse-row"><span class="label">Dedução de Materiais:</span> <span class="value">${c.deducao_material ? Formatters.currency(c.deducao_material) : '-'}</span></div>
      </div>

      <div class="danfse-box">
        <div class="danfse-box-title">TEXTO INTEGRAL DE INFORMAÇÕES COMPLEMENTARES (xInfComp)</div>
        <div style="background: rgba(0, 0, 0, 0.03); padding: 0.75rem; border-radius: 4px; font-family: monospace; font-size: 0.8rem; color: #334155; white-space: pre-line;">${n.informacoes_complementares || 'Sem observações declaradas.'}</div>
      </div>
    </div>
  `;
}

// Renderizar Aba de Auditoria Contábil
function renderAuditoriaTab(n) {
  const container = document.getElementById('tab-auditoria');
  if (!container) return;

  const a = n.auditoria;
  const statusColor = a.status_conciliacao === 'CONCILIADO' ? '#10b981' : a.status_conciliacao === 'ALERTA' ? '#f59e0b' : '#f43f5e';

  container.innerHTML = `
    <div style="display: flex; flex-direction: column; gap: 1.25rem;">
      <div class="danfse-box" style="border-left: 4px solid ${statusColor};">
        <div class="danfse-box-title">RESULTADO DA CONCILIAÇÃO CONTÁBIL AUTOMÁTICA</div>
        <div class="danfse-row"><span class="label">Status Geral:</span> <span class="value" style="color: ${statusColor}; font-weight: 800;">${a.status_conciliacao}</span></div>
        <div class="danfse-row"><span class="label">Equação vLiq = vServ - vTotalRet:</span> <span class="value">${a.equacao_liquido_valida ? '✓ Válida (100% Conciliada)' : `Divergência: R$ ${a.diferenca_liquido.toFixed(2)}`}</span></div>
        <div class="danfse-row"><span class="label">Consistência da Soma das Retenções:</span> <span class="value">${a.soma_retencoes_valida ? '✓ Válida' : `Diferença: R$ ${a.diferenca_retencoes.toFixed(2)}`}</span></div>
        <div style="margin-top: 0.75rem;">
          <strong style="font-size: 0.75rem; color: #475569;">Trilha de Verificação Contábil:</strong>
          <ul style="margin-top: 0.25rem; padding-left: 1.25rem; font-size: 0.78rem; color: #334155;">
            ${a.detalhes_auditoria.map((d) => `<li>${d}</li>`).join('')}
          </ul>
        </div>
      </div>

      <div class="danfse-box">
        <div class="danfse-box-title">INTEGRIDADE CRIPTOGRÁFICA (W3C XMLDSIG)</div>
        <div class="danfse-row"><span class="label">Digest SHA-256 (Canonical):</span> <span class="value" style="font-family: monospace; font-size: 0.72rem;">${n.digest_value || 'Presente'}</span></div>
        <div class="danfse-row"><span class="label">Assinatura Digital RSA:</span> <span class="value" style="font-family: monospace; font-size: 0.72rem;">${n.signature_value ? n.signature_value.substring(0, 32) + '...' : 'Presente'}</span></div>
        <div class="danfse-row"><span class="label">Ambiente Emissor:</span> <span class="value">${n.ambiente_gerador === 1 ? 'Produção Nacional' : 'Homologação'}</span></div>
      </div>
    </div>
  `;
}

// Fechar Modal
function closeModal() {
  const overlay = document.getElementById('modalOverlay');
  if (overlay) overlay.classList.remove('active');
  AppState.currentNote = null;
}

// Copiar Chave
function copyToClipboard(text) {
  navigator.clipboard.writeText(text).then(() => {
    showToast('Chave de acesso copiada para a área de transferência!', 'info');
  });
}

function copyJsonToClipboard() {
  if (AppState.currentNote) {
    navigator.clipboard.writeText(JSON.stringify(AppState.currentNote, null, 2)).then(() => {
      showToast('JSON copiado com sucesso!', 'success');
    });
  }
}

// Baixar JSON individual
function downloadSingleJson(chave) {
  const note = AppState.notes.find((n) => n.chave_nfse === chave) || AppState.currentNote;
  if (!note) return;

  const blob = new Blob([JSON.stringify(note, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `${note.chave_nfse}.json`;
  a.click();
  URL.revokeObjectURL(url);
}

// Excluir Nota
async function deleteNote(chave) {
  if (!confirm('Deseja excluir esta nota fiscal do sistema?')) return;

  try {
    const res = await fetch(`/api/notes/${chave}`, { method: 'DELETE' });
    const data = await res.json();
    if (data.success) {
      showToast('Nota fiscal removida com sucesso.', 'info');
      loadDashboardData();
    }
  } catch (err) {
    showToast(`Erro ao remover: ${err.message}`, 'error');
  }
}
