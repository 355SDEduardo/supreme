"use strict";

const tabs = Array.from(document.querySelectorAll("[data-tab-target]"));
const panels = Array.from(document.querySelectorAll("[data-tab-panel]"));

function activateTab(targetId, updateUrl = true) {
  const target = document.getElementById(targetId);
  if (!target) {
    return;
  }
  tabs.forEach((tab) => {
    const selected = tab.dataset.tabTarget === targetId;
    tab.setAttribute("aria-selected", selected ? "true" : "false");
    tab.tabIndex = selected ? 0 : -1;
  });
  panels.forEach((panel) => {
    panel.hidden = panel.id !== targetId;
  });
  if (updateUrl) {
    const url = new URL(window.location.href);
    url.searchParams.set("tab", targetId);
    window.history.replaceState({}, "", url);
  }
}

tabs.forEach((tab, index) => {
  tab.addEventListener("click", () => activateTab(tab.dataset.tabTarget));
  tab.addEventListener("keydown", (event) => {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) {
      return;
    }
    event.preventDefault();
    let nextIndex = index;
    if (event.key === "ArrowLeft") nextIndex = (index - 1 + tabs.length) % tabs.length;
    if (event.key === "ArrowRight") nextIndex = (index + 1) % tabs.length;
    if (event.key === "Home") nextIndex = 0;
    if (event.key === "End") nextIndex = tabs.length - 1;
    tabs[nextIndex].focus();
    activateTab(tabs[nextIndex].dataset.tabTarget);
  });
});

const requestedTab = new URL(window.location.href).searchParams.get("tab");
activateTab(tabs.some((tab) => tab.dataset.tabTarget === requestedTab) ? requestedTab : "importacao", false);

document.querySelectorAll(".async-form").forEach((form) => {
  form.addEventListener("submit", () => {
    const button = form.querySelector("button[type='submit']");
    if (!button || button.disabled) {
      return;
    }
    button.disabled = true;
    button.setAttribute("aria-busy", "true");
    if (button.dataset.pendingLabel) {
      button.textContent = button.dataset.pendingLabel;
    }
  });
});

document.querySelectorAll("form[data-confirm]").forEach((form) => {
  form.addEventListener("submit", (event) => {
    if (!window.confirm(form.dataset.confirm)) {
      event.preventDefault();
    }
  });
});

const tableSortStatus = document.getElementById("table-sort-status");
const tableCollator = new Intl.Collator("pt-BR", {
  numeric: true,
  sensitivity: "base",
});

function normalizedText(value) {
  return value
    .trim()
    .toLocaleLowerCase("pt-BR")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "");
}

function localizedNumber(value) {
  const match = value.replace(/\u00a0/g, " ").match(/-?\d[\d.\s]*(?:,\d+)?/);
  if (!match) {
    return Number.NaN;
  }
  return Number(match[0].replace(/\s/g, "").replace(/\./g, "").replace(",", "."));
}

function sortableCellValue(cell, sortType) {
  const select = cell?.querySelector("select");
  const textValue = (select
    ? (select.value ? select.selectedOptions[0]?.textContent || "" : "")
    : (cell?.dataset.sortValue || cell?.textContent || "")).trim();
  if (!textValue || textValue === "—") {
    return { missing: true, value: "" };
  }
  if (sortType === "number") {
    const numberValue = localizedNumber(textValue);
    return { missing: Number.isNaN(numberValue), value: numberValue };
  }
  if (sortType === "date") {
    const timestamp = Date.parse(textValue);
    return { missing: Number.isNaN(timestamp), value: timestamp };
  }
  return { missing: false, value: normalizedText(textValue) };
}

