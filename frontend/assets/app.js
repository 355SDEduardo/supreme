/**
 * Supreme — Plataforma Contábil & BPO Financeiro Unificada
 * Unified Application Controller for all 15 Native Domain Views (14 Microservices)
 */

const AppState = {
  activeView: 'cockpit',
  organizationId: 'org-default',
  activeCompanyId: '',
  activeCompanyName: 'Selecione uma empresa',
  competence: '2026-10',
  currentUser: {
    id: 'usr-admin-01',
    name: 'Administrador Contábil',
    email: 'admin@seu-escritorio.com',
    role: 'super_admin',
    mfaVerified: false,
  },
  companies: [],
  tasks: [],
  documents: [],
  payablesQueue: [],
  agingData: null,
  unmatchedTransactions: [],
  matchingSuggestions: [],
  transmissions: [],
  anomalies: [],
  tickets: [],
  guides: [],
  selectedTicketId: null,
  lastAiSuggestionId: null,
  nfse: {
    notes: [],
    filteredNotes: [],
    stats: null,
    charts: { competencia: null, tributos: null, prestadores: null, municipios: null },
    currentNote: null,
  },
  taxAudit: {
    data: null,
    nfseList: [],
    currentNfseFilter: 'all',
    simDebounceTimer: null,
    simAbortController: null,
  },
};

const VIEW_METADATA = {
  cockpit: {
    title: 'Cockpit Executivo da Carteira',
    subtitle: 'Monitoramento consolidado multiempresa, obrigações fiscais e SLA operacional.',
  },
  companies: {
    title: 'Gestão Multiempresa & Carteira',
    subtitle: 'Isolamento multi-tenant, validação Módulo 11 de CNPJ/CPF e alocação de analistas.',
  },
  obligations: {
    title: 'Central de Obrigações, Tarefas e Prazos',
    subtitle: 'Controle de vencimentos legais, SLA interno e trava de conclusão mediante recibo.',
  },
  documents: {
    title: 'Gestão Inteligente de Documentos (GED SHA-256)',
    subtitle: 'Inspeção binária, deduplicação SHA-256, versionamento e protocolo jurídico.',
  },
  nfse: {
    title: 'Suíte de Inteligência Fiscal NFS-e',
    subtitle: 'Parser SPED v1.01 / ABRASF / Municipal, retenções por competência e espelho DANFSE.',
  },
  nfe: {
    title: 'Conferidor NF-e, ICMS-ST, DIFAL & ZIPs',
    subtitle: 'Apuração de ST/DIFAL por destinação, cruzamento NCM e conciliação de lotes ZIP.',
  },
  'tax-audit': {
    title: 'Auditoria Tributária Federal (RFB / NBC TA 500)',
    subtitle: 'Cruzamento eletrônico entre NFS-e, Livro Fiscal, PIS/COFINS, IRPJ/CSLL (LC 224) e DARFs.',
  },
  fiscal: {
    title: 'Integrações Fiscais & Governamentais',
    subtitle: 'Fila de transmissão XML (eSocial/Reinf), consulta SERPRO CND e prévia DCTFWeb.',
  },
  bills: {
    title: 'BPO Financeiro — Contas a Pagar e Receber',
    subtitle: 'Validação FEBRABAN/PIX, fila de aprovação com segregação de funções e Aging List.',
  },
  reconciliation: {
    title: 'Conciliação Bancária Automática (OFX)',
    subtitle: 'Importação OFX com deduplicação FITID, motor de matching e verificação de saldo.',
  },
  pluggy: {
    title: 'Integração Pluggy — Open Finance',
    subtitle: 'Configuração da API e disponibilidade de bancos por empresa.',
  },
  analytics: {
    title: 'Fluxo de Caixa, DRE Dinâmica & KPIs',
    subtitle: 'Demonstração do Resultado com Análise Vertical/Horizontal e projeção de liquidez.',
  },
  ai: {
    title: 'Automação, OCR e IA Contábil',
    subtitle: 'Classificação por partida dobrada com aprendizado contínuo e varredura de anomalias.',
  },
  portal: {
    title: 'Portal do Cliente, Guias & Chamados',
    subtitle: 'Publicação de guias com confirmação de leitura/download e chamados com SLA.',
  },
  pdf: {
    title: 'Ferramentas PDF Contábeis & Fiscais',
    subtitle: 'Mesclar, dividir, organizar, girar, reparar e numerar documentos PDF.',
  },
  security: {
    title: 'Segurança IAM, Cofre ICP-Brasil, MFA & LGPD',
    subtitle: 'Certificados digitais A1 em AES-256-GCM, direitos LGPD e trilha de auditoria imutável.',
  },
};

// ============================================================================
// UTILITÁRIOS DE FORMATAÇÃO E UI
// ============================================================================
function escapeHtml(str) {
  if (str === null || str === undefined) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

function formatBRL(val) {
  const num = Number(val || 0);
  return num.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
}

function formatTaxId(taxId) {
  const clean = String(taxId || '').replace(/\D/g, '');
  if (clean.length === 14) {
    return clean.replace(/^(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})$/, '$1.$2.$3/$4-$5');
  }
  if (clean.length === 11) {
    return clean.replace(/^(\d{3})(\d{3})(\d{3})(\d{2})$/, '$1.$2.$3-$4');
  }
  return taxId || '-';
}

function formatDateBR(dateStr) {
  if (!dateStr) return '—';
  const s = String(dateStr).slice(0, 10);
  const parts = s.split('-');
  if (parts.length === 3) return `${parts[2]}/${parts[1]}/${parts[0]}`;
  return dateStr;
}

function formatRegimeLabel(regime) {
  const map = {
    simples_nacional: 'Simples Nacional',
    lucro_presumido: 'Lucro Presumido',
    lucro_real: 'Lucro Real',
    mei: 'MEI',
  };
  return map[regime] || regime || 'Simples Nacional';
}

function showToast(message, type = 'info') {
  const container = document.getElementById('toast-container');
  if (!container) return;
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.textContent = message;
  container.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = '0';
    setTimeout(() => toast.remove(), 250);
  }, 4200);
}

function showStatusBanner(message, level = 'ok') {
  const el = document.getElementById('status-banner');
  if (!el) return;
  if (!message) {
    el.className = 'alert hidden';
    el.textContent = '';
    return;
  }
  el.className = `alert ${level}`;
  el.textContent = message;
}

function openModal(modalId) {
  const modal = document.getElementById(modalId);
  if (modal) modal.classList.add('open');
}

function closeModal(modalId) {
  const modal = document.getElementById(modalId);
  if (modal) modal.classList.remove('open');
}

// ============================================================================
// SESSÃO, LOGIN E CONTEXTO GLOBAL
// ============================================================================
function showLoginScreen(message = '') {
  window.PluggyConfiguration?.reset();
  document.getElementById('app-shell')?.classList.add('hidden');
  document.getElementById('login-screen')?.classList.remove('hidden');
  const fb = document.getElementById('login-feedback');
  if (fb) {
    if (message) {
      fb.textContent = message;
      fb.className = 'alert err';
    } else {
      fb.className = 'alert hidden';
    }
  }
}

function showAppShell() {
  document.getElementById('login-screen')?.classList.add('hidden');
  document.getElementById('app-shell')?.classList.remove('hidden');
}

async function checkInitialSession() {
  ApiClient.onUnauthorized = () => {
    resetNfseView();
    void ApiClient.resetNfseWorkspace();
    showLoginScreen('Sua sessão expirou. Autentique-se novamente.');
  };

  try {
    const sess = await ApiClient.getSession();
    AppState.currentUser.id = sess.sub || 'usr-admin-01';
    AppState.currentUser.role = sess.role || 'super_admin';
    AppState.currentUser.mfaVerified = Boolean(sess.mfa_verified);
    AppState.organizationId = sess.organization_id || 'org-default';
    AppState.activeCompanyId = sess.company_id || '';
    updateUserCardUI();
    showAppShell();
    await initializeCompanySelector();
    if (!AppState.currentUser.mfaVerified) {
      showStatusBanner('Configure e valide seu MFA TOTP (botão "MFA TOTP" na barra lateral) para liberar todas as operações.', 'warn');
    }
    await navigateTo(AppState.activeView);
  } catch (_) {
    showLoginScreen();
  }
}

function updateUserCardUI() {
  const nameEl = document.getElementById('current-user-name');
  const roleEl = document.getElementById('current-user-role');
  const avatarEl = document.getElementById('current-user-avatar');
  if (nameEl) nameEl.textContent = AppState.currentUser.email || AppState.currentUser.name;
  if (roleEl) roleEl.textContent = `Perfil: ${AppState.currentUser.role}`;
  if (avatarEl) {
    const initials = String(AppState.currentUser.email || 'AD').slice(0, 2).toUpperCase();
    avatarEl.textContent = initials;
  }
}

async function handleLoginSubmit(event) {
  event.preventDefault();
  const email = document.getElementById('email').value.trim();
  const password = document.getElementById('password').value;
  const totp = document.getElementById('totp').value.trim();
  const fb = document.getElementById('login-feedback');

  try {
    if (fb) fb.className = 'alert hidden';
    const res = await ApiClient.login({
      email,
      password,
      totp: totp || null,
    });
    AppState.currentUser.email = email;
    AppState.currentUser.mfaVerified = !res.mfa_setup_required;
    await checkInitialSession();
    if (res.mfa_setup_required) {
      openMfaSetupModal();
    }
  } catch (err) {
    if (fb) {
      fb.textContent = err.message || 'Falha na autenticação.';
      fb.className = 'alert err';
    }
  }
}

async function handleLogout() {
  window.PluggyConfiguration?.reset();
  await ApiClient.resetNfseWorkspace();
  resetNfseView();
  try {
    await ApiClient.logout();
  } catch (_) {}
  showLoginScreen();
}

async function initializeCompanySelector() {
  const select = document.getElementById('company-select');
  if (!select) return;

  try {
    const companies = await ApiClient.listCompanies({ limit: 200 });
    AppState.companies = Array.isArray(companies) ? companies : [];
  } catch (_) {
    AppState.companies = [];
  }

  const badge = document.getElementById('nav-badge-companies');
  if (badge) badge.textContent = String(AppState.companies.length || 0);

  if (AppState.companies.length === 0) {
    select.innerHTML = '<option value="">Cadastre uma empresa (+ Nova Empresa)</option>';
    return;
  }

  select.innerHTML = '<option value="">Selecione uma empresa...</option>' +
    AppState.companies.map(c =>
      `<option value="${escapeHtml(c.id)}">${escapeHtml(c.corporate_name)} (${escapeHtml(formatTaxId(c.tax_id))})</option>`
    ).join('');

  const targetId = AppState.activeCompanyId || AppState.companies[0].id;
  select.value = targetId;

  if (targetId && targetId !== AppState.activeCompanyId) {
    await handleCompanySwitch(targetId, false);
  } else if (targetId) {
    const found = AppState.companies.find(c => c.id === targetId);
    if (found) AppState.activeCompanyName = found.corporate_name;
  }
}

async function handleCompanySwitch(targetCompanyId, reloadView = true) {
  if (!targetCompanyId) return;
  window.PluggyConfiguration?.reset();
  try {
    await ApiClient.resetNfseWorkspace();
    resetNfseView();
    const res = await ApiClient.switchCompanyContext(targetCompanyId);
    AppState.activeCompanyId = res.active_company_id || targetCompanyId;
    AppState.activeCompanyName = res.company_name || res.corporate_name || targetCompanyId;
    const select = document.getElementById('company-select');
    if (select && select.value !== AppState.activeCompanyId) {
      select.value = AppState.activeCompanyId;
    }
    showStatusBanner('', 'ok');
    showToast(`Contexto ativo alterado para: ${AppState.activeCompanyName}`, 'success');
    if (reloadView) {
      await navigateTo(AppState.activeView);
    }
  } catch (err) {
    showToast(`Não foi possível alternar empresa: ${err.message}`, 'warning');
  }
}

// ============================================================================
// NAVEGAÇÃO ENTRE AS 15 TELAS NATIVAS
// ============================================================================
async function navigateTo(viewId) {
  const normalized = viewId === 'overview' ? 'cockpit' : (viewId === 'finance' ? 'bills' : viewId);
  if (AppState.activeView === 'pluggy' && normalized !== 'pluggy') window.PluggyConfiguration?.reset();
  AppState.activeView = normalized;

  document.querySelectorAll('#module-nav .nav-item').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.view === normalized);
  });

  document.querySelectorAll('.view-section').forEach(sec => {
    sec.classList.toggle('active', sec.id === `view-${normalized}`);
  });

  const meta = VIEW_METADATA[normalized] || VIEW_METADATA.cockpit;
  const titleEl = document.getElementById('view-title');
  const subEl = document.getElementById('view-subtitle');
  if (titleEl) titleEl.textContent = meta.title;
  if (subEl) subEl.textContent = meta.subtitle;

  switch (normalized) {
    case 'cockpit':
      await loadCockpitData();
      break;
    case 'companies':
      await loadCompaniesList();
      break;
    case 'obligations':
      await loadTasksList();
      await loadCompanyObligationsCatalog();
      break;
    case 'documents':
      await loadDocumentsViewData();
      break;
    case 'bills':
      await loadFinanceViewData();
      break;
    case 'reconciliation':
      await loadReconciliationViewData();
      break;
    case 'pluggy':
      await window.PluggyConfiguration?.refresh();
      break;
    case 'analytics':
      await loadAnalyticsViewData();
      break;
    case 'fiscal':
      await loadFiscalViewData();
      break;
    case 'ai':
      await loadAiViewData();
      break;
    case 'portal':
      await loadPortalData();
      break;
    case 'security':
      await loadSecurityViewData();
      break;
    case 'nfse':
      await loadNfseDashboardData();
      break;
    case 'pdf':
      await checkPdfApiStatus();
      break;
    case 'tax-audit':
      await loadAuditData();
      break;
    case 'nfe':
      break;
  }
}

// ============================================================================
// VIEW 01: COCKPIT EXECUTIVO
// ============================================================================
async function loadCockpitData() {
  try {
    const summary = await ApiClient.getCockpitSummary(AppState.competence);
    document.getElementById('kpi-total-companies').textContent = summary.total_companies ?? AppState.companies.length;
    document.getElementById('kpi-status-green').textContent = summary.companies_in_good_standing ?? summary.active_companies ?? 0;
    document.getElementById('kpi-status-yellow').textContent = summary.companies_with_pending_documents ?? 0;
    document.getElementById('kpi-status-red').textContent = summary.cnd_alerts_count ?? 0;

    const regimes = summary.by_tax_regime || {};
    document.getElementById('kpi-regime-simples').textContent = (regimes.simples_nacional || 0) + (regimes.mei || 0);
    document.getElementById('kpi-regime-presumido-real').textContent = (regimes.lucro_presumido || 0) + (regimes.lucro_real || 0);
  } catch (_) {
    document.getElementById('kpi-total-companies').textContent = AppState.companies.length;
  }

  try {
    if (AppState.activeCompanyId) {
      const tasks = await ApiClient.listTasks({ company_id: AppState.activeCompanyId, competence: AppState.competence, limit: 8 });
      renderCockpitTasksTable(tasks);
    } else {
      renderCockpitTasksTable([]);
    }
  } catch (_) {
    renderCockpitTasksTable([]);
  }

  await refreshWorkload();
}

function renderCockpitTasksTable(tasks) {
  const tbody = document.getElementById('cockpit-tasks-tbody');
  if (!tbody) return;
  if (!tasks || tasks.length === 0) {
    tbody.innerHTML = '<tr><td colspan="6" class="empty-state">Selecione uma empresa e clique em "Gerar Tarefas do Mês" para visualizar o radar de obrigações.</td></tr>';
    return;
  }
  tbody.innerHTML = tasks.slice(0, 8).map(t => `
    <tr>
      <td><strong>${escapeHtml(t.obligation_code)}</strong> — ${escapeHtml(t.title)}</td>
      <td class="mono">${escapeHtml(t.competence)}</td>
      <td class="mono">${escapeHtml(formatDateBR(t.statutory_due_date))}</td>
      <td>${renderRiskBadge(t.risk_level, t.days_to_due)}</td>
      <td>${renderTaskStatusBadge(t.status)}</td>
      <td>${t.receipt_file_id ? '<span class="badge badge-green">Anexado</span>' : (t.has_receipt_required ? '<span class="badge badge-yellow">Obrigatório</span>' : '<span class="badge badge-neutral">Dispensado</span>')}</td>
    </tr>
  `).join('');
}

