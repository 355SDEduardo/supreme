/**
 * API Client for Portal Contabilidades & BPO Financeiro
 * Handles real-time communications with FastAPI endpoints.
 */

const API_BASE = window.location.origin;

class ApiClient {
  static async request(path, options = {}) {
    const url = `${API_BASE}${path}`;
    const headers = {
      ...options.headers,
    };

    // If body is json and not FormData
    if (options.body && !(options.body instanceof FormData) && typeof options.body === 'object') {
      headers['Content-Type'] = 'application/json';
      options.body = JSON.stringify(options.body);
    }

    try {
      const response = await fetch(url, { ...options, headers });
      
      if (!response.ok) {
        let errMessage = `Erro HTTP ${response.status}`;
        try {
          const errData = await response.json();
          errMessage = errData.detail || errData.message || JSON.stringify(errData);
        } catch (_) {}
        throw new Error(errMessage);
      }

      // Check if response is json or text
      const contentType = response.headers.get('content-type') || '';
      if (contentType.includes('application/json')) {
        return await response.json();
      }
      return await response.text();
    } catch (err) {
      console.error(`[API Error] ${options.method || 'GET'} ${path}:`, err);
      throw err;
    }
  }

  // Multiempresa
  static getCockpitSummary(organizationId = 'org-default-01') {
    return this.request(`/cockpit/companies/summary?organization_id=${encodeURIComponent(organizationId)}`);
  }

  static getCompanies(organizationId = 'org-default-01', taxRegime = '', search = '') {
    let url = `/companies?organization_id=${encodeURIComponent(organizationId)}&limit=100`;
    if (taxRegime) url += `&tax_regime=${encodeURIComponent(taxRegime)}`;
    if (search) url += `&search=${encodeURIComponent(search)}`;
    return this.request(url);
  }

  static createCompany(payload) {
    return this.request('/companies', { method: 'POST', body: payload });
  }

  static batchRequestDocuments(payload) {
    return this.request('/companies/batch/request-documents', { method: 'POST', body: payload });
  }

  static assignAnalyst(companyId, payload) {
    return this.request(`/companies/${encodeURIComponent(companyId)}/assign-analyst`, { method: 'POST', body: payload });
  }

  static switchCompanyContext(targetCompanyId) {
    return this.request('/auth/switch-company-context', {
      method: 'POST',
      body: { target_company_id: targetCompanyId }
    });
  }

  // Central de Obrigações & Tarefas
  static getTasks(params = {}) {
    const q = new URLSearchParams();
    if (params.company_id) q.set('company_id', params.company_id);
    if (params.competence) q.set('competence', params.competence);
    if (params.status) q.set('status', params.status);
    if (params.assigned_to) q.set('assigned_to', params.assigned_to);
    return this.request(`/tasks?${q.toString()}`);
  }

  static generateCompetenceTasks(payload) {
    return this.request('/tasks/generate-competence', { method: 'POST', body: payload });
  }

  static updateTaskStatus(taskId, payload) {
    return this.request(`/tasks/${encodeURIComponent(taskId)}/status`, { method: 'PATCH', body: payload });
  }

  static attachTaskReceipt(taskId, payload) {
    return this.request(`/tasks/${encodeURIComponent(taskId)}/attachments`, { method: 'POST', body: payload });
  }

  static getWorkload(competence = '') {
    const url = competence ? `/tasks/workload?competence=${encodeURIComponent(competence)}` : '/tasks/workload';
    return this.request(url);
  }

  // Gestão Inteligente de Documentos
  static getDocuments(params = {}) {
    const q = new URLSearchParams();
    if (params.company_id) q.set('company_id', params.company_id);
    if (params.competence) q.set('competence', params.competence);
    if (params.department) q.set('department', params.department);
    return this.request(`/documents?${q.toString()}`);
  }

  static uploadDocument(formData) {
    return this.request('/documents/upload', { method: 'POST', body: formData });
  }

  static getDocumentReceipt(documentId) {
    return this.request(`/documents/${encodeURIComponent(documentId)}/receipt`);
  }

  static requestChecklist(payload) {
    return this.request('/documents/checklists/request', { method: 'POST', body: payload });
  }

  // Contas a Pagar e Receber
  static getPayableApprovalQueue(companyId) {
    return this.request(`/bills/payable/approval-queue?company_id=${encodeURIComponent(companyId)}`);
  }

  static createPayableBill(payload) {
    return this.request('/bills/payable', { method: 'POST', body: payload });
  }

  static approveBill(billId, payload) {
    return this.request(`/bills/${encodeURIComponent(billId)}/approve`, { method: 'POST', body: payload });
  }

  static rejectBill(billId, payload) {
    return this.request(`/bills/${encodeURIComponent(billId)}/reject`, { method: 'POST', body: payload });
  }

  static getReceivableAging(companyId) {
    return this.request(`/bills/receivable/aging?company_id=${encodeURIComponent(companyId)}`);
  }

  static dispatchReminder(billId, payload) {
    return this.request(`/bills/${encodeURIComponent(billId)}/dispatch-reminder`, { method: 'POST', body: payload });
  }

  // Conciliação Bancária OFX
  static getUnmatchedTransactions(accountId) {
    return this.request(`/bank-accounts/${encodeURIComponent(accountId)}/transactions/unmatched`);
  }