function initializeSortableTable(table) {
  const body = table.tBodies[0];
  const headerRow = table.tHead?.rows[0];
  if (!body || !headerRow) {
    return;
  }

  const headers = Array.from(headerRow.cells);
  headers.forEach((header, columnIndex) => {
    const label = header.textContent.trim();
    const sortType = header.dataset.sortType ||
      (header.classList.contains("number") ? "number" : "text");
    const button = document.createElement("button");
    button.type = "button";
    button.className = "sort-button";
    button.textContent = label;
    button.setAttribute("aria-label", `Ordenar ${label} em ordem crescente`);
    button.title = `Ordenar ${label} em ordem crescente`;
    header.replaceChildren(button);
    header.classList.add("sortable-column");
    header.setAttribute("aria-sort", "none");

    button.addEventListener("click", () => {
      const direction = header.getAttribute("aria-sort") === "ascending"
        ? "descending"
        : "ascending";
      const directionFactor = direction === "ascending" ? 1 : -1;
      const rows = Array.from(
        body.querySelectorAll("tr:not([data-table-empty])")
      ).map((row, originalIndex) => ({ row, originalIndex }));

      rows.sort((left, right) => {
        const leftValue = sortableCellValue(left.row.cells[columnIndex], sortType);
        const rightValue = sortableCellValue(right.row.cells[columnIndex], sortType);
        if (leftValue.missing !== rightValue.missing) {
          return leftValue.missing ? 1 : -1;
        }
        if (leftValue.missing && rightValue.missing) {
          return left.originalIndex - right.originalIndex;
        }
        const comparison = sortType === "text"
          ? tableCollator.compare(leftValue.value, rightValue.value)
          : leftValue.value - rightValue.value;
        return comparison === 0
          ? left.originalIndex - right.originalIndex
          : comparison * directionFactor;
      });

      rows.forEach(({ row }) => body.append(row));
      body.querySelectorAll("[data-table-empty]").forEach((row) => body.append(row));
      headers.forEach((otherHeader) => {
        otherHeader.setAttribute("aria-sort", "none");
        const otherButton = otherHeader.querySelector(".sort-button");
        const otherLabel = otherButton?.textContent.trim() || "coluna";
        if (otherButton) {
          otherButton.setAttribute(
            "aria-label",
            `Ordenar ${otherLabel} em ordem crescente`
          );
          otherButton.title = `Ordenar ${otherLabel} em ordem crescente`;
        }
      });
      header.setAttribute("aria-sort", direction);
      const nextDirection = direction === "ascending" ? "decrescente" : "crescente";
      button.setAttribute("aria-label", `Ordenar ${label} em ordem ${nextDirection}`);
      button.title = `Ordenar ${label} em ordem ${nextDirection}`;

      if (tableSortStatus) {
        const tableName = table.dataset.tableName || "Tabela";
        const currentDirection = direction === "ascending" ? "crescente" : "decrescente";
        tableSortStatus.textContent =
          `${tableName}: ordenada por ${label}, em ordem ${currentDirection}.`;
      }
    });
  });
}

document.querySelectorAll(".sortable-table").forEach(initializeSortableTable);

document.querySelectorAll("[data-reconciliation-filter]").forEach((input) => {
  const table = document.getElementById(input.dataset.reconciliationFilter);
  const count = document.getElementById(`${table.id}-count`);
  input.addEventListener("input", () => {
    const query = normalizedText(input.value);
    const rows = Array.from(table.querySelectorAll("tbody tr:not([data-table-empty])"));
    let visible = 0;
    rows.forEach((row) => {
      row.hidden = !normalizedText(row.textContent).includes(query);
      if (!row.hidden) visible += 1;
    });
    table.querySelector("[data-table-empty]").hidden = visible !== 0;
    count.textContent = `${visible} de ${rows.length} nota(s)`;
  });
});