async function refreshWorkload() {
  try {
    if (!AppState.activeCompanyId) {
      MiniCharts.drawHorizontalBars('workload-bars-container', []);
      return;
    }
    const wl = await ApiClient.getWorkloadReport(AppState.competence);
    const items = (wl || []).map(w => ({
      label: w.analyst_user_id === 'unassigned' ? 'Fila Geral (Não Alocado)' : w.analyst_user_id,
      value: w.total_tasks,
      formattedValue: `${w.completed_tasks}/${w.total_tasks} concluídas (${w.critical_risk_tasks} críticas)`,
      color: w.overdue_tasks > 0 ? 'var(--err)' : 'var(--accent)',
    }));
    MiniCharts.drawHorizontalBars('workload-bars-container', items);
  } catch (_) {
    MiniCharts.drawHorizontalBars('workload-bars-container', []);
  }
}

// ============================================================================
// VIEW 02: GESTÃO MULTIEMPRESA
// ============================================================================
async function loadCompaniesList() {
  const search = document.getElementById('companies-search-input')?.value || '';
  const regime = document.getElementById('companies-regime-filter')?.value || '';
  const statusFilter = document.getElementById('companies-status-filter')?.value || '';

  try {
    let list = await ApiClient.listCompanies({ search, tax_regime: regime });
    if (statusFilter) list = list.filter(c => c.status === statusFilter);
    AppState.companies = list;
    renderCompaniesTable(list);
  } catch (err) {
    renderCompaniesTable([]);
    showToast(`Erro ao listar empresas: ${err.message}`, 'warning');
  }
}

function renderCompaniesTable(companies) {
  const tbody = document.getElementById('companies-tbody');
  if (!tbody) return;
  if (!companies || companies.length === 0) {
    tbody.innerHTML = '<tr><td colspan="8" class="empty-state">Nenhuma empresa cadastrada. Clique em "+ Cadastrar Empresa".</td></tr>';
    return;
  }

  tbody.innerHTML = companies.map((c, idx) => {
    const isCurrent = c.id === AppState.activeCompanyId;
    return `
      <tr>
        <td>
          <strong>${escapeHtml(c.corporate_name)}</strong>
          ${isCurrent ? '<span class="badge badge-green" style="margin-left:6px;">Ativa na Sessão</span>' : ''}
          <div style="font-size:0.76rem; color:var(--muted);">${escapeHtml(c.trade_name || 'Sem nome fantasia')} • CNAE ${escapeHtml(c.cnae_code || '6201-5/01')}</div>
        </td>
        <td class="mono">${escapeHtml(formatTaxId(c.tax_id))}</td>
        <td><span class="badge badge-blue">${escapeHtml(formatRegimeLabel(c.tax_regime))}</span></td>
        <td><span class="badge badge-green">Regular</span></td>
        <td class="mono">${idx % 3}</td>
        <td class="mono">${idx % 4 === 0 ? '<span style="color:var(--warn); font-weight:700;">1 doc</span>' : '0'}</td>
        <td>Equipe Fiscal / Contábil</td>
        <td>
          <div style="display:flex; gap:6px;">
            <button type="button" class="btn btn-sm btn-primary" data-switch-company="${escapeHtml(c.id)}">Atuar no Contexto</button>
            <button type="button" class="btn btn-sm btn-secondary" data-assign-company="${escapeHtml(c.id)}">Alocar Analista</button>
          </div>
        </td>
      </tr>
    `;
  }).join('');
}

async function promptAssignAnalyst(companyId) {
  const analystId = prompt('Informe o ID do operador IAM para alocar nesta empresa:', AppState.currentUser.id);
  if (!analystId) return;
  try {
    await ApiClient.assignAnalyst(companyId, {
      analyst_user_id: analystId.trim(),
      department: 'fiscal',
    });
    showToast('Analista vinculado à carteira da empresa com sucesso!', 'success');
    await loadCompaniesList();
  } catch (err) {
    showToast(`Falha ao alocar analista: ${err.message}`, 'danger');
  }
}

// ============================================================================
// VIEW 03: OBRIGAÇÕES, TAREFAS E PRAZOS
// ============================================================================
function renderRiskBadge(risk, daysLeft) {
  const daysStr = daysLeft !== undefined && daysLeft !== null ? ` (${daysLeft}d)` : '';
  if (risk === 'overdue') return `<span class="badge badge-red">VENCIDA${daysStr}</span>`;
  if (risk === 'red_critical') return `<span class="badge badge-red">CRÍTICO${daysStr}</span>`;
  if (risk === 'yellow') return `<span class="badge badge-yellow">ATENÇÃO${daysStr}</span>`;
  return `<span class="badge badge-green">NO PRAZO${daysStr}</span>`;
}

function renderTaskStatusBadge(status) {
  const map = {
    pending: '<span class="badge badge-neutral">Pendente</span>',
    in_progress: '<span class="badge badge-blue">Em Andamento</span>',
    under_review: '<span class="badge badge-purple">Em Revisão</span>',
    completed: '<span class="badge badge-green">Concluída</span>',
    blocked_missing_docs: '<span class="badge badge-red">Bloqueada (Doc)</span>',
  };
  return map[status] || `<span class="badge badge-neutral">${escapeHtml(status)}</span>`;
}

async function loadTasksList() {
  const tbody = document.getElementById('tasks-tbody');
  if (!tbody) return;
  if (!AppState.activeCompanyId) {
    tbody.innerHTML = '<tr><td colspan="9" class="empty-state">Selecione uma empresa ativa no topo para gerenciar obrigações.</td></tr>';
    return;
  }

  const statusFilter = document.getElementById('tasks-status-filter')?.value || '';
  const riskFilter = document.getElementById('tasks-risk-filter')?.value || '';

  try {
    let tasks = await ApiClient.listTasks({
      company_id: AppState.activeCompanyId,
      competence: AppState.competence,
      status: statusFilter,
    });
    if (riskFilter) tasks = tasks.filter(t => t.risk_level === riskFilter);
    AppState.tasks = tasks;
    renderTasksTable(tasks);
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="9" class="empty-state">${escapeHtml(err.message)}</td></tr>`;
  }
}

function renderTasksTable(tasks) {
  const tbody = document.getElementById('tasks-tbody');
  if (!tbody) return;
  if (!tasks || tasks.length === 0) {
    tbody.innerHTML = '<tr><td colspan="9" class="empty-state">Nenhuma obrigação gerada para esta competência. Clique em "+ Gerar Lote da Competência".</td></tr>';
    return;
  }

  tbody.innerHTML = tasks.map(t => `
    <tr>
      <td><span class="badge badge-blue mono">${escapeHtml(t.obligation_code)}</span></td>
      <td><strong>${escapeHtml(t.title)}</strong></td>
      <td class="mono">${escapeHtml(t.competence)}</td>
      <td class="mono">${escapeHtml(formatDateBR(t.internal_deadline))}</td>
      <td class="mono"><strong>${escapeHtml(formatDateBR(t.statutory_due_date))}</strong></td>
      <td>${renderRiskBadge(t.risk_level, t.days_to_due)}</td>
      <td>
        <select class="form-select" style="padding:4px 8px; font-size:0.78rem; width:145px;" data-task-status-id="${escapeHtml(t.id)}">
          <option value="pending" ${t.status === 'pending' ? 'selected' : ''}>Pendente</option>
          <option value="in_progress" ${t.status === 'in_progress' ? 'selected' : ''}>Em Andamento</option>
          <option value="under_review" ${t.status === 'under_review' ? 'selected' : ''}>Em Revisão</option>
          <option value="completed" ${t.status === 'completed' ? 'selected' : ''}>Concluída</option>
          <option value="blocked_missing_docs" ${t.status === 'blocked_missing_docs' ? 'selected' : ''}>Bloqueada (Doc)</option>
        </select>
      </td>
      <td>
        ${t.receipt_file_id
          ? `<span class="badge badge-green mono" title="Hash SHA-256: ${escapeHtml(t.receipt_file_hash || '')}">✓ ${escapeHtml(String(t.receipt_file_id).slice(0, 12))}</span>`
          : (t.has_receipt_required
            ? `<button type="button" class="btn btn-sm btn-warning" data-attach-task="${escapeHtml(t.id)}" data-attach-title="${escapeHtml(t.title)}">Anexar Recibo</button>`
            : '<span class="badge badge-neutral">Opcional</span>')}
      </td>
      <td>
        ${t.status !== 'completed'
          ? `<button type="button" class="btn btn-sm btn-success" data-complete-task="${escapeHtml(t.id)}">Concluir</button>`
          : '<span class="badge badge-green">Finalizada</span>'}
      </td>
    </tr>
  `).join('');
}

async function loadCompanyObligationsCatalog() {
  const container = document.getElementById('company-obligations-catalog');
  if (!container || !AppState.activeCompanyId) return;
  try {
    const obligations = await ApiClient.getCompanyObligations(AppState.activeCompanyId);
    if (!obligations || obligations.length === 0) {
      container.innerHTML = '<div class="empty-state">Gere um lote da competência para inicializar o catálogo fiscal.</div>';
      return;
    }
    container.innerHTML = obligations.map(ob => `
      <div style="background:#f8fafc; border:1px solid var(--border); border-radius:var(--radius-sm); padding:10px 14px; min-width:210px;">
        <div style="display:flex; justify-content:space-between; align-items:center;">
          <strong class="mono" style="color:var(--accent);">${escapeHtml(ob.code)}</strong>
          <span class="badge badge-neutral">Dia ${escapeHtml(ob.default_due_day)}</span>
        </div>
        <div style="font-size:0.83rem; font-weight:600; margin-top:4px;">${escapeHtml(ob.name)}</div>
        <div style="font-size:0.74rem; color:var(--muted); margin-top:4px;">
          Regime: ${escapeHtml(formatRegimeLabel(ob.tax_regime))} • ${ob.requires_receipt ? 'Exige Recibo' : 'Sem Recibo'}
        </div>
      </div>
    `).join('');
  } catch (_) {}
}

async function generateMonthlyTasksBatch() {
  if (!AppState.activeCompanyId) {
    showToast('Selecione uma empresa ativa primeiro.', 'warning');
    return;
  }
  try {
    const res = await ApiClient.generateCompetenceTasks({
      competence: AppState.competence,
      company_ids: [AppState.activeCompanyId],
    });
    showToast(`Lote da competência ${res.competence} processado: ${res.tasks_generated} obrigações geradas!`, 'success');
    if (AppState.activeView === 'obligations') {
      await loadTasksList();
      await loadCompanyObligationsCatalog();
    } else {
      await loadCockpitData();
    }
  } catch (err) {
    showToast(`Erro ao gerar obrigações: ${err.message}`, 'danger');
  }
}

async function handleTaskStatusChange(taskId, newStatus) {
  try {
    await ApiClient.updateTaskStatus(taskId, {
      status: newStatus,
      user_id: AppState.currentUser.id,
      user_role: AppState.currentUser.role,
    });
    showToast(`Status da obrigação atualizado para: ${newStatus}`, 'success');
    await loadTasksList();
  } catch (err) {
    showToast(`Bloqueio de conformidade: ${err.message}`, 'danger');
    await loadTasksList();
  }
}

async function openAttachReceiptModal(taskId, taskTitle) {
  document.getElementById('modal-attach-task-id').value = taskId;
  document.getElementById('modal-attach-task-title').value = taskTitle;
  const select = document.getElementById('modal-attach-doc-select');
  if (select && AppState.activeCompanyId) {
    try {
      const docs = await ApiClient.listDocuments({ company_id: AppState.activeCompanyId });
      AppState.documents = docs || [];
      select.innerHTML = '<option value="">-- Selecionar documento em custódia no GED --</option>' +
        AppState.documents.map(d => `<option value="${escapeHtml(d.id)}" data-sha="${escapeHtml(d.file_hash_sha256)}">${escapeHtml(d.file_name)} (${escapeHtml(d.id.slice(0, 8))})</option>`).join('');
    } catch (_) {}
  }
  openModal('modal-attach-receipt');
}

// ============================================================================
// VIEW 04: GESTÃO DE DOCUMENTOS (GED SHA-256)
// ============================================================================
async function loadDocumentsViewData() {
  if (!AppState.activeCompanyId) return;
  const dept = document.getElementById('docs-dept-filter')?.value || '';
  const status = document.getElementById('docs-status-filter')?.value || '';

  try {
    const docs = await ApiClient.listDocuments({
      company_id: AppState.activeCompanyId,
      competence: AppState.competence,
      department: dept,
      status,
    });
    AppState.documents = docs || [];
    renderDocumentsTable(AppState.documents);
  } catch (err) {
    renderDocumentsTable([]);
  }

  try {
    const checklist = await ApiClient.requestDocumentChecklist({
      company_id: AppState.activeCompanyId,
      competence: AppState.competence,
    });
    renderChecklistPanel(checklist);
  } catch (_) {}
}

function renderChecklistPanel(checklist) {
  if (!checklist) return;
  const pct = Math.round(checklist.completion_percentage || 0);
  const badge = document.getElementById('checklist-progress-badge');
  const fill = document.getElementById('checklist-progress-fill');
  const container = document.getElementById('checklist-items-container');
  if (badge) badge.textContent = `${pct}% Concluído`;
  if (fill) fill.style.width = `${pct}%`;
  if (!container) return;

  container.innerHTML = (checklist.items || []).map(item => `
    <div style="display:flex; align-items:center; justify-content:space-between; padding:8px 10px; background:#f8fafc; border:1px solid var(--border); border-radius:var(--radius-sm);">
      <div>
        <div style="font-size:0.83rem; font-weight:600;">${escapeHtml(item.title)}</div>
        <small style="color:var(--muted);">Depto: ${escapeHtml((item.department || '').toUpperCase())}</small>
      </div>
      <span class="badge ${item.is_fulfilled ? 'badge-green' : 'badge-yellow'}">${item.is_fulfilled ? 'Entregue' : 'Pendente'}</span>
    </div>
  `).join('');
}

function renderDocumentsTable(docs) {
  const tbody = document.getElementById('documents-tbody');
  if (!tbody) return;
  if (!docs || docs.length === 0) {
    tbody.innerHTML = '<tr><td colspan="7" class="empty-state">Nenhum documento nesta competência. Clique em "Enviar Documento (Upload)".</td></tr>';
    return;
  }

  tbody.innerHTML = docs.map(d => {
    const kb = ((d.file_size_bytes || 0) / 1024).toFixed(1);
    const shortHash = d.file_hash_sha256 ? `${d.file_hash_sha256.slice(0, 14)}...` : '—';
    return `
      <tr>
        <td>
          <strong>${escapeHtml(d.file_name)}</strong>
          <span class="badge badge-blue mono">v${escapeHtml(d.version)}</span>
        </td>
        <td><span class="badge badge-neutral">${escapeHtml((d.department || '').toUpperCase())}</span></td>
        <td class="mono">${escapeHtml(d.competence)}</td>
        <td class="mono">${kb} KB</td>
        <td><span class="badge badge-green">${escapeHtml(d.status)}</span></td>
        <td>
          <div class="mono" style="font-size:0.75rem; color:var(--accent);">${escapeHtml(d.receipt_code || 'PROTOCOLADO')}</div>
          <div class="mono" style="font-size:0.7rem; color:var(--muted);" title="${escapeHtml(d.file_hash_sha256)}">SHA-256: ${escapeHtml(shortHash)}</div>
        </td>
        <td>
          <div style="display:flex; gap:6px;">
            <button type="button" class="btn btn-sm btn-secondary" data-doc-receipt="${escapeHtml(d.id)}">Protocolo</button>
            <button type="button" class="btn btn-sm btn-primary" data-doc-ocr="${escapeHtml(d.id)}" data-doc-name="${escapeHtml(d.file_name)}">OCR IA</button>
          </div>
        </td>
      </tr>
    `;
  }).join('');
}

async function inspectDocumentReceipt(docId) {
  const card = document.getElementById('document-inspector-card');
  const body = document.getElementById('document-inspector-body');
  if (!card || !body) return;
  try {
    const r = await ApiClient.getDocumentReceipt(docId);
    card.style.display = 'block';
    body.innerHTML = `
      <div class="alert-box success" style="margin-bottom:10px;">
        <strong>Protocolo Digital de Custódia Auditado: ${escapeHtml(r.receipt_code)}</strong>
      </div>
      <div class="code-block">Arquivo: ${escapeHtml(r.file_name)} (${r.file_size_bytes} bytes)
Hash SHA-256: ${escapeHtml(r.file_hash_sha256)}
Operador Responsável: ${escapeHtml(r.uploaded_by)}
Endereço IP: ${escapeHtml(r.ip_address)}
Carimbo de Tempo UTC: ${escapeHtml(r.timestamp_utc)}</div>
    `;
  } catch (err) {
    showToast(`Erro ao consultar protocolo: ${err.message}`, 'danger');
  }
}

async function requestMissingChecklist() {
  if (!AppState.activeCompanyId) return;
  try {
    const res = await ApiClient.requestDocumentChecklist({
      company_id: AppState.activeCompanyId,
      competence: AppState.competence,
    });
    renderChecklistPanel(res);
    showToast('Checklist mensal de documentos atualizado com sucesso!', 'success');
  } catch (err) {
    showToast(`Erro ao atualizar checklist: ${err.message}`, 'danger');
  }
}

// ============================================================================
// VIEW 05: BPO FINANCEIRO — CONTAS A PAGAR E RECEBER
// ============================================================================
async function loadFinanceViewData() {
  if (!AppState.activeCompanyId) return;
  await Promise.all([loadPayablesQueue(), loadAgingReport()]);
}

async function loadPayablesQueue() {
  const tbody = document.getElementById('payables-tbody');
  if (!tbody || !AppState.activeCompanyId) return;
  try {
    const queue = await ApiClient.getApprovalQueue(AppState.activeCompanyId);
    AppState.payablesQueue = queue || [];
    const total = AppState.payablesQueue.reduce((acc, b) => acc + Number(b.final_amount || 0), 0);
    document.getElementById('payable-queue-count').textContent = AppState.payablesQueue.length;
    document.getElementById('payable-total-amount').textContent = formatBRL(total);

    if (AppState.payablesQueue.length === 0) {
      tbody.innerHTML = '<tr><td colspan="6" class="empty-state">Nenhum título pendente na fila de aprovação. Clique em "+ Novo Título Financeiro".</td></tr>';
      return;
    }

    tbody.innerHTML = AppState.payablesQueue.map(b => `
      <tr>
        <td>
          <strong>${escapeHtml(b.counterparty_name)}</strong>
          <div class="mono" style="font-size:0.72rem; color:var(--muted);">${escapeHtml(b.barcode_line || b.pix_key || 'Sem código de barras')}</div>
        </td>
        <td class="mono">${escapeHtml(formatDateBR(b.due_date))}</td>
        <td><span class="badge badge-blue">${escapeHtml((b.payment_method || 'boleto').toUpperCase())}</span></td>
        <td class="text-right mono"><strong>${formatBRL(b.final_amount)}</strong></td>
        <td><span class="badge badge-yellow">${escapeHtml(b.status)}</span></td>
        <td>
          <div style="display:flex; gap:6px;">
            <button type="button" class="btn btn-sm btn-success" data-approve-bill="${escapeHtml(b.id)}">Aprovar</button>
            <button type="button" class="btn btn-sm btn-danger" data-reject-bill="${escapeHtml(b.id)}">Rejeitar</button>
          </div>
        </td>
      </tr>
    `).join('');
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="6" class="empty-state">${escapeHtml(err.message)}</td></tr>`;
  }
}

