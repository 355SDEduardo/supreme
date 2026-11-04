/**
 * Supreme — Plataforma Contábil Unificada
 * Unified API Client for the 14 FastAPI Microservices via BFF Gateway (:8080)
 * Preserves HttpOnly cookie session, X-Supreme-CSRF: 1 on mutations, and X-Correlation-ID.
 */

(function () {
  const nativeFetch = window.fetch.bind(window);
  const MUTATING_METHODS = new Set(['POST', 'PUT', 'PATCH', 'DELETE']);

  function generateCorrelationId() {
    if (window.crypto && typeof window.crypto.randomUUID === 'function') {
      return window.crypto.randomUUID();
    }
    return 'corr-' + Date.now() + '-' + Math.random().toString(16).slice(2, 10);
  }

  // Ensure every same-origin mutating fetch automatically carries X-Supreme-CSRF: 1
  window.fetch = function (input, init = {}) {
    const method = String(init.method || (input && input.method) || 'GET').toUpperCase();
    const urlStr = typeof input === 'string' ? input : (input && input.url) || '';
    const isSameOrigin = !urlStr.startsWith('http://') && !urlStr.startsWith('https://') || urlStr.startsWith(window.location.origin);

    if (isSameOrigin) {
      const headers = new Headers(init.headers || (input instanceof Request ? input.headers : undefined) || {});
      if (MUTATING_METHODS.has(method) && !headers.has('X-Supreme-CSRF')) {
        headers.set('X-Supreme-CSRF', '1');
      }
      if (!headers.has('X-Correlation-ID')) {
        headers.set('X-Correlation-ID', generateCorrelationId());
      }
      init = {
        ...init,
        credentials: init.credentials || 'same-origin',
        headers,
      };
    }
    return nativeFetch(input, init);
  };

  const API_BASE = '/api/v1';

  const ApiClient = {
    onUnauthorized: null,
    nfseWorkspace: null,
    nfseWorkspacePending: null,
    nfseGeneration: 0,

    async nfseEndpoint(endpoint) {
      if (!/^\/(api\/v1\/)?nfse\//.test(endpoint) || endpoint.includes('/nfse/workspaces')) return endpoint;
      const generation = this.nfseGeneration;
      if (!this.nfseWorkspacePending && !this.nfseWorkspace) {
        this.nfseWorkspacePending = this.request('/nfse/workspaces', { method: 'POST' })
          .then(result => {
            if (generation === this.nfseGeneration) this.nfseWorkspace = result.workspace;
            else void this.request(`/nfse/workspaces/${encodeURIComponent(result.workspace)}`, { method: 'DELETE' }).catch(() => {});
          }).finally(() => {
            if (generation === this.nfseGeneration) this.nfseWorkspacePending = null;
          });
      }
      await this.nfseWorkspacePending;
      if (generation !== this.nfseGeneration) throw new Error('Contexto de NFS-e alterado. Reabra o módulo.');
      return `${endpoint}${endpoint.includes('?') ? '&' : '?'}workspace=${encodeURIComponent(this.nfseWorkspace)}`;
    },

    async resetNfseWorkspace() {
      const workspace = this.nfseWorkspace;
      this.nfseGeneration += 1;
      this.nfseWorkspace = null;
      this.nfseWorkspacePending = null;
      if (workspace) {
        try { await this.request(`/nfse/workspaces/${encodeURIComponent(workspace)}`, { method: 'DELETE' }); }
        catch (_) { /* The server also expires abandoned workspaces. */ }
      }
    },

    async request(endpoint, options = {}) {
      const nfseGeneration = this.nfseGeneration;
      endpoint = await this.nfseEndpoint(endpoint);
      const url = endpoint.startsWith('http') || endpoint.startsWith('/api/')
        ? endpoint
        : `${API_BASE}${endpoint}`;
      const method = String(options.method || 'GET').toUpperCase();
      const headers = {
        Accept: 'application/json',
        'X-Correlation-ID': generateCorrelationId(),
        ...(options.headers || {}),
      };

      if (MUTATING_METHODS.has(method)) {
        headers['X-Supreme-CSRF'] = '1';
      }

      if (!(options.body instanceof FormData) && options.body && typeof options.body === 'object') {
        headers['Content-Type'] = 'application/json';
        options.body = JSON.stringify(options.body);
      }

      const response = await nativeFetch(url, {
        ...options,
        method,
        credentials: 'same-origin',
        headers,
      });
      if (url.includes('/nfse/') && !url.includes('/nfse/workspaces') && nfseGeneration !== this.nfseGeneration) {
        throw new Error('Contexto de NFS-e alterado. Reabra o módulo.');
      }

      if (response.status === 401 && !url.endsWith('/security/auth/token') && !url.endsWith('/platform/session')) {
        if (typeof this.onUnauthorized === 'function') {
          this.onUnauthorized();
        }
      }

      if (!response.ok) {
        let errorDetail = `Erro HTTP ${response.status}`;
        try {
          const errJson = await response.json();
          if (typeof errJson.detail === 'string') {
            errorDetail = errJson.detail;
          } else if (Array.isArray(errJson.detail)) {
            errorDetail = errJson.detail.map(e => `${(e.loc || []).slice(-1)[0] || 'campo'}: ${e.msg}`).join('; ');
          } else if (errJson.detail) {
            errorDetail = JSON.stringify(errJson.detail);
          }
        } catch (_) {
          const text = await response.text().catch(() => '');
          if (text) errorDetail = text;
        }
        const error = new Error(errorDetail);
        error.status = response.status;
        throw error;
      }

      const contentType = response.headers.get('content-type') || '';
      if (contentType.includes('application/json')) {
        return await response.json();
      }
      return await response.text();
    },

    async download(endpoint, filenameFallback = 'arquivo.bin', options = {}) {
      const generation = this.nfseGeneration;
      endpoint = await this.nfseEndpoint(endpoint);
      const url = endpoint.startsWith('http') || endpoint.startsWith('/api/')
        ? endpoint
        : `${API_BASE}${endpoint}`;
      const method = String(options.method || 'GET').toUpperCase();
      const headers = {
        'X-Correlation-ID': generateCorrelationId(),
        ...(options.headers || {}),
      };
      if (MUTATING_METHODS.has(method)) {
        headers['X-Supreme-CSRF'] = '1';
      }
      if (!(options.body instanceof FormData) && options.body && typeof options.body === 'object') {
        headers['Content-Type'] = 'application/json';
        options.body = JSON.stringify(options.body);
      }

      const response = await nativeFetch(url, {
        ...options,
        method,
        credentials: 'same-origin',
        headers,
      });

      if (!response.ok) {
        let errorDetail = `Erro HTTP ${response.status}`;
        try {
          const errJson = await response.json();
          errorDetail = errJson.detail || errorDetail;
        } catch (_) {}
        throw new Error(errorDetail);
      }

      const blob = await response.blob();
      if (url.includes('/nfse/') && generation !== this.nfseGeneration) {
        throw new Error('Contexto de NFS-e alterado. Refaça a exportação.');
      }
      const disp = response.headers.get('content-disposition') || '';
      const match = disp.match(/filename\*?=(?:UTF-8'')?["']?([^"';]+)["']?/i);
      const filename = match ? decodeURIComponent(match[1]) : filenameFallback;

      const objectUrl = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = objectUrl;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
      return { filename, size: blob.size };
    },

    // =========================================================================
    // PLATFORM & SESSION (Gateway + MS-01: svc-security-iam)
    // =========================================================================
    login(payload) {
      return this.request('/security/auth/token', { method: 'POST', body: payload });
    },
    logout() {
      return this.request('/platform/logout', { method: 'POST' });
    },
    getSession() {
      return this.request('/platform/session');
    },
    getPlatformHealth() {
      return this.request('/platform/health');
    },
    createUser(payload) {
      return this.request('/security/auth/users', { method: 'POST', body: payload });
    },

    // =========================================================================
    // FEATURE 09: GESTÃO MULTIEMPRESA (MS-02: svc-companies)
    // =========================================================================
    getCockpitSummary(competence) {
      const q = competence ? `?competence=${encodeURIComponent(competence)}` : '';
      return this.request(`/cockpit/companies/summary${q}`);
    },
    listCompanies(params = {}) {
      const clean = {};
      Object.entries(params).forEach(([k, v]) => {
        if (v !== undefined && v !== null && v !== '' && k !== 'organization_id') {
          clean[k] = v;
        }
      });
      const qs = new URLSearchParams(clean).toString();
      return this.request(`/companies${qs ? '?' + qs : ''}`);
    },
    createCompany(data) {
      return this.request('/companies', { method: 'POST', body: data });
    },
    batchRequestDocuments(payload) {
      return this.request('/companies/batch/request-documents', { method: 'POST', body: payload });
    },
    assignAnalyst(companyId, payload) {
      return this.request(`/companies/${encodeURIComponent(companyId)}/assign-analyst`, {
        method: 'POST',
        body: payload,
      });
    },
    switchCompanyContext(targetCompanyId) {
      return this.request('/auth/switch-company-context', {
        method: 'POST',
        body: { target_company_id: targetCompanyId },
      });
    },

    // =========================================================================
    // FEATURE 01: CENTRAL DE OBRIGAÇÕES, TAREFAS E PRAZOS (MS-03: svc-obligations)
    // =========================================================================
    getCompanyObligations(companyId) {
      return this.request(`/companies/${encodeURIComponent(companyId)}/obligations`);
    },
    generateCompetenceTasks(payload) {
      return this.request('/tasks/generate-competence', { method: 'POST', body: payload });
    },
    listTasks(params = {}) {
      const clean = {};
      Object.entries(params).forEach(([k, v]) => {
        if (v !== undefined && v !== null && v !== '') clean[k] = v;
      });
      const qs = new URLSearchParams(clean).toString();
      return this.request(`/tasks${qs ? '?' + qs : ''}`);
    },
    updateTaskStatus(taskId, payload) {
      return this.request(`/tasks/${encodeURIComponent(taskId)}/status`, {
        method: 'PATCH',
        body: payload,
      });
    },
    attachTaskReceipt(taskId, payload) {
      return this.request(`/tasks/${encodeURIComponent(taskId)}/attachments`, {
        method: 'POST',
        body: payload,
      });
    },
    getWorkloadReport(competence) {
      const q = competence ? `?competence=${encodeURIComponent(competence)}` : '';
      return this.request(`/tasks/workload${q}`);
    },

    // =========================================================================
    // FEATURE 02: GESTÃO INTELIGENTE DE DOCUMENTOS (MS-04: svc-documents)
    // =========================================================================
    uploadDocument(formData) {
      return this.request('/documents/upload', { method: 'POST', body: formData });
    },
    listDocuments(params = {}) {
      const clean = {};
      Object.entries(params).forEach(([k, v]) => {
        if (v !== undefined && v !== null && v !== '') clean[k] = v;
      });
      const qs = new URLSearchParams(clean).toString();
      return this.request(`/documents${qs ? '?' + qs : ''}`);
    },
    getDocumentReceipt(documentId) {
      return this.request(`/documents/${encodeURIComponent(documentId)}/receipt`);
    },
    previewDocument(documentId) {
      return this.request(`/documents/${encodeURIComponent(documentId)}/preview`);
    },
    requestDocumentChecklist(payload) {
      return this.request('/documents/checklists/request', { method: 'POST', body: payload });
    },

    // =========================================================================
    // FEATURE 03: CONCILIAÇÃO BANCÁRIA AUTOMÁTICA (MS-09: svc-bank-reconciliation)
    // =========================================================================
    listBankAccounts() {
      return this.request('/bank-accounts');
    },
    createBankAccount(payload) {
      return this.request('/bank-accounts', { method: 'POST', body: payload });
    },
    importOfxStatement(accountId, formData) {
      return this.request(`/bank-accounts/${encodeURIComponent(accountId)}/statements/import-ofx`, {
        method: 'POST',
        body: formData,
      });
    },
    getUnmatchedTransactions(accountId) {
      return this.request(`/bank-accounts/${encodeURIComponent(accountId)}/transactions/unmatched`);
    },
    getMatchingSuggestions(accountId) {
      return this.request(`/reconciliations/suggest?account_id=${encodeURIComponent(accountId)}`, {
        method: 'POST',
      });
    },
    confirmReconciliation(payload) {
      return this.request('/reconciliations/confirm', { method: 'POST', body: payload });
    },
    quickReconcileExpense(payload) {
      return this.request('/reconciliations/quick-expense', { method: 'POST', body: payload });
    },
    getBalanceCheck(accountId) {
      return this.request(`/bank-accounts/${encodeURIComponent(accountId)}/balance-check`);
    },

    // =========================================================================
    // FEATURE 04: CONTAS A PAGAR E RECEBER (MS-10: svc-finance-bpo)
    // =========================================================================
    createPayableBill(payload) {
      const endpoint = payload.type === 'receivable' ? '/bills/receivable' : '/bills/payable';
      return this.request(endpoint, { method: 'POST', body: payload });
    },
    listBills() {
      return this.request('/bills');
    },
    getApprovalQueue(companyId) {
      return this.request(`/bills/payable/approval-queue?company_id=${encodeURIComponent(companyId)}`);
    },
    approveBill(billId, payload) {
      return this.request(`/bills/${encodeURIComponent(billId)}/approve`, {
        method: 'POST',
        body: payload,
      });
    },
    rejectBill(billId, payload) {
      return this.request(`/bills/${encodeURIComponent(billId)}/reject`, {
        method: 'POST',
        body: payload,
      });
    },
    getAgingList(companyId) {
      return this.request(`/bills/receivable/aging?company_id=${encodeURIComponent(companyId)}`);
    },
    dispatchReminder(billId, payload) {
      return this.request(`/bills/${encodeURIComponent(billId)}/dispatch-reminder`, {
        method: 'POST',
        body: payload,
      });
    },

    // =========================================================================
    // FEATURE 05: INTEGRAÇÕES FISCAIS E GOVERNAMENTAIS (MS-11: svc-fiscal-gov)
    // =========================================================================
    enqueueTransmission(payload) {
      return this.request('/fiscal/transmissions/enqueue', { method: 'POST', body: payload });
    },
    getTransmissionStatus(transmissionId) {
      return this.request(`/fiscal/transmissions/${encodeURIComponent(transmissionId)}/status`);
    },
    retryTransmission(transmissionId) {
      return this.request(`/fiscal/transmissions/${encodeURIComponent(transmissionId)}/retry`, {
        method: 'POST',
      });
    },
    getCompanyCndStatus(companyId) {
      return this.request(`/fiscal/companies/${encodeURIComponent(companyId)}/cnd-status`);
    },
    consolidateDctfweb(payload) {
      return this.request('/fiscal/dctfweb/consolidate', { method: 'POST', body: payload });
    },

    // =========================================================================
    // FEATURE 06: PORTAL DO CLIENTE E COMUNICAÇÃO (MS-12: svc-client-portal)
    // =========================================================================
    createTicket(payload) {
      return this.request('/portal/tickets', { method: 'POST', body: payload });
    },
    listTickets(companyId, status = '') {
      const qs = new URLSearchParams({ company_id: companyId, ...(status ? { status } : {}) }).toString();
      return this.request(`/portal/tickets?${qs}`);
    },
    postTicketMessage(ticketId, payload) {
      return this.request(`/portal/tickets/${encodeURIComponent(ticketId)}/messages`, {
        method: 'POST',
        body: payload,
      });
    },
    publishGuide(payload) {
      return this.request('/portal/guides', { method: 'POST', body: payload });
    },
    listAvailableGuides(companyId) {
      return this.request(`/portal/guides/available?company_id=${encodeURIComponent(companyId)}`);
    },
    confirmGuideReceipt(documentId, payload) {
      return this.request(`/portal/guides/${encodeURIComponent(documentId)}/confirm-receipt`, {
        method: 'POST',
        body: payload,
      });
    },

    // =========================================================================
    // FEATURE 07: FLUXO DE CAIXA, DRE E DASHBOARDS (MS-13: svc-analytics-dre)
    // =========================================================================
    getDre(companyId, competence = '2026-09') {
      return this.request(`/analytics/companies/${encodeURIComponent(companyId)}/dre?competence=${encodeURIComponent(competence)}`);
    },
    getCashFlow(companyId, days = 30) {
      return this.request(`/analytics/companies/${encodeURIComponent(companyId)}/cash-flow?days=${encodeURIComponent(days)}`);
    },
    getKpis(companyId, competence = '2026-09') {
      return this.request(`/analytics/companies/${encodeURIComponent(companyId)}/kpis?competence=${encodeURIComponent(competence)}`);
    },
    exportExecutivePdf(companyId, payload) {
      return this.download(`/analytics/companies/${encodeURIComponent(companyId)}/export-pdf`, `DRE_${companyId}_${payload.competence}.pdf`, {
        method: 'POST',
        body: payload,
      });
    },

    // =========================================================================
    // FEATURE 08: AUTOMAÇÃO E IA CONTÁBIL (MS-14: svc-accounting-ai)
    // =========================================================================
    extractDocumentOcr(documentId, rawText) {
      return this.request(`/ai/documents/${encodeURIComponent(documentId)}/extract`, {
        method: 'POST',
        body: { raw_text: rawText },
      });
    },
    suggestClassification(payload) {
      return this.request('/ai/transactions/suggest-classification', {
        method: 'POST',
        body: payload,
      });
    },
    registerClassificationFeedback(suggestionId, payload) {
      return this.request(`/ai/suggestions/${encodeURIComponent(suggestionId)}/feedback`, {
        method: 'POST',
        body: payload,
      });
    },
    getAnomalies(companyId) {
      return this.request(`/ai/companies/${encodeURIComponent(companyId)}/anomalies`);
    },
    scanAnomalies(companyId, payload) {
      return this.request(`/ai/companies/${encodeURIComponent(companyId)}/scan-anomalies`, {
        method: 'POST',
        body: payload,
      });
    },
    generateExecutiveSummary(companyId, payload) {
      return this.request(`/ai/companies/${encodeURIComponent(companyId)}/generate-executive-summary`, {
        method: 'POST',
        body: payload,
      });
    },

    // =========================================================================
    // FEATURE 10: SEGURANÇA, LGPD E CERTIFICADOS (MS-01: svc-security-iam)
    // =========================================================================
    setupMfa() {
      return this.request('/security/mfa/setup', { method: 'POST' });
    },
    verifyMfa(payload) {
      return this.request('/security/mfa/verify', {
        method: 'POST',
        body: { token: payload.token },
      });
    },
    uploadCertificateVault(formData) {
      return this.request('/certificates/vault/upload', { method: 'POST', body: formData });
    },
    getExpiringCertificates(companyId = '') {
      const q = companyId ? `?company_id=${encodeURIComponent(companyId)}` : '';
      return this.request(`/certificates/expirations${q}`);
    },
    getAuditLogs(params = {}) {
      const clean = {};
      Object.entries(params).forEach(([k, v]) => {
        if (v !== undefined && v !== null && v !== '') clean[k] = v;
      });
      const qs = new URLSearchParams(clean).toString();
      return this.request(`/security/audit-logs${qs ? '?' + qs : ''}`);
    },
    submitPrivacyConsent(payload) {
      return this.request('/security/privacy/consent', { method: 'POST', body: payload });
    },
    submitLgpdRequest(payload) {
      return this.request('/security/lgpd/requests', { method: 'POST', body: payload });
    },
  };

  window.ApiClient = ApiClient;
  window.addEventListener('pagehide', () => {
    if (!ApiClient.nfseWorkspace) return;
    void nativeFetch(`/api/v1/nfse/workspaces/${encodeURIComponent(ApiClient.nfseWorkspace)}`, {
      method: 'DELETE', credentials: 'same-origin', keepalive: true,
      headers: { 'X-Supreme-CSRF': '1', 'X-Correlation-ID': generateCorrelationId() },
    }).catch(() => {}); // Abandoned workspaces are also removed by the server TTL.
  });
  window.addEventListener('pageshow', event => {
    if (event.persisted) window.location.reload();
  });
})();