const filters = document.getElementById("product-filters");
const productTable = document.getElementById("products-table");
const productCount = document.getElementById("product-count");
const productExport = document.getElementById("products-export");
const clearFilters = document.getElementById("clear-filters");
const activeFilterCount = document.getElementById("active-filter-count");
const activeFilters = document.getElementById("active-filters");
const activeFilterChips = document.getElementById("active-filter-chips");
const productFilterEmpty = document.getElementById("product-filter-empty");
const filterDefinitions = [
  { id: "filter-note", parameter: "nota", label: "Nota" },
  { id: "filter-operacao", parameter: "operacao", label: "Operação" },
  { id: "filter-cfop", parameter: "cfop", label: "CFOP" },
  { id: "filter-cst", parameter: "cst", label: "CST / CSOSN" },
  { id: "filter-status", parameter: "status", label: "Status" },
  { id: "filter-query", parameter: "q", label: "Pesquisa" },
];

function currentProductFilters() {
  return filterDefinitions.map((definition) => {
    const field = document.getElementById(definition.id);
    return { ...definition, field, value: field?.value.trim() || "" };
  });
}

function filterDisplayValue(filter) {
  if (filter.field?.tagName === "SELECT") {
    return filter.field.selectedOptions[0]?.textContent.trim() || filter.value;
  }
  return filter.value;
}

function renderActiveProductFilters(filterValues) {
  if (!activeFilters || !activeFilterChips || !activeFilterCount || !clearFilters) {
    return;
  }
  const selectedFilters = filterValues.filter((filter) => filter.value);
  activeFilterChips.replaceChildren();
  selectedFilters.forEach((filter) => {
    const chip = document.createElement("button");
    const displayValue = filterDisplayValue(filter);
    chip.type = "button";
    chip.className = "filter-chip";
    chip.textContent = `${filter.label}: ${displayValue} ×`;
    chip.setAttribute(
      "aria-label",
      `Remover filtro ${filter.label}: ${displayValue}`
    );
    chip.addEventListener("click", () => {
      filter.field.value = "";
      applyProductFilters();
      filter.field.focus();
    });
    activeFilterChips.append(chip);
  });
  activeFilters.hidden = selectedFilters.length === 0;
  clearFilters.disabled = selectedFilters.length === 0;
  activeFilterCount.textContent = selectedFilters.length === 0
    ? "Nenhum filtro ativo."
    : `${selectedFilters.length} filtro(s) ativo(s).`;
}

function syncProductFilterUrl(filterValues) {
  const url = new URL(window.location.href);
  filterValues.forEach((filter) => {
    if (filter.value) {
      url.searchParams.set(filter.parameter, filter.value);
    } else {
      url.searchParams.delete(filter.parameter);
    }
  });
  window.history.replaceState({}, "", url);
}

function updateProductExport(filterValues) {
  if (!productExport) {
    return;
  }
  if (!productExport.dataset.baseUrl) {
    productExport.dataset.baseUrl = productExport.href;
  }
  const url = new URL(productExport.dataset.baseUrl, window.location.href);
  filterValues.forEach((filter) => {
    if (filter.value) {
      url.searchParams.set(filter.parameter, filter.value);
    }
  });
  productExport.href = url.toString();
}

function applyProductFilters(updateUrl = true) {
  if (!filters || !productTable) {
    return;
  }
  const filterValues = currentProductFilters();
  const values = Object.fromEntries(
    filterValues.map((filter) => [filter.parameter, filter.value])
  );
  const query = normalizedText(values.q);
  const rows = Array.from(
    productTable.querySelectorAll("tbody tr:not([data-table-empty])")
  );
  let visible = 0;

  rows.forEach((row) => {
    const matchesStatus =
      !values.status ||
      (values.status === "applicable"
        ? row.dataset.applicable === "yes"
        : row.dataset.registration === values.status);
    const matches =
      (!values.nota || row.dataset.note === values.nota) &&
      (!values.operacao || row.dataset.cfop?.startsWith(
        values.operacao === "estadual" ? "5" : "6"
      )) &&
      (!values.cfop || row.dataset.cfop === values.cfop) &&
      (!values.cst || row.dataset.cst === values.cst) &&
      matchesStatus &&
      (!query || normalizedText(row.dataset.search || "").includes(query));
    row.hidden = !matches;
    if (matches) {
      visible += 1;
    }
  });

  const hasActiveFilters = filterValues.some((filter) => filter.value);
  if (productCount) {
    productCount.textContent = hasActiveFilters
      ? `${visible} de ${rows.length} produto(s) visível(is)`
      : `${rows.length} produto(s)`;
  }
  if (productFilterEmpty) {
    productFilterEmpty.hidden = visible !== 0;
    const message = productFilterEmpty.cells[0];
    if (message) {
      message.textContent = hasActiveFilters
        ? "Nenhum produto corresponde aos filtros. Remova um filtro ou ajuste a pesquisa."
        : "Nenhum produto foi encontrado nas notas processadas.";
    }
  }
  renderActiveProductFilters(filterValues);
  updateProductExport(filterValues);
  if (updateUrl) {
    syncProductFilterUrl(filterValues);
  }
}