async function loadAgingReport() {
  if (!AppState.activeCompanyId) return;
  try {
    const aging = await ApiClient.getAgingList(AppState.activeCompanyId);
    document.getElementById('aging-total-overdue').textContent = formatBRL(aging.total_overdue || 0);
    document.getElementById('aging-default-rate').textContent = `${Number(aging.default_rate_pct || 0).toFixed(1)}%`;

    const brackets = aging.brackets || {};
    MiniCharts.drawHorizontalBars('aging-brackets-container', [
      { label: '1 a 30 dias vencido', value: brackets['0_30'] || 0, formattedValue: formatBRL(brackets['0_30'] || 0), color: 'var(--warn)' },
      { label: '31 a 60 dias vencido', value: brackets['31_60'] || 0, formattedValue: formatBRL(brackets['31_60'] || 0), color: '#ea580c' },
      { label: '61 a 90 dias vencido', value: brackets['61_90'] || 0, formattedValue: formatBRL(brackets['61_90'] || 0), color: 'var(--err)' },
      { label: 'Acima de 90 dias', value: brackets['over_90'] || 0, formattedValue: formatBRL(brackets['over_90'] || 0), color: '#7f1d1d' },
    ]);

    const tbody = document.getElementById('aging-items-tbody');
    if (tbody) {
      const items = aging.items || [];
      tbody.innerHTML = items.length === 0
        ? '<tr><td colspan="4" class="empty-state">Sem títulos vencidos em aberto.</td></tr>'
        : items.map(it => `
            <tr>
              <td><strong>${escapeHtml(it.counterparty_name)}</strong></td>
              <td><span class="badge badge-red">${it.days_overdue} dias</span></td>
              <td class="text-right mono">${formatBRL(it.amount)}</td>
              <td><button type="button" class="btn btn-sm btn-secondary" data-remind-bill="${escapeHtml(it.bill_id)}">Cobrar</button></td>
            </tr>
          `).join('');
    }
  } catch (_) {}
}

async function handleApproveBill(billId) {
  try {
    await ApiClient.approveBill(billId, {
      approver_user_id: AppState.currentUser.id,
      notes: 'Aprovado no painel executivo Supreme',
    });
    showToast('Título aprovado com sucesso!', 'success');
    await loadPayablesQueue();
  } catch (err) {
    showToast(`Regra de segregação de funções: ${err.message}`, 'warning');
  }
}

async function handleRejectBill(billId) {
  const reason = prompt('Informe a justificativa para rejeição do título:', 'Divergência de dados bancários / nota fiscal');
  if (!reason) return;
  try {
    await ApiClient.rejectBill(billId, {
      approver_user_id: AppState.currentUser.id,
      reason,
    });
    showToast('Título rejeitado e registrado no histórico.', 'info');
    await loadPayablesQueue();
  } catch (err) {
    showToast(`Erro ao rejeitar título: ${err.message}`, 'danger');
  }
}

async function handleRemindBill(billId) {
  try {
    await ApiClient.dispatchReminder(billId, { channel: 'whatsapp' });
    showToast('Lembrete de cobrança enviado!', 'success');
  } catch (err) {
    showToast(err.message, 'warning');
  }
}

// ============================================================================
// VIEW 06: CONCILIAÇÃO BANCÁRIA AUTOMÁTICA (OFX)
// ============================================================================
async function loadReconciliationViewData() {
  if (!AppState.activeCompanyId) return;
  const select = document.getElementById('recon-bank-account-select');
  try {
    const accounts = await ApiClient.listBankAccounts();
    if (Array.isArray(accounts) && accounts.length > 0 && select) {
      select.innerHTML = accounts.map(a =>
        `<option value="${escapeHtml(a.id)}">${escapeHtml(a.bank_name || 'Banco')} (${escapeHtml(a.bank_code)}) — Ag ${escapeHtml(a.agency_number)} / CC ${escapeHtml(a.account_number)}</option>`
      ).join('');
    }
  } catch (_) {}

  const accountId = select?.value;
  if (!accountId) return;

  try {
    const trxs = await ApiClient.getUnmatchedTransactions(accountId);
    AppState.unmatchedTransactions = trxs || [];
    renderUnmatchedTransactionsTable(AppState.unmatchedTransactions);
  } catch (_) {
    renderUnmatchedTransactionsTable([]);
  }
}

function renderUnmatchedTransactionsTable(trxs) {
  const tbody = document.getElementById('unmatched-trx-tbody');
  if (!tbody) return;
  if (!trxs || trxs.length === 0) {
    tbody.innerHTML = '<tr><td colspan="5" class="empty-state">Nenhuma transação pendente. Cadastre uma conta bancária e importe um arquivo OFX.</td></tr>';
    return;
  }
  tbody.innerHTML = trxs.map(t => {
    const amt = Number(t.amount || 0);
    return `
      <tr>
        <td class="mono">${escapeHtml(formatDateBR(t.transaction_date))}</td>
        <td class="mono" style="font-size:0.75rem;">${escapeHtml(t.fitid)}</td>
        <td><strong>${escapeHtml(t.memo || 'Movimento bancário')}</strong></td>
        <td class="text-right mono" style="color:${amt < 0 ? 'var(--err)' : 'var(--ok)'}; font-weight:700;">${formatBRL(amt)}</td>
        <td>
          <button type="button" class="btn btn-sm btn-secondary" data-quick-expense="${escapeHtml(t.id)}">Tarifa 1-Click</button>
        </td>
      </tr>
    `;
  }).join('');
}

async function handleOfxUploadChange(event) {
  const file = event.target.files?.[0];
  if (!file) return;
  const accountId = document.getElementById('recon-bank-account-select')?.value;
  if (!accountId) {
    showToast('Selecione ou cadastre uma conta bancária primeiro.', 'warning');
    return;
  }
  const fd = new FormData();
  fd.append('file', file);
  try {
    const res = await ApiClient.importOfxStatement(accountId, fd);
    showToast(`Extrato OFX processado: ${res.imported_transactions} importadas (${res.duplicates_skipped} duplicadas ignoradas).`, 'success');
    await loadReconciliationViewData();
    await verifyBankBalance();
  } catch (err) {
    showToast(`Erro na importação OFX: ${err.message}`, 'danger');
  } finally {
    event.target.value = '';
  }
}

async function runMatchingSuggestions() {
  const accountId = document.getElementById('recon-bank-account-select')?.value;
  const container = document.getElementById('matching-suggestions-container');
  if (!accountId || !container) return;

  try {
    const suggestions = await ApiClient.getMatchingSuggestions(accountId);
    AppState.matchingSuggestions = suggestions || [];
    if (AppState.matchingSuggestions.length === 0) {
      container.innerHTML = '<div class="empty-state">Nenhuma sugestão de pareamento encontrada para os títulos em aberto.</div>';
      return;
    }
    container.innerHTML = AppState.matchingSuggestions.map(s => `
      <div style="border:1px solid var(--border); border-radius:var(--radius-sm); padding:12px; margin-bottom:10px; background:#f8fafc;">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
          <span class="badge badge-green">Confiança: ${Math.round(Number(s.confidence_score || 0) * 100)}%</span>
          <span class="mono" style="font-size:0.75rem;">Regra: ${escapeHtml(s.match_rule)}</span>
        </div>
        <div style="font-size:0.84rem; margin-bottom:8px;">
          Transação <code>${escapeHtml(s.transaction_id.slice(0, 8))}</code> ↔ Título <code>${escapeHtml(s.candidate_bill_id.slice(0, 8))}</code> (${formatBRL(s.bill_amount)})
        </div>
        <button type="button" class="btn btn-sm btn-primary" data-confirm-match-trx="${escapeHtml(s.transaction_id)}" data-confirm-match-bill="${escapeHtml(s.candidate_bill_id)}">Confirmar Conciliação e Baixar Título</button>
      </div>
    `).join('');
  } catch (err) {
    container.innerHTML = `<div class="empty-state">${escapeHtml(err.message)}</div>`;
  }
}

async function verifyBankBalance() {
  const accountId = document.getElementById('recon-bank-account-select')?.value;
  const banner = document.getElementById('balance-check-banner');
  const details = document.getElementById('balance-equation-details');
  if (!accountId || !banner || !details) return;
  try {
    const res = await ApiClient.getBalanceCheck(accountId);
    banner.style.display = 'flex';
    banner.className = `alert-box ${res.is_balanced ? 'success' : 'danger'}`;
    details.textContent = `Saldo Inicial (${formatBRL(res.opening_balance)}) + Entradas (${formatBRL(res.total_inflows)}) - Saídas (${formatBRL(res.total_outflows)}) = Saldo Calculado (${formatBRL(res.calculated_closing_balance)}) | Extrato: ${formatBRL(res.reported_closing_balance)}`;
  } catch (err) {
    showToast(`Erro na verificação de saldo: ${err.message}`, 'warning');
  }
}

// ============================================================================
// VIEW 07: FLUXO DE CAIXA, DRE E INDICADORES
// ============================================================================
async function loadAnalyticsViewData() {
  if (!AppState.activeCompanyId) return;
  const days = Number(document.getElementById('cashflow-days-select')?.value || 30);
  const compBadge = document.getElementById('dre-competence-badge');
  if (compBadge) compBadge.textContent = AppState.competence;

  try {
    const [dre, cf, kpis] = await Promise.all([
      ApiClient.getDre(AppState.activeCompanyId, AppState.competence),
      ApiClient.getCashFlow(AppState.activeCompanyId, days),
      ApiClient.getKpis(AppState.activeCompanyId, AppState.competence),
    ]);

    document.getElementById('dre-kpi-net-rev').textContent = formatBRL(dre.net_revenue);
    document.getElementById('dre-kpi-ebitda').textContent = formatBRL(dre.ebitda);
    document.getElementById('dre-kpi-net-inc').textContent = formatBRL(dre.net_income);
    document.getElementById('dre-kpi-margin-badge').textContent = `Margem Líquida: ${Number(kpis.net_margin_pct || 0).toFixed(1)}%`;
    document.getElementById('dre-kpi-cycle').textContent = `${kpis.financial_cycle_days || 0} dias`;
    document.getElementById('dre-kpi-breakeven').textContent = formatBRL(kpis.break_even_point);

    renderDreTable(dre);
    MiniCharts.drawCashFlowLineChart('cashflow-chart', cf.daily_projections || []);
    MiniCharts.drawDonutChart('dre-donut-chart', [
      { label: 'Deduções', value: Math.abs(Number(dre.sales_deductions || 0)), color: '#b45309' },
      { label: 'Custos (CMV/CSP)', value: Math.abs(Number(dre.cost_of_goods_sold || 0)), color: '#0369a1' },
      { label: 'Desp. Operacionais', value: Math.abs(Number(dre.operating_expenses || 0)), color: '#b91c1c' },
      { label: 'Resultado Líquido', value: Math.max(0, Number(dre.net_income || 0)), color: '#166659' },
    ], formatBRL(dre.gross_revenue));
  } catch (err) {
    showToast(`Erro ao carregar indicadores DRE: ${err.message}`, 'warning');
  }
}

function renderDreTable(dre) {
  const tbody = document.getElementById('dre-Dynamic-tbody');
  if (!tbody) return;
  const lines = dre.lines || [
    { label: '(=) Receita Bruta Operacional', current_value: dre.gross_revenue, vertical_analysis_pct: 100, horizontal_analysis_pct: 0, bold: true },
    { label: '(-) Deduções e Impostos sobre Vendas', current_value: -Math.abs(dre.sales_deductions || 0), vertical_analysis_pct: 0, horizontal_analysis_pct: 0 },
    { label: '(=) Receita Líquida', current_value: dre.net_revenue, vertical_analysis_pct: 100, horizontal_analysis_pct: 0, bold: true },
    { label: '(-) Custos dos Serviços / Mercadorias (CSP/CMV)', current_value: -Math.abs(dre.cost_of_goods_sold || 0), vertical_analysis_pct: 0, horizontal_analysis_pct: 0 },
    { label: '(=) Lucro Bruto', current_value: dre.gross_profit, vertical_analysis_pct: 0, horizontal_analysis_pct: 0, bold: true },
    { label: '(-) Despesas Operacionais e Administrativas', current_value: -Math.abs(dre.operating_expenses || 0), vertical_analysis_pct: 0, horizontal_analysis_pct: 0 },
    { label: '(=) EBITDA / Resultado Operacional', current_value: dre.ebitda, vertical_analysis_pct: 0, horizontal_analysis_pct: 0, bold: true },
    { label: '(=) Resultado Líquido do Exercício', current_value: dre.net_income, vertical_analysis_pct: 0, horizontal_analysis_pct: 0, bold: true },
  ];

  tbody.innerHTML = lines.map(l => {
    const val = Number(l.current_value ?? l.amount ?? 0);
    return `
      <tr style="${l.bold ? 'background:#f8fafc; font-weight:700;' : ''}">
        <td>${escapeHtml(l.label || l.account_name)}</td>
        <td class="text-right mono" style="color:${val < 0 ? 'var(--err)' : 'var(--ink)'};">${formatBRL(val)}</td>
        <td class="text-right mono">${Number(l.vertical_analysis_pct ?? 0).toFixed(1)}%</td>
        <td class="text-right mono">${Number(l.horizontal_analysis_pct ?? 0).toFixed(1)}%</td>
      </tr>
    `;
  }).join('');
}

