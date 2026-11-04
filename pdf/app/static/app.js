(() => {
    "use strict";

    const TOOL_IDS = ["mesclar", "dividir", "organizar", "girar", "reparar", "numerar"];
    const TOOL_TITLES = {
        mesclar: "Mesclar PDF",
        dividir: "Dividir PDF",
        organizar: "Organizar PDF",
        girar: "Girar PDF",
        reparar: "Reparar PDF",
        numerar: "Numerar páginas",
    };
    const controllers = new Map();
    const downloadUrls = new WeakMap();

    function createIcon(symbolId) {
        const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
        svg.setAttribute("aria-hidden", "true");
        const use = document.createElementNS("http://www.w3.org/2000/svg", "use");
        use.setAttribute("href", `#${symbolId}`);
        svg.append(use);
        return svg;
    }

    function formatFileSize(bytes) {
        if (!Number.isFinite(bytes) || bytes < 1) {
            return "0 KB";
        }

        const units = ["bytes", "KB", "MB", "GB"];
        const unitIndex = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
        const value = bytes / (1024 ** unitIndex);
        const maximumFractionDigits = unitIndex === 0 || value >= 10 ? 0 : 1;

        return `${new Intl.NumberFormat("pt-BR", { maximumFractionDigits }).format(value)} ${units[unitIndex]}`;
    }

    function isProbablyPdf(file) {
        return file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf");
    }

    async function hasPdfSignature(file) {
        try {
            const header = await file.slice(0, 5).arrayBuffer();
            return new TextDecoder("ascii").decode(header) === "%PDF-";
        } catch {
            return false;
        }
    }

    function revokeDownload(form) {
        const currentUrl = downloadUrls.get(form);
        if (currentUrl) {
            URL.revokeObjectURL(currentUrl);
            downloadUrls.delete(form);
        }
    }

    function setFormStatus(form, type, title, message, options = {}) {
        const status = form.querySelector("[data-form-status]");
        if (!status) {
            return null;
        }

        status.replaceChildren();
        status.hidden = false;
        status.className = `form-status is-${type}`;
        status.setAttribute("role", type === "error" ? "alert" : "status");

        const heading = document.createElement("strong");
        heading.textContent = title;
        const description = document.createElement("span");
        description.textContent = message;
        status.append(heading, description);

        if (options.downloadUrl && options.filename) {
            const link = document.createElement("a");
            link.href = options.downloadUrl;
            link.download = options.filename;
            link.append(createIcon("icon-download"), document.createTextNode("Baixar novamente"));
            status.append(document.createElement("br"), link);
            options.link = link;
        }

        if (options.focus) {
            status.focus({ preventScroll: true });
            status.scrollIntoView({ behavior: "smooth", block: "nearest" });
        }

        return options.link || null;
    }

    function clearFormStatus(form) {
        revokeDownload(form);
        const status = form.querySelector("[data-form-status]");
        if (!status) {
            return;
        }
        status.hidden = true;
        status.className = "form-status";
        status.replaceChildren();
        status.setAttribute("role", "status");
    }

    function makeIconButton(label, iconId, action, disabled = false, danger = false) {
        const button = document.createElement("button");
        button.type = "button";
        button.className = `icon-button${danger ? " danger" : ""}`;
        button.setAttribute("aria-label", label);
        button.dataset.action = action;
        button.disabled = disabled;
        button.append(createIcon(iconId));
        return button;
    }

    function initializeFilePicker(input) {
        const form = input.closest("form");
        const dropzone = document.querySelector(`[data-dropzone="${input.id}"]`);
        const section = document.querySelector(`[data-file-section="${input.id}"]`);
        const list = document.querySelector(`[data-file-list="${input.id}"]`);
        const count = section?.querySelector("[data-file-count]");
        let files = [];
        let selectionToken = 0;

        function notifyChange() {
            input.dispatchEvent(new CustomEvent("managed-files-change", {
                bubbles: true,
                detail: { files: [...files] },
            }));
        }

        function render() {
            list.replaceChildren();
            section.hidden = files.length === 0;

            if (count) {
                count.textContent = `${files.length} ${files.length === 1 ? "arquivo" : "arquivos"}`;
            }

            files.forEach((file, index) => {
                const item = document.createElement("li");
                item.className = "file-item";

                const order = document.createElement("span");
                order.className = "file-order";
                order.textContent = String(index + 1);

                const details = document.createElement("span");
                details.className = "file-details";
                const filename = document.createElement("strong");
                filename.textContent = file.name;
                filename.title = file.name;
                const size = document.createElement("small");
                size.textContent = formatFileSize(file.size);
                details.append(filename, size);

                const actions = document.createElement("span");
                actions.className = "file-actions";

                if (input.id === "merge-files") {
                    actions.append(
                        makeIconButton(`Mover ${file.name} para cima`, "icon-arrow-up", "up", index === 0),
                        makeIconButton(`Mover ${file.name} para baixo`, "icon-arrow-down", "down", index === files.length - 1),
                    );
                }

                actions.append(makeIconButton(`Remover ${file.name}`, "icon-trash", "remove", false, true));
                item.append(order, details, actions);

                actions.addEventListener("click", (event) => {
                    const button = event.target.closest("button[data-action]");
                    if (!button) {
                        return;
                    }
                    const action = button.dataset.action;
                    if (action === "up" && index > 0) {
                        [files[index - 1], files[index]] = [files[index], files[index - 1]];
                    } else if (action === "down" && index < files.length - 1) {
                        [files[index + 1], files[index]] = [files[index], files[index + 1]];
                    } else if (action === "remove") {
                        files.splice(index, 1);
                        if (files.length === 0) {
                            input.value = "";
                        }
                    }
                    clearFormStatus(form);
                    render();
                    notifyChange();
                });

                list.append(item);
            });
        }

        async function addFiles(fileList) {
            const token = ++selectionToken;
            const candidates = Array.from(fileList);
            if (candidates.length === 0) {
                return;
            }

            const checked = await Promise.all(candidates.map(async (file) => ({
                file,
                valid: isProbablyPdf(file) && await hasPdfSignature(file),
            })));

            if (token !== selectionToken) {
                return;
            }

            const validFiles = checked.filter((item) => item.valid).map((item) => item.file);
            const invalidFiles = checked.filter((item) => !item.valid).map((item) => item.file.name);

            if (input.multiple) {
                const existingKeys = new Set(files.map((file) => `${file.name}:${file.size}:${file.lastModified}`));
                for (const file of validFiles) {
                    const key = `${file.name}:${file.size}:${file.lastModified}`;
                    if (!existingKeys.has(key)) {
                        files.push(file);
                        existingKeys.add(key);
                    }
                }
            } else {
                files = validFiles.slice(0, 1);
            }

            render();
            notifyChange();

            if (invalidFiles.length > 0) {
                const names = invalidFiles.slice(0, 3).join(", ");
                const extra = invalidFiles.length > 3 ? ` e mais ${invalidFiles.length - 3}` : "";
                setFormStatus(
                    form,
                    "error",
                    "Arquivo não reconhecido como PDF",
                    `${names}${extra}. Selecione um arquivo com assinatura PDF válida.`,
                    { focus: true },
                );
            } else {
                clearFormStatus(form);
            }
        }

        input.addEventListener("change", () => addFiles(input.files));

        for (const eventName of ["dragenter", "dragover"]) {
            dropzone.addEventListener(eventName, (event) => {
                event.preventDefault();
                if (!form.matches('[aria-busy="true"]')) {
                    dropzone.classList.add("is-dragging");
                }
            });
        }

        for (const eventName of ["dragleave", "drop"]) {
            dropzone.addEventListener(eventName, (event) => {
                event.preventDefault();
                dropzone.classList.remove("is-dragging");
            });
        }

        dropzone.addEventListener("drop", (event) => {
            if (!form.matches('[aria-busy="true"]')) {
                addFiles(event.dataTransfer.files);
            }
        });

        const controller = {
            getFiles: () => [...files],
            clear: () => {
                selectionToken += 1;
                files = [];
                input.value = "";
                render();
                notifyChange();
            },
            setMultiple: (isMultiple) => {
                input.multiple = isMultiple;
                if (!isMultiple && files.length > 1) {
                    files = files.slice(0, 1);
                    render();
                    notifyChange();
                }
            },
        };

        controllers.set(input.id, controller);
        render();
        return controller;
    }

    function updateConditionalFields(select, namespace) {
        const container = document.querySelector(`[data-mode-fields="${namespace}"]`);
        if (!container) {
            return;
        }

        container.querySelectorAll("[data-visible-when]").forEach((group) => {
            const shouldShow = group.dataset.visibleWhen.split(" ").includes(select.value);
            group.hidden = !shouldShow;
            group.querySelectorAll("input, select, button").forEach((control) => {
                control.disabled = !shouldShow;
            });
        });
    }

    function initializeCustomBuilder(fileController) {
        const list = document.getElementById("custom-page-list");
        const emptyMessage = document.getElementById("custom-page-empty");
        const addButton = document.getElementById("add-page-item");
        const form = document.getElementById("organize-form");
        let items = [];

        function render() {
            const files = fileController.getFiles();
            items = items.filter((item) => files.includes(item.file));
            list.replaceChildren();
            emptyMessage.hidden = items.length > 0;
            addButton.disabled = files.length === 0;

            items.forEach((item, index) => {
                const row = document.createElement("li");
                row.className = "page-item";

                const number = document.createElement("span");
                number.className = "page-item-number";
                number.textContent = String(index + 1);

                const fields = document.createElement("div");
                fields.className = "page-item-fields";

                const sourceLabel = document.createElement("label");
                sourceLabel.append(document.createTextNode("Arquivo de origem"));
                const sourceSelect = document.createElement("select");
                sourceSelect.setAttribute("aria-label", `Arquivo de origem do item ${index + 1}`);
                files.forEach((file, fileIndex) => {
                    const option = document.createElement("option");
                    option.value = String(fileIndex);
                    option.textContent = file.name;
                    option.selected = file === item.file;
                    sourceSelect.append(option);
                });
                sourceSelect.addEventListener("change", () => {
                    item.file = files[Number(sourceSelect.value)];
                });
                sourceLabel.append(sourceSelect);

                const pageLabel = document.createElement("label");
                pageLabel.append(document.createTextNode("Página"));
                const pageInput = document.createElement("input");
                pageInput.type = "number";
                pageInput.min = "1";
                pageInput.step = "1";
                pageInput.required = true;
                pageInput.value = String(item.page);
                pageInput.setAttribute("aria-label", `Página do item ${index + 1}`);
                pageInput.addEventListener("input", () => {
                    item.page = Number(pageInput.value);
                });
                pageLabel.append(pageInput);

                const rotationLabel = document.createElement("label");
                rotationLabel.append(document.createTextNode("Rotação"));
                const rotationSelect = document.createElement("select");
                rotationSelect.setAttribute("aria-label", `Rotação do item ${index + 1}`);
                for (const angle of [0, 90, 180, 270]) {
                    const option = document.createElement("option");
                    option.value = String(angle);
                    option.textContent = `${angle}°`;
                    option.selected = angle === item.rotation;
                    rotationSelect.append(option);
                }
                rotationSelect.addEventListener("change", () => {
                    item.rotation = Number(rotationSelect.value);
                });
                rotationLabel.append(rotationSelect);

                fields.append(sourceLabel, pageLabel, rotationLabel);

                const actions = document.createElement("div");
                actions.className = "page-item-actions";
                const up = makeIconButton(`Mover item ${index + 1} para cima`, "icon-arrow-up", "up", index === 0);
                const down = makeIconButton(`Mover item ${index + 1} para baixo`, "icon-arrow-down", "down", index === items.length - 1);
                const remove = makeIconButton(`Remover item ${index + 1}`, "icon-trash", "remove", false, true);
                actions.append(up, down, remove);

                up.addEventListener("click", () => {
                    [items[index - 1], items[index]] = [items[index], items[index - 1]];
                    render();
                });
                down.addEventListener("click", () => {
                    [items[index + 1], items[index]] = [items[index], items[index + 1]];
                    render();
                });
                remove.addEventListener("click", () => {
                    items.splice(index, 1);
                    render();
                });

                row.append(number, fields, actions);
                list.append(row);
            });
        }

        addButton.addEventListener("click", () => {
            const files = fileController.getFiles();
            if (files.length === 0) {
                setFormStatus(form, "error", "Selecione um arquivo", "Adicione ao menos um PDF antes de criar a sequência.", { focus: true });
                document.getElementById("organize-files").focus();
                return;
            }
            items.push({ file: files[0], page: 1, rotation: 0 });
            clearFormStatus(form);
            render();
            list.lastElementChild?.querySelector("select")?.focus();
        });

        document.getElementById("organize-files").addEventListener("managed-files-change", render);

        const builder = {
            clear: () => {
                items = [];
                render();
            },
            getPayload: () => {
                const files = fileController.getFiles();
                return items.map((item) => ({
                    source: `file_${files.indexOf(item.file)}`,
                    page: item.page,
                    rotation: item.rotation,
                }));
            },
            isValid: () => items.length > 0 && items.every((item) => Number.isInteger(item.page) && item.page >= 1),
        };

        render();
        return builder;
    }

    function initializeNavigation() {
        const buttons = Array.from(document.querySelectorAll("[data-tool]"));
        const panels = Array.from(document.querySelectorAll("[data-panel]"));

        function requestedTool() {
            const hash = window.location.hash.replace(/^#/, "");
            return TOOL_IDS.includes(hash) ? hash : "mesclar";
        }

        function activate(tool, moveFocus = false) {
            buttons.forEach((button) => {
                const isActive = button.dataset.tool === tool;
                button.classList.toggle("is-active", isActive);
                if (isActive) {
                    button.setAttribute("aria-current", "page");
                } else {
                    button.removeAttribute("aria-current");
                }
            });

            panels.forEach((panel) => {
                panel.hidden = panel.dataset.panel !== tool;
            });

            document.title = `${TOOL_TITLES[tool]} — PDF Tools`;

            if (moveFocus) {
                const panel = document.querySelector(`[data-panel="${tool}"]`);
                panel?.scrollIntoView({ behavior: "smooth", block: "start" });
                panel?.querySelector("h2")?.focus({ preventScroll: true });
            }
        }

        buttons.forEach((button) => {
            button.addEventListener("click", () => {
                const tool = button.dataset.tool;
                if (window.location.hash === `#${tool}`) {
                    activate(tool);
                } else {
                    window.location.hash = tool;
                }
            });
        });

        window.addEventListener("hashchange", () => activate(requestedTool()));
        activate(requestedTool());
    }

    function initializeModes(organizeController) {
        const splitMode = document.getElementById("split-mode");
        const organizeMode = document.getElementById("organize-mode");

        function updateSplit() {
            updateConditionalFields(splitMode, "split");
            clearFormStatus(splitMode.form);
        }

        function updateOrganize() {
            updateConditionalFields(organizeMode, "organize");
            const customMode = organizeMode.value === "custom";
            organizeController.setMultiple(customMode);
            const helper = document.getElementById("organize-file-help");
            helper.textContent = customMode
                ? "Você pode selecionar vários PDFs para combinar páginas."
                : "Um arquivo por vez para esta operação.";
            clearFormStatus(organizeMode.form);
        }

        splitMode.addEventListener("change", updateSplit);
        organizeMode.addEventListener("change", updateOrganize);
        updateSplit();
        updateOrganize();

        return { updateSplit, updateOrganize };
    }

    function validateTextPatterns(form) {
        const listPattern = /^\s*\d+(?:\s*,\s*\d+)*\s*$/;
        const rangePattern = /^\s*\d+(?:\s*-\s*\d+)?(?:\s*,\s*\d+(?:\s*-\s*\d+)?)*\s*$/;

        if (form.id === "split-form") {
            const mode = document.getElementById("split-mode").value;
            if (mode === "range") {
                const first = Number(document.getElementById("split-first-page").value);
                const last = Number(document.getElementById("split-last-page").value);
                if (first > last) {
                    return { input: document.getElementById("split-last-page"), message: "A última página deve ser igual ou maior que a primeira." };
                }
            }
            if (mode === "ranges" && !rangePattern.test(document.getElementById("split-ranges").value)) {
                return { input: document.getElementById("split-ranges"), message: "Use intervalos válidos, como 1-3, 5, 8-10." };
            }
        }

        if (form.id === "organize-form") {
            const mode = document.getElementById("organize-mode").value;
            const input = mode === "reorder"
                ? document.getElementById("organize-order")
                : document.getElementById("organize-delete");
            if (["reorder", "delete"].includes(mode) && !listPattern.test(input.value)) {
                return { input, message: "Informe números de página separados por vírgula, como 3, 1, 2." };
            }
        }

        if (form.id === "rotate-form") {
            const input = document.getElementById("rotate-pages");
            if (input.value.trim() && !rangePattern.test(input.value)) {
                return { input, message: "Use páginas ou intervalos válidos, como 1-4, 7, 10." };
            }
        }

        if (form.id === "number-form") {
            const input = document.getElementById("number-template");
            const remainder = input.value.replace(/\{(?:current|total|document_total)\}/g, "");
            if (/[{}]/.test(remainder)) {
                return { input, message: "Use somente os campos {current}, {total} e {document_total}." };
            }
        }

        return null;
    }

    function validateVisibleControls(form) {
        const invalidControl = Array.from(form.querySelectorAll("input:not([type='file']), select"))
            .find((control) => !control.disabled && !control.checkValidity());

        if (invalidControl) {
            invalidControl.reportValidity();
            return false;
        }

        const patternError = validateTextPatterns(form);
        if (patternError) {
            patternError.input.setAttribute("aria-invalid", "true");
            setFormStatus(form, "error", "Revise as configurações", patternError.message, { focus: true });
            patternError.input.focus();
            return false;
        }

        form.querySelectorAll("[aria-invalid='true']").forEach((control) => control.removeAttribute("aria-invalid"));
        return true;
    }

    function fileConfiguration(formId) {
        const configurations = {
            "merge-form": { inputId: "merge-files", field: "files", minimum: 2 },
            "split-form": { inputId: "split-file", field: "file", minimum: 1 },
            "organize-form": { inputId: "organize-files", field: "files", minimum: 1 },
            "rotate-form": { inputId: "rotate-file", field: "file", minimum: 1 },
            "repair-form": { inputId: "repair-file", field: "file", minimum: 1 },
            "number-form": { inputId: "number-file", field: "file", minimum: 1 },
        };
        return configurations[formId];
    }

    function prepareFormData(form, customBuilder) {
        const config = fileConfiguration(form.id);
        const fileController = controllers.get(config.inputId);
        const selectedFiles = fileController.getFiles();
        const data = new FormData(form);
        data.delete(config.field);

        const filesToSend = form.id === "organize-form" && document.getElementById("organize-mode").value !== "custom"
            ? selectedFiles.slice(0, 1)
            : selectedFiles;
        filesToSend.forEach((file) => data.append(config.field, file, file.name));

        if (form.id === "organize-form" && document.getElementById("organize-mode").value === "custom") {
            data.set("custom_json", JSON.stringify(customBuilder.getPayload()));
        }

        return { data, selectedFiles, minimum: config.minimum, inputId: config.inputId };
    }

    async function errorMessageFromResponse(response) {
        const contentType = response.headers.get("content-type") || "";
        if (contentType.includes("application/json")) {
            const payload = await response.json();
            if (typeof payload.detail === "string") {
                return payload.detail;
            }
            if (Array.isArray(payload.detail)) {
                return payload.detail.map((item) => item.msg || "Parâmetro inválido.").join(" ");
            }
        }
        const message = await response.text();
        return message || `O servidor respondeu com o código ${response.status}.`;
    }

    function filenameFromResponse(response, fallback) {
        const disposition = response.headers.get("content-disposition") || "";
        const encodedMatch = disposition.match(/filename\*=utf-8''([^;]+)/i);
        const basicMatch = disposition.match(/filename="?([^";]+)"?/i);
        let filename = fallback;

        try {
            if (encodedMatch) {
                filename = decodeURIComponent(encodedMatch[1]);
            } else if (basicMatch) {
                filename = basicMatch[1];
            }
        } catch {
            filename = fallback;
        }

        return filename.replace(/[\\/:*?"<>|]/g, "_");
    }

    function fallbackFilename(form, response) {
        const isZip = (response.headers.get("content-type") || "").includes("application/zip");
        if (isZip) {
            return "arquivos_processados.zip";
        }
        const names = {
            "merge-form": "documentos_mesclados.pdf",
            "split-form": "documento_dividido.pdf",
            "organize-form": "documento_organizado.pdf",
            "rotate-form": "documento_girado.pdf",
            "repair-form": "documento_reparado.pdf",
            "number-form": "documento_numerado.pdf",
        };
        return names[form.id] || "documento_processado.pdf";
    }

    function setSubmitting(form, submitting) {
        form.setAttribute("aria-busy", String(submitting));
        const submitButton = form.querySelector("button[type='submit']");
        const label = submitButton.querySelector("[data-button-label]");
        if (!submitButton.dataset.originalLabel) {
            submitButton.dataset.originalLabel = label.textContent;
        }
        submitButton.disabled = submitting;
        submitButton.classList.toggle("is-loading", submitting);
        label.textContent = submitting ? "Processando…" : submitButton.dataset.originalLabel;
    }

    function initializeFormSubmission(customBuilder) {
        document.querySelectorAll("form.tool-form").forEach((form) => {
            form.addEventListener("submit", async (event) => {
                event.preventDefault();
                clearFormStatus(form);

                if (!validateVisibleControls(form)) {
                    return;
                }

                const prepared = prepareFormData(form, customBuilder);
                if (prepared.selectedFiles.length < prepared.minimum) {
                    const message = prepared.minimum === 2
                        ? "Adicione pelo menos dois arquivos PDF para continuar."
                        : "Selecione um arquivo PDF para continuar.";
                    setFormStatus(form, "error", "Arquivo necessário", message, { focus: true });
                    document.getElementById(prepared.inputId).focus();
                    return;
                }

                if (
                    form.id === "organize-form"
                    && document.getElementById("organize-mode").value === "custom"
                    && !customBuilder.isValid()
                ) {
                    setFormStatus(form, "error", "Sequência incompleta", "Adicione ao menos uma página e confira os números informados.", { focus: true });
                    document.getElementById("add-page-item").focus();
                    return;
                }

                setSubmitting(form, true);
                setFormStatus(form, "loading", "Processando seu PDF", "Isso pode levar alguns instantes. Mantenha esta página aberta.");

                try {
                    const response = await fetch(form.action, {
                        method: "POST",
                        body: prepared.data,
                        headers: { Accept: "application/pdf, application/zip, application/json" },
                    });

                    if (!response.ok) {
                        throw new Error(await errorMessageFromResponse(response));
                    }

                    const blob = await response.blob();
                    if (blob.size === 0) {
                        throw new Error("O servidor retornou um arquivo vazio. Tente novamente.");
                    }

                    const filename = filenameFromResponse(response, fallbackFilename(form, response));
                    const downloadUrl = URL.createObjectURL(blob);
                    downloadUrls.set(form, downloadUrl);
                    const link = setFormStatus(
                        form,
                        "success",
                        "Arquivo pronto!",
                        `O download de ${filename} começou automaticamente (${formatFileSize(blob.size)}).`,
                        { downloadUrl, filename, focus: true },
                    );
                    window.requestAnimationFrame(() => link?.click());
                } catch (error) {
                    const message = error instanceof TypeError
                        ? "Não foi possível conectar ao servidor. Verifique sua conexão e tente novamente."
                        : error.message;
                    setFormStatus(form, "error", "Não foi possível concluir", message, { focus: true });
                } finally {
                    setSubmitting(form, false);
                }
            });
        });
    }

    function initializeResets(customBuilder, modeHandlers) {
        document.querySelectorAll("form.tool-form").forEach((form) => {
            form.addEventListener("reset", () => {
                window.setTimeout(() => {
                    const config = fileConfiguration(form.id);
                    controllers.get(config.inputId).clear();
                    clearFormStatus(form);
                    form.querySelectorAll("[aria-invalid='true']").forEach((control) => control.removeAttribute("aria-invalid"));

                    if (form.id === "split-form") {
                        modeHandlers.updateSplit();
                    } else if (form.id === "organize-form") {
                        customBuilder.clear();
                        modeHandlers.updateOrganize();
                    } else if (form.id === "number-form") {
                        updateNumberPreview();
                    }
                }, 0);
            });
        });
    }

    function updateNumberPreview() {
        const position = document.getElementById("number-position").value;
        const firstNumber = Number(document.getElementById("number-first").value) || 1;
        const template = document.getElementById("number-template").value;
        const font = document.getElementById("number-font").value;
        const fontSize = Math.max(6, Math.min(72, Number(document.getElementById("number-font-size").value) || 10));
        const preview = document.getElementById("number-preview-text");

        preview.className = `page-number-preview ${position}`;
        preview.textContent = template
            .replaceAll("{current}", String(firstNumber))
            .replaceAll("{total}", String(firstNumber + 2))
            .replaceAll("{document_total}", "3");
        preview.style.fontFamily = font === "Times-Roman" ? "Georgia, serif" : font === "Courier" ? "monospace" : "Arial, sans-serif";
        preview.style.fontSize = `${Math.max(7, Math.min(12, fontSize * 0.7))}px`;
    }

    function initializeNumberPreview() {
        ["number-position", "number-first", "number-template", "number-font", "number-font-size"]
            .forEach((id) => document.getElementById(id).addEventListener("input", updateNumberPreview));
        updateNumberPreview();
    }

    function initializePasswordToggles() {
        document.querySelectorAll("[data-toggle-password]").forEach((button) => {
            button.addEventListener("click", () => {
                const input = document.getElementById(button.dataset.togglePassword);
                const showing = input.type === "text";
                input.type = showing ? "password" : "text";
                button.textContent = showing ? "Mostrar" : "Ocultar";
                button.setAttribute("aria-label", showing ? "Mostrar senha" : "Ocultar senha");
            });
        });
    }

    async function checkApiStatus() {
        const container = document.getElementById("api-status");
        const text = document.getElementById("api-status-text");
        const controller = new AbortController();
        const timeout = window.setTimeout(() => controller.abort(), 5000);

        try {
            const response = await fetch("/api/status", {
                headers: { Accept: "application/json" },
                signal: controller.signal,
            });
            if (!response.ok) {
                throw new Error("API indisponível");
            }
            const payload = await response.json();
            if (payload.status !== "online") {
                throw new Error("API indisponível");
            }
            container.classList.add("is-online");
            container.classList.remove("is-offline");
            text.textContent = "API pronta";
        } catch {
            container.classList.add("is-offline");
            container.classList.remove("is-online");
            text.textContent = "API indisponível";
        } finally {
            window.clearTimeout(timeout);
        }
    }

    function initialize() {
        document.querySelectorAll(".file-input").forEach(initializeFilePicker);
        const organizeController = controllers.get("organize-files");
        const customBuilder = initializeCustomBuilder(organizeController);
        const modeHandlers = initializeModes(organizeController);

        initializeNavigation();
        initializeFormSubmission(customBuilder);
        initializeResets(customBuilder, modeHandlers);
        initializeNumberPreview();
        initializePasswordToggles();
        checkApiStatus();

        window.addEventListener("beforeunload", () => {
            document.querySelectorAll("form.tool-form").forEach(revokeDownload);
        });
    }

    initialize();
})();