function restoreProductFiltersFromUrl() {
  const parameters = new URL(window.location.href).searchParams;
  currentProductFilters().forEach((filter) => {
    const requestedValue = parameters.get(filter.parameter) || "";
    if (filter.field?.tagName === "SELECT") {
      const optionExists = Array.from(filter.field.options).some(
        (option) => option.value === requestedValue
      );
      filter.field.value = optionExists ? requestedValue : "";
    } else if (filter.field) {
      filter.field.value = requestedValue;
    }
  });
}

if (filters) {
  let pendingFilterFrame = 0;
  const scheduleProductFilters = () => {
    window.cancelAnimationFrame(pendingFilterFrame);
    pendingFilterFrame = window.requestAnimationFrame(() => applyProductFilters());
  };
  filters.addEventListener("input", scheduleProductFilters);
  filters.addEventListener("change", scheduleProductFilters);
  filters.addEventListener("submit", (event) => {
    event.preventDefault();
    window.cancelAnimationFrame(pendingFilterFrame);
    applyProductFilters();
  });
  clearFilters?.addEventListener("click", () => {
    filters.reset();
    applyProductFilters();
    document.getElementById("filter-query")?.focus();
  });
  restoreProductFiltersFromUrl();
  applyProductFilters(false);
}

function destinationDialogElement() {
  const existing = document.getElementById("destination-dialog");
  if (existing) return existing;

  const dialog = document.createElement("dialog");
  dialog.id = "destination-dialog";
  dialog.setAttribute("aria-labelledby", "destination-dialog-title");
  dialog.setAttribute("aria-describedby", "destination-dialog-message");
  const form = document.createElement("form");
  form.method = "dialog";
  const title = document.createElement("h3");
  title.id = "destination-dialog-title";
  title.textContent = "Aplicar destinação aos produtos com o mesmo NCM?";
  const message = document.createElement("p");
  message.id = "destination-dialog-message";
  const actions = document.createElement("div");
  actions.className = "destination-dialog-actions";
  [
    ["all", "Aplicar a todos", "button button-primary"],
    ["one", "Somente este produto", "button button-secondary"],
    ["cancel", "Voltar", "button button-secondary"],
  ].forEach(([value, label, className]) => {
    const button = document.createElement("button");
    button.type = "submit";
    button.value = value;
    button.className = className;
    button.textContent = label;
    if (value === "one") button.autofocus = true;
    actions.append(button);
  });
  form.append(title, message, actions);
  dialog.append(form);
  document.body.append(dialog);
  return dialog;
}

function requestDestinationScope(destination, ncm, otherCount) {
  const destinationDialog = destinationDialogElement();
  if (!destinationDialog.showModal) {
    return Promise.resolve(window.confirm(
      `Aplicar “${destination}” também aos outros ${otherCount} produtos com NCM ${ncm}?`
    ) ? "all" : "one");
  }
  const message = document.getElementById("destination-dialog-message");
  const productLabel = otherCount === 1 ? "outro produto" : "outros produtos";
  message.textContent = `Aplicar “${destination}” também a ${otherCount} ${productLabel} com NCM ${ncm}?`;
  destinationDialog.returnValue = "cancel";
  return new Promise((resolve) => {
    destinationDialog.addEventListener("close", () => {
      resolve(destinationDialog.returnValue);
    }, { once: true });
    destinationDialog.showModal();
  });
}