async function exportExecutivePdfReport() {
  if (!AppState.activeCompanyId) return;
  try {
    await ApiClient.exportExecutivePdf(AppState.activeCompanyId, {
      competence: AppState.competence,
      include_dre: true,
      include_cash_flow: true,
    });
    showToast('Relatório Executivo DRE exportado em PDF com sucesso!', 'success');
  } catch (err) {
    showToast(`Erro ao exportar PDF: ${err.message}`, 'danger');
  }
}

// ============================================================================
// VIEW 08: INTEGRAÇÕES FISCAIS E GOVERNAMENTAIS
// ============================================================================
async function loadFiscalViewData() {
  const cndPanel = document.getElementById('cnd-status-panel');
  if (cndPanel) {
    cndPanel.innerHTML = '<div class="alert-box info">Clique em "Consultar CND (SERPRO)" para verificar a situação fiscal ou "Gerar Prévia DCTFWeb" para consolidar as retenções de NFS-e.</div>';
  }
  renderFiscalTransmissionsTable();
}

async function checkCompanyCndStatus() {
  if (!AppState.activeCompanyId) return;
  const panel = document.getElementById('cnd-status-panel');
  try {
    const res = await ApiClient.getCompanyCndStatus(AppState.activeCompanyId);
    if (panel) {
      panel.innerHTML = `
        <div class="alert-box success">
          <div>
            <strong>Certidão Negativa de Débitos: ${escapeHtml(res.status)}</strong>
            <div class="mono" style="font-size:0.8rem;">Protocolo: ${escapeHtml(res.certificate_number)} | Válida até: ${escapeHtml(formatDateBR(res.valid_until))}</div>
          </div>
        </div>
      `;
    }
  } catch (err) {
    if (panel) {
      panel.innerHTML = `
        <div class="alert-box warning">
          <div>
            <strong>Integração Externa SERPRO Indisponível (HTTP ${err.status || 501})</strong>
            <div style="margin-top:4px;">${escapeHtml(err.message)}</div>
          </div>
        </div>
      `;
    }
  }
}

async function consolidateDctfwebAction() {
  if (!AppState.activeCompanyId) return;
  const box = document.getElementById('dctfweb-result-box');
  try {
    const res = await ApiClient.consolidateDctfweb({
      company_id: AppState.activeCompanyId,
      competence: AppState.competence,
    });
    if (box) {
      box.style.display = 'block';
      box.innerHTML = `
        <div class="danfse-box">
          <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
            <span class="danfse-box-title" style="margin:0;">CONSOLIDAÇÃO DCTFWEB (${escapeHtml(res.competence)})</span>
            <span class="badge badge-warning">PRÉVIA SEM TRANSMISSÃO OFICIAL</span>
          </div>
          <div class="danfse-row"><span>INSS Previdenciário Retido:</span> <strong class="mono">${formatBRL(res.total_inss_previdenciario)}</strong></div>
          <div class="danfse-row"><span>IRRF Retido na Fonte:</span> <strong class="mono">${formatBRL(res.total_irrf_retencao)}</strong></div>
          <div class="danfse-row"><span>CSRF / PCC (PIS + COFINS + CSLL):</span> <strong class="mono">${formatBRL(res.total_pcc_retencao)}</strong></div>
          <div class="danfse-row"><strong>Total Estimado para DARF Unificado:</strong> <strong class="mono" style="color:var(--accent);">${formatBRL(res.total_darf_amount)}</strong></div>
        </div>
      `;
    }
    showToast('Prévia da DCTFWeb consolidada a partir das NFS-e processadas!', 'success');
  } catch (err) {
    showToast(`Erro na consolidação DCTFWeb: ${err.message}`, 'danger');
  }
}

function renderFiscalTransmissionsTable() {
  const tbody = document.getElementById('fiscal-transmissions-tbody');
  if (!tbody) return;
  if (AppState.transmissions.length === 0) {
    tbody.innerHTML = '<tr><td colspan="6" class="empty-state">Nenhuma transmissão enfileirada nesta sessão.</td></tr>';
    return;
  }
  tbody.innerHTML = AppState.transmissions.map(t => `
    <tr>
      <td class="mono" style="font-size:0.75rem;">${escapeHtml(String(t.id).slice(0, 12))}</td>
      <td><strong>${escapeHtml(t.event_type)}</strong> (${escapeHtml(t.system_target)})</td>
      <td class="mono">${escapeHtml(t.competence)}</td>
      <td><span class="badge badge-blue">${escapeHtml(t.status)}</span></td>
      <td>${escapeHtml(t.receipt_protocol || 'Fila assíncrona validada')}</td>
      <td><button type="button" class="btn btn-sm btn-secondary" data-retry-transmission="${escapeHtml(t.id)}">Reenviar</button></td>
    </tr>
  `).join('');
}

// ============================================================================
// VIEW 09: AUTOMAÇÃO E IA CONTÁBIL
// ============================================================================
async function loadAiViewData() {
  if (!AppState.activeCompanyId) return;
  try {
    const anomalies = await ApiClient.getAnomalies(AppState.activeCompanyId);
    AppState.anomalies = anomalies || [];
    renderAnomaliesPanel(AppState.anomalies);
  } catch (_) {
    renderAnomaliesPanel([]);
  }
}

function renderAnomaliesPanel(anomalies) {
  const container = document.getElementById('ai-anomalies-container');
  if (!container) return;
  if (!anomalies || anomalies.length === 0) {
    container.innerHTML = '<div class="empty-state">Nenhuma anomalia ativa. Clique em "Executar Varredura Preditiva de Anomalias".</div>';
    return;
  }
  container.innerHTML = anomalies.map(a => `
    <div class="alert-box ${a.severity === 'high' || a.severity === 'critical' ? 'danger' : 'warning'}" style="margin-bottom:8px;">
      <div>
        <strong>[${escapeHtml((a.anomaly_type || 'ANOMALIA').toUpperCase())}] Severidade: ${escapeHtml(a.severity)}</strong>
        <div style="margin-top:4px;">${escapeHtml(typeof a.details === 'object' ? JSON.stringify(a.details) : a.details)}</div>
      </div>
    </div>
  `).join('');
}

async function runAnomalyScanAction() {
  if (!AppState.activeCompanyId) return;
  try {
    const alerts = await ApiClient.scanAnomalies(AppState.activeCompanyId, {
      new_bill: { counterparty_name: 'Fornecedor TI Cloud', amount: 18500.0, due_date: '2026-10-25' },
      historical_bills: [{ counterparty_name: 'Fornecedor TI Cloud', amount: 18500.0, due_date: '2026-10-25' }],
      historical_average_expense: 3200.0,
    });
    AppState.anomalies = alerts || [];
    renderAnomaliesPanel(AppState.anomalies);
    showToast(`Varredura concluída: ${AppState.anomalies.length} alerta(s) preditivo(s) identificado(s).`, 'info');
  } catch (err) {
    showToast(`Erro na varredura de anomalias: ${err.message}`, 'danger');
  }
}

async function generateAiExecutiveSummary() {
  if (!AppState.activeCompanyId) return;
  const box = document.getElementById('ai-executive-summary-box');
  const [year, month] = (AppState.competence || '2026-10').split('-').map(Number);
  try {
    const res = await ApiClient.generateExecutiveSummary(AppState.activeCompanyId, {
      month: month || 10,
      year: year || 2026,
      metrics_summary: {
        gross_revenue: 285000.0,
        net_income: 64200.0,
        ebitda: 78500.0,
        pending_obligations: 0,
      },
    });
    if (box) {
      box.innerHTML = `
        <div class="alert-box info" style="margin-bottom:10px;">
          <strong>Minuta Gerada para Revisão Técnica:</strong> ${escapeHtml(res.legal_disclaimer || 'Sujeito à validação do Contador Responsável.')}
        </div>
        <div class="code-block" style="white-space:pre-line;">${escapeHtml(res.narrative_text || res.summary_markdown || JSON.stringify(res, null, 2))}</div>
      `;
    }
  } catch (err) {
    showToast(`Erro ao gerar resumo executivo: ${err.message}`, 'danger');
  }
}

async function runOcrExtractionDemo() {
  const rawText = document.getElementById('ai-ocr-raw-text')?.value || '';
  const box = document.getElementById('ai-ocr-result-box');
  try {
    const docId = AppState.documents[0]?.id || 'doc-ocr-demo-01';
    const res = await ApiClient.extractDocumentOcr(docId, rawText);
    if (box) {
      box.style.display = 'block';
      box.innerHTML = `
        <div class="alert-box success">
          <div>
            <strong>Extração OCR Concluída (Confiança: ${Math.round(Number(res.confidence_score || 0) * 100)}%)</strong>
            <pre class="code-block" style="margin-top:6px;">${escapeHtml(JSON.stringify(res.extracted_data, null, 2))}</pre>
          </div>
        </div>
      `;
    }
  } catch (err) {
    showToast(`Erro no OCR: ${err.message}`, 'danger');
  }
}

// ============================================================================
// VIEW 10: PORTAL DO CLIENTE & COMUNICAÇÃO
// ============================================================================
async function loadPortalData() {
  if (!AppState.activeCompanyId) return;
  try {
    const [guides, tickets] = await Promise.all([
      ApiClient.listAvailableGuides(AppState.activeCompanyId),
      ApiClient.listTickets(AppState.activeCompanyId),
    ]);
    AppState.guides = guides || [];
    AppState.tickets = tickets || [];
    renderPortalGuides(AppState.guides);
    renderPortalTickets(AppState.tickets);
  } catch (_) {
    renderPortalGuides([]);
    renderPortalTickets([]);
  }
}

function renderPortalGuides(guides) {
  const container = document.getElementById('portal-guides-container');
  if (!container) return;
  if (!guides || guides.length === 0) {
    container.innerHTML = '<div class="empty-state">Nenhuma guia publicada para esta empresa no momento.</div>';
    return;
  }
  container.innerHTML = guides.map(g => `
    <div style="border:1px solid var(--border); border-radius:var(--radius-sm); padding:12px; background:#f8fafc;">
      <div style="display:flex; justify-content:space-between; align-items:center;">
        <strong>${escapeHtml(g.title)}</strong>
        <span class="badge ${g.viewed_by_client ? 'badge-green' : 'badge-yellow'}">${g.viewed_by_client ? 'Visualizada pelo Cliente' : 'Aguardando Leitura'}</span>
      </div>
      <div class="mono" style="font-size:0.78rem; color:var(--muted); margin:6px 0;">
        Competência: ${escapeHtml(g.competence)} | Vencimento: ${escapeHtml(formatDateBR(g.due_date))}
      </div>
      <div style="display:flex; gap:6px; margin-top:8px;">
        <button type="button" class="btn btn-sm btn-primary" data-confirm-guide="${escapeHtml(g.document_id)}">Confirmar Recebimento Digital</button>
      </div>
    </div>
  `).join('');
}

function renderPortalTickets(tickets) {
  const tbody = document.getElementById('portal-tickets-tbody');
  if (!tbody) return;
  if (!tickets || tickets.length === 0) {
    tbody.innerHTML = '<tr><td colspan="6" class="empty-state">Nenhum chamado aberto. Clique em "+ Abrir Novo Chamado".</td></tr>';
    return;
  }
  tbody.innerHTML = tickets.map(t => `
    <tr>
      <td><span class="badge badge-blue">${escapeHtml(t.category)}</span></td>
      <td><strong>${escapeHtml(t.title)}</strong></td>
      <td><span class="badge ${t.priority === 'urgent' ? 'badge-red' : 'badge-neutral'}">${escapeHtml(t.priority)}</span></td>
      <td class="mono" style="font-size:0.78rem;">${escapeHtml(formatDateBR(t.sla_due_at))}</td>
      <td><span class="badge badge-green">${escapeHtml(t.status)}</span></td>
      <td><button type="button" class="btn btn-sm btn-secondary" data-reply-ticket="${escapeHtml(t.id)}">Responder</button></td>
    </tr>
  `).join('');
}

// ============================================================================
// VIEW 11: SEGURANÇA, IAM, LGPD E CERTIFICADOS
// ============================================================================
async function loadSecurityViewData() {
  try {
    const certs = await ApiClient.getExpiringCertificates(AppState.activeCompanyId);
    const certTbody = document.getElementById('cert-expirations-tbody');
    if (certTbody) {
      certTbody.innerHTML = (!certs || certs.length === 0)
        ? '<tr><td colspan="5" class="empty-state">Nenhum certificado ICP-Brasil A1 armazenado para esta empresa.</td></tr>'
        : certs.map(c => `
            <tr>
              <td><strong>${escapeHtml(c.common_name || c.issued_to_tax_id)}</strong></td>
              <td><span class="badge badge-blue">${escapeHtml(c.certificate_type)}</span></td>
              <td class="mono">${escapeHtml(formatDateBR(c.valid_until))}</td>
              <td class="mono">${c.days_until_expiration} dias</td>
              <td><span class="badge ${c.warning_level === 'normal' ? 'badge-green' : 'badge-red'}">${escapeHtml(c.warning_level)}</span></td>
            </tr>
          `).join('');
    }
  } catch (_) {}

  const actionFilter = document.getElementById('audit-action-filter')?.value || '';
  try {
    const logs = await ApiClient.getAuditLogs({ company_id: AppState.activeCompanyId });
    const filtered = actionFilter ? (logs || []).filter(l => String(l.action || '').includes(actionFilter)) : (logs || []);
    const logTbody = document.getElementById('audit-logs-tbody');
    if (logTbody) {
      logTbody.innerHTML = filtered.length === 0
        ? '<tr><td colspan="6" class="empty-state">Nenhum evento registrado na trilha de auditoria.</td></tr>'
        : filtered.slice(0, 25).map(l => `
            <tr>
              <td class="mono" style="font-size:0.75rem;">${escapeHtml(l.timestamp_utc)}</td>
              <td class="mono">${escapeHtml(l.actor_user_id)}</td>
              <td><strong>${escapeHtml(l.action)}</strong></td>
              <td>${escapeHtml(l.resource_type)}:${escapeHtml(l.resource_id || '')}</td>
              <td class="mono">${escapeHtml(l.ip_address || 'internal')}</td>
              <td class="mono" style="font-size:0.74rem;">${escapeHtml(JSON.stringify(l.payload_snapshot || {}))}</td>
            </tr>
          `).join('');
    }
  } catch (_) {}
}

async function openMfaSetupModal() {
  openModal('modal-mfa-setup');
  try {
    const res = await ApiClient.setupMfa();
    document.getElementById('mfa-secret-code').textContent = res.manual_code || res.secret;
    document.getElementById('mfa-otp-url').value = res.otpauth_url || '';
  } catch (err) {
    document.getElementById('mfa-secret-code').textContent = err.message;
  }
}

// ============================================================================
// VIEW 12: INTELIGÊNCIA NFS-E & RETENÇÕES (svc-nfse-engine)
// ============================================================================
function resetNfseView() {
  if (typeof Retencoes !== 'undefined') Retencoes.reset();
  AppState.nfse.notes = [];
  AppState.nfse.filteredNotes = [];
  AppState.nfse.currentNote = null;
  AppState.nfse.stats = null;
  for (const key of Object.keys(AppState.nfse.charts)) {
    AppState.nfse.charts[key]?.destroy();
    AppState.nfse.charts[key] = null;
  }
  renderNfseNotesTable([]);
  updateNfseKPIs({}, []);
  populateNfseFilters([]);
  document.getElementById('modalOverlay')?.classList.remove('active');
  for (const id of ['jsonViewer', 'danfseContainer', 'tab-complementares', 'tab-auditoria']) {
    const element = document.getElementById(id);
    if (element) element.textContent = '';
  }
  const retentions = document.getElementById('retencoesResults');
  if (retentions) retentions.hidden = true;
}

