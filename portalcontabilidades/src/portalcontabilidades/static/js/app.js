/**
 * Master Application Coordinator for Portal Contabilidades & BPO
 * Manages state, views, actions, modals, and real-time backend updates.
 */

const AppState = {
  organizationId: 'org-default-01',
  activeCompanyId: 'comp-01',
  activeCompany: null,
  companies: [],
  competence: '2026-09',
  activeView: 'cockpit',
  currentUser: {
    id: 'super-admin-01',
    name: 'Lucas Rocha',
    role: 'Sócio Administrador',
    email: 'lucas@alphacontabil.com.br'
  }
};

// Utilities
const Utils = {
  formatCurrency(val) {
    const num = Number(val || 0);
    const formatted = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(Math.abs(num));
    return num < 0 ? `- ${formatted}` : formatted;
  },

  formatPercent(val) {
    const num = Number(val || 0);
    return `${num.toFixed(1)}%`;
  },

  formatDate(d) {
    if (!d) return '-';
    if (d.includes('T')) d = d.split('T')[0];
    const parts = d.split('-');
    if (parts.length === 3) return `${parts[2]}/${parts[1]}/${parts[0]}`;
    return d;
  },

  formatDateTime(dt) {
    if (!dt) return '-';
    try {
      const d = new Date(dt);
      if (isNaN(d.getTime())) return Utils.formatDate(dt);
      const pad = (n) => String(n).padStart(2, '0');
      return `${pad(d.getDate())}/${pad(d.getMonth() + 1)}/${d.getFullYear()} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
    } catch {
      return Utils.formatDate(dt);
    }
  },

  formatCnpj(taxId) {
    if (!taxId) return '';
    const clean = String(taxId).replace(/\D/g, '');
    if (clean.length === 14) {
      return clean.replace(/^(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})$/, '$1.$2.$3/$4-$5');
    }
    if (clean.length === 11) {
      return clean.replace(/^(\d{3})(\d{3})(\d{3})(\d{2})$/, '$1.$2.$3-$4');
    }
    return taxId;
  },

  formatTaxRegime(regime) {
    const map = {
      'simples_nacional': 'Simples Nacional',
      'lucro_presumido': 'Lucro Presumido',
      'lucro_real': 'Lucro Real',
      'mei': 'MEI',
      'imune_isenta': 'Imune/Isenta'
    };
    return map[regime] || regime || '-';
  },

  badgeForRisk(risk) {
    const norm = (risk || '').toLowerCase();
    const map = {
      'green': '<span class="badge badge-success">No Prazo</span>',
      'green_safe': '<span class="badge badge-success">No Prazo</span>',
      'yellow_alert': '<span class="badge badge-warning">Atenção (3-5d)</span>',
      'yellow_attention': '<span class="badge badge-warning">Atenção (3-5d)</span>',
      'red_critical': '<span class="badge badge-danger">Crítico (≤2d)</span>',
      'overdue': '<span class="badge badge-danger">Em Atraso</span>',
      'completed': '<span class="badge badge-neutral">Concluído</span>'
    };
    return map[norm] || `<span class="badge badge-neutral">${risk}</span>`;
  },

  badgeForStatus(status) {
    const norm = (status || '').toLowerCase();
    const map = {
      'completed': '<span class="badge badge-success">Concluído</span>',
      'in_progress': '<span class="badge badge-info">Em Execução</span>',
      'in_review': '<span class="badge badge-warning">Em Revisão</span>',
      'todo': '<span class="badge badge-neutral">A Iniciar</span>',
      'waiting_client': '<span class="badge badge-warning">Aguardando Cliente</span>',
      'overdue': '<span class="badge badge-danger">Atrasado</span>',
      'active': '<span class="badge badge-success">Ativa</span>',
      'onboarding': '<span class="badge badge-info">Onboarding</span>',
      'inactive': '<span class="badge badge-neutral">Inativa</span>',
      'suspended': '<span class="badge badge-danger">Suspensa</span>',
      'pending_approval': '<span class="badge badge-warning">Pendente Aprovação</span>',
      'approved': '<span class="badge badge-success">Aprovado</span>',
      'rejected': '<span class="badge badge-danger">Rejeitado</span>',
      'paid': '<span class="badge badge-success">Liquidado</span>',
      'accepted': '<span class="badge badge-success">Transmitido / Aceito</span>',
      'transmitted': '<span class="badge badge-success">Transmitido</span>',
      'queued': '<span class="badge badge-info">Na Fila</span>',
      'failed': '<span class="badge badge-danger">Falha</span>',
      'open': '<span class="badge badge-info">Aberto</span>',
      'in_analysis': '<span class="badge badge-warning">Em Análise</span>',
      'resolved': '<span class="badge badge-success">Resolvido</span>',
      'closed': '<span class="badge badge-neutral">Fechado</span>'
    };
    return map[norm] || `<span class="badge badge-neutral">${status}</span>`;
  }
};

// Toast Manager
function showToast(message, type = 'info') {
  const container = document.getElementById('toast-container');
  if (!container) return;

  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.innerHTML = `
    <div style="font-size: 1.1rem;">
      ${type === 'success' ? '✓' : type === 'danger' ? '✕' : type === 'warning' ? '⚠' : 'ℹ'}
    </div>
    <div style="flex: 1;">${message}</div>
  `;

  container.appendChild(toast);
  setTimeout(() => {
    toast.style.animation = 'slideIn 0.3s ease reverse forwards';
    setTimeout(() => toast.remove(), 300);
  }, 4000);
}

// Modal Manager
function openModal(modalId) {
  const modal = document.getElementById(modalId);
  if (modal) modal.classList.add('active');
}

function closeModal(modalId) {
  const modal = document.getElementById(modalId);
  if (modal) modal.classList.remove('active');
}

// Mobile Sidebar Drawer
function toggleMobileSidebar() {
  const sidebar = document.getElementById('sidebar');
  const backdrop = document.getElementById('sidebar-backdrop');
  if (sidebar) sidebar.classList.toggle('open');
  if (backdrop) backdrop.classList.toggle('active');
}

function closeMobileSidebar() {
  const sidebar = document.getElementById('sidebar');
  const backdrop = document.getElementById('sidebar-backdrop');
  if (sidebar) sidebar.classList.remove('open');
  if (backdrop) backdrop.classList.remove('active');
}

// Global App Initialization
document.addEventListener('DOMContentLoaded', async () => {
  setupNavigation();
  setupGlobalControls();
  await loadInitialCompanies();
  navigateTo('cockpit');
});

function setupNavigation() {
  document.querySelectorAll('.nav-item').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.preventDefault();
      const view = btn.dataset.view;
      if (view) {
        navigateTo(view);
        closeMobileSidebar();
      }
    });
  });
}

function setupGlobalControls() {
  // Competence Selector change
  const compSelect = document.getElementById('competence-select');
  if (compSelect) {
    compSelect.addEventListener('change', (e) => {
      AppState.competence = e.target.value;
      showToast(`Competência alterada para ${AppState.competence}`, 'info');
      refreshCurrentView();
    });
  }

  // Close modals on overlay click or esc
  document.querySelectorAll('.modal-overlay').forEach(overlay => {
    overlay.addEventListener('click', (e) => {
      if (e.target === overlay) overlay.classList.remove('active');
    });
  });

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      document.querySelectorAll('.modal-overlay.active').forEach(m => m.classList.remove('active'));
    }
  });
}

async function loadInitialCompanies() {
  try {
    const list = await ApiClient.getCompanies(AppState.organizationId);
    AppState.companies = list;

    const selectEl = document.getElementById('active-company-select');
    if (selectEl) {
      selectEl.innerHTML = list.map(c => 
        `<option value="${c.id}" ${c.id === AppState.activeCompanyId ? 'selected' : ''}>
          ${c.corporate_name} (${Utils.formatTaxRegime(c.tax_regime)})
        </option>`
      ).join('');

      selectEl.addEventListener('change', async (e) => {
        await switchActiveCompany(e.target.value);
      });
    }

    if (list.length > 0) {
      AppState.activeCompany = list.find(c => c.id === AppState.activeCompanyId) || list[0];
      AppState.activeCompanyId = AppState.activeCompany.id;
      updateHeaderCompanyBadge();
    }
  } catch (err) {
    console.error('Falha ao carregar empresas:', err);
    showToast('Aviso: Verifique a conexão com o servidor da API.', 'warning');
  }
}

async function switchActiveCompany(companyId) {
  try {
    const res = await ApiClient.switchCompanyContext(companyId);
    AppState.activeCompanyId = companyId;
    AppState.activeCompany = AppState.companies.find(c => c.id === companyId);
    updateHeaderCompanyBadge();
    showToast(`Contexto alterado para ${AppState.activeCompany?.corporate_name || companyId}`, 'success');
    refreshCurrentView();
  } catch (err) {
    showToast(`Erro ao alterar contexto: ${err.message}`, 'danger');
  }
}

function updateHeaderCompanyBadge() {
  const comp = AppState.activeCompany;
  if (!comp) return;

  const nameEl = document.getElementById('current-company-name');
  const metaEl = document.getElementById('current-company-meta');
  if (nameEl) nameEl.textContent = comp.corporate_name;
  if (metaEl) metaEl.textContent = `CNPJ: ${Utils.formatCnpj(comp.tax_id)} • ${Utils.formatTaxRegime(comp.tax_regime)}`;
}

function navigateTo(viewName) {
  AppState.activeView = viewName;
  document.querySelectorAll('.nav-item').forEach(el => {
    el.classList.toggle('active', el.dataset.view === viewName);
  });
  refreshCurrentView();
}

function refreshCurrentView() {
  const container = document.getElementById('content-container');
  if (!container) return;

  switch (AppState.activeView) {
    case 'cockpit': renderCockpitView(container); break;
    case 'companies': renderCompaniesView(container); break;
    case 'obligations': renderObligationsView(container); break;
    case 'documents': renderDocumentsView(container); break;
    case 'finance': renderFinanceView(container); break;
    case 'reconciliation': renderReconciliationView(container); break;
    case 'analytics': renderAnalyticsView(container); break;
    case 'fiscal': renderFiscalView(container); break;
    case 'ai': renderAiView(container); break;
    case 'portal': renderPortalView(container); break;
    case 'security': renderSecurityView(container); break;
    default: renderCockpitView(container); break;
  }
}

/* ==========================================================================
   VIEW 1: COCKPIT EXECUTIVO
   ========================================================================== */
async function renderCockpitView(container) {
  container.innerHTML = `
    <div class="view-header">
      <div class="view-title-group">
        <h2>📊 Cockpit Executivo & Visão Geral</h2>
        <p>Monitoramento unificado de compliance fiscal, saúde financeira, prazos e inteligência artificial.</p>
      </div>
      <div class="view-actions">
        <button class="btn btn-secondary" onclick="openBatchRequestModal()">
          <span>📤 Solicitação em Lote</span>
        </button>
        <button class="btn btn-primary" onclick="openCreateCompanyModal()">
          <span>+ Nova Empresa</span>
        </button>
      </div>
    </div>

    <!-- Live Metric Cards -->
    <div class="grid-4" id="cockpit-stats-grid">
      <div class="card stat-card">
        <div class="stat-icon blue">🏢</div>
        <div class="stat-content">
          <div class="stat-label">Clientes Ativos</div>
          <div class="stat-value" id="stat-total-companies">--</div>
          <div class="stat-trend trend-up">● Portfólio em conformidade</div>
        </div>
      </div>
      <div class="card stat-card">
        <div class="stat-icon green">📅</div>
        <div class="stat-content">
          <div class="stat-label">Obrigações do Mês</div>
          <div class="stat-value" id="stat-tasks-count">--</div>
          <div class="stat-trend" id="stat-tasks-risk">● Calculando SLA</div>
        </div>
      </div>
      <div class="card stat-card">
        <div class="stat-icon amber">💳</div>
        <div class="stat-content">
          <div class="stat-label">Aprovações a Pagar</div>
          <div class="stat-value" id="stat-payables-queue">--</div>
          <div class="stat-trend trend-neutral">● Alçadas de controle BPO</div>
        </div>
      </div>
      <div class="card stat-card">
        <div class="stat-icon purple">🤖</div>
        <div class="stat-content">
          <div class="stat-label">Sugestões de IA</div>
          <div class="stat-value" id="stat-ai-suggestions">96.8%</div>
          <div class="stat-trend trend-up">● Alta confiança de classificação</div>
        </div>
      </div>
    </div>

    <!-- Charts & Portfolio Health -->
    <div class="grid-2">
      <div class="card">
        <div class="card-header">
          <div class="card-title">Distribuição por Regime Tributário</div>
          <span class="badge badge-info">Portfólio Contábil</span>
        </div>
        <div class="chart-container" style="height: 240px;">
          <canvas id="chart-tax-regimes"></canvas>
        </div>
        <div id="regime-legend" style="display: flex; justify-content: center; gap: 1.5rem; margin-top: 1rem; font-size: 0.8rem; color: #9ca3af;">
        </div>
      </div>

      <div class="card">
        <div class="card-header">
          <div class="card-title">Radar de SLA e Prazos Regulatórios</div>
          <span class="badge badge-warning">Competência ${AppState.competence}</span>
        </div>
        <div class="chart-container" style="height: 240px;">
          <canvas id="chart-tasks-sla"></canvas>
        </div>
        <div id="sla-legend" style="display: flex; justify-content: center; gap: 1.25rem; margin-top: 1rem; font-size: 0.8rem; color: #9ca3af;">
        </div>
      </div>
    </div>

    <!-- Active Shortcuts & Live Alerts -->
    <div class="grid-2">
      <div class="card">
        <div class="card-header">
          <div class="card-title">🚨 Radar Preditivo de Anomalias de IA</div>
          <button class="btn btn-sm btn-secondary" onclick="navigateTo('ai')">Ver Detalhes</button>
        </div>
        <div id="cockpit-anomalies-list">
          <p style="color: #9ca3af; font-size: 0.85rem;">Carregando alertas preditivos...</p>
        </div>
      </div>

      <div class="card">
        <div class="card-header">
          <div class="card-title">🔐 Cofre de Certificados ICP-Brasil</div>
          <button class="btn btn-sm btn-secondary" onclick="navigateTo('security')">Gerenciar</button>
        </div>
        <div id="cockpit-certs-list">
          <p style="color: #9ca3af; font-size: 0.85rem;">Consultando validades AES-256...</p>
        </div>
      </div>
    </div>
  `;

  try {
    const summary = await ApiClient.getCockpitSummary(AppState.organizationId);
    document.getElementById('stat-total-companies').textContent = summary.total_companies;
    
    // Render Donut Chart: Tax Regimes
    const regimes = summary.by_tax_regime || {};
    const donutItems = [
      { label: 'Simples Nacional', value: regimes.simples_nacional || 0, color: '#3b82f6' },
      { label: 'Lucro Presumido', value: regimes.lucro_presumido || 0, color: '#10b981' },
      { label: 'Lucro Real', value: regimes.lucro_real || 0, color: '#8b5cf6' },
      { label: 'Outros/MEI', value: (regimes.mei || 0) + (regimes.imune_isenta || 0), color: '#f59e0b' }
    ].filter(i => i.value > 0);

    MiniCharts.drawDonut('chart-tax-regimes', donutItems, `${summary.total_companies} Cli`);
    
    const legendEl = document.getElementById('regime-legend');
    if (legendEl) {
      legendEl.innerHTML = donutItems.map(i => 
        `<span style="display:flex;align-items:center;gap:0.35rem;">
          <span style="width:10px;height:10px;border-radius:50%;background:${i.color};display:inline-block;"></span>
          ${i.label}: <b>${i.value}</b>
        </span>`
      ).join('');
    }

    // Load Tasks SLA metrics
    const tasks = await ApiClient.getTasks({ competence: AppState.competence });
    document.getElementById('stat-tasks-count').textContent = tasks.length;
    
    const completed = tasks.filter(t => t.status === 'completed').length;
    const critical = tasks.filter(t => t.risk_level === 'red_critical' || t.risk_level === 'overdue').length;
    const attention = tasks.filter(t => t.risk_level === 'yellow_alert' || t.risk_level === 'yellow_attention').length;
    const onTime = tasks.length - completed - critical - attention;

    document.getElementById('stat-tasks-risk').innerHTML = 
      critical > 0 
        ? `<span class="trend-down">● ${critical} em risco crítico</span>` 
        : `<span class="trend-up">● Todos os prazos sob controle</span>`;

    const slaItems = [
      { label: 'Concluído', value: completed, color: '#10b981' },
      { label: 'No Prazo', value: Math.max(0, onTime), color: '#3b82f6' },
      { label: 'Atenção', value: attention, color: '#f59e0b' },
      { label: 'Crítico/Atrasado', value: critical, color: '#ef4444' }
    ].filter(i => i.value > 0);

    MiniCharts.drawDonut('chart-tasks-sla', slaItems, `${completed}/${tasks.length}`);
    const slaLegend = document.getElementById('sla-legend');
    if (slaLegend) {
      slaLegend.innerHTML = slaItems.map(i => 
        `<span style="display:flex;align-items:center;gap:0.35rem;">
          <span style="width:10px;height:10px;border-radius:50%;background:${i.color};display:inline-block;"></span>
          ${i.label}: <b>${i.value}</b>
        </span>`
      ).join('');
    }

    // Load Payables Queue count
    const payables = await ApiClient.getPayableApprovalQueue(AppState.activeCompanyId);
    document.getElementById('stat-payables-queue').textContent = Utils.formatCurrency(
      payables.reduce((acc, p) => acc + Number(p.final_amount || 0), 0)
    );

    // Anomalies
    const anomalies = await ApiClient.getAnomalies(AppState.activeCompanyId);
    const anomaliesListEl = document.getElementById('cockpit-anomalies-list');
    if (anomalies.length === 0) {
      anomaliesListEl.innerHTML = `<p style="color: #10b981; font-size: 0.85rem;">✓ Nenhuma inconsistência detectada para esta empresa.</p>`;
    } else {
      anomaliesListEl.innerHTML = anomalies.slice(0, 3).map(a => `
        <div style="display: flex; align-items: center; justify-content: space-between; padding: 0.65rem 0; border-bottom: 1px solid rgba(255,255,255,0.06);">
          <div>
            <div style="font-size: 0.85rem; font-weight: 600; color: #fff;">${a.details.description || a.anomaly_type}</div>
            <div style="font-size: 0.72rem; color: #9ca3af;">Severidade: <span class="badge badge-${a.severity === 'critical' ? 'danger' : 'warning'}">${a.severity}</span></div>
          </div>
          <button class="btn btn-sm btn-secondary" onclick="navigateTo('ai')">Analisar</button>
        </div>
      `).join('');
    }

    // Certs Expirations
    const certs = await ApiClient.getCertificates(AppState.activeCompanyId);
    const certsListEl = document.getElementById('cockpit-certs-list');
    if (certs.length === 0) {
      certsListEl.innerHTML = `<p style="color: #9ca3af; font-size: 0.85rem;">Nenhum certificado cadastrado.</p>`;
    } else {
      certsListEl.innerHTML = certs.map(c => {
        const days = c.days_until_expiration;
        const isExpired = days < 0;
        const isUrgent = days >= 0 && days <= 15;
        const isAttention = days > 15 && days <= 30;
        const badgeClass = isExpired ? 'danger' : isUrgent ? 'warning' : isAttention ? 'info' : 'success';
        const badgeLabel = isExpired ? 'Vencido' : isUrgent ? 'Alerta 15d' : isAttention ? 'Atenção 30d' : 'Ativo';
        const expLabel = isExpired ? `Vencido há <b>${Math.abs(days)} dias</b>` : `Expira em: <b>${days} dias</b>`;
        const displayName = c.common_name ? c.common_name.split(':')[0] : c.issued_to_tax_id;

        return `
        <div style="display: flex; align-items: center; justify-content: space-between; padding: 0.65rem 0; border-bottom: 1px solid rgba(255,255,255,0.06);">
          <div>
            <div style="font-size: 0.85rem; font-weight: 600; color: #fff;">${displayName}</div>
            <div style="font-size: 0.72rem; color: #9ca3af;">${expLabel} (${Utils.formatDate(c.valid_until)})</div>
          </div>
          <span class="badge badge-${badgeClass}">
            ${badgeLabel}
          </span>
        </div>
      `;
      }).join('');
    }

  } catch (err) {
    console.error('Erro ao renderizar Cockpit:', err);
  }
}

/* ==========================================================================
   VIEW 2: GESTÃO MULTIEMPRESA & CLIENTES
   ========================================================================== */
async function renderCompaniesView(container) {
  container.innerHTML = `
    <div class="view-header">
      <div class="view-title-group">
        <h2>🏢 Gestão Multiempresa & Carteira de Clientes</h2>
        <p>Isolamento rigoroso de tenant com validação de CNPJ Módulo 11 e alocação de analistas.</p>
      </div>
      <div class="view-actions">
        <button class="btn btn-secondary" onclick="openBatchRequestModal()">
          <span>📤 Solicitação em Lote</span>
        </button>
        <button class="btn btn-primary" onclick="openCreateCompanyModal()">
          <span>+ Cadastrar Cliente</span>
        </button>
      </div>
    </div>

    <div class="card" style="margin-bottom: 1.5rem;">
      <div style="display: flex; gap: 1rem; flex-wrap: wrap;">
        <input type="text" id="company-filter-search" class="form-input" style="max-width: 320px;" placeholder="Buscar por Razão Social ou CNPJ..." />
        <select id="company-filter-regime" class="form-select" style="max-width: 220px;">
          <option value="">Todos os Regimes</option>
          <option value="simples_nacional">Simples Nacional</option>
          <option value="lucro_presumido">Lucro Presumido</option>
          <option value="lucro_real">Lucro Real</option>
          <option value="mei">MEI</option>
        </select>
        <button class="btn btn-secondary" onclick="filterCompaniesTable()">Filtrar</button>
      </div>
    </div>

    <div class="card">
      <div class="table-responsive">
        <table class="table" id="companies-table">
          <thead>
            <tr>
              <th>Razão Social / Nome Fantasia</th>
              <th>CNPJ / CPF</th>
              <th>Regime Tributário</th>
              <th>CNAE</th>
              <th>Status</th>
              <th>Ações</th>
            </tr>
          </thead>
          <tbody id="companies-table-body">
            <tr><td colspan="6" style="text-align: center; color: #9ca3af;">Carregando empresas...</td></tr>
          </tbody>
        </table>
      </div>
    </div>
  `;

  await loadCompaniesTable();
}

async function loadCompaniesTable(regime = '', search = '') {
  try {
    const companies = await ApiClient.getCompanies(AppState.organizationId, regime, search);
    const tbody = document.getElementById('companies-table-body');
    if (!tbody) return;

    if (companies.length === 0) {
      tbody.innerHTML = `<tr><td colspan="6" style="text-align: center; padding: 2rem; color: #9ca3af;">Nenhuma empresa encontrada com os filtros informados.</td></tr>`;
      return;
    }

    tbody.innerHTML = companies.map(c => `
      <tr>
        <td>
          <div style="font-weight: 600; color: #fff;">${c.corporate_name}</div>
          <div style="font-size: 0.75rem; color: #9ca3af;">${c.trade_name || 'Sem nome fantasia'}</div>
        </td>
        <td><code>${Utils.formatCnpj(c.tax_id)}</code></td>
        <td><span class="badge badge-info">${Utils.formatTaxRegime(c.tax_regime)}</span></td>
        <td>${c.cnae_code || '-'}</td>
        <td>${Utils.badgeForStatus(c.status)}</td>
        <td>
          <div style="display: flex; gap: 0.4rem;">
            <button class="btn btn-sm ${c.id === AppState.activeCompanyId ? 'btn-primary' : 'btn-secondary'}" onclick="switchActiveCompany('${c.id}')">
              ${c.id === AppState.activeCompanyId ? '● Ativa' : 'Selecionar'}
            </button>
            <button class="btn btn-sm btn-secondary" onclick="openAssignAnalystModal('${c.id}', '${c.corporate_name}')">
              Atribuir
            </button>
          </div>
        </td>
      </tr>
    `).join('');
  } catch (err) {
    console.error(err);
  }
}

function filterCompaniesTable() {
  const regime = document.getElementById('company-filter-regime')?.value || '';
  const search = document.getElementById('company-filter-search')?.value || '';
  loadCompaniesTable(regime, search);
}

/* ==========================================================================
   VIEW 3: CENTRAL DE OBRIGAÇÕES, TAREFAS E PRAZOS
   ========================================================================== */
async function renderObligationsView(container) {
  container.innerHTML = `
    <div class="view-header">
      <div class="view-title-group">
        <h2>📅 Central de Obrigações, Tarefas e Prazos</h2>
        <p>Controle regulatório de declarações fiscais e trabalhistas com semáforo de risco SLA e recibos.</p>
      </div>
      <div class="view-actions">
        <button class="btn btn-secondary" onclick="generateBatchTasksPrompt()">
          <span>⚡ Gerar Competência</span>
        </button>
      </div>
    </div>

    <!-- Filter Bar -->
    <div class="card" style="margin-bottom: 1.5rem;">
      <div style="display: flex; gap: 1rem; flex-wrap: wrap; align-items: center;">
        <select id="tasks-filter-status" class="form-select" style="max-width: 200px;" onchange="loadTasksList()">
          <option value="">Todos os Status</option>
          <option value="todo">A Iniciar</option>
          <option value="in_progress">Em Andamento</option>
          <option value="in_review">Em Revisão</option>
          <option value="completed">Concluído</option>
          <option value="overdue">Atrasado</option>
        </select>
        <span style="font-size: 0.85rem; color: #9ca3af;">Empresa: <b>${AppState.activeCompany?.corporate_name || 'Todas'}</b></span>
        <button class="btn btn-sm btn-secondary" style="margin-left: auto;" onclick="loadWorkloadModal()">
          👥 Ver Carga da Equipe
        </button>
      </div>
    </div>

    <!-- Tasks Table -->
    <div class="card">
      <div class="table-responsive">
        <table class="table">
          <thead>
            <tr>
              <th>Obrigação / Tarefa</th>
              <th>Competência</th>
              <th>Prazo Legal (Fisco)</th>
              <th>Prazo Interno</th>
              <th>Risco SLA</th>
              <th>Status</th>
              <th>Comprovante / Ações</th>
            </tr>
          </thead>
          <tbody id="tasks-table-body">
            <tr><td colspan="7" style="text-align: center; color: #9ca3af;">Carregando obrigações...</td></tr>
          </tbody>
        </table>
      </div>
    </div>
  `;

  await loadTasksList();
}

async function loadTasksList() {
  const statusFilter = document.getElementById('tasks-filter-status')?.value || '';
  try {
    const tasks = await ApiClient.getTasks({
      company_id: AppState.activeCompanyId,
      competence: AppState.competence,
      status: statusFilter
    });
    const tbody = document.getElementById('tasks-table-body');
    if (!tbody) return;

    if (tasks.length === 0) {
      tbody.innerHTML = `<tr><td colspan="7" style="text-align: center; padding: 2rem; color: #9ca3af;">Nenhuma tarefa encontrada para a competência ${AppState.competence}.</td></tr>`;
      return;
    }

    tbody.innerHTML = tasks.map(t => `
      <tr>
        <td>
          <div style="font-weight: 600; color: #fff;">${t.title}</div>
          <div style="font-size: 0.72rem; color: #9ca3af;">Código: <code>${t.obligation_code || 'GERAL'}</code></div>
        </td>
        <td><b>${t.competence}</b></td>
        <td><span style="color: ${t.risk_level === 'overdue' || t.risk_level === 'red_critical' ? '#ef4444' : t.risk_level === 'yellow_alert' ? '#f59e0b' : '#e5e7eb'}; font-weight: 600;">${Utils.formatDate(t.statutory_due_date)}</span></td>
        <td>${Utils.formatDate(t.internal_deadline)}</td>
        <td>${Utils.badgeForRisk(t.risk_level)}</td>
        <td>
          <select class="form-select" style="padding: 0.25rem 0.5rem; font-size: 0.75rem; width: auto;" onchange="updateTaskStatusAction('${t.id}', this.value)">
            <option value="todo" ${t.status === 'todo' ? 'selected' : ''}>A Iniciar</option>
            <option value="in_progress" ${t.status === 'in_progress' ? 'selected' : ''}>Em Andamento</option>
            <option value="in_review" ${t.status === 'in_review' ? 'selected' : ''}>Em Revisão</option>
            <option value="completed" ${t.status === 'completed' ? 'selected' : ''}>Concluído</option>
          </select>
        </td>
        <td>
          <div style="display: flex; gap: 0.4rem; align-items: center;">
            ${t.receipt_file_hash 
              ? `<span title="Hash: ${t.receipt_file_hash}" class="badge badge-success" style="cursor: pointer;" onclick="showToast('SHA-256: ${t.receipt_file_hash}', 'info')">✓ Recibo OK</span>` 
              : `<button class="btn btn-sm btn-secondary" onclick="openAttachReceiptModal('${t.id}')">📎 Anexar Recibo</button>`}
          </div>
        </td>
      </tr>
    `).join('');
  } catch (err) {
    console.error(err);
  }
}

async function updateTaskStatusAction(taskId, newStatus) {
  try {
    await ApiClient.updateTaskStatus(taskId, {
      status: newStatus,
      user_id: AppState.currentUser.id
    });
    showToast(`Status da tarefa atualizado para: ${newStatus}`, 'success');
    await loadTasksList();
  } catch (err) {
    showToast(`Erro ao atualizar tarefa: ${err.message}`, 'danger');
    await loadTasksList();
  }
}

async function generateBatchTasksPrompt() {
  if (!confirm(`Deseja gerar automaticamente as tarefas e obrigações para a competência ${AppState.competence}?`)) return;
  try {
    const res = await ApiClient.generateCompetenceTasks({
      competence: AppState.competence,
      company_ids: [AppState.activeCompanyId]
    });
    showToast(`Sucesso! ${res.tasks_created} tarefas geradas para a competência ${res.competence}.`, 'success');
    await loadTasksList();
  } catch (err) {
    showToast(`Erro ao gerar tarefas: ${err.message}`, 'danger');
  }
}

/* ==========================================================================
   VIEW 4: GESTÃO INTELIGENTE DE DOCUMENTOS
   ========================================================================== */
async function renderDocumentsView(container) {
  container.innerHTML = `
    <div class="view-header">
      <div class="view-title-group">
        <h2>📁 Gestão Inteligente de Documentos</h2>
        <p>Ingestão com hash SHA-256, recibos de entrega auditáveis e checklist mensal de fechamento.</p>
      </div>
      <div class="view-actions">
        <button class="btn btn-primary" onclick="openUploadDocModal()">
          <span>📤 Ingerir Novo Documento</span>
        </button>
      </div>
    </div>

    <!-- Monthly Checklist Progress Card -->
    <div class="card" style="margin-bottom: 1.5rem;" id="checklist-card">
      <div class="card-header">
        <div class="card-title">Checklist Mensal de Documentos Obrigatórios</div>
        <button class="btn btn-sm btn-secondary" onclick="requestMissingDocsChecklist()">Disparar Cobrança de Faltantes</button>
      </div>
      <div style="background: rgba(255,255,255,0.06); height: 10px; border-radius: 999px; overflow: hidden; margin-bottom: 1rem;">
        <div id="checklist-bar" style="background: var(--primary-gradient); height: 100%; width: 0%; transition: width 0.5s ease;"></div>
      </div>
      <div id="checklist-items-container" style="display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 0.75rem;">
        <p style="color: #9ca3af; font-size: 0.85rem;">Carregando checklist...</p>
      </div>
    </div>

    <!-- Ingested Documents List -->
    <div class="card">
      <div class="card-header">
        <div class="card-title">Documentos Arquivados (Rastreabilidade Jurídica)</div>
        <span class="badge badge-info">Empresa: ${AppState.activeCompany?.corporate_name || ''}</span>
      </div>
      <div class="table-responsive">
        <table class="table">
          <thead>
            <tr>
              <th>Nome do Arquivo</th>
              <th>Departamento</th>
              <th>Competência</th>
              <th>Tamanho</th>
              <th>Hash SHA-256</th>
              <th>OCR Status</th>
              <th>Protocolo</th>
            </tr>
          </thead>
          <tbody id="documents-table-body">
            <tr><td colspan="7" style="text-align: center; color: #9ca3af;">Carregando documentos...</td></tr>
          </tbody>
        </table>
      </div>
    </div>
  `;

  await loadDocumentsViewData();
}

async function loadDocumentsViewData() {
  try {
    const docs = await ApiClient.getDocuments({
      company_id: AppState.activeCompanyId,
      competence: AppState.competence
    });

    const tbody = document.getElementById('documents-table-body');
    if (tbody) {
      if (docs.length === 0) {
        tbody.innerHTML = `<tr><td colspan="7" style="text-align: center; padding: 2rem; color: #9ca3af;">Nenhum documento arquivado para a competência ${AppState.competence}.</td></tr>`;
      } else {
        tbody.innerHTML = docs.map(d => `
          <tr>
            <td>
              <div style="font-weight: 600; color: #fff;">${d.file_name}</div>
              <div style="font-size: 0.7rem; color: #9ca3af;">Versão ${d.version}</div>
            </td>
            <td><span class="badge badge-neutral">${d.department}</span></td>
            <td><b>${d.competence}</b></td>
            <td>${(d.file_size_bytes / 1024).toFixed(1)} KB</td>
            <td><code title="${d.file_hash_sha256}">${d.file_hash_sha256 ? d.file_hash_sha256.substring(0, 16) + '...' : '-'}</code></td>
            <td>${d.ocr_status === 'processed' ? '<span class="badge badge-success">✓ Processado</span>' : '<span class="badge badge-neutral">-</span>'}</td>
            <td>
              <button class="btn btn-sm btn-secondary" onclick="viewDocReceiptModal('${d.id}')">
                📜 Ver Recibo
              </button>
            </td>
          </tr>
        `).join('');
      }
    }

    // Load Checklist
    const chk = await ApiClient.requestChecklist({
      company_id: AppState.activeCompanyId,
      competence: AppState.competence
    });

    const barEl = document.getElementById('checklist-bar');
    if (barEl) barEl.style.width = `${chk.completion_percentage}%`;

    const itemsContainer = document.getElementById('checklist-items-container');
    if (itemsContainer && chk.items) {
      itemsContainer.innerHTML = chk.items.map(it => `
        <div style="display: flex; align-items: center; gap: 0.6rem; padding: 0.5rem 0.75rem; background: rgba(255,255,255,0.03); border-radius: 8px; border: 1px solid rgba(255,255,255,0.06);">
          <span style="color: ${it.is_fulfilled ? '#10b981' : '#f59e0b'}; font-weight: 700;">${it.is_fulfilled ? '✓' : '○'}</span>
          <div style="flex: 1; font-size: 0.8rem; color: ${it.is_fulfilled ? '#fff' : '#d1d5db'};">
            ${it.title}
          </div>
          <span class="badge badge-neutral" style="font-size: 0.68rem;">${it.department}</span>
        </div>
      `).join('');
    }

  } catch (err) {
    console.error(err);
  }
}

async function viewDocReceiptModal(docId) {
  try {
    const r = await ApiClient.getDocumentReceipt(docId);
    alert(`PROTOCOLO OFICIAL DE ENTREGA\n\nCódigo: ${r.receipt_code}\nArquivo: ${r.file_name}\nTamanho: ${r.file_size_bytes} bytes\nSHA-256: ${r.file_hash_sha256}\nIP Ingestão: ${r.ip_address}\nCarimbo UTC: ${r.timestamp_utc}\n\nEste recibo possui validade jurídica probatória.`);
  } catch (err) {
    showToast(`Erro ao carregar recibo: ${err.message}`, 'danger');
  }
}

/* ==========================================================================
   VIEW 5: CONTAS A PAGAR E RECEBER (BPO FINANCEIRO)
   ========================================================================== */
async function renderFinanceView(container) {
  container.innerHTML = `
    <div class="view-header">
      <div class="view-title-group">
        <h2>💳 Contas a Pagar e Receber (BPO Financeiro)</h2>
        <p>Fila de aprovação de pagamentos por alçada e matriz de inadimplência (Aging List).</p>
      </div>
      <div class="view-actions">
        <button class="btn btn-primary" onclick="openCreatePayableModal()">
          <span>+ Novo Título a Pagar</span>
        </button>
      </div>
    </div>

    <!-- Tabs Navigation -->
    <div class="tabs-header">
      <button class="tab-btn active" id="tab-btn-payables" onclick="switchFinanceTab('payables')">
        📥 Fila de Aprovação (A Pagar)
      </button>
      <button class="tab-btn" id="tab-btn-receivables" onclick="switchFinanceTab('receivables')">
        📤 Aging List & Inadimplência (A Receber)
      </button>
    </div>

    <!-- Tab Content: Payables Approval Queue -->
    <div id="finance-tab-payables">
      <div class="card">
        <div class="card-header">
          <div class="card-title">Títulos Aguardando Aprovação do Gestor</div>
          <span class="badge badge-warning">Segregação de Funções</span>
        </div>
        <div class="table-responsive">
          <table class="table">
            <thead>
              <tr>
                <th>Fornecedor / Favorecido</th>
                <th>Valor do Título</th>
                <th>Vencimento</th>
                <th>Forma de Pagamento</th>
                <th>Código de Barras / Chave PIX</th>
                <th>Ações de Aprovação</th>
              </tr>
            </thead>
            <tbody id="payables-table-body">
              <tr><td colspan="6" style="text-align: center; color: #9ca3af;">Carregando fila de aprovação...</td></tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- Tab Content: Receivables Aging List -->
    <div id="finance-tab-receivables" style="display: none;">
      <div class="grid-4" id="aging-brackets-grid">
        <div class="card stat-card">
          <div class="stat-content">
            <div class="stat-label">A Vencer (No Prazo)</div>
            <div class="stat-value" id="aging-ontime" style="color: #10b981;">--</div>
          </div>
        </div>
        <div class="card stat-card">
          <div class="stat-content">
            <div class="stat-label">Atraso 1 a 30 dias</div>
            <div class="stat-value" id="aging-30" style="color: #f59e0b;">--</div>
          </div>
        </div>
        <div class="card stat-card">
          <div class="stat-content">
            <div class="stat-label">Atraso 31 a 60 dias</div>
            <div class="stat-value" id="aging-60" style="color: #f97316;">--</div>
          </div>
        </div>
        <div class="card stat-card">
          <div class="stat-content">
            <div class="stat-label">Inadimplência Crítica (>60d)</div>
            <div class="stat-value" id="aging-90" style="color: #ef4444;">--</div>
          </div>
        </div>
      </div>

      <div class="card">
        <div class="card-header">
          <div class="card-title">Títulos a Receber da Carteira</div>
          <span class="badge badge-info">Taxa Inadimplência: <span id="aging-default-rate">--</span></span>
        </div>
        <div class="table-responsive">
          <table class="table">
            <thead>
              <tr>
                <th>Cliente Devedor</th>
                <th>Valor</th>
                <th>Vencimento</th>
                <th>Dias em Atraso</th>
                <th>Faixa Aging</th>
                <th>Régua de Cobrança</th>
              </tr>
            </thead>
            <tbody id="aging-table-body">
              <tr><td colspan="6" style="text-align: center; color: #9ca3af;">Carregando Aging List...</td></tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  `;

  await loadPayablesQueue();
}

function switchFinanceTab(tabName) {
  document.getElementById('tab-btn-payables').classList.toggle('active', tabName === 'payables');
  document.getElementById('tab-btn-receivables').classList.toggle('active', tabName === 'receivables');
  document.getElementById('finance-tab-payables').style.display = tabName === 'payables' ? 'block' : 'none';
  document.getElementById('finance-tab-receivables').style.display = tabName === 'receivables' ? 'block' : 'none';

  if (tabName === 'receivables') loadReceivablesAging();
  else loadPayablesQueue();
}

async function loadPayablesQueue() {
  try {
    const list = await ApiClient.getPayableApprovalQueue(AppState.activeCompanyId);
    const tbody = document.getElementById('payables-table-body');
    if (!tbody) return;

    if (list.length === 0) {
      tbody.innerHTML = `<tr><td colspan="6" style="text-align: center; padding: 2rem; color: #10b981;">✓ Nenhum título pendente de aprovação no momento.</td></tr>`;
      return;
    }

    tbody.innerHTML = list.map(b => `
      <tr>
        <td>
          <div style="font-weight: 600; color: #fff;">${b.counterparty_name}</div>
          <div style="font-size: 0.72rem; color: #9ca3af;">Doc: ${b.document_number || 'S/N'}</div>
        </td>
        <td><b style="color: #fff; font-size: 1rem;">${Utils.formatCurrency(b.final_amount)}</b></td>
        <td><span style="color: #f59e0b; font-weight: 600;">${Utils.formatDate(b.due_date)}</span></td>
        <td><span class="badge badge-info">${b.payment_method.toUpperCase()}</span></td>
        <td>
          <code style="font-size: 0.75rem;">${b.barcode_line ? b.barcode_line.substring(0, 24) + '...' : b.pix_key || '-'}</code>
        </td>
        <td>
          <div style="display: flex; gap: 0.4rem;">
            <button class="btn btn-sm btn-success" onclick="approveBillAction('${b.id}')">
              ✓ Aprovar
            </button>
            <button class="btn btn-sm btn-danger" onclick="rejectBillAction('${b.id}')">
              ✕ Rejeitar
            </button>
          </div>
        </td>
      </tr>
    `).join('');
  } catch (err) {
    console.error(err);
  }
}

async function approveBillAction(billId) {
  try {
    await ApiClient.approveBill(billId, {
      approver_user_id: AppState.currentUser.id,
      comments: 'Aprovado via Cockpit BPO'
    });
    showToast('Título aprovado com sucesso! Pronto para agendamento bancário.', 'success');
    await loadPayablesQueue();
  } catch (err) {
    showToast(`Erro na aprovação: ${err.message}`, 'danger');
  }
}

async function rejectBillAction(billId) {
  const reason = prompt('Informe a justificativa obrigatória da rejeição:');
  if (!reason) return;
  try {
    await ApiClient.rejectBill(billId, {
      approver_user_id: AppState.currentUser.id,
      justification: reason
    });
    showToast('Título rejeitado e estornado para revisão.', 'warning');
    await loadPayablesQueue();
  } catch (err) {
    showToast(`Erro ao rejeitar: ${err.message}`, 'danger');
  }
}

async function loadReceivablesAging() {
  try {
    const data = await ApiClient.getReceivableAging(AppState.activeCompanyId);
    
    document.getElementById('aging-ontime').textContent = Utils.formatCurrency(data.current_due_total || 0);
    document.getElementById('aging-30').textContent = Utils.formatCurrency(data.overdue_1_30_total || 0);
    document.getElementById('aging-60').textContent = Utils.formatCurrency(data.overdue_31_60_total || 0);
    document.getElementById('aging-90').textContent = Utils.formatCurrency(data.overdue_61_90_plus_total || 0);
    document.getElementById('aging-default-rate').textContent = Utils.formatPercent(data.default_rate_pct || 0);

    const tbody = document.getElementById('aging-table-body');
    if (tbody && data.bills) {
      tbody.innerHTML = data.bills.map(b => `
        <tr>
          <td>
            <div style="font-weight: 600; color: #fff;">${b.counterparty_name}</div>
            <div style="font-size: 0.72rem; color: #9ca3af;">Doc: ${b.document_number}</div>
          </td>
          <td><b>${Utils.formatCurrency(b.final_amount)}</b></td>
          <td>${Utils.formatDate(b.due_date)}</td>
          <td><b style="color: ${b.days_overdue > 0 ? '#ef4444' : '#10b981'};">${b.days_overdue > 0 ? `${b.days_overdue} dias` : 'No prazo'}</b></td>
          <td><span class="badge badge-${b.days_overdue > 30 ? 'danger' : b.days_overdue > 0 ? 'warning' : 'success'}">${b.bracket}</span></td>
          <td>
            <button class="btn btn-sm btn-secondary" onclick="dispatchReminderAction('${b.id}')">
              📱 Disparar Cobrança
            </button>
          </td>
        </tr>
      `).join('');
    }
  } catch (err) {
    console.error(err);
  }
}

async function dispatchReminderAction(billId) {
  try {
    await ApiClient.dispatchReminder(billId, {
      channel: 'whatsapp',
      message_type: 'collection_notice'
    });
    showToast('Lembrete automático de cobrança disparado via WhatsApp!', 'success');
  } catch (err) {
    showToast(`Erro ao disparar: ${err.message}`, 'danger');
  }
}

/* ==========================================================================
   VIEW 6: CONCILIAÇÃO BANCÁRIA OFX
   ========================================================================== */
async function renderReconciliationView(container) {
  container.innerHTML = `
    <div class="view-header">
      <div class="view-title-group">
        <h2>🏦 Conciliação Bancária Automática</h2>
        <p>Importação de extratos OFX, deduplicação FITID e motor inteligente de matching com livros contábeis.</p>
      </div>
      <div class="view-actions">
        <button class="btn btn-primary" onclick="openImportOfxModal()">
          <span>📥 Importar Extrato OFX</span>
        </button>
      </div>
    </div>

    <!-- Balance Check Audit Card -->
    <div class="card" style="margin-bottom: 1.5rem;">
      <div class="card-header">
        <div class="card-title">Conferência Matemática de Saldos Bancários</div>
        <span class="badge badge-success" id="balance-check-badge">Equação Verificada</span>
      </div>
      <div class="grid-4" style="margin-bottom: 0;">
        <div>
          <div class="stat-label">Saldo Inicial</div>
          <div style="font-size: 1.25rem; font-weight: 700; color: #fff;" id="rec-bal-opening">R$ 120.000,00</div>
        </div>
        <div>
          <div class="stat-label">(+) Entradas Reconciliadas</div>
          <div style="font-size: 1.25rem; font-weight: 700; color: #10b981;" id="rec-bal-in">+ R$ 45.000,00</div>
        </div>
        <div>
          <div class="stat-label">(-) Saídas Reconciliadas</div>
          <div style="font-size: 1.25rem; font-weight: 700; color: #ef4444;" id="rec-bal-out">- R$ 16.479,55</div>
        </div>
        <div>
          <div class="stat-label">(=) Saldo Final Auditado</div>
          <div style="font-size: 1.25rem; font-weight: 700; color: #3b82f6;" id="rec-bal-closing">R$ 148.520,45</div>
        </div>
      </div>
    </div>

    <!-- Unmatched Transactions -->
    <div class="card">
      <div class="card-header">
        <div class="card-title">Extrato Bancário: Transações Pendentes de Conciliação</div>
        <button class="btn btn-sm btn-secondary" onclick="loadReconciliationSuggestions()">
          ⚡ Executar Motor de Sugestões
        </button>
      </div>
      <div class="table-responsive">
        <table class="table">
          <thead>
            <tr>
              <th>Data</th>
              <th>Descrição do Lançamento Bancário (Memo)</th>
              <th>FITID (Identificador Único)</th>
              <th>Valor (R$)</th>
              <th>Tipo</th>
              <th>Ação Inteligente</th>
            </tr>
          </thead>
          <tbody id="reconciliation-table-body">
            <tr><td colspan="6" style="text-align: center; color: #9ca3af;">Carregando transações bancárias...</td></tr>
          </tbody>
        </table>
      </div>
    </div>
  `;

  await loadReconciliationData();
}

async function loadReconciliationData() {
  try {
    const accountId = 'bank-acc-01'; // Default Itaú
    const trxs = await ApiClient.getUnmatchedTransactions(accountId);
    const tbody = document.getElementById('reconciliation-table-body');
    if (!tbody) return;

    if (trxs.length === 0) {
      tbody.innerHTML = `<tr><td colspan="6" style="text-align: center; padding: 2rem; color: #10b981;">✓ Todas as transações do extrato estão conciliadas!</td></tr>`;
      return;
    }

    tbody.innerHTML = trxs.map(t => {
      const isCredit = Number(t.amount) > 0;
      const isTariff = t.memo.toLowerCase().includes('tar') || t.memo.toLowerCase().includes('taxa');
      return `
        <tr>
          <td><b>${Utils.formatDate(t.transaction_date)}</b></td>
          <td>
            <div style="font-weight: 600; color: #fff;">${t.memo}</div>
          </td>
          <td><code>${t.fitid}</code></td>
          <td><b style="color: ${isCredit ? '#10b981' : '#ef4444'}; font-size: 1rem;">${Utils.formatCurrency(t.amount)}</b></td>
          <td><span class="badge badge-${isCredit ? 'success' : 'danger'}">${isCredit ? 'Entrada' : 'Saída'}</span></td>
          <td>
            <div style="display: flex; gap: 0.4rem;">
              ${isTariff 
                ? `<button class="btn btn-sm btn-primary" onclick="quickReconcileTariffAction('${t.id}')">⚡ 1-Clique Tarifa</button>` 
                : `<button class="btn btn-sm btn-secondary" onclick="matchTransactionWithBill('${t.id}', '${t.amount}')">Vincular a Título</button>`}
            </div>
          </td>
        </tr>
      `;
    }).join('');
  } catch (err) {
    console.error(err);
  }
}

async function quickReconcileTariffAction(trxId) {
  try {
    await ApiClient.quickReconcileExpense({
      transaction_id: trxId,
      expense_category: 'Tarifas e Custódia Bancária'
    });
    showToast('Tarifa conciliada em 1 clique e lançada na DRE com sucesso!', 'success');
    await loadReconciliationData();
  } catch (err) {
    showToast(`Erro na conciliação rápida: ${err.message}`, 'danger');
  }
}

async function matchTransactionWithBill(trxId, amount) {
  try {
    await ApiClient.confirmReconciliation({
      company_id: AppState.activeCompanyId,
      bank_account_id: 'bank-acc-01',
      transaction_ids: [trxId],
      bill_ids: ['bill-pay-01'],
      match_type: 'exact_1_1'
    });
    showToast('Transação vinculada e conciliada contra título a pagar!', 'success');
    await loadReconciliationData();
  } catch (err) {
    showToast(`Erro ao conciliar: ${err.message}`, 'danger');
  }
}

/* ==========================================================================
   VIEW 7: DRE, FLUXO DE CAIXA E DASHBOARDS
   ========================================================================== */
async function renderAnalyticsView(container) {
  container.innerHTML = `
    <div class="view-header">
      <div class="view-title-group">
        <h2>📈 DRE Dinâmica, Fluxo de Caixa & Indicadores</h2>
        <p>Demonstração contábil por competência com Análise Vertical/Horizontal e projeção preditiva diária.</p>
      </div>
      <div class="view-actions">
        <button class="btn btn-secondary" onclick="exportPdfReportPrompt()">
          <span>📄 Exportar Relatório PDF</span>
        </button>
      </div>
    </div>

    <!-- Financial KPI Cards -->
    <div class="grid-4" id="kpi-cards-grid">
      <div class="card stat-card">
        <div class="stat-content">
          <div class="stat-label">PMR (Recebimento)</div>
          <div class="stat-value" id="kpi-pmr">--</div>
          <div class="stat-trend trend-neutral">Prazo Médio em dias</div>
        </div>
      </div>
      <div class="card stat-card">
        <div class="stat-content">
          <div class="stat-label">PMP (Pagamento)</div>
          <div class="stat-value" id="kpi-pmp">--</div>
          <div class="stat-trend trend-neutral">Prazo Médio em dias</div>
        </div>
      </div>
      <div class="card stat-card">
        <div class="stat-content">
          <div class="stat-label">Ponto de Equilíbrio</div>
          <div class="stat-value" id="kpi-breakeven">--</div>
          <div class="stat-trend trend-up">Faturamento mínimo</div>
        </div>
      </div>
      <div class="card stat-card">
        <div class="stat-content">
          <div class="stat-label">Liquidez Corrente</div>
          <div class="stat-value" id="kpi-liquidity">--</div>
          <div class="stat-trend trend-up">Capacidade de solvência</div>
        </div>
      </div>
    </div>

    <!-- Predictive Deficit Alert Banner -->
    <div id="deficit-alert-container"></div>

    <!-- Daily Cash Flow Chart -->
    <div class="card" style="margin-bottom: 1.5rem;">
      <div class="card-header">
        <div class="card-title">Projeção Diária de Fluxo de Caixa (Próximos 30 Dias)</div>
        <span class="badge badge-info">Saldo Inicial: R$ 120.000,00</span>
      </div>
      <div class="chart-container" style="height: 300px;">
        <canvas id="chart-cash-flow"></canvas>
      </div>
    </div>

    <!-- DRE Statement Table -->
    <div class="card">
      <div class="card-header">
        <div class="card-title">DRE - Demonstração do Resultado do Exercício (${AppState.competence})</div>
        <span class="badge badge-success">Regime de Competência</span>
      </div>
      <div class="table-responsive">
        <table class="table">
          <thead>
            <tr>
              <th>Estrutura da DRE</th>
              <th style="text-align: right;">Realizado (R$)</th>
              <th style="text-align: right;">Análise Vertical (%)</th>
              <th style="text-align: right;">Análise Horizontal (%)</th>
            </tr>
          </thead>
          <tbody id="dre-table-body">
            <tr><td colspan="4" style="text-align: center; color: #9ca3af;">Carregando DRE contábil...</td></tr>
          </tbody>
        </table>
      </div>
    </div>
  `;

  await loadAnalyticsData();
}

async function loadAnalyticsData() {
  try {
    // 1. KPIs
    const kpis = await ApiClient.getKpis(AppState.activeCompanyId, AppState.competence);
    document.getElementById('kpi-pmr').textContent = `${kpis.prazo_medio_recebimento_dias || 30} dias`;
    document.getElementById('kpi-pmp').textContent = `${kpis.prazo_medio_pagamento_dias || 30} dias`;
    document.getElementById('kpi-breakeven').textContent = Utils.formatCurrency(kpis.ponto_de_equilibrio_reais || 100000);
    document.getElementById('kpi-liquidity').textContent = (kpis.indice_liquidez_corrente || 1.5).toFixed(2);

    // 2. Cash Flow
    const cf = await ApiClient.getCashFlow(AppState.activeCompanyId, 30);
    if (cf && cf.timeline) {
      MiniCharts.drawCashFlow('chart-cash-flow', cf.timeline);
    }

    // Check Deficit Alerts
    const alertContainer = document.getElementById('deficit-alert-container');
    if (cf.has_negative_balance_alert && cf.deficit_alerts && cf.deficit_alerts.length > 0) {
      const firstDeficit = cf.deficit_alerts[0];
      alertContainer.innerHTML = `
        <div class="deficit-alert-banner">
          <div>
            <b style="color: #ef4444; font-size: 0.95rem;">🚨 ALERTA PREDITIVO DE DEFICIT EM FLUXO DE CAIXA</b>
            <div style="font-size: 0.85rem; color: #fca5a5; margin-top: 0.2rem;">
              Projeção indica saldo negativo no dia <b>${Utils.formatDate(firstDeficit.date)}</b> com déficit de <b>${Utils.formatCurrency(firstDeficit.deficit_amount)}</b>. Necessária ação antecipada de capital de giro ou reprogramação de contas.
            </div>
          </div>
          <button class="btn btn-sm btn-danger" onclick="navigateTo('finance')">Reprogramar Contas</button>
        </div>
      `;
    }

    // 3. DRE
    const dre = await ApiClient.getDre(AppState.activeCompanyId, AppState.competence);
    const tbody = document.getElementById('dre-table-body');
    if (!tbody) return;

    const dreRows = [
      { label: '(=) RECEITA BRUTA DE VENDAS E SERVIÇOS', val: dre.gross_revenue, pct: 100.0, ah: dre.horizontal_analysis?.gross_revenue_growth_pct, isBold: true },
      { label: '(-) Deduções da Receita Bruta (Impostos e Tributos)', val: -Math.abs(dre.sales_deductions), pct: dre.gross_revenue ? (dre.sales_deductions / dre.gross_revenue) * 100 : 0 },
      { label: '(=) RECEITA LÍQUIDA', val: dre.net_revenue, pct: dre.gross_revenue ? (dre.net_revenue / dre.gross_revenue) * 100 : 0, ah: dre.horizontal_analysis?.net_revenue_growth_pct, isBold: true, isHighlight: true },
      { label: '(-) Custos dos Serviços Prestados (CSP/CPV)', val: -Math.abs(dre.cogs), pct: dre.gross_revenue ? (dre.cogs / dre.gross_revenue) * 100 : 0 },
      { label: '(=) LUCRO BRUTO', val: dre.gross_profit, pct: dre.gross_margin_pct, ah: dre.horizontal_analysis?.gross_profit_growth_pct, isBold: true },
      { label: '(-) Despesas Operacionais e Administrativas', val: -Math.abs(dre.operating_expenses), pct: dre.gross_revenue ? (dre.operating_expenses / dre.gross_revenue) * 100 : 0 },
      { label: '(=) EBITDA (Resultado Operacional)', val: dre.ebitda, pct: dre.ebitda_margin_pct, ah: dre.horizontal_analysis?.ebitda_growth_pct, isBold: true, isHighlight: true },
      { label: '(+) Receitas Financeiras', val: dre.financial_revenues, pct: dre.gross_revenue ? (dre.financial_revenues / dre.gross_revenue) * 100 : 0 },
      { label: '(-) Despesas Financeiras', val: -Math.abs(dre.financial_expenses), pct: dre.gross_revenue ? (dre.financial_expenses / dre.gross_revenue) * 100 : 0 },
      { label: '(=) LUCRO LÍQUIDO DO EXERCÍCIO', val: dre.net_income, pct: dre.net_margin_pct, ah: dre.horizontal_analysis?.net_income_growth_pct, isBold: true, isFinal: true },
    ];

    tbody.innerHTML = dreRows.map(r => `
      <tr style="${r.isFinal ? 'background: rgba(16, 185, 129, 0.1); border-top: 2px solid var(--success);' : r.isHighlight ? 'background: rgba(59, 130, 246, 0.08);' : ''}">
        <td style="${r.isBold ? 'font-weight: 700; color: #fff;' : 'padding-left: 2rem; color: #9ca3af;'}">${r.label}</td>
        <td style="text-align: right; ${r.isBold ? 'font-weight: 700; color: #fff;' : ''}">${Utils.formatCurrency(r.val)}</td>
        <td style="text-align: right; color: #9ca3af;">${r.pct ? r.pct.toFixed(1) + '%' : '-'}</td>
        <td style="text-align: right; color: ${r.ah > 0 ? '#10b981' : r.ah < 0 ? '#ef4444' : '#9ca3af'};">${r.ah !== undefined ? (r.ah > 0 ? '+' : '') + r.ah.toFixed(1) + '%' : '-'}</td>
      </tr>
    `).join('');

  } catch (err) {
    console.error(err);
  }
}

async function exportPdfReportPrompt() {
  try {
    const res = await ApiClient.exportPdf(AppState.activeCompanyId, {
      competence: AppState.competence,
      format: 'pdf',
      include_cover: true
    });
    showToast(`Relatório Executivo PDF gerado com sucesso! Arquivo: ${res.download_url}`, 'success');
  } catch (err) {
    showToast(`Erro ao exportar PDF: ${err.message}`, 'danger');
  }
}

/* ==========================================================================
   VIEW 8: AUTOMAÇÃO E IA CONTÁBIL (HUMAN-IN-THE-LOOP)
   ========================================================================== */
async function renderAiView(container) {
  container.innerHTML = `
    <div class="view-header">
      <div class="view-title-group">
        <h2>🤖 Automação e IA Contábil (Human-in-the-Loop)</h2>
        <p>Extração OCR, sugestão de partidas dobradas e ciclo de aprendizado supervisionado.</p>
      </div>
      <div class="view-actions">
        <button class="btn btn-primary" onclick="generateExecutiveSummaryAction()">
          <span>📝 Gerar Sumário Executivo</span>
        </button>
      </div>
    </div>

    <!-- AI Suggestion Pipeline Card -->
    <div class="card" style="margin-bottom: 1.5rem;">
      <div class="card-header">
        <div class="card-title">
          <span>🧠 Sugestões de Partidas Dobradas (Plano de Contas)</span>
          <span class="ai-pill">✨ Auto-Classifier</span>
        </div>
        <span class="badge badge-purple">Supervisão Humana Ativa</span>
      </div>
      <p style="color: #9ca3af; font-size: 0.85rem; margin-bottom: 1.25rem;">
        O motor de Inteligência Artificial correlaciona extratos bancários e notas fiscais para classificar Débito/Crédito com score numérico de assertividade.
      </p>

      <div style="background: rgba(0,0,0,0.25); border: 1px solid var(--border-card); border-radius: 12px; padding: 1.25rem;">
        <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 0.75rem;">
          <div>
            <div style="font-weight: 700; color: #fff; font-size: 1rem;">Aquisição de Notebooks Dell (NF 88291)</div>
            <div style="color: #9ca3af; font-size: 0.8rem;">Valor: R$ 4.500,00 • Transação: ITAU-20261003-998812</div>
          </div>
          <span class="badge badge-success" style="font-size: 0.85rem;">Confiança: 96.8%</span>
        </div>

        <div class="grid-2" style="margin-bottom: 1rem;">
          <div style="background: rgba(255,255,255,0.03); padding: 0.75rem; border-radius: 8px;">
            <div style="font-size: 0.72rem; color: #9ca3af; text-transform: uppercase;">Conta Débito Sugerida (Aplicação)</div>
            <div style="font-weight: 600; color: #60a5fa; margin-top: 0.2rem;">1.1.03.01 - Equipamentos de Informática (Ativo Imobilizado)</div>
          </div>
          <div style="background: rgba(255,255,255,0.03); padding: 0.75rem; border-radius: 8px;">
            <div style="font-size: 0.72rem; color: #9ca3af; text-transform: uppercase;">Conta Crédito Sugerida (Origem)</div>
            <div style="font-weight: 600; color: #10b981; margin-top: 0.2rem;">1.1.01.02 - Banco Itaú Conta Movimento</div>
          </div>
        </div>

        <div style="display: flex; gap: 0.75rem; justify-content: flex-end;">
          <button class="btn btn-sm btn-secondary" onclick="aiCorrectModal('sugg-01')">✏️ Ajustar Plano</button>
          <button class="btn btn-sm btn-success" onclick="aiApproveSuggestion('sugg-01')">✓ Confirmar e Treinar Modelo</button>
        </div>
      </div>
    </div>

    <!-- AI Anomaly Detection Grid -->
    <div class="card">
      <div class="card-header">
        <div class="card-title">Radar de Inconsistências & Duplicidades Preditivas</div>
        <button class="btn btn-sm btn-secondary" onclick="scanAnomaliesAction()">Reexecutar Varredura</button>
      </div>
      <div id="ai-anomalies-container">
        <p style="color: #9ca3af; font-size: 0.85rem;">Carregando alertas...</p>
      </div>
    </div>
  `;

  await loadAiViewData();
}

async function loadAiViewData() {
  try {
    const list = await ApiClient.getAnomalies(AppState.activeCompanyId);
    const container = document.getElementById('ai-anomalies-container');
    if (!container) return;

    if (list.length === 0) {
      container.innerHTML = `<p style="color: #10b981; font-size: 0.85rem;">✓ Nenhuma anomalia fiscal ou financeira detectada para esta empresa.</p>`;
      return;
    }

    container.innerHTML = list.map(a => `
      <div style="background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.08); border-radius: 8px; padding: 1rem; margin-bottom: 0.75rem; display: flex; align-items: center; justify-content: space-between;">
        <div>
          <div style="font-weight: 600; color: #fff;">${a.details.description || a.anomaly_type}</div>
          <div style="font-size: 0.75rem; color: #9ca3af; margin-top: 0.2rem;">Tipo: <code>${a.anomaly_type}</code> • Severidade: <span class="badge badge-${a.severity === 'critical' ? 'danger' : 'warning'}">${a.severity}</span></div>
        </div>
        <button class="btn btn-sm btn-secondary" onclick="showToast('Alerta arquivado pelo operador.', 'info')">Dispensar</button>
      </div>
    `).join('');
  } catch (err) {
    console.error(err);
  }
}

async function aiApproveSuggestion(suggId) {
  try {
    await ApiClient.sendClassificationFeedback(suggId, {
      decision: 'accepted',
      reviewed_by: AppState.currentUser.id
    });
    showToast('Classificação aceita com sucesso! Ciclo de aprendizado contínuo atualizado.', 'success');
  } catch (err) {
    showToast(`Erro ao enviar feedback: ${err.message}`, 'danger');
  }
}

async function generateExecutiveSummaryAction() {
  try {
    const res = await ApiClient.generateExecutiveSummary(AppState.activeCompanyId, {
      month: 9,
      year: 2026,
      metrics_summary: {
        faturamento_bruto: 245000.0,
        lucro_liquido: 61000.0,
        margem_liquida_pct: 24.9
      }
    });
    alert(`SUMÁRIO EXECUTIVO GERADO PELA IA:\n\n${res.executive_summary_text}\n\nAVISO LEGAL CFC OBRIGATÓRIO:\n${res.legal_disclaimer}`);
  } catch (err) {
    showToast(`Erro ao gerar sumário: ${err.message}`, 'danger');
  }
}

/* ==========================================================================
   VIEW 9: INTEGRAÇÕES FISCAIS E GOVERNAMENTAIS
   ========================================================================== */
async function renderFiscalView(container) {
  container.innerHTML = `
    <div class="view-header">
      <div class="view-title-group">
        <h2>🏛️ Integrações Fiscais e Governamentais</h2>
        <p>Transmissões eSocial, EFD-Reinf, DCTFWeb com fila resiliente e monitoramento CND.</p>
      </div>
      <div class="view-actions">
        <button class="btn btn-primary" onclick="openConsolidateDctfwebModal()">
          <span>📑 Consolidar DCTFWeb & DARF</span>
        </button>
      </div>
    </div>

    <!-- CND Status Card -->
    <div class="card" style="margin-bottom: 1.5rem;">
      <div class="card-header">
        <div class="card-title">Certidão Negativa de Débitos Federais (CND / SERPRO Integra Contador)</div>
        <span class="badge badge-success" id="cnd-badge">Regular</span>
      </div>
      <div class="grid-3" style="margin-bottom: 0;">
        <div>
          <div class="stat-label">Número da Certidão</div>
          <div style="font-weight: 600; color: #fff;" id="cnd-number">CND-RFB-2026-998877</div>
        </div>
        <div>
          <div class="stat-label">Validade Jurídica</div>
          <div style="font-weight: 600; color: #10b981;" id="cnd-validity">90 dias restantes</div>
        </div>
        <div>
          <div class="stat-label">Proxy e-CAC Autenticado</div>
          <div style="font-weight: 600; color: #3b82f6;">✓ Conexão Ativa</div>
        </div>
      </div>
    </div>

    <!-- Fiscal Transmissions Queue -->
    <div class="card">
      <div class="card-header">
        <div class="card-title">Fila de Eventos Transmitidos (eSocial & EFD-Reinf)</div>
        <button class="btn btn-sm btn-secondary" onclick="enqueueDemoTransmission()">+ Enfileirar Novo Evento</button>
      </div>
      <div class="table-responsive">
        <table class="table">
          <thead>
            <tr>
              <th>Sistema de Destino</th>
              <th>Evento</th>
              <th>Competência</th>
              <th>Idempotência</th>
              <th>Recibo / Protocolo</th>
              <th>Status</th>
              <th>Ações</th>
            </tr>
          </thead>
          <tbody id="fiscal-table-body">
            <tr><td colspan="7" style="text-align: center; color: #9ca3af;">Carregando transmissões...</td></tr>
          </tbody>
        </table>
      </div>
    </div>
  `;

  await loadFiscalData();
}

async function loadFiscalData() {
  try {
    const cnd = await ApiClient.getCndStatus(AppState.activeCompanyId);
    document.getElementById('cnd-number').textContent = cnd.certificate_number || 'Consultando...';
    document.getElementById('cnd-badge').textContent = cnd.status === 'regular_certidao_negativa' ? 'Regular' : 'Pendência';

    const tbody = document.getElementById('fiscal-table-body');
    if (!tbody) return;

    tbody.innerHTML = `
      <tr>
        <td><b>eSocial</b></td>
        <td><code>S-1200</code> (Remuneração)</td>
        <td>2026-09</td>
        <td><code>ESOCIAL-S1200-01</code></td>
        <td><code style="color: #10b981;">1.2.202609.491823</code></td>
        <td><span class="badge badge-success">✓ Aceito</span></td>
        <td><button class="btn btn-sm btn-secondary" onclick="alert('Recibo oficial eSocial arquivado.')">Ver XML</button></td>
      </tr>
      <tr>
        <td><b>EFD-Reinf</b></td>
        <td><code>R-4020</code> (Retenção PJ)</td>
        <td>2026-09</td>
        <td><code>REINF-R4020-01</code></td>
        <td>-</td>
        <td><span class="badge badge-info">Na Fila</span></td>
        <td><button class="btn btn-sm btn-primary" onclick="showToast('Transmissão reprocessada com sucesso!', 'success')">Transmitir</button></td>
      </tr>
    `;
  } catch (err) {
    console.error(err);
  }
}

async function enqueueDemoTransmission() {
  try {
    await ApiClient.enqueueFiscalTransmission({
      company_id: AppState.activeCompanyId,
      system_target: 'esocial',
      event_type: 'S-2200',
      competence: AppState.competence,
      xml_payload: '<eSocial><evtAdmissao>...</evtAdmissao></eSocial>'
    });
    showToast('Evento fiscal enfileirado com sucesso!', 'success');
    await loadFiscalData();
  } catch (err) {
    showToast(`Erro ao enfileirar: ${err.message}`, 'danger');
  }
}

/* ==========================================================================
   VIEW 10: PORTAL DO CLIENTE E ATENDIMENTO
   ========================================================================== */
async function renderPortalView(container) {
  container.innerHTML = `
    <div class="view-header">
      <div class="view-title-group">
        <h2>💬 Portal do Cliente & Atendimento Estruturado</h2>
        <p>Chamados com SLA, troca segura de mensagens e entrega probatória de guias de impostos.</p>
      </div>
      <div class="view-actions">
        <button class="btn btn-primary" onclick="openNewTicketModal()">
          <span>+ Novo Chamado</span>
        </button>
      </div>
    </div>

    <!-- Available Tax Guides for Client -->
    <div class="card" style="margin-bottom: 1.5rem;">
      <div class="card-header">
        <div class="card-title">Guias Tributárias Disponíveis para Download</div>
        <span class="badge badge-warning">Confirmação de Leitura Registrada</span>
      </div>
      <div class="table-responsive">
        <table class="table">
          <thead>
            <tr>
              <th>Guia / Documento</th>
              <th>Competência</th>
              <th>Vencimento</th>
              <th>Código de Barras / Chave PIX</th>
              <th>Confirmação do Cliente</th>
              <th>Ação</th>
            </tr>
          </thead>
          <tbody id="guides-table-body">
            <tr><td colspan="6" style="text-align: center; color: #9ca3af;">Carregando guias...</td></tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Tickets / Helpdesk -->
    <div class="card">
      <div class="card-header">
        <div class="card-title">Chamados de Atendimento (${AppState.activeCompany?.corporate_name || ''})</div>
        <span class="badge badge-info">SLA Médio: 24h</span>
      </div>
      <div class="table-responsive">
        <table class="table">
          <thead>
            <tr>
              <th>Assunto / Título</th>
              <th>Categoria</th>
              <th>Prioridade</th>
              <th>SLA Vencimento</th>
              <th>Status</th>
              <th>Ações</th>
            </tr>
          </thead>
          <tbody id="tickets-table-body">
            <tr><td colspan="6" style="text-align: center; color: #9ca3af;">Carregando chamados...</td></tr>
          </tbody>
        </table>
      </div>
    </div>
  `;

  await loadPortalData();
}

async function loadPortalData() {
  try {
    // 1. Guides
    const guides = await ApiClient.getAvailableGuides(AppState.activeCompanyId);
    const tbodyGuides = document.getElementById('guides-table-body');
    if (tbodyGuides) {
      tbodyGuides.innerHTML = guides.map(g => `
        <tr>
          <td><b style="color: #fff;">${g.title}</b></td>
          <td>${g.competence}</td>
          <td><b style="color: #ef4444;">${Utils.formatDate(g.due_date)}</b></td>
          <td><code>${g.barcode_line ? g.barcode_line.substring(0, 20) + '...' : g.pix_key || '-'}</code></td>
          <td>${g.viewed_by_client ? '<span class="badge badge-success">✓ Confirmado pelo Cliente</span>' : '<span class="badge badge-warning">Aguardando Leitura</span>'}</td>
          <td>
            <button class="btn btn-sm btn-primary" onclick="confirmGuideAction('${g.document_id}')">
              📥 Baixar e Confirmar
            </button>
          </td>
        </tr>
      `).join('');
    }

    // 2. Tickets
    const tickets = await ApiClient.getTickets(AppState.activeCompanyId);
    const tbodyTickets = document.getElementById('tickets-table-body');
    if (tbodyTickets) {
      if (tickets.length === 0) {
        tbodyTickets.innerHTML = `<tr><td colspan="6" style="text-align: center; padding: 2rem; color: #9ca3af;">Nenhum chamado aberto para este cliente.</td></tr>`;
      } else {
        tbodyTickets.innerHTML = tickets.map(t => `
          <tr>
            <td>
              <div style="font-weight: 600; color: #fff;">${t.title}</div>
              <div style="font-size: 0.72rem; color: #9ca3af;">Aberto em: ${Utils.formatDate(t.created_at)}</div>
            </td>
            <td><span class="badge badge-neutral">${t.category}</span></td>
            <td><span class="badge badge-${t.priority === 'urgent' || t.priority === 'high' ? 'danger' : 'info'}">${t.priority}</span></td>
            <td>${Utils.formatDate(t.sla_due_at)}</td>
            <td>${Utils.badgeForStatus(t.status)}</td>
            <td>
              <button class="btn btn-sm btn-secondary" onclick="alert('Thread do chamado:\\n\\n${t.title}\\nStatus: ${t.status}')">
                💬 Mensagens
              </button>
            </td>
          </tr>
        `).join('');
      }
    }
  } catch (err) {
    console.error(err);
  }
}

async function confirmGuideAction(docId) {
  try {
    await ApiClient.confirmGuideReceipt(docId, {
      user_id: AppState.currentUser.id,
      action_type: 'downloaded_and_confirmed'
    });
    showToast('Download e confirmação probatória de recebimento registrados com sucesso!', 'success');
    await loadPortalData();
  } catch (err) {
    showToast(`Erro ao confirmar: ${err.message}`, 'danger');
  }
}

/* ==========================================================================
   VIEW 11: SEGURANÇA, LGPD E CERTIFICADOS DIGITAIS
   ========================================================================== */
async function renderSecurityView(container) {
  container.innerHTML = `
    <div class="view-header">
      <div class="view-title-group">
        <h2>🔐 Segurança, LGPD & Cofre de Certificados</h2>
        <p>Cofre criptografado AES-256-GCM, autenticação multifator (MFA TOTP) e trilha imutável de auditoria.</p>
      </div>
      <div class="view-actions">
        <button class="btn btn-secondary" onclick="openMfaSetupModal()">
          <span>📱 Configurar MFA TOTP</span>
        </button>
      </div>
    </div>

    <!-- Digital Certificates Vault Card -->
    <div class="card" style="margin-bottom: 1.5rem;">
      <div class="card-header">
        <div class="card-title">Cofre de Certificados Digitais ICP-Brasil (AES-256-GCM)</div>
        <span class="badge badge-success">Criptografia em Repouso</span>
      </div>
      <div class="table-responsive">
        <table class="table">
          <thead>
            <tr>
              <th>Titular / Razão Social</th>
              <th>CNPJ / CPF</th>
              <th>Tipo</th>
              <th>Validade Até</th>
              <th>Dias Restantes</th>
              <th>Status / Régua de Alerta</th>
            </tr>
          </thead>
          <tbody id="vault-certs-body">
            <tr><td colspan="6" style="text-align: center; color: #9ca3af;">Consultando cofre...</td></tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Immutable Audit Trail -->
    <div class="card">
      <div class="card-header">
        <div class="card-title">Trilha Imutável de Auditoria (Append-Only Log)</div>
        <span class="badge badge-info">LGPD Compliance</span>
      </div>
      <div class="table-responsive">
        <table class="table">
          <thead>
            <tr>
              <th>Data/Hora (UTC)</th>
              <th>Usuário / Ator</th>
              <th>Ação Auditada</th>
              <th>Tipo de Recurso</th>
              <th>Endereço IP</th>
              <th>Snapshot / Detalhes</th>
            </tr>
          </thead>
          <tbody id="audit-logs-body">
            <tr><td colspan="6" style="text-align: center; color: #9ca3af;">Carregando logs de auditoria...</td></tr>
          </tbody>
        </table>
      </div>
    </div>
  `;

  await loadSecurityData();
}

async function loadSecurityData() {
  try {
    // 1. Certs
    const certs = await ApiClient.getCertificates();
    const tbodyCerts = document.getElementById('vault-certs-body');
    if (tbodyCerts) {
      tbodyCerts.innerHTML = certs.map(c => {
        const days = c.days_until_expiration;
        const isExpired = days < 0;
        const isUrgent = days >= 0 && days <= 15;
        const isAttention = days > 15 && days <= 30;
        const badgeClass = isExpired ? 'danger' : isUrgent ? 'warning' : isAttention ? 'info' : 'success';
        const badgeLabel = isExpired ? 'Vencido' : isUrgent ? 'Alerta 15d' : isAttention ? 'Atenção 30d' : 'Ativo';
        const daysText = isExpired ? `Vencido há ${Math.abs(days)} dias` : `${days} dias`;
        const daysColor = isExpired ? '#ef4444' : isUrgent ? '#f59e0b' : '#10b981';
        const displayName = c.common_name ? c.common_name.split(':')[0] : c.issued_to_tax_id;

        return `
        <tr>
          <td><b style="color: #fff;">${displayName}</b></td>
          <td><code>${Utils.formatCnpj(c.issued_to_tax_id)}</code></td>
          <td><span class="badge badge-info">${c.certificate_type.toUpperCase()}</span></td>
          <td>${Utils.formatDate(c.valid_until)}</td>
          <td><b style="color: ${daysColor};">${daysText}</b></td>
          <td>
            <span class="badge badge-${badgeClass}">
              ${badgeLabel}
            </span>
          </td>
        </tr>
      `;
      }).join('');
    }

    // 2. Audit Logs
    const logs = await ApiClient.getAuditLogs({ limit: 20 });
    const tbodyLogs = document.getElementById('audit-logs-body');
    if (tbodyLogs) {
      tbodyLogs.innerHTML = logs.map(l => `
        <tr>
          <td>${Utils.formatDateTime(l.created_at)}</td>
          <td><code>${l.actor_user_id || 'system'}</code></td>
          <td><b style="color: #60a5fa;">${l.action}</b></td>
          <td><span class="badge badge-neutral">${l.resource_type}</span></td>
          <td><code>${l.ip_address}</code></td>
          <td><code style="font-size: 0.72rem;">${l.payload_snapshot ? JSON.stringify(l.payload_snapshot).substring(0, 35) + '...' : '-'}</code></td>
        </tr>
      `).join('');
    }
  } catch (err) {
    console.error(err);
  }
}

/* ==========================================================================
   MODAL CONTROLLERS & FORM SUBMISSIONS
   ========================================================================== */

// Modal: Nova Empresa
function openCreateCompanyModal() {
  openModal('modal-create-company');
}

async function submitCreateCompanyForm(event) {
  event.preventDefault();
  const corporate_name = document.getElementById('modal-comp-name').value;
  const tax_id = document.getElementById('modal-comp-cnpj').value;
  const tax_regime = document.getElementById('modal-comp-regime').value;

  try {
    await ApiClient.createCompany({
      organization_id: AppState.organizationId,
      corporate_name,
      tax_id,
      tax_regime
    });
    showToast('Empresa cadastrada com sucesso com CNPJ validado!', 'success');
    closeModal('modal-create-company');
    await loadInitialCompanies();
    if (AppState.activeView === 'companies') await renderCompaniesView(document.getElementById('content-container'));
  } catch (err) {
    showToast(`Erro ao cadastrar: ${err.message}`, 'danger');
  }
}

// Modal: Solicitação em Lote
function openBatchRequestModal() {
  openModal('modal-batch-request');
}

async function submitBatchRequestForm(event) {
  event.preventDefault();
  try {
    const res = await ApiClient.batchRequestDocuments({
      organization_id: AppState.organizationId,
      competence: AppState.competence
    });
    showToast(`Solicitação em lote enviada! Sucessos: ${res.success_count}, Falhas: ${res.failed_count}`, 'success');
    closeModal('modal-batch-request');
  } catch (err) {
    showToast(`Erro na solicitação: ${err.message}`, 'danger');
  }
}

// Modal: Anexar Recibo
function openAttachReceiptModal(taskId) {
  document.getElementById('modal-attach-task-id').value = taskId;
  openModal('modal-attach-receipt');
}

async function submitAttachReceiptForm(event) {
  event.preventDefault();
  const taskId = document.getElementById('modal-attach-task-id').value;
  const fileHash = document.getElementById('modal-attach-hash').value || 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855';

  try {
    await ApiClient.attachTaskReceipt(taskId, {
      file_id: 'rec-' + Date.now(),
      file_hash: fileHash,
      user_id: AppState.currentUser.id
    });
    showToast('Comprovante oficial anexado com hash registrado!', 'success');
    closeModal('modal-attach-receipt');
    if (AppState.activeView === 'obligations') await loadTasksList();
  } catch (err) {
    showToast(`Erro ao anexar: ${err.message}`, 'danger');
  }
}

// Modal: Ingerir Documento
function openUploadDocModal() {
  openModal('modal-upload-doc');
}

async function submitUploadDocForm(event) {
  event.preventDefault();
  const fileInput = document.getElementById('modal-upload-file');
  if (!fileInput.files.length) {
    showToast('Por favor selecione um arquivo.', 'warning');
    return;
  }

  const fd = new FormData();
  fd.append('company_id', AppState.activeCompanyId);
  fd.append('competence', AppState.competence);
  fd.append('department', document.getElementById('modal-upload-dept').value);
  fd.append('file', fileInput.files[0]);

  try {
    const res = await ApiClient.uploadDocument(fd);
    showToast(`Documento ${res.file_name} ingerido e auditado com sucesso!`, 'success');
    closeModal('modal-upload-doc');
    if (AppState.activeView === 'documents') await loadDocumentsViewData();
  } catch (err) {
    showToast(`Erro no upload: ${err.message}`, 'danger');
  }
}

// Modal: Novo Título a Pagar
function openCreatePayableModal() {
  openModal('modal-create-payable');
}

async function submitCreatePayableForm(event) {
  event.preventDefault();
  const payload = {
    company_id: AppState.activeCompanyId,
    type: 'payable',
    counterparty_name: document.getElementById('modal-pay-counterparty').value,
    original_amount: Number(document.getElementById('modal-pay-amount').value),
    final_amount: Number(document.getElementById('modal-pay-amount').value),
    issue_date: new Date().toISOString().split('T')[0],
    due_date: document.getElementById('modal-pay-duedate').value,
    payment_method: document.getElementById('modal-pay-method').value,
    barcode_line: document.getElementById('modal-pay-barcode').value || undefined,
    pix_key: document.getElementById('modal-pay-pix').value || undefined
  };

  try {
    await ApiClient.createPayableBill(payload);
    showToast('Título a pagar registrado na fila de aprovação BPO!', 'success');
    closeModal('modal-create-payable');
    if (AppState.activeView === 'finance') await loadPayablesQueue();
  } catch (err) {
    showToast(`Erro ao registrar título: ${err.message}`, 'danger');
  }
}

// Modal: Novo Chamado
function openNewTicketModal() {
  openModal('modal-new-ticket');
}

async function submitNewTicketForm(event) {
  event.preventDefault();
  const payload = {
    company_id: AppState.activeCompanyId,
    category: document.getElementById('modal-ticket-category').value,
    title: document.getElementById('modal-ticket-title').value,
    priority: document.getElementById('modal-ticket-priority').value,
    created_by_user_id: AppState.currentUser.id,
    structured_data: { description: document.getElementById('modal-ticket-desc').value }
  };

  try {
    await ApiClient.createTicket(payload);
    showToast('Chamado registrado com sucesso com SLA inicializado!', 'success');
    closeModal('modal-new-ticket');
    if (AppState.activeView === 'portal') await loadPortalData();
  } catch (err) {
    showToast(`Erro ao abrir chamado: ${err.message}`, 'danger');
  }
}

// Modal: MFA Setup
async function openMfaSetupModal() {
  openModal('modal-mfa-setup');
  try {
    const res = await ApiClient.setupMfa(AppState.currentUser.id, AppState.currentUser.email);
    document.getElementById('mfa-secret-code').textContent = res.manual_code;
    document.getElementById('mfa-otp-url').value = res.otpauth_url;
  } catch (err) {
    console.error(err);
  }
}

async function submitMfaVerifyForm(event) {
  event.preventDefault();
  const token = document.getElementById('modal-mfa-token').value;
  try {
    await ApiClient.verifyMfa({
      user_id: AppState.currentUser.id,
      token
    });
    showToast('Autenticação multifator (MFA TOTP) verificada e ativada com sucesso!', 'success');
    closeModal('modal-mfa-setup');
  } catch (err) {
    showToast(`Código TOTP inválido: ${err.message}`, 'danger');
  }
}

window.AppState = AppState;
window.navigateTo = navigateTo;
window.openModal = openModal;
window.closeModal = closeModal;
window.showToast = showToast;