productTable?.addEventListener("change", async (event) => {
  const select = event.target;
  if (!(select instanceof HTMLSelectElement) || !select.classList.contains("destination-select")) {
    return;
  }
  const row = select.closest("tr");
  const status = document.getElementById("destination-status");
  const previousValue = select.dataset.savedValue || "";
  const destination = select.value;
  const ncm = row.dataset.ncm;
  const matchingRows = ncm
    ? Array.from(productTable.querySelectorAll("tbody tr[data-ncm]")).filter(
      (candidate) => candidate.dataset.ncm === ncm
    )
    : [];
  const otherCount = matchingRows.filter((candidate) => candidate !== row).length;
  const scope = otherCount > 0
    ? await requestDestinationScope(destination, ncm, otherCount)
    : "one";
  select.focus();
  if (scope === "cancel") {
    select.value = previousValue;
    if (status) status.textContent = "Alteração de destinação cancelada.";
    return;
  }
  const applySameNcm = scope === "all";
  const lockedSelects = matchingRows.length
    ? matchingRows.map((candidate) => candidate.querySelector(".destination-select"))
    : [select];
  const body = new URLSearchParams({
    csrf_token: productTable.dataset.csrfToken,
    note_index: row.dataset.noteIndex,
    product_index: row.dataset.productIndex,
    note_key: row.dataset.noteKey,
    item: row.dataset.item,
    destinacao: destination,
    aplicar_ncm: applySameNcm ? "1" : "0",
  });
  lockedSelects.forEach((currentSelect) => { currentSelect.disabled = true; });
  if (status) status.textContent = "Salvando destinação…";
  try {
    const response = await fetch(productTable.dataset.destinationUrl, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body,
    });
    if (!response.ok) throw new Error("Falha ao salvar");
    const updatedSelects = applySameNcm ? lockedSelects : [select];
    updatedSelects.forEach((currentSelect) => {
      currentSelect.value = destination;
      currentSelect.dataset.savedValue = destination;
    });
    if (status) status.textContent = applySameNcm
      ? `Destinação salva para ${updatedSelects.length} produtos com NCM ${ncm}.`
      : `Destinação salva para o item ${row.dataset.item} da NF-e ${row.dataset.note}.`;
  } catch {
    select.value = previousValue;
    if (status) status.textContent = "Não foi possível salvar a destinação. Tente novamente ou atualize a página.";
  } finally {
    lockedSelects.forEach((currentSelect) => { currentSelect.disabled = false; });
  }
});

// NFS-e upload: native file input also provides a keyboard-accessible fallback.
const nfseDropZone = document.getElementById("drop-zone-nfse");
const nfseFileInput = document.getElementById("arquivos_nfse");
const nfseFileCount = document.getElementById("nfse-file-count");
if (nfseDropZone && nfseFileInput) {
  const showNfseFiles = () => {
    nfseFileCount.textContent = `${nfseFileInput.files.length} arquivo(s) selecionado(s).`;
  };
  nfseFileInput.addEventListener("change", showNfseFiles);
  nfseDropZone.addEventListener("dragover", (event) => {
    event.preventDefault();
    nfseDropZone.classList.add("nfse-dragging");
  });
  nfseDropZone.addEventListener("dragleave", () => nfseDropZone.classList.remove("nfse-dragging"));
  nfseDropZone.addEventListener("drop", (event) => {
    event.preventDefault();
    nfseDropZone.classList.remove("nfse-dragging");
    if (event.dataTransfer?.files.length) {
      nfseFileInput.files = event.dataTransfer.files;
      showNfseFiles();
    }
  });
}