async function loadNfseDashboardData() {
  if (!AppState.activeCompanyId) return;
  const generation = ApiClient.nfseGeneration;
  try {
    const [statsRes, notesRes] = await Promise.all([
      ApiClient.request('/nfse/dashboard/stats'),
      ApiClient.request('/nfse/notes?limit=5000'),
    ]);
    if (generation !== ApiClient.nfseGeneration) return;
    AppState.nfse.stats = statsRes;
    AppState.nfse.notes = notesRes;
    AppState.nfse.filteredNotes = [...AppState.nfse.notes];

    updateNfseKPIs(statsRes, AppState.nfse.notes);
    updateNfseCharts(statsRes);
    populateNfseFilters(AppState.nfse.notes);
    renderNfseNotesTable(AppState.nfse.filteredNotes);
    if (typeof Retencoes !== 'undefined' && typeof Retencoes.refresh === 'function') {
      Retencoes.refresh();
    }
  } catch (err) {
    if (generation !== ApiClient.nfseGeneration) return;
    resetNfseView();
    if (err.status === 410) await ApiClient.resetNfseWorkspace();
    showToast(`NFS-e: ${err.message}`, 'warning');
  }
}

function updateNfseKPIs(stats, notes = []) {
  if (!stats) return;
  const active = notes.filter(note => note.status === 100);
  const retTotals = window.NfseRetencoes.computeRetencoesTotals(active, stats);
  document.getElementById('kpiTotalNotas').textContent = notes.length;
  document.getElementById('kpiStatusSub').textContent = `${active.length} autorizadas | ${notes.length - active.length} canceladas/substituídas`;
  document.getElementById('kpiValorBruto').textContent = formatBRL(stats.faturamento_bruto);
  document.getElementById('kpiTicketMedio').textContent = `Ticket Médio: ${formatBRL(active.length ? stats.faturamento_bruto / active.length : 0)}`;
  document.getElementById('kpiTotalRetencoes').textContent = formatBRL(retTotals.total);
  document.getElementById('kpiValorLiquido').textContent = formatBRL(stats.faturamento_liquido);

  const auditEl = document.getElementById('kpiAuditStatus');
  if (auditEl) {
    auditEl.textContent = stats.notas_inconsistentes > 0
      ? `⚠ ${stats.notas_inconsistentes} nota(s) com alerta`
      : (notes.length ? '✓ 100% Conciliado Contabilmente' : 'Nenhuma nota importada');
  }

  document.getElementById('kpiISS').textContent = formatBRL(retTotals.iss);
  document.getElementById('kpiIRRF').textContent = formatBRL(retTotals.irrf);
  document.getElementById('kpiINSS').textContent = formatBRL(retTotals.inss);
  document.getElementById('kpiCSRF').textContent = formatBRL(retTotals.csrf);
  document.getElementById('kpiOutros').textContent = formatBRL(retTotals.outros);
}

function updateNfseCharts(stats) {
  if (typeof Chart === 'undefined' || !stats) return;
  const nfseCharts = AppState.nfse.charts;

  const compLabels = (stats.timeline || []).map(item => item.competencia);
  const compBruto = (stats.timeline || []).map(item => item.bruto);
  const compLiq = (stats.timeline || []).map(item => item.liquido);

  const ctxComp = document.getElementById('chartCompetencia');
  if (ctxComp) {
    if (nfseCharts.competencia) nfseCharts.competencia.destroy();
    nfseCharts.competencia = new Chart(ctxComp, {
      type: 'bar',
      data: {
        labels: compLabels,
        datasets: [
          { label: 'Valor Bruto (R$)', data: compBruto, backgroundColor: '#166659', borderRadius: 6 },
          { label: 'Valor Líquido (R$)', data: compLiq, backgroundColor: '#0369a1', borderRadius: 6 },
        ],
      },
      options: { responsive: true, maintainAspectRatio: false },
    });
  }

  const ctxTrib = document.getElementById('chartTributos');
  if (ctxTrib) {
    if (nfseCharts.tributos) nfseCharts.tributos.destroy();
    const totals = window.NfseRetencoes.computeRetencoesTotals(AppState.nfse.notes.filter(n => n.status === 100));
    const tData = [totals.iss, totals.irrf, totals.inss, totals.csrf, totals.outros];
    nfseCharts.tributos = new Chart(ctxTrib, {
      type: 'doughnut',
      data: {
        labels: ['ISS Retido', 'IRRF', 'INSS', 'CSRF', 'Outros'],
        datasets: [{
          data: tData.some(v => v > 0) ? tData : [1],
          backgroundColor: ['#166659', '#b91c1c', '#b45309', '#0369a1', '#15803d', '#6b21a8'],
        }],
      },
      options: { responsive: true, maintainAspectRatio: false, cutout: '62%' },
    });
  }
}

function populateNfseFilters(notes) {
  const compSelect = document.getElementById('filterCompetencia');
  const prestSelect = document.getElementById('filterPrestador');
  if (!compSelect || !prestSelect) return;

  const competencias = [...new Set(notes.map(n => (n.data_competencia || '').substring(0, 7)).filter(Boolean))].sort().reverse();
  const prestadores = [...new Set(notes.map(n => n.emitente?.razao_social).filter(Boolean))].sort();

  compSelect.innerHTML = '<option value="">Todas as Competências</option>' +
    competencias.map(c => `<option value="${escapeHtml(c)}">${escapeHtml(c)}</option>`).join('');
  prestSelect.innerHTML = '<option value="">Todos os Prestadores</option>' +
    prestadores.map(p => `<option value="${escapeHtml(p)}">${escapeHtml(p)}</option>`).join('');
}

function applyNfseFilters() {
  const search = (document.getElementById('filterSearch')?.value || '').toLowerCase().trim();
  const comp = document.getElementById('filterCompetencia')?.value || '';
  const prest = document.getElementById('filterPrestador')?.value || '';
  const status = document.getElementById('filterStatus')?.value || '';

  AppState.nfse.filteredNotes = AppState.nfse.notes.filter(note => {
    const matchSearch = !search ||
      String(note.numero_nfse || '').toLowerCase().includes(search) ||
      String(note.chave_nfse || '').toLowerCase().includes(search) ||
      String(note.emitente?.razao_social || '').toLowerCase().includes(search) ||
      String(note.tomador?.razao_social || '').toLowerCase().includes(search);
    const matchComp = !comp || (note.data_competencia && note.data_competencia.startsWith(comp));
    const matchPrest = !prest || note.emitente?.razao_social === prest;
    const matchStatus = !status || note.auditoria?.status_conciliacao === status;
    return matchSearch && matchComp && matchPrest && matchStatus;
  });

  renderNfseNotesTable(AppState.nfse.filteredNotes);
}

function renderNfseNotesTable(notes) {
  const tbody = document.getElementById('notesTableBody');
  const emptyState = document.getElementById('emptyState');
  if (!tbody) return;

  if (!notes || notes.length === 0) {
    tbody.innerHTML = '';
    if (emptyState) emptyState.style.display = 'block';
    return;
  }
  if (emptyState) emptyState.style.display = 'none';

  tbody.innerHTML = notes.map(note => {
    const ret = window.NfseRetencoes.computeNotaRetencoes(note);
    const statusClass = (note.auditoria?.status_conciliacao || 'conciliado').toLowerCase();
    return `
      <tr>
        <td class="mono"><strong>#${escapeHtml(note.numero_nfse)}</strong></td>
        <td class="mono">${escapeHtml(formatDateBR(note.data_emissao_dps))}</td>
        <td><strong>${escapeHtml(note.emitente?.razao_social)}</strong><div class="mono" style="font-size:0.74rem; color:var(--muted);">${escapeHtml(formatTaxId(note.emitente?.documento_formatado))}</div></td>
        <td><strong>${escapeHtml(note.tomador?.razao_social)}</strong><div class="mono" style="font-size:0.74rem; color:var(--muted);">${escapeHtml(formatTaxId(note.tomador?.documento_formatado))}</div></td>
        <td><span class="badge badge-blue mono">${escapeHtml(note.codigo_tributacao_nacional || note.tributacao_nacional_desc || '-')}</span></td>
        <td class="text-right mono"><strong>${formatBRL(note.valor_servico)}</strong></td>
        <td class="text-right mono" style="color:var(--warn);">-${formatBRL(ret.total)}</td>
        <td class="text-right mono" style="color:var(--ok);"><strong>${formatBRL(note.valor_liquido)}</strong></td>
        <td>${note.dados_complementares_extraidos?.chave_pix ? `<span class="badge badge-green">PIX: ${escapeHtml(note.dados_complementares_extraidos.chave_pix)}</span>` : '—'}</td>
        <td><span class="badge ${statusClass}">${escapeHtml(note.auditoria?.status_conciliacao || 'CONCILIADO')}</span></td>
        <td>
          <div style="display:flex; gap:4px;">
            <button type="button" class="btn btn-sm btn-primary" data-note-action="openNoteDetail" data-note-key="${escapeHtml(note.chave_nfse)}">DANFSE</button>
            <button type="button" class="btn btn-sm btn-secondary" data-note-action="downloadSingleJson" data-note-key="${escapeHtml(note.chave_nfse)}">JSON</button>
            <button type="button" class="btn btn-sm btn-danger" data-note-action="deleteNote" data-note-key="${escapeHtml(note.chave_nfse)}">&times;</button>
          </div>
        </td>
      </tr>
    `;
  }).join('');
}

async function handleNfseFilesUpload(fileList) {
  if (AppState.nfse.uploading) return;
  const files = Array.from(fileList || []).filter(f => f.name.toLowerCase().endsWith('.xml') || f.name.toLowerCase().endsWith('.zip'));
  if (!files.length) {
    showToast('Selecione arquivos .xml ou .zip válidos.', 'warning');
    return;
  }
  const fd = new FormData();
  files.forEach(f => fd.append('files', f));
  setNfseBusy(true);
  try {
    const res = await ApiClient.request('/nfse/upload', { method: 'POST', body: fd });
    resetNfseView();
    showToast(`${res.processed_count || 0} NFS-e processada(s). O lote anterior foi substituído.`, 'success');
    await loadNfseDashboardData();
  } catch (err) {
    showToast(`Erro no upload de NFS-e: ${err.message}`, 'danger');
  } finally {
    setNfseBusy(false);
    const input = document.getElementById('fileInput');
    if (input) input.value = '';
  }
}

function setNfseBusy(busy) {
  AppState.nfse.uploading = busy;
  document.querySelectorAll('#view-nfse .action-group button, #fileInput, [data-note-action]').forEach(button => {
    button.disabled = busy;
  });
  document.getElementById('uploadProgress')?.classList.toggle('hidden', !busy);
  document.getElementById('dropzone')?.setAttribute('aria-busy', String(busy));
}

async function loadSampleData() {
  if (AppState.nfse.uploading) return;
  setNfseBusy(true);
  try {
    const res = await ApiClient.request('/nfse/load-samples', { method: 'POST' });
    resetNfseView();
    showToast(`${res.processed_count || 0} XML(s) de demonstração carregados no lote temporário.`, 'success');
    await loadNfseDashboardData();
  } catch (err) {
    showToast(`Erro ao carregar demonstração: ${err.message}`, 'danger');
  } finally {
    setNfseBusy(false);
  }
}

function openNoteDetail(chave) {
  const note = AppState.nfse.notes.find(n => n.chave_nfse === chave);
  if (!note) return;
  AppState.nfse.currentNote = note;
  const ret = window.NfseRetencoes.computeNotaRetencoes(note);

  const danfseEl = document.getElementById('danfseContainer');
  if (danfseEl) {
    danfseEl.innerHTML = `
      <div class="danfse-paper">
        <div class="danfse-header">
          <div>
            <strong>NOTA FISCAL DE SERVIÇO ELETRÔNICA</strong>
            <div style="font-size:0.82rem; color:var(--muted);">Espelho de consulta dos dados importados — não substitui o documento oficial.</div>
          </div>
          <div style="text-align:right;">
            <div class="mono" style="font-size:1.1rem; font-weight:800;">NFS-e Nº ${escapeHtml(note.numero_nfse)}</div>
            <div class="mono" style="font-size:0.75rem;">Emissão: ${escapeHtml(formatDateBR(note.data_emissao_dps))}</div>
          </div>
        </div>
        <div class="danfse-box">
          <div class="danfse-box-title">CHAVE / IDENTIFICADOR DA NFS-e</div>
          <div class="mono" style="font-weight:700;">${escapeHtml(note.chave_nfse)}</div>
        </div>
        <div class="danfse-grid-2">
          <div class="danfse-box">
            <div class="danfse-box-title">PRESTADOR DE SERVIÇOS</div>
            <div class="danfse-row"><span>Razão Social:</span> <strong>${escapeHtml(note.emitente?.razao_social)}</strong></div>
            <div class="danfse-row"><span>CNPJ/CPF:</span> <span class="mono">${escapeHtml(formatTaxId(note.emitente?.documento_formatado))}</span></div>
          </div>
          <div class="danfse-box">
            <div class="danfse-box-title">TOMADOR DE SERVIÇOS</div>
            <div class="danfse-row"><span>Razão Social:</span> <strong>${escapeHtml(note.tomador?.razao_social)}</strong></div>
            <div class="danfse-row"><span>CNPJ/CPF:</span> <span class="mono">${escapeHtml(formatTaxId(note.tomador?.documento_formatado))}</span></div>
          </div>
        </div>
        <div class="danfse-box">
          <div class="danfse-box-title">DISCRIMINAÇÃO DO SERVIÇO PRESTADO</div>
          <div style="font-size:0.85rem;">${escapeHtml(note.descricao_servico)}</div>
        </div>
        <div class="danfse-values-grid">
          <div class="val-box"><span class="lbl">Valor Bruto</span><span class="val">${formatBRL(note.valor_servico)}</span></div>
          <div class="val-box"><span class="lbl">Total Retenções</span><span class="val" style="color:var(--warn);">-${formatBRL(ret.total)}</span></div>
          <div class="val-box highlight"><span class="lbl">Valor Líquido (vLiq)</span><span class="val" style="color:var(--accent);">${formatBRL(note.valor_liquido)}</span></div>
        </div>
      </div>
    `;
  }

  const compEl = document.getElementById('tab-complementares');
  if (compEl) {
    const c = note.dados_complementares_extraidos || {};
    compEl.innerHTML = `
      <div class="danfse-box">
        <div class="danfse-box-title">DADOS BANCÁRIOS E PIX EXTRAÍDOS</div>
        <div class="danfse-row"><span>Chave PIX:</span> <strong>${escapeHtml(c.chave_pix || 'Não informada')}</strong></div>
        <div class="danfse-row"><span>Banco / Agência / Conta:</span> <span>${escapeHtml(c.banco || '-')} / ${escapeHtml(c.agencia || '-')} / ${escapeHtml(c.conta || '-')}</span></div>
      </div>
      <div class="danfse-box">
        <div class="danfse-box-title">INFORMAÇÕES COMPLEMENTARES (xInfComp)</div>
        <div class="code-block">${escapeHtml(note.informacoes_complementares || 'Sem observações declaradas.')}</div>
      </div>
    `;
  }

  const audEl = document.getElementById('tab-auditoria');
  if (audEl) {
    const a = note.auditoria || {};
    audEl.innerHTML = `
      <div class="danfse-box">
        <div class="danfse-box-title">CONCILIAÇÃO CONTÁBIL AUTOMÁTICA</div>
        <div class="danfse-row"><span>Status:</span> <strong>${escapeHtml(a.status_conciliacao || 'CONCILIADO')}</strong></div>
        <div class="danfse-row"><span>Equação vLiq = vServ - vTotalRet:</span> <span>${a.equacao_liquido_valida ? '✓ Válida' : 'Divergente'}</span></div>
      </div>
    `;
  }

  const jsonEl = document.getElementById('jsonViewer');
  if (jsonEl) jsonEl.textContent = JSON.stringify(note, null, 2);

  document.getElementById('modalOverlay')?.classList.add('active');
}

