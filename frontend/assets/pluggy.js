/* Company-scoped configuration. Credentials only live in form fields until submitted. */
(() => {
  'use strict';
  const base = '/bank-accounts/open-finance';
  const state = { generation: 0, busy: false, controller: null, config: null };
  const el = id => document.getElementById(id);
  const authorized = () => Boolean(AppState.activeCompanyId && AppState.currentUser.mfaVerified
    && ['super_admin', 'supervisor'].includes(AppState.currentUser.role));

  function feedback(text, level = '') {
    el('pluggy-feedback').textContent = text;
    el('pluggy-feedback').className = `alert ${level}`;
  }

  function controls() {
    const ready = authorized() && !state.busy && state.config !== null;
    el('pluggy-fields').disabled = !ready;
    el('pluggy-reload').disabled = !authorized() || state.busy;
    el('pluggy-save').disabled = !ready || !state.config?.storage_available;
    el('pluggy-test').disabled = !ready || !state.config?.configured;
    el('pluggy-connectors-load').disabled = !ready || !state.config?.configured;
    el('pluggy-remove').disabled = !ready || state.config?.source !== 'company';
    el('pluggy-sandbox').disabled = !ready || !state.config?.sandbox_allowed;
    el('view-pluggy').setAttribute('aria-busy', String(state.busy));
  }

  function clearConnectors() {
    el('pluggy-connectors').replaceChildren();
    el('pluggy-connectors-summary').textContent = 'Consulte os bancos para verificar a disponibilidade atual.';
  }

  function render(config) {
    state.config = config;
    el('pluggy-company').textContent = AppState.activeCompanyName;
    el('pluggy-source').textContent = {
      none: 'Não configurada', environment: 'Credenciais do servidor', company: 'Credenciais desta empresa',
    }[config.source] || 'Indisponível';
    el('pluggy-updated').textContent = config.updated_at
      ? new Intl.DateTimeFormat('pt-BR', { dateStyle: 'short', timeStyle: 'short', timeZone: 'America/Sao_Paulo' }).format(new Date(config.updated_at)) + ' (Brasília)'
      : '—';
    el('pluggy-client-id').required = !config.configured;
    el('pluggy-client-secret').required = !config.configured;
    el('pluggy-id-help').textContent = config.configured
      ? `Identificador atual: ${config.client_id_masked}. Deixe em branco para manter. Ao trocar o ID, informe também o segredo.`
      : 'Informe o identificador da aplicação no Dashboard Pluggy.';
    el('pluggy-secret-help').textContent = config.configured
      ? 'Deixe em branco para manter o segredo atual. Um novo segredo substitui o anterior após validação.'
      : 'O segredo será criptografado no servidor e não será exibido novamente.';
    el('pluggy-sandbox').checked = config.allow_sandbox && config.sandbox_allowed;
  }

  async function operation(message, work) {
    if (state.busy || !authorized()) return;
    const generation = state.generation;
    const controller = new AbortController();
    state.controller = controller;
    state.busy = true;
    controls();
    feedback(message);
    let timedOut = false;
    const timer = setTimeout(() => { timedOut = true; controller.abort(); }, 30000);
    const request = async (path, options = {}) => {
      const response = await ApiClient.request(base + path, { ...options, signal: controller.signal });
      if (generation !== state.generation) throw new DOMException('Contexto alterado', 'AbortError');
      return response;
    };
    try {
      await work(request);
    } catch (error) {
      if (generation === state.generation) {
        feedback(timedOut
          ? 'A operação demorou mais que o esperado. Recarregue a configuração para conferir o resultado antes de tentar novamente.'
          : error.message || 'Não foi possível concluir. Tente novamente.', 'err');
      }
    } finally {
      clearTimeout(timer);
      if (generation === state.generation) {
        state.busy = false;
        state.controller = null;
        controls();
      }
    }
  }

  function reset() {
    state.generation += 1;
    state.controller?.abort();
    state.controller = null;
    state.busy = false;
    state.config = null;
    if (!el('pluggy-form')) return;
    el('pluggy-form').reset();
    el('pluggy-company').textContent = '—';
    el('pluggy-source').textContent = 'Não consultada';
    el('pluggy-updated').textContent = '—';
    el('pluggy-id-help').textContent = 'Informe o identificador da aplicação.';
    el('pluggy-secret-help').textContent = 'O segredo será criptografado no servidor e não será exibido novamente.';
    clearConnectors();
    controls();
  }

  async function refresh() {
    reset();
    el('pluggy-company').textContent = AppState.activeCompanyId ? AppState.activeCompanyName : 'Nenhuma empresa selecionada';
    if (!AppState.activeCompanyId) return feedback('Selecione uma empresa na barra superior.', 'warn');
    if (!AppState.currentUser.mfaVerified) return feedback('Conclua a verificação MFA para configurar a integração.', 'warn');
    if (!authorized()) return feedback('Somente administradores e supervisores podem configurar a API Pluggy.', 'warn');
    return operation('Carregando configuração…', async request => {
      const config = await request('/configuration');
      render(config);
      if (config.configuration_error) {
        feedback(config.configuration_error, 'warn');
      } else if (!config.storage_available) {
        feedback('O servidor precisa de uma chave de criptografia válida para salvar credenciais. Solicite a configuração ao responsável pela plataforma.', 'warn');
      } else {
        feedback(config.configured
          ? 'Configuração carregada. Use o teste para verificar a autenticação atual.'
          : 'Cadastre as credenciais da aplicação para habilitar a API nesta empresa.');
      }
    });
  }

  document.addEventListener('DOMContentLoaded', () => {
    if (!el('pluggy-form')) return;
    reset();
    el('pluggy-reload').addEventListener('click', refresh);
    el('pluggy-form').addEventListener('submit', event => {
      event.preventDefault();
      if (!state.config || !el('pluggy-form').reportValidity()) return;
      const clientId = el('pluggy-client-id').value.trim();
      const secret = el('pluggy-client-secret').value;
      if (clientId && !secret.trim()) {
        feedback('Informe também o Client Secret ao informar um Client ID.', 'warn');
        el('pluggy-client-secret').focus();
        return;
      }
      const body = { revision: state.config.revision, allow_sandbox: el('pluggy-sandbox').checked };
      if (clientId) body.client_id = clientId;
      if (secret) body.client_secret = secret;
      void operation('Validando credenciais com a Pluggy e salvando…', async request => {
        const config = await request('/configuration', { method: 'PUT', body });
        el('pluggy-form').reset();
        render(config);
        clearConnectors();
        feedback('Credenciais validadas e salvas para esta empresa.', 'ok');
      });
    });
    el('pluggy-test').addEventListener('click', () => operation('Testando a configuração salva…', async request => {
      const result = await request('/configuration/test', { method: 'POST' });
      feedback(`${result.message} Este teste usa as credenciais salvas, sem aplicar alterações do formulário.`, 'ok');
    }));
    el('pluggy-remove').addEventListener('click', () => {
      if (state.busy || state.config?.source !== 'company') return;
      if (!window.confirm(`Remover a configuração Pluggy de ${AppState.activeCompanyName}? A configuração do servidor será usada, se disponível. Nenhuma conexão bancária será excluída por esta ação.`)) return;
      const revision = state.config.revision;
      void operation('Removendo configuração da empresa…', async request => {
        const config = await request(`/configuration?revision=${revision}`, { method: 'DELETE' });
        el('pluggy-form').reset();
        render(config);
        clearConnectors();
        feedback('Configuração da empresa removida.', 'ok');
      });
    });
    el('pluggy-connectors-load').addEventListener('click', () => operation('Consultando bancos disponíveis…', async request => {
      clearConnectors();
      const connectors = await request('/connectors');
      for (const connector of [...connectors].sort((a, b) => a.name.localeCompare(b.name, 'pt-BR'))) {
        const item = document.createElement('li');
        const name = document.createElement('strong');
        name.textContent = connector.name;
        const detail = document.createElement('span');
        detail.textContent = `${connector.type === 'BUSINESS_BANK' ? 'Pessoa jurídica' : 'Pessoa física'}${connector.isSandbox ? ' · Sandbox' : ''}`;
        item.append(name, detail);
        el('pluggy-connectors').append(item);
      }
      el('pluggy-connectors-summary').textContent = connectors.length
        ? `${connectors.length} banco(s) disponível(is). A conexão depende de consentimento e da disponibilidade da instituição.`
        : 'Nenhum banco compatível está disponível para esta configuração.';
      feedback('Consulta de disponibilidade concluída.', 'ok');
    }));
  });

  window.PluggyConfiguration = { refresh, reset };
})();