  static getReconciliationSuggestions(accountId) {
    return this.request(`/reconciliations/suggest?account_id=${encodeURIComponent(accountId)}`, { method: 'POST' });
  }

  static confirmReconciliation(payload) {
    return this.request('/reconciliations/confirm', { method: 'POST', body: payload });
  }

  static quickReconcileExpense(payload) {
    return this.request('/reconciliations/quick-expense', { method: 'POST', body: payload });
  }

  static checkAccountBalance(accountId) {
    return this.request(`/bank-accounts/${encodeURIComponent(accountId)}/balance-check`);
  }

  // Analytics, DRE e Fluxo de Caixa
  static getDre(companyId, competence = '2026-09') {
    return this.request(`/analytics/companies/${encodeURIComponent(companyId)}/dre?competence=${encodeURIComponent(competence)}`);
  }

  static getCashFlow(companyId, days = 30) {
    return this.request(`/analytics/companies/${encodeURIComponent(companyId)}/cash-flow?days=${encodeURIComponent(days)}`);
  }

  static getKpis(companyId, competence = '2026-09') {
    return this.request(`/analytics/companies/${encodeURIComponent(companyId)}/kpis?competence=${encodeURIComponent(competence)}`);
  }

  static exportPdf(companyId, payload) {
    return this.request(`/analytics/companies/${encodeURIComponent(companyId)}/export-pdf`, { method: 'POST', body: payload });
  }

  // Automação e IA Contábil
  static extractDocumentOcr(documentId, rawText) {
    return this.request(`/api/v1/ai/documents/${encodeURIComponent(documentId)}/extract`, {
      method: 'POST',
      body: { raw_text: rawText }
    });
  }

  static suggestClassification(payload) {
    return this.request('/api/v1/ai/transactions/suggest-classification', { method: 'POST', body: payload });
  }

  static sendClassificationFeedback(suggestionId, payload) {
    return this.request(`/api/v1/ai/suggestions/${encodeURIComponent(suggestionId)}/feedback`, { method: 'POST', body: payload });
  }

  static getAnomalies(companyId) {
    return this.request(`/api/v1/ai/companies/${encodeURIComponent(companyId)}/anomalies`);
  }

  static scanAnomalies(companyId, payload) {
    return this.request(`/api/v1/ai/companies/${encodeURIComponent(companyId)}/scan-anomalies`, { method: 'POST', body: payload });
  }

  static generateExecutiveSummary(companyId, payload) {
    return this.request(`/api/v1/ai/companies/${encodeURIComponent(companyId)}/generate-executive-summary`, { method: 'POST', body: payload });
  }

  // Integrações Fiscais e Governamentais
  static enqueueFiscalTransmission(payload) {
    return this.request('/fiscal/transmissions/enqueue', { method: 'POST', body: payload });
  }

  static getFiscalStatus(transId) {
    return this.request(`/fiscal/transmissions/${encodeURIComponent(transId)}/status`);
  }

  static retryFiscal(transId) {
    return this.request(`/fiscal/transmissions/${encodeURIComponent(transId)}/retry`, { method: 'POST' });
  }

  static getCndStatus(companyId) {
    return this.request(`/fiscal/companies/${encodeURIComponent(companyId)}/cnd-status`);
  }

  static consolidateDctfweb(payload) {
    return this.request('/fiscal/dctfweb/consolidate', { method: 'POST', body: payload });
  }

  // Portal do Cliente
  static getTickets(companyId, status = '', category = '') {
    let url = `/portal/tickets?company_id=${encodeURIComponent(companyId)}`;
    if (status) url += `&status=${encodeURIComponent(status)}`;
    if (category) url += `&category=${encodeURIComponent(category)}`;
    return this.request(url);
  }

  static createTicket(payload) {
    return this.request('/portal/tickets', { method: 'POST', body: payload });
  }

  static postTicketMessage(ticketId, payload) {
    return this.request(`/portal/tickets/${encodeURIComponent(ticketId)}/messages`, { method: 'POST', body: payload });
  }

  static getAvailableGuides(companyId) {
    return this.request(`/portal/guides/available?company_id=${encodeURIComponent(companyId)}`);
  }

  static confirmGuideReceipt(docId, payload) {
    return this.request(`/portal/guides/${encodeURIComponent(docId)}/confirm-receipt`, { method: 'POST', body: payload });
  }

  // Segurança, LGPD & Certificados
  static setupMfa(userId, email) {
    return this.request(`/security/mfa/setup?user_id=${encodeURIComponent(userId)}&email=${encodeURIComponent(email)}`, { method: 'POST' });
  }

  static verifyMfa(payload) {
    return this.request('/security/mfa/verify', { method: 'POST', body: payload });
  }

  static getAuditLogs(params = {}) {
    const q = new URLSearchParams();
    if (params.company_id) q.set('company_id', params.company_id);
    if (params.limit) q.set('limit', params.limit);
    return this.request(`/security/audit-logs?${q.toString()}`);
  }

  static submitPrivacyConsent(payload) {
    return this.request('/security/privacy/consent', { method: 'POST', body: payload });
  }

  static submitLgpdRequest(payload) {
    return this.request('/security/lgpd/requests', { method: 'POST', body: payload });
  }

  static getCertificates(companyId = '') {
    const url = companyId ? `/certificates/expirations?company_id=${encodeURIComponent(companyId)}` : '/certificates/expirations';
    return this.request(url);
  }
}

window.ApiClient = ApiClient;