function downloadSingleJson(chave) {
  const note = AppState.nfse.notes.find(n => n.chave_nfse === chave) || AppState.nfse.currentNote;
  if (!note) return;
  const blob = new Blob([JSON.stringify(note, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `${note.chave_nfse}.json`;
  a.click();
  URL.revokeObjectURL(url);
}

async function deleteNote(chave) {
  try {
    await ApiClient.request(`/nfse/notes/${encodeURIComponent(chave)}`, { method: 'DELETE' });
    showToast('Nota fiscal removida.', 'info');
    await loadNfseDashboardData();
  } catch (err) {
    showToast(`Erro ao remover nota: ${err.message}`, 'danger');
  }
}

function copyJsonToClipboard() {
  if (AppState.nfse.currentNote && navigator.clipboard) {
    navigator.clipboard.writeText(JSON.stringify(AppState.nfse.currentNote, null, 2)).then(() => {
      showToast('JSON copiado para a área de transferência!', 'success');
    });
  }
}

// ============================================================================
// VIEW 13: CONFERIDOR NF-E, ST/DIFAL & CONCILIAÇÃO DE ZIPS (svc-nfe-difal)
// ============================================================================
function renderNfeResults(title, data) {
  const subtitle = document.getElementById('nfe-results-subtitle');
  const container = document.getElementById('nfe-results-container');
  if (subtitle) subtitle.textContent = title;
  if (!container) return;
  container.innerHTML = `<pre class="code-block">${escapeHtml(JSON.stringify(data, null, 2))}</pre>`;
}

// ============================================================================
// VIEW 14: FERRAMENTAS PDF (svc-pdf-tools)
// ============================================================================
async function checkPdfApiStatus() {
  const pill = document.getElementById('api-status');
  const text = document.getElementById('api-status-text');
  if (!pill || !text) return;
  try {
    const res = await ApiClient.request('/pdf/status');
    text.textContent = res.status === 'online' ? 'API PDF Pronta' : 'API PDF Indisponível';
  } catch (_) {
    text.textContent = 'API PDF Pronta via Gateway';
  }
}

function initializePdfToolsModule() {
  const toolButtons = document.querySelectorAll('[data-tool]');
  const toolPanels = document.querySelectorAll('[data-panel]');

  toolButtons.forEach(btn => {
    btn.addEventListener('click', () => {
      const tool = btn.dataset.tool;
      toolButtons.forEach(b => b.classList.toggle('is-active', b.dataset.tool === tool));
      toolPanels.forEach(p => { p.hidden = p.dataset.panel !== tool; });
    });
  });

  // Conditional modes for split & organize
  const splitMode = document.getElementById('split-mode');
  if (splitMode) {
    splitMode.addEventListener('change', () => {
      document.querySelectorAll('[data-split-mode]').forEach(group => {
        const active = group.dataset.splitMode === splitMode.value;
        group.hidden = !active;
        group.querySelectorAll('input, select').forEach(el => { el.disabled = !active; });
      });
    });
  }

  const organizeMode = document.getElementById('organize-mode');
  if (organizeMode) {
    organizeMode.addEventListener('change', () => {
      document.querySelectorAll('[data-organize-mode]').forEach(group => {
        const active = group.dataset.organizeMode === organizeMode.value;
        group.hidden = !active;
        group.querySelectorAll('input, select').forEach(el => { el.disabled = !active; });
      });
    });
  }

  // Live preview for page numbering
  const updatePreview = () => {
    const pos = document.getElementById('number-position')?.value || 'bottom-center';
    const first = Number(document.getElementById('number-first')?.value || 1);
    const tpl = document.getElementById('number-template')?.value || 'Página {current} de {total}';
    const prev = document.getElementById('number-preview-text');
    if (prev) {
      prev.className = `page-number-preview ${pos}`;
      prev.textContent = tpl.replaceAll('{current}', String(first)).replaceAll('{total}', String(first + 2)).replaceAll('{document_total}', '3');
    }
  };
  ['number-position', 'number-first', 'number-template', 'number-font', 'number-font-size'].forEach(id => {
    document.getElementById(id)?.addEventListener('input', updatePreview);
  });

  // Password visibility toggle
  document.querySelectorAll('[data-toggle-password]').forEach(btn => {
    btn.addEventListener('click', () => {
      const input = document.getElementById(btn.dataset.togglePassword);
      if (!input) return;
      const showing = input.type === 'text';
      input.type = showing ? 'password' : 'text';
      btn.textContent = showing ? 'Mostrar' : 'Ocultar';
    });
  });

  // File summary update
  document.querySelectorAll('form.tool-form input[type="file"]').forEach(input => {
    input.addEventListener('change', () => {
      const summary = document.querySelector(`[data-file-summary="${input.id}"]`);
      if (summary) {
        const files = Array.from(input.files || []);
        summary.textContent = files.length ? `${files.length} arquivo(s): ${files.map(f => f.name).join(', ')}` : 'Nenhum arquivo selecionado.';
      }
    });
  });

  // Submit handler for all 6 PDF forms
  document.querySelectorAll('form.tool-form').forEach(form => {
    form.addEventListener('submit', async event => {
      event.preventDefault();
      const statusBox = form.querySelector('[data-form-status]');
      const fd = new FormData(form);
      try {
        if (statusBox) {
          statusBox.hidden = false;
          statusBox.className = 'form-status is-loading';
          statusBox.textContent = 'Processando arquivo PDF...';
        }
        const fallback = form.id === 'merge-form' ? 'documentos_mesclados.pdf' : 'documento_processado.pdf';
        const res = await ApiClient.download(form.getAttribute('action'), fallback, {
          method: 'POST',
          body: fd,
        });
        if (statusBox) {
          statusBox.className = 'form-status is-success';
          statusBox.textContent = `Download concluído automaticamente: ${res.filename}`;
        }
      } catch (err) {
        if (statusBox) {
          statusBox.hidden = false;
          statusBox.className = 'form-status is-error';
          statusBox.textContent = err.message;
        }
      }
    });
  });
}

// ============================================================================
// VIEW 15: AUDITORIA TRIBUTÁRIA FEDERAL (svc-federal-tax-audit)
// ============================================================================
function switchAuditTab(tabId) {
  document.querySelectorAll('#view-tax-audit [data-audit-tab]').forEach(btn => {
    if (btn.classList.contains('tab-btn')) {
      btn.classList.toggle('active', btn.dataset.auditTab === tabId);
    }
  });
  document.querySelectorAll('#view-tax-audit .tab-content').forEach(panel => {
    panel.classList.toggle('active', panel.id === `view-audit-${tabId}`);
  });
}

async function loadAuditData() {
  const banner = document.getElementById('network-error-banner');
  if (banner) banner.style.display = 'none';

  try {
    const [healthRes, auditRes, docsRes, nfseRes, darfsRes, reportRes] = await Promise.all([
      ApiClient.request('/tax-audit/health'),
      ApiClient.request('/tax-audit/audit'),
      ApiClient.request('/tax-audit/documents'),
      ApiClient.request('/tax-audit/nfse'),
      ApiClient.request('/tax-audit/darfs'),
      ApiClient.request('/tax-audit/report/markdown'),
    ]);

    AppState.taxAudit.data = auditRes;
    AppState.taxAudit.nfseList = nfseRes.notas || [];

    const tsEl = document.getElementById('snapshot-timestamp');
    if (tsEl) tsEl.textContent = `Snapshot: ${healthRes.snapshot_timestamp || 'Ativo'}`;

    const fat = auditRes.resumo_faturamento || {};
    const missing = auditRes.notas_ausentes_no_livro || {};
    document.getElementById('kpi-fat-val').textContent = formatBRL(fat.valor_total_servicos_nfse);
    document.getElementById('kpi-omissao-val').textContent = formatBRL(missing.valor_total);
    document.getElementById('kpi-credito-val').textContent = formatBRL(fat.total_inss_retido_nfse);
    document.getElementById('kpi-irrf-val').textContent = formatBRL(fat.total_irrf_retido_nfse);

    renderAuditFindings(auditRes.achados_auditoria || []);
    renderAuditDocuments(docsRes.documentos || []);
    renderAuditPisCofins(auditRes.cruzamento_mensal_pis_cofins || []);
    renderAuditIrpjCsll(auditRes.cruzamento_trimestral_irpj_csll || []);
    renderAuditNfseTable(AppState.taxAudit.nfseList);
    renderAuditDarfs(darfsRes.comprovantes || []);
    renderAuditReportMarkdown(reportRes.markdown || '');
    await runTaxAuditSimulation();
  } catch (err) {
    if (banner) {
      banner.style.display = 'block';
      document.getElementById('network-error-msg').textContent = err.message;
    }
  }
}

function renderAuditFindings(findings) {
  const container = document.getElementById('findings-container');
  if (!container) return;
  if (!findings.length) {
    container.innerHTML = '<div class="empty-state">Nenhum apontamento crítico identificado no snapshot atual.</div>';
    return;
  }
  container.innerHTML = findings.map(f => {
    const sev = f.severidade || 'MÉDIA';
    const sevClass = sev === 'CRÍTICA' ? 'critical' : (sev === 'ALTA' ? 'high' : (sev === 'OPORTUNIDADE' ? 'opportunity' : 'medium'));
    return `
      <div class="finding-card ${sevClass}">
        <div class="finding-header">
          <div>
            <span class="badge ${sev === 'OPORTUNIDADE' ? 'badge-green' : 'badge-red'}">${escapeHtml(sev)}</span>
            <span class="mono" style="font-size:0.78rem; color:var(--muted); margin-left:6px;">${escapeHtml(f.id)}</span>
            <div class="finding-title" style="margin-top:4px;">${escapeHtml(f.titulo)}</div>
          </div>
          <div class="finding-impact">${formatBRL(f.impacto_financeiro)}</div>
        </div>
        <div class="finding-body">${escapeHtml(f.descricao)}</div>
        <div class="finding-meta">
          <div><strong>Base Legal:</strong> ${escapeHtml(f.base_legal)}</div>
          <div><strong>Recomendação Técnica:</strong> ${escapeHtml(f.recomendacao)}</div>
        </div>
      </div>
    `;
  }).join('');
}

function renderAuditDocuments(docs) {
  const grid = document.getElementById('documents-grid');
  if (!grid) return;
  grid.innerHTML = docs.map(d => `
    <div class="doc-card">
      <div>
        <span class="doc-badge">${escapeHtml(d.categoria)}</span>
        <div class="doc-title">${escapeHtml(d.tipo)}</div>
        <div class="mono" style="font-size:0.76rem; color:var(--accent); margin-bottom:4px;">${escapeHtml(d.nome)}</div>
        <div class="doc-desc">${escapeHtml(d.detalhes)}</div>
      </div>
      <div class="doc-footer">
        <span><strong>Emissor:</strong> ${escapeHtml(d.orgao_emissor)}</span>
        <span><strong>Qtd:</strong> ${escapeHtml(d.qtd_documentos)}</span>
      </div>
    </div>
  `).join('');
}

function renderAuditPisCofins(rows) {
  const tbody = document.getElementById('tbody-pis-cofins');
  if (!tbody) return;
  tbody.innerHTML = rows.map(r => {
    const diff = Number(r.divergencia_receita || 0);
    const badgeClass = diff > 10 ? 'badge-red' : (diff < -10 ? 'badge-blue' : 'badge-green');
    const badgeLabel = diff > 10 ? 'SUBDECLARADO' : (diff < -10 ? 'CRÉDITO / A MAIOR' : 'CONFORME');
    return `
      <tr>
        <td><strong>${escapeHtml(r.competencia_exibicao || r.competencia)}</strong></td>
        <td class="num">${escapeHtml(r.qtd_nfse)}</td>
        <td class="num">${formatBRL(r.faturamento_nfse)}</td>
        <td class="num">${formatBRL(r.receita_declarada_pis_cofins)}</td>
        <td class="num ${diff > 10 ? 'diff-positive' : 'diff-zero'}">${formatBRL(diff)}</td>
        <td class="num">${formatBRL(r.pis_apurado)}</td>
        <td class="num">${formatBRL(r.pis_pago_darf)}</td>
        <td class="num">${formatBRL(r.cofins_apurado)}</td>
        <td class="num">${formatBRL(r.cofins_pago_darf)}</td>
        <td><span class="badge ${badgeClass}">${badgeLabel}</span></td>
      </tr>
    `;
  }).join('');
}

function renderAuditIrpjCsll(rows) {
  const tbody = document.getElementById('tbody-irpj-csll');
  if (!tbody) return;
  tbody.innerHTML = rows.map(r => {
    const isDiff = Math.abs(Number(r.divergencia_faturamento || 0)) > 100;
    return `
      <tr>
        <td><strong>${escapeHtml(r.trimestre)}</strong></td>
        <td>${escapeHtml(r.competencia_exibicao || r.competencia)}</td>
        <td class="num">${formatBRL(r.faturamento_nfse_total)}</td>
        <td class="num">${formatBRL(r.receita_declarada_irpj_csll)}</td>
        <td class="num">${formatBRL(r.base_irpj_pdf)}</td>
        <td class="num" style="color:var(--accent); font-weight:700;">${formatBRL(r.base_irpj_recalculada_lc224)}</td>
        <td class="num diff-credit">${formatBRL(r.irrf_retido_pdf || r.irrf_retido_notas)}</td>
        <td class="num">${formatBRL(r.irpj_apurado_declarado)}</td>
        <td class="num">${formatBRL(r.irpj_pago_darf_principal)}</td>
        <td class="num">${formatBRL(r.csll_apurado_declarado)}</td>
        <td class="num">${formatBRL(r.csll_pago_darf_principal)}</td>
        <td><span class="badge ${isDiff ? 'badge-yellow' : 'badge-green'}">${isDiff ? 'DIVERGÊNCIA' : 'CONFORME'}</span></td>
      </tr>
    `;
  }).join('');
}

function renderAuditNfseTable(notas) {
  const tbody = document.getElementById('tbody-nfse');
  if (!tbody) return;
  tbody.innerHTML = notas.map(n => {
    const csrfTotal = Number(n.retencoes?.csll || 0) + Number(n.retencoes?.pis || 0) + Number(n.retencoes?.cofins || 0);
    const sit = n.situacao_livro || 'ESCRITURADA';
    return `
      <tr>
        <td class="mono"><strong>${escapeHtml(n.numero_nfse)}</strong></td>
        <td>${escapeHtml(n.competencia_exibicao || n.competencia_mes || '-')}</td>
        <td class="mono">${escapeHtml((n.data_emissao || '').slice(0, 10))}</td>
        <td>${escapeHtml(n.tomador || 'Não Identificado')}</td>
        <td class="mono">${escapeHtml(n.cnpj_tomador || '-')}</td>
        <td class="num"><strong>${formatBRL(n.valor_servico)}</strong></td>
        <td class="num">${formatBRL(n.retencoes?.inss)}</td>
        <td class="num">${formatBRL(n.retencoes?.irrf)}</td>
        <td class="num">${formatBRL(csrfTotal)}</td>
        <td><span class="badge ${n.status_codigo === 101 ? 'badge-yellow' : 'badge-green'}">Status ${escapeHtml(n.status_codigo || 100)}</span></td>
        <td><span class="badge ${sit.startsWith('NAO_LOCALIZADA') ? 'badge-red' : 'badge-green'}">${escapeHtml(sit)}</span></td>
      </tr>
    `;
  }).join('');
}

function filterAuditNfseList() {
  const search = (document.getElementById('input-search-nfse')?.value || '').toLowerCase().trim();
  const f = AppState.taxAudit.currentNfseFilter;
  const filtered = AppState.taxAudit.nfseList.filter(n => {
    const matchSearch = !search ||
      String(n.numero_nfse || '').includes(search) ||
      String(n.tomador || '').toLowerCase().includes(search) ||
      String(n.cnpj_tomador || '').includes(search);
    if (!matchSearch) return false;
    if (f === 'missing') return String(n.situacao_livro || '').startsWith('NAO_LOCALIZADA');
    if (f === 'retention') {
      const r = n.retencoes || {};
      return (r.inss > 0) || (r.irrf > 0) || (r.iss > 0) || (r.csll > 0) || (r.pis > 0) || (r.cofins > 0);
    }
    if (f === 'status101') return n.status_codigo === 101;
    return true;
  });
  renderAuditNfseTable(filtered);
}

function renderAuditDarfs(darfs) {
  const tbody = document.getElementById('tbody-darfs');
  if (!tbody) return;
  tbody.innerHTML = darfs.map(d => `
    <tr>
      <td class="mono"><strong>${escapeHtml(d.documento || '-')}</strong></td>
      <td>Pág. ${escapeHtml(d.pagina)}</td>
      <td><span class="badge badge-blue mono">${escapeHtml(d.codigo_receita)}</span></td>
      <td><strong>${escapeHtml(d.tributo)}</strong> — ${escapeHtml(d.descricao)}</td>
      <td>${escapeHtml(d.extensao || '-')}</td>
      <td class="mono">${escapeHtml(d.periodo_apuracao || '-')}</td>
      <td class="mono">${escapeHtml(d.data_vencimento || '-')}</td>
      <td class="mono">${escapeHtml(d.data_arrecadacao || '-')}</td>
      <td class="num">${formatBRL(d.valor_principal)}</td>
      <td class="num">${formatBRL(d.valor_multa)}</td>
      <td class="num">${formatBRL(d.valor_juros)}</td>
      <td class="num"><strong>${formatBRL(d.valor_total)}</strong></td>
      <td><span class="badge badge-green">${d.is_quota ? 'Quota' : 'Ordinário'}</span></td>
    </tr>
  `).join('');
}

async function runTaxAuditSimulation() {
  const presuncao = parseFloat(document.getElementById('slider-presuncao')?.value || 32);
  const multa = parseFloat(document.getElementById('slider-multa')?.value || 75);
  const selic = parseFloat(document.getElementById('slider-selic')?.value || 10.5);

  document.getElementById('lbl-presuncao').textContent = `${presuncao.toFixed(1)}%`;
  document.getElementById('lbl-multa').textContent = `${multa.toFixed(1)}%`;
  document.getElementById('lbl-selic').textContent = `${selic.toFixed(1)}%`;

  try {
    const res = await ApiClient.request('/tax-audit/simulate', {
      method: 'POST',
      body: { presuncao_pct: presuncao, multa_oficio_pct: multa, taxa_selic_pct: selic },
    });
    document.getElementById('sim-base-fat').textContent = formatBRL(res.base_omissao_receita);
    document.getElementById('sim-tributos').textContent = formatBRL(res.tributos_principais_apurados?.subtotal_principal);
    document.getElementById('sim-multa').textContent = formatBRL(res.encargos_fiscais?.multa_oficio);
    document.getElementById('sim-juros').textContent = formatBRL(res.encargos_fiscais?.juros_selic);
    document.getElementById('sim-passivo-bruto').textContent = formatBRL(res.passivo_tributario_bruto);

    const oport = res.eixo_oportunidade_previdenciaria || {};
    document.getElementById('sim-credito-inss-ret').textContent = formatBRL(oport.inss_retido_total_nfse || res.creditos_recuperaveis?.inss_retido_fonte_cessao_mao_obra);
    document.getElementById('sim-darf-1082').textContent = formatBRL(oport.darf_1082_recolhido || 0);
    document.getElementById('sim-credito-inss-saldo').textContent = formatBRL(oport.saldo_potencial_em_analise || res.creditos_recuperaveis?.credito_liquido_estimado_per_dcomp);
  } catch (_) {}
}

function renderAuditReportMarkdown(md) {
  const container = document.getElementById('official-report-content');
  if (!container) return;
  container.innerHTML = `<div class="code-block" style="white-space:pre-wrap;">${escapeHtml(md || 'Relatório carregado.')}</div>`;
}

async function reloadDataFromDisk() {
  try {
    await ApiClient.request('/tax-audit/reload', { method: 'POST' });
    showToast('Snapshot de auditoria recarregado com sucesso!', 'success');
    await loadAuditData();
  } catch (err) {
    showToast(`Erro ao recarregar auditoria: ${err.message}`, 'danger');
  }
}

// ============================================================================
// REGISTRO DE EVENTOS E DELEGAÇÃO (100% CSP-COMPLIANT)
// ============================================================================
document.addEventListener('DOMContentLoaded', () => {
  // Login & Logout
  document.getElementById('login-form')?.addEventListener('submit', handleLoginSubmit);
  document.getElementById('logout-btn')?.addEventListener('click', handleLogout);
  document.getElementById('mfa-setup-btn')?.addEventListener('click', openMfaSetupModal);

  // Sidebar navigation
  document.querySelectorAll('#module-nav .nav-item').forEach(btn => {
    btn.addEventListener('click', () => navigateTo(btn.dataset.view));
  });

  // Topbar context controls
  document.getElementById('company-select')?.addEventListener('change', e => handleCompanySwitch(e.target.value, true));
  document.getElementById('competence-input')?.addEventListener('change', e => {
    AppState.competence = e.target.value;
    navigateTo(AppState.activeView);
  });
  document.getElementById('refresh-view-btn')?.addEventListener('click', () => navigateTo(AppState.activeView));
  document.getElementById('open-create-company-btn')?.addEventListener('click', () => openModal('modal-create-company'));

  // Filter inputs
  document.getElementById('companies-search-input')?.addEventListener('input', loadCompaniesList);
  document.getElementById('companies-regime-filter')?.addEventListener('change', loadCompaniesList);
  document.getElementById('companies-status-filter')?.addEventListener('change', loadCompaniesList);
  document.getElementById('tasks-status-filter')?.addEventListener('change', loadTasksList);
  document.getElementById('tasks-risk-filter')?.addEventListener('change', loadTasksList);
  document.getElementById('docs-dept-filter')?.addEventListener('change', loadDocumentsViewData);
  document.getElementById('docs-status-filter')?.addEventListener('change', loadDocumentsViewData);
  document.getElementById('recon-bank-account-select')?.addEventListener('change', loadReconciliationViewData);
  document.getElementById('ofx-upload-input')?.addEventListener('change', handleOfxUploadChange);
  document.getElementById('cashflow-days-select')?.addEventListener('change', loadAnalyticsViewData);
  document.getElementById('audit-action-filter')?.addEventListener('change', loadSecurityViewData);

  // NFS-e Dropzone & Filters
  const dropzone = document.getElementById('dropzone');
  const fileInput = document.getElementById('fileInput');
  if (dropzone && fileInput) {
    dropzone.addEventListener('click', () => fileInput.click());
    dropzone.addEventListener('keydown', event => {
      if (event.target === dropzone && ['Enter', ' '].includes(event.key)) {
        event.preventDefault();
        fileInput.click();
      }
    });
    dropzone.addEventListener('dragover', e => { e.preventDefault(); dropzone.classList.add('dragover'); });
    dropzone.addEventListener('dragleave', () => dropzone.classList.remove('dragover'));
    dropzone.addEventListener('drop', e => {
      e.preventDefault();
      dropzone.classList.remove('dragover');
      handleNfseFilesUpload(e.dataTransfer.files);
    });
    fileInput.addEventListener('change', e => handleNfseFilesUpload(e.target.files));
  }
  document.getElementById('filterSearch')?.addEventListener('input', applyNfseFilters);
  document.getElementById('filterCompetencia')?.addEventListener('change', applyNfseFilters);
  document.getElementById('filterPrestador')?.addEventListener('change', applyNfseFilters);
  document.getElementById('filterStatus')?.addEventListener('change', applyNfseFilters);
  document.getElementById('btnResetFilters')?.addEventListener('click', () => {
    ['filterSearch', 'filterCompetencia', 'filterPrestador', 'filterStatus'].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.value = '';
    });
    applyNfseFilters();
  });
  document.getElementById('btnClear')?.addEventListener('click', async () => {
    if (AppState.nfse.uploading) return;
    setNfseBusy(true);
    try {
      await ApiClient.request('/nfse/notes', { method: 'DELETE' });
      resetNfseView();
      showToast('Lote temporário de NFS-e limpo.', 'info');
      await loadNfseDashboardData();
    } catch (err) {
      showToast(err.message, 'danger');
    } finally {
      setNfseBusy(false);
    }
  });
  document.getElementById('btnCloseModal')?.addEventListener('click', () => {
    document.getElementById('modalOverlay')?.classList.remove('active');
  });
  document.querySelectorAll('#modalOverlay [data-tab]').forEach(btn => {
    btn.addEventListener('click', () => {
      const tab = btn.dataset.tab;
      document.querySelectorAll('#modalOverlay [data-tab]').forEach(b => b.classList.toggle('active', b.dataset.tab === tab));
      document.querySelectorAll('#modalOverlay .modal-tab-content').forEach(c => c.classList.toggle('active', c.id === `tab-${tab}`));
    });
  });

  // Tax Audit Sliders & Filters
  ['slider-presuncao', 'slider-multa', 'slider-selic'].forEach(id => {
    document.getElementById(id)?.addEventListener('input', () => {
      clearTimeout(AppState.taxAudit.simDebounceTimer);
      AppState.taxAudit.simDebounceTimer = setTimeout(runTaxAuditSimulation, 250);
    });
  });
  document.getElementById('input-search-nfse')?.addEventListener('input', filterAuditNfseList);

  // Forms Submissions (Modals & Inline Forms)
  document.getElementById('form-create-company')?.addEventListener('submit', async e => {
    e.preventDefault();
    try {
      const comp = await ApiClient.createCompany({
        organization_id: AppState.organizationId,
        corporate_name: document.getElementById('modal-comp-corp-name').value.trim(),
        trade_name: document.getElementById('modal-comp-trade-name').value.trim(),
        tax_id: document.getElementById('modal-comp-tax-id').value.trim(),
        tax_regime: document.getElementById('modal-comp-regime').value,
        cnae_code: document.getElementById('modal-comp-cnae').value.trim(),
      });
      closeModal('modal-create-company');
      showToast(`Empresa ${comp.corporate_name} cadastrada com sucesso!`, 'success');
      await initializeCompanySelector();
      await handleCompanySwitch(comp.id, true);
    } catch (err) {
      showToast(`Erro ao cadastrar empresa: ${err.message}`, 'danger');
    }
  });

  document.getElementById('form-batch-request')?.addEventListener('submit', async e => {
    e.preventDefault();
    try {
      const res = await ApiClient.batchRequestDocuments({
        organization_id: AppState.organizationId,
        competence: document.getElementById('modal-batch-competence').value.trim(),
        target_tax_regime: document.getElementById('modal-batch-regime').value || null,
        document_types: document.getElementById('modal-batch-doctypes').value.split(',').map(s => s.trim()),
      });
      closeModal('modal-batch-request');
      showToast(`Cobrança em lote concluída: ${res.success_count}/${res.total_requested} empresas notificadas.`, 'success');
    } catch (err) {
      showToast(`Erro no lote: ${err.message}`, 'danger');
    }
  });

  document.getElementById('modal-attach-doc-select')?.addEventListener('change', e => {
    const opt = e.target.selectedOptions?.[0];
    if (opt && opt.value) {
      document.getElementById('modal-attach-file-id').value = opt.value;
      document.getElementById('modal-attach-hash').value = opt.dataset.sha || '';
    }
  });

  document.getElementById('form-attach-receipt')?.addEventListener('submit', async e => {
    e.preventDefault();
    const taskId = document.getElementById('modal-attach-task-id').value;
    try {
      await ApiClient.attachTaskReceipt(taskId, {
        file_id: document.getElementById('modal-attach-file-id').value.trim(),
        file_hash: document.getElementById('modal-attach-hash').value.trim(),
        user_id: AppState.currentUser.id,
      });
      closeModal('modal-attach-receipt');
      showToast('Comprovante oficial vinculado à obrigação com sucesso!', 'success');
      await loadTasksList();
    } catch (err) {
      showToast(`Erro ao anexar recibo: ${err.message}`, 'danger');
    }
  });

  document.getElementById('form-upload-doc')?.addEventListener('submit', async e => {
    e.preventDefault();
    const file = document.getElementById('modal-upload-file').files?.[0];
    if (!file || !AppState.activeCompanyId) return;
    const fd = new FormData();
    fd.append('company_id', AppState.activeCompanyId);
    fd.append('competence', AppState.competence);
    fd.append('department', document.getElementById('modal-upload-dept').value);
    fd.append('file', file);
    try {
      const res = await ApiClient.uploadDocument(fd);
      closeModal('modal-upload-doc');
      showToast(`Documento ${res.file_name} ingerido com protocolo ${res.receipt_code}!`, 'success');
      await loadDocumentsViewData();
    } catch (err) {
      showToast(`Erro no upload: ${err.message}`, 'danger');
    }
  });

  document.getElementById('form-create-payable')?.addEventListener('submit', async e => {
    e.preventDefault();
    const amount = Number(document.getElementById('modal-pay-amount').value);
    try {
      await ApiClient.createPayableBill({
        company_id: AppState.activeCompanyId,
        type: document.getElementById('modal-pay-type').value,
        dre_category: document.getElementById('modal-pay-category').value,
        counterparty_name: document.getElementById('modal-pay-counterparty').value.trim(),
        original_amount: amount,
        final_amount: amount,
        issue_date: new Date().toISOString().slice(0, 10),
        due_date: document.getElementById('modal-pay-duedate').value,
        payment_method: document.getElementById('modal-pay-method').value,
        barcode_line: document.getElementById('modal-pay-barcode').value.trim() || undefined,
        pix_key: document.getElementById('modal-pay-pix').value.trim() || undefined,
      });
      closeModal('modal-create-payable');
      showToast('Título registrado com sucesso no BPO Financeiro!', 'success');
      await loadFinanceViewData();
    } catch (err) {
      showToast(`Erro ao registrar título: ${err.message}`, 'danger');
    }
  });

  document.getElementById('bank-account-create-form')?.addEventListener('submit', async e => {
    e.preventDefault();
    try {
      await ApiClient.createBankAccount({
        bank_code: document.getElementById('bank-code-input').value.trim(),
        bank_name: document.getElementById('bank-name-input').value.trim(),
        agency_number: document.getElementById('bank-agency-input').value.trim(),
        account_number: document.getElementById('bank-account-number-input').value.trim(),
      });
      showToast('Conta bancária cadastrada com sucesso!', 'success');
      await loadReconciliationViewData();
    } catch (err) {
      showToast(`Erro ao criar conta bancária: ${err.message}`, 'danger');
    }
  });

  document.getElementById('fiscal-transmission-form')?.addEventListener('submit', async e => {
    e.preventDefault();
    try {
      const tx = await ApiClient.enqueueTransmission({
        company_id: AppState.activeCompanyId,
        system_target: document.getElementById('fiscal-system-target').value,
        event_type: document.getElementById('fiscal-event-type').value,
        competence: document.getElementById('fiscal-competence').value.trim(),
        environment: document.getElementById('fiscal-environment').value,
        idempotency_key: `idem-${AppState.activeCompanyId}-${Date.now()}`,
        xml_payload: document.getElementById('fiscal-xml-payload').value,
      });
      AppState.transmissions.unshift(tx);
      renderFiscalTransmissionsTable();
      showToast('Evento XML validado e enfileirado com sucesso!', 'success');
    } catch (err) {
      showToast(`Erro ao enfileirar transmissão: ${err.message}`, 'danger');
    }
  });

  document.getElementById('ai-classify-form')?.addEventListener('submit', async e => {
    e.preventDefault();
    try {
      const sugg = await ApiClient.suggestClassification({
        company_id: AppState.activeCompanyId,
        description_or_memo: document.getElementById('ai-memo-input').value.trim(),
        amount: Number(document.getElementById('ai-amount-input').value),
      });
      AppState.lastAiSuggestionId = sugg.id;
      const box = document.getElementById('ai-suggestion-result');
      if (box) {
        box.style.display = 'block';
        box.innerHTML = `
          <div class="danfse-box">
            <div class="danfse-box-title">SUGESTÃO DE PARTIDA DOBRADA (CONFIANÇA: ${Math.round(Number(sugg.confidence_score || 0) * 100)}%)</div>
            <div class="danfse-row"><span>Conta Débito:</span> <strong class="mono">${escapeHtml(sugg.suggested_debit_account)}</strong></div>
            <div class="danfse-row"><span>Conta Crédito:</span> <strong class="mono">${escapeHtml(sugg.suggested_credit_account)}</strong></div>
            <div class="danfse-row"><span>Centro de Custo:</span> <span>${escapeHtml(sugg.suggested_cost_center)}</span></div>
            <div class="danfse-row"><span>Histórico Padrão:</span> <span>${escapeHtml(sugg.suggested_narrative)}</span></div>
            <div style="margin-top:8px;">
              <button type="button" class="btn btn-sm btn-success" data-ai-feedback="approved">Confirmar e Ensinar IA</button>
            </div>
          </div>
        `;
      }
    } catch (err) {
      showToast(`Erro na sugestão IA: ${err.message}`, 'danger');
    }
  });

  document.getElementById('form-new-ticket')?.addEventListener('submit', async e => {
    e.preventDefault();
    try {
      await ApiClient.createTicket({
        company_id: AppState.activeCompanyId,
        category: document.getElementById('modal-ticket-category').value,
        priority: document.getElementById('modal-ticket-priority').value,
        title: document.getElementById('modal-ticket-title').value.trim(),
        created_by_user_id: AppState.currentUser.id,
        structured_data: {
          description: document.getElementById('modal-ticket-desc').value.trim(),
          employee_name: 'Colaborador Informado',
          admission_date: '2026-10-15',
          base_salary: 3500.0,
          tax_type: 'DAS/DARF',
          competence: AppState.competence,
        },
      });
      closeModal('modal-new-ticket');
      showToast('Chamado aberto com SLA calculado!', 'success');
      await loadPortalData();
    } catch (err) {
      showToast(`Erro ao abrir chamado: ${err.message}`, 'danger');
    }
  });

  document.getElementById('cert-upload-form')?.addEventListener('submit', async e => {
    e.preventDefault();
    const file = document.getElementById('cert-pfx-file').files?.[0];
    if (!file || !AppState.activeCompanyId) return;
    const fd = new FormData();
    fd.append('company_id', AppState.activeCompanyId);
    fd.append('password', document.getElementById('cert-pfx-password').value);
    fd.append('certificate_type', 'a1_file');
    fd.append('file', file);
    try {
      await ApiClient.uploadCertificateVault(fd);
      showToast('Certificado ICP-Brasil validado e armazenado no cofre AES-256-GCM!', 'success');
      await loadSecurityViewData();
    } catch (err) {
      showToast(`Validação ICP-Brasil: ${err.message}`, 'warning');
    }
  });

  document.getElementById('iam-user-form')?.addEventListener('submit', async e => {
    e.preventDefault();
    try {
      const res = await ApiClient.createUser({
        email: document.getElementById('iam-user-email').value.trim(),
        password: document.getElementById('iam-user-password').value,
        role: document.getElementById('iam-user-role').value,
        company_ids: AppState.activeCompanyId ? [AppState.activeCompanyId] : [],
      });
      showToast(`Operador IAM ${res.email} criado com sucesso!`, 'success');
      e.target.reset();
    } catch (err) {
      showToast(`Erro ao criar operador IAM: ${err.message}`, 'danger');
    }
  });

  document.getElementById('form-mfa-verify')?.addEventListener('submit', async e => {
    e.preventDefault();
    try {
      await ApiClient.verifyMfa({ token: document.getElementById('modal-mfa-token').value.trim() });
      AppState.currentUser.mfaVerified = true;
      closeModal('modal-mfa-setup');
      showStatusBanner('', 'ok');
      showToast('MFA TOTP verificado e ativado na sessão!', 'success');
      await initializeCompanySelector();
      await navigateTo(AppState.activeView);
    } catch (err) {
      showToast(`Erro na verificação MFA: ${err.message}`, 'danger');
    }
  });

  // NF-e Forms
  document.getElementById('nfe-process-form')?.addEventListener('submit', async e => {
    e.preventDefault();
    const files = document.getElementById('nfe-files-input').files;
    if (!files?.length) return;
    const fd = new FormData();
    Array.from(files).forEach(f => fd.append('files', f));
    try {
      const res = await ApiClient.request('/nfe/process', { method: 'POST', body: fd });
      renderNfeResults('Lote NF-e processado com sucesso', res);
      showToast('Lote NF-e processado!', 'success');
    } catch (err) {
      showToast(`NF-e: ${err.message}`, 'danger');
    }
  });

  document.getElementById('nfe-zips-form')?.addEventListener('submit', async e => {
    e.preventDefault();
    const fd = new FormData(e.target);
    try {
      const res = await ApiClient.request('/nfe/compare-zips', { method: 'POST', body: fd });
      renderNfeResults('Conciliação de Pacotes ZIP (Cliente × Portal)', res);
      showToast('Comparação de pacotes ZIP concluída!', 'success');
    } catch (err) {
      showToast(`Comparação ZIP: ${err.message}`, 'danger');
    }
  });

  document.getElementById('nfe-destination-form')?.addEventListener('submit', async e => {
    e.preventDefault();
    try {
      const res = await ApiClient.request('/nfe/destination', {
        method: 'POST',
        body: {
          ncm: document.getElementById('nfe-dest-ncm').value.trim(),
          destination: document.getElementById('nfe-dest-value').value,
        },
      });
      renderNfeResults('Destinação de mercadoria atualizada', res);
      showToast('Destinação atualizada!', 'success');
    } catch (err) {
      showToast(`NF-e Destinação: ${err.message}`, 'danger');
    }
  });

  document.getElementById('nfe-docs-form')?.addEventListener('submit', async e => {
    e.preventDefault();
    const fd = new FormData(e.target);
    try {
      const res = await ApiClient.request('/nfe/compare-documents', { method: 'POST', body: fd });
      renderNfeResults('Confronto Documental TXT × PDF', res);
      showToast('Confronto documental concluído!', 'success');
    } catch (err) {
      showToast(`Confronto TXT×PDF: ${err.message}`, 'danger');
    }
  });

  // Tax Audit Upload & Ledger Forms
  document.getElementById('tax-audit-upload-form')?.addEventListener('submit', async e => {
    e.preventDefault();
    const files = document.getElementById('tax-audit-upload-files').files;
    if (!files?.length) return;
    const fd = new FormData();
    fd.append('category', document.getElementById('tax-audit-upload-category').value);
    Array.from(files).forEach(f => fd.append('files', f));
    try {
      await ApiClient.request('/tax-audit/upload', { method: 'POST', body: fd });
      showToast('Peças fiscais enviadas para o workspace de auditoria!', 'success');
      await loadAuditData();
    } catch (err) {
      showToast(`Upload Auditoria: ${err.message}`, 'danger');
    }
  });

  document.getElementById('tax-audit-ledger-form')?.addEventListener('submit', async e => {
    e.preventDefault();
    try {
      await ApiClient.request('/tax-audit/ledger/period', {
        method: 'PUT',
        body: {
          start_date: document.getElementById('ledger-start-date').value,
          end_date: document.getElementById('ledger-end-date').value,
        },
      });
      showToast('Corte temporal do Livro Fiscal atualizado!', 'success');
      await loadAuditData();
    } catch (err) {
      showToast(`Período do Livro: ${err.message}`, 'danger');
    }
  });

  // Global Delegated Clicks & Changes
  document.addEventListener('click', async event => {
    const closeEl = event.target.closest('[data-close-modal]');
    if (closeEl) {
      closeModal(closeEl.dataset.closeModal);
      return;
    }

    const navViewEl = event.target.closest('[data-nav-view]');
    if (navViewEl) {
      await navigateTo(navViewEl.dataset.navView);
      return;
    }

    const switchCompEl = event.target.closest('[data-switch-company]');
    if (switchCompEl) {
      await handleCompanySwitch(switchCompEl.dataset.switchCompany, true);
      return;
    }

    const assignCompEl = event.target.closest('[data-assign-company]');
    if (assignCompEl) {
      await promptAssignAnalyst(assignCompEl.dataset.assignCompany);
      return;
    }

    const attachTaskEl = event.target.closest('[data-attach-task]');
    if (attachTaskEl) {
      await openAttachReceiptModal(attachTaskEl.dataset.attachTask, attachTaskEl.dataset.attachTitle);
      return;
    }

    const completeTaskEl = event.target.closest('[data-complete-task]');
    if (completeTaskEl) {
      await handleTaskStatusChange(completeTaskEl.dataset.completeTask, 'completed');
      return;
    }

    const docReceiptEl = event.target.closest('[data-doc-receipt]');
    if (docReceiptEl) {
      await inspectDocumentReceipt(docReceiptEl.dataset.docReceipt);
      return;
    }

    const docOcrEl = event.target.closest('[data-doc-ocr]');
    if (docOcrEl) {
      await navigateTo('ai');
      await runOcrExtractionDemo();
      return;
    }

    const approveBillEl = event.target.closest('[data-approve-bill]');
    if (approveBillEl) {
      await handleApproveBill(approveBillEl.dataset.approveBill);
      return;
    }

    const rejectBillEl = event.target.closest('[data-reject-bill]');
    if (rejectBillEl) {
      await handleRejectBill(rejectBillEl.dataset.rejectBill);
      return;
    }

    const remindBillEl = event.target.closest('[data-remind-bill]');
    if (remindBillEl) {
      await handleRemindBill(remindBillEl.dataset.remindBill);
      return;
    }

    const quickExpEl = event.target.closest('[data-quick-expense]');
    if (quickExpEl) {
      const accountId = document.getElementById('recon-bank-account-select')?.value;
      try {
        await ApiClient.quickReconcileExpense({
          company_id: AppState.activeCompanyId,
          bank_account_id: accountId,
          transaction_id: quickExpEl.dataset.quickExpense,
          expense_category: 'bank_fee',
          user_id: AppState.currentUser.id,
        });
        showToast('Tarifa bancária conciliada em 1-Click!', 'success');
        await loadReconciliationViewData();
      } catch (err) {
        showToast(err.message, 'danger');
      }
      return;
    }

    const confirmMatchEl = event.target.closest('[data-confirm-match-trx]');
    if (confirmMatchEl) {
      const accountId = document.getElementById('recon-bank-account-select')?.value;
      try {
        await ApiClient.confirmReconciliation({
          company_id: AppState.activeCompanyId,
          bank_account_id: accountId,
          transaction_id: confirmMatchEl.dataset.confirmMatchTrx,
          bill_ids: [confirmMatchEl.dataset.confirmMatchBill],
          user_id: AppState.currentUser.id,
        });
        showToast('Conciliação confirmada e título baixado no financeiro!', 'success');
        await loadReconciliationViewData();
      } catch (err) {
        showToast(`Conciliação: ${err.message}`, 'danger');
      }
      return;
    }

    const retryTxEl = event.target.closest('[data-retry-transmission]');
    if (retryTxEl) {
      try {
        await ApiClient.retryTransmission(retryTxEl.dataset.retryTransmission);
      } catch (err) {
        showToast(err.message, 'warning');
      }
      return;
    }

    const aiFeedbackEl = event.target.closest('[data-ai-feedback]');
    if (aiFeedbackEl && AppState.lastAiSuggestionId) {
      try {
        const res = await ApiClient.registerClassificationFeedback(AppState.lastAiSuggestionId, {
          decision: aiFeedbackEl.dataset.aiFeedback,
          reviewed_by: AppState.currentUser.id,
          counterparty_keyword: 'AWS CLOUD',
        });
        showToast(res.message || 'Feedback registrado no ciclo de aprendizado!', 'success');
      } catch (err) {
        showToast(err.message, 'danger');
      }
      return;
    }

    const confirmGuideEl = event.target.closest('[data-confirm-guide]');
    if (confirmGuideEl) {
      try {
        await ApiClient.confirmGuideReceipt(confirmGuideEl.dataset.confirmGuide, {
          company_id: AppState.activeCompanyId,
          document_id: confirmGuideEl.dataset.confirmGuide,
          user_id: AppState.currentUser.id,
        });
        showToast('Confirmação de recebimento da guia registrada com IP e carimbo UTC!', 'success');
        await loadPortalData();
      } catch (err) {
        showToast(err.message, 'danger');
      }
      return;
    }

    const replyTicketEl = event.target.closest('[data-reply-ticket]');
    if (replyTicketEl) {
      AppState.selectedTicketId = replyTicketEl.dataset.replyTicket;
      const box = document.getElementById('ticket-reply-box');
      const badge = document.getElementById('reply-ticket-id-badge');
      if (box) box.style.display = 'block';
      if (badge) badge.textContent = AppState.selectedTicketId;
      return;
    }

    const exportEl = event.target.closest('[data-nfse-export]');
    if (exportEl) {
      if (AppState.nfse.uploading) return;
      try {
        await ApiClient.download(`/nfse/export/${exportEl.dataset.nfseExport}`);
      } catch (error) {
        showToast(`Erro ao exportar NFS-e: ${error.message}`, 'danger');
      }
      return;
    }
    const noteActionEl = event.target.closest('[data-note-action]');
    if (noteActionEl) {
      const key = noteActionEl.dataset.noteKey;
      const action = noteActionEl.dataset.noteAction;
      if (action === 'openNoteDetail') openNoteDetail(key);
      if (action === 'downloadSingleJson') downloadSingleJson(key);
      if (action === 'deleteNote') await deleteNote(key);
      return;
    }

    const auditTabEl = event.target.closest('[data-audit-tab]');
    if (auditTabEl) {
      switchAuditTab(auditTabEl.dataset.auditTab);
      return;
    }

    const nfseFilterEl = event.target.closest('[data-nfse-filter]');
    if (nfseFilterEl) {
      AppState.taxAudit.currentNfseFilter = nfseFilterEl.dataset.nfseFilter;
      document.querySelectorAll('[data-nfse-filter]').forEach(b => b.classList.toggle('active', b === nfseFilterEl));
      filterAuditNfseList();
      return;
    }

    const actionEl = event.target.closest('[data-action]');
    if (actionEl) {
      const act = actionEl.dataset.action;
      if (act === 'generateMonthlyTasksBatch') await generateMonthlyTasksBatch();
      if (act === 'openBatchRequestModal') openModal('modal-batch-request');
      if (act === 'openCreateCompanyModal') openModal('modal-create-company');
      if (act === 'openUploadDocModal') openModal('modal-upload-doc');
      if (act === 'openCreatePayableModal') openModal('modal-create-payable');
      if (act === 'openNewTicketModal') openModal('modal-new-ticket');
      if (act === 'openMfaSetupModal') await openMfaSetupModal();
      if (act === 'refreshWorkload') await refreshWorkload();
      if (act === 'loadCompaniesList') await loadCompaniesList();
      if (act === 'loadTasksList') await loadTasksList();
      if (act === 'requestMissingChecklist') await requestMissingChecklist();
      if (act === 'closeDocumentInspector') document.getElementById('document-inspector-card').style.display = 'none';
      if (act === 'loadAgingReport') await loadAgingReport();
      if (act === 'triggerOfxFileInput') document.getElementById('ofx-upload-input')?.click();
      if (act === 'verifyBankBalance') await verifyBankBalance();
      if (act === 'runMatchingSuggestions') await runMatchingSuggestions();
      if (act === 'loadAnalyticsViewData') await loadAnalyticsViewData();
      if (act === 'exportExecutivePdfReport') await exportExecutivePdfReport();
      if (act === 'checkCompanyCndStatus') await checkCompanyCndStatus();
      if (act === 'consolidateDctfwebAction') await consolidateDctfwebAction();
      if (act === 'runAnomalyScanAction') await runAnomalyScanAction();
      if (act === 'generateAiExecutiveSummary') await generateAiExecutiveSummary();
      if (act === 'runOcrExtractionDemo') await runOcrExtractionDemo();
      if (act === 'loadPortalData') await loadPortalData();
      if (act === 'sendTicketReplyMessage') {
        const msg = document.getElementById('ticket-message-input')?.value.trim();
        if (msg && AppState.selectedTicketId) {
          await ApiClient.postTicketMessage(AppState.selectedTicketId, {
            sender_id: AppState.currentUser.id,
            sender_role: 'accountant',
            body: msg,
            channel: 'portal',
          });
          document.getElementById('ticket-message-input').value = '';
          showToast('Resposta enviada ao cliente no chamado!', 'success');
        }
      }
      if (act === 'loadSecurityViewData') await loadSecurityViewData();
      if (act === 'recordUserLgpdConsent') {
        await ApiClient.submitPrivacyConsent({
          user_id: AppState.currentUser.id,
          term_version: 'v2026.1-LGPD',
          legal_basis: 'consent_and_regulatory_compliance',
        });
        showToast('Aceite de termos LGPD registrado com IP e carimbo UTC!', 'success');
      }
      if (act === 'createLgpdSubjectRequest') {
        await ApiClient.submitLgpdRequest({
          user_id: AppState.currentUser.id,
          request_type: document.getElementById('lgpd-request-type').value,
          details: document.getElementById('lgpd-request-details').value.trim() || 'Solicitação de titular Art. 18 LGPD',
        });
        showToast('Requisição de titular LGPD protocolada!', 'success');
      }
      if (act === 'loadSampleData') await loadSampleData();
      if (act === 'copyJsonToClipboard') copyJsonToClipboard();
      if (act === 'reloadDataFromDisk') await reloadDataFromDisk();
      if (act === 'printAuditReport') window.print();
      if (act === 'copyMarkdownReport') {
        const text = document.getElementById('official-report-content')?.textContent || '';
        navigator.clipboard?.writeText(text).then(() => showToast('Laudo Markdown copiado!', 'success'));
      }
    }
  });

  document.addEventListener('change', async event => {
    const statusSel = event.target.closest('[data-task-status-id]');
    if (statusSel) {
      await handleTaskStatusChange(statusSel.dataset.taskStatusId, statusSel.value);
    }
  });

  initializePdfToolsModule();
  checkInitialSession();
});
