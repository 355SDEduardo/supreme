from __future__ import annotations

import hmac
import os
import secrets
from datetime import datetime
from decimal import Decimal, InvalidOperation
from io import BytesIO
from pathlib import Path
from typing import Any

from flask import (
    Flask,
    Request,
    abort,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)
from werkzeug.datastructures import FileStorage

from core.document_comparison import compare_products_to_pdf, text_report
from core.fiscal_registration import FiscalRegistration, FiscalRegistrationService
from core.models import ParseIssue, ProcessingState, ZipComparisonResult
from core.zip_comparison import compare_nfe_zips
from core.ncm_comparison import (
    compare_nfes,
    load_fiscal_catalog,
    load_fiscal_catalog_bytes,
)
from core.nfe_parser import NfeParser
from core.zip_extractor import extract_xmls_from_zip
from core.reporting import (
    aggregate_rows,
    comparison_payload,
    csv_download,
    excel_download,
    json_download,
    note_rows,
    product_rows,
    report_payload,
    totals,
    zip_comparison_excel,
    zip_comparison_csv,
    zip_comparison_divergences_csv,
    zip_comparison_payload,
)
from state import SessionStore
from core.nfse_pipeline import process_nfse_batch
from core.nfse_reporting import (
    build_nfse_json_payload, generate_nfse_excel_report, generate_nfse_csv_notes,
    generate_nfse_csv_findings, severity_counts,
)
from core.nfse_security import DEFAULT_MAX_XML_BYTES, MAX_ZIP_BYTES

BASE_DIR = Path(__file__).resolve().parent
MAX_XML_FILES = 200
MAX_XML_BYTES = 5 * 1024 * 1024
MAX_ZIP_ENTRIES = 500
MAX_ZIP_TOTAL_BYTES = 100 * 1024 * 1024
MAX_FISCAL_BYTES = 10 * 1024 * 1024
MAX_TXT_BYTES = 2 * 1024 * 1024
MAX_PDF_BYTES = 30 * 1024 * 1024

NOTE_COLUMNS = [
    ("arquivo", "Arquivo"),
    ("chave", "Chave de Acesso"),
    ("numero", "Número"),
    ("serie", "Série"),
    ("cnpj_emissor", "CNPJ Emissor"),
    ("emissor", "Emissor"),
    ("cnpj_destinatario", "CNPJ Destinatário"),
    ("destinatario", "Destinatário"),
    ("data_emissao", "Data Emissão"),
    ("cfops", "CFOPs"),
    ("csts", "CSTs"),
    ("valor_produtos", "Valor Produtos"),
    ("valor_icms", "ICMS"),
    ("valor_bc_st", "BC ST"),
    ("valor_icms_st", "ICMS ST"),
    ("valor_total", "Valor Total"),
]
AGGREGATE_VALUE_COLUMNS = [
    ("quantidade_itens", "Qtd. Itens"),
    ("quantidade_notas", "Qtd. Notas"),
    ("valor_produtos", "Valor Produtos"),
    ("valor_icms", "ICMS"),
    ("valor_bc_st", "BC ST"),
    ("valor_icms_st", "ICMS ST"),
    ("valor_total", "Produtos + ST"),
]
PRODUCT_COLUMNS = [
    ("nfe", "NF-e"),
    ("item", "Item"),
    ("codigo", "Código"),
    ("descricao", "Descrição"),
    ("ncm", "NCM"),
    ("cst", "CST"),
    ("cfop", "CFOP"),
    ("quantidade", "Qtd."),
    ("unidade", "UN"),
    ("valor_unitario", "Valor Unit."),
    ("valor_total", "Valor Total"),
    ("valor_icms", "ICMS"),
    ("valor_bc_st", "BC ST"),
    ("valor_icms_st", "ICMS ST"),
    ("destinacao", "Destinação"),
]
COMPARISON_COLUMNS = [
    ("ncm", "NCM"),
    ("posicao", "Posição"),
    ("subposicao", "Subposição"),
    ("item", "Item"),
    ("cfops", "CFOPs"),
    ("ncm_cadastrado", "Cadastrado"),
    ("st", "Status ST"),
    ("mva", "MVA"),
    ("cest", "CEST"),
]


class MemoryUploadRequest(Request):
    """Recebe multipart em RAM, sem spool de arquivos para disco."""

    def _get_file_stream(
        self,
        total_content_length: int | None,
        content_type: str | None,
        filename: str | None = None,
        content_length: int | None = None,
    ) -> BytesIO:
        return BytesIO()


def create_app(test_config: dict[str, Any] | None = None) -> Flask:
    app = Flask(__name__)
    app.request_class = MemoryUploadRequest
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("NFE_WEB_SECRET") or secrets.token_hex(32),
        MAX_CONTENT_LENGTH=55 * 1024 * 1024,
        MAX_FORM_MEMORY_SIZE=2 * 1024 * 1024,
        MAX_FORM_PARTS=500,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=False,
        FISCAL_DATA_PATH=BASE_DIR / "data" / "fiscal_data.json",
    )
    if test_config:
        app.config.update(test_config)

    store = SessionStore(
        ttl_seconds=int(app.config.get("STATE_TTL_SECONDS", 7200)),
        max_sessions=int(app.config.get("MAX_SESSIONS", 100)),
    )
    parser = NfeParser()
    registration_service = FiscalRegistrationService()
    fiscal_path = Path(app.config["FISCAL_DATA_PATH"])
    registration_service.ensure_file(fiscal_path)

    @app.before_request
    def prepare_session() -> None:
        session.setdefault("sid", store.create_id())
        session.setdefault("csrf_token", secrets.token_urlsafe(32))

    @app.context_processor
    def inject_csrf() -> dict[str, str]:
        return {"csrf_token": session["csrf_token"]}

    @app.after_request
    def add_security_headers(response: Any) -> Any:
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "img-src 'self' data:; object-src 'none'; base-uri 'self'; "
            "form-action 'self'; frame-ancestors 'none'"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.template_filter("brl")
    def format_brl(value: object) -> str:
        try:
            formatted = f"{Decimal(str(value)):,.2f}"
        except (TypeError, ValueError, InvalidOperation):
            formatted = "0.00"
        return "R$ " + formatted.replace(",", "X").replace(".", ",").replace("X", ".")

    @app.template_filter("decimal_br")
    def format_decimal(value: object) -> str:
        try:
            formatted = f"{Decimal(str(value)):,.2f}"
        except (TypeError, ValueError, InvalidOperation):
            formatted = "0.00"
        return formatted.replace(",", "X").replace(".", ",").replace("X", ".")

    @app.get("/")
    def index() -> str:
        state = _state(store)
        try:
            fiscal_count = len(load_fiscal_catalog(fiscal_path))
            fiscal_error = ""
        except (OSError, ValueError) as exc:
            fiscal_count = 0
            fiscal_error = str(exc)

        products = product_rows(state.nfes)
        return render_template(
            "index.html",
            state=state,
            totals=totals(state.nfes),
            notes=note_rows(state.nfes),
            products=products,
            cfop_rows=aggregate_rows(state.nfes, "cfop"),
            cst_rows=aggregate_rows(state.nfes, "cst"),
            note_options=sorted({note.numero for note in state.nfes if note.numero}),
            cfop_options=sorted({row["cfop"] for row in products if row["cfop"]}),
            cst_options=sorted({row["cst"] for row in products if row["cst"]}),
            fiscal_count=fiscal_count,
            fiscal_error=fiscal_error,
            nfse_state=state.nfse_state,
            nfse_severity=severity_counts(state.nfse_state) if state.nfse_state else {},
        )

    @app.post("/nfse/processar")
    def process_nfse() -> Any:
        _validate_csrf()
        destination = url_for('index', tab='auditoria-nfse')
        uploads = [f for f in request.files.getlist('arquivos_nfse') if f.filename]
        try:
            if not uploads or len(uploads) > MAX_XML_FILES:
                raise ValueError('Selecione de 1 a 200 arquivos XML ou ZIP de NFS-e.')

            def inputs():
                for upload in uploads:
                    name = _safe_name(upload.filename)
                    limit = MAX_ZIP_BYTES if Path(name).suffix.casefold() == '.zip' else DEFAULT_MAX_XML_BYTES
                    yield name, _read_upload(upload, limit, 'NFS-e')

            result = process_nfse_batch(inputs())
        except (OSError, ValueError) as exc:
            if request.accept_mimetypes.best == 'application/json':
                return {'error': str(exc)}, 400
            flash(str(exc), 'error')
            return redirect(destination)
        if result.documents or result.events or _state(store).nfse_state is None:
            _state(store).nfse_state = result
        if request.accept_mimetypes.best == 'application/json':
            return build_nfse_json_payload(result)
        if result.documents or result.events:
            flash(f'{len(result.documents)} documento(s) NFS-e/DPS e {len(result.events)} evento(s) processados.', 'success')
        else:
            flash('Nenhuma NFS-e válida. ' + '; '.join(i['message'] for i in result.issues[:3]), 'error')
        return redirect(destination)

    def require_nfse():
        result = _state(store).nfse_state
        if result is None:
            abort(404)
        return result

    @app.get('/nfse/exportar/excel')
    def export_nfse_excel() -> Any:
        return _send_bytes(generate_nfse_excel_report(require_nfse()).getvalue(),
            'auditoria_nfse_' + datetime.now().strftime('%Y%m%d_%H%M%S') + '.xlsx',
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

    @app.get('/nfse/exportar/csv/<dataset>')
    def export_nfse_csv(dataset: str) -> Any:
        functions = {'notas': generate_nfse_csv_notes, 'apontamentos': generate_nfse_csv_findings}
        if dataset not in functions:
            abort(404)
        return _send_bytes(functions[dataset](require_nfse()).encode('utf-8'),
                           f'auditoria_nfse_{dataset}.csv', 'text/csv; charset=utf-8')

    @app.get('/nfse/exportar/json')
    def export_nfse_json() -> Any:
        return _send_bytes(json_download(build_nfse_json_payload(require_nfse())),
                           'auditoria_nfse.json', 'application/json')

    @app.post('/nfse/limpar')
    def clear_nfse() -> Any:
        _validate_csrf()
        _state(store).nfse_state = None
        flash('Dados de NFS-e removidos desta sessão.', 'success')
        return redirect(url_for('index', tab='auditoria-nfse'))

    @app.post("/produtos/destinacao")
    def save_product_destination() -> Any:
        _validate_csrf()
        destination = request.form.get("destinacao", "")
        if destination not in {"Comercialização", "Uso e Consumo", "Imobilizado"}:
            abort(400)
        apply_same_ncm = request.form.get("aplicar_ncm", "0")
        if apply_same_ncm not in {"0", "1"}:
            abort(400)
        note_index = request.form.get("note_index", "")
        product_index = request.form.get("product_index", "")
        if not note_index.isdecimal() or not product_index.isdecimal():
            abort(400)
        state = _require_nfes(store)
        if int(note_index) >= len(state.nfes):
            abort(404)
        note = state.nfes[int(note_index)]
        if note.chave != request.form.get("note_key", ""):
            abort(409)
        if int(product_index) >= len(note.produtos):
            abort(404)
        product = note.produtos[int(product_index)]
        if str(product.numero) != request.form.get("item", ""):
            abort(409)
        if apply_same_ncm == "1":
            if not product.ncm.strip():
                abort(400)
            for current_note in state.nfes:
                for current_product in current_note.produtos:
                    if current_product.ncm == product.ncm:
                        current_product.destinacao = destination
        else:
            product.destinacao = destination
        return "", 204

    @app.post("/processar")
    def process_xmls() -> Any:
        _validate_csrf()
        uploads = [
            upload
            for upload in (
                request.files.getlist("xml_files")
                + request.files.getlist("xml_folder")
            )
            if upload and upload.filename
        ]
        if not uploads:
            flash("Selecione ao menos um arquivo XML ou ZIP.", "error")
            return redirect(url_for("index", tab="importacao"))
        if len(uploads) > MAX_XML_FILES:
            flash(f"Envie no máximo {MAX_XML_FILES} arquivos XML ou ZIP por processamento.", "error")
            return redirect(url_for("index", tab="importacao"))

        try:
            catalog = _catalog_for_processing(
                request.files.get("fiscal_file"), fiscal_path
            )
        except (OSError, ValueError) as exc:
            flash(str(exc), "error")
            return redirect(url_for("index", tab="importacao"))

        nfes = []
        issues: list[ParseIssue] = []
        logs = [_log_line(f"Recebidos {len(uploads)} arquivo(s) XML ou ZIP.")]
        total_xml_bytes = 0
        for upload in uploads:
            filename = _safe_name(upload.filename)
            suffix = Path(filename).suffix.casefold()
            if suffix not in {".xml", ".zip"}:
                issues.append(ParseIssue(filename, "Extensão diferente de .xml ou .zip."))
                continue
            try:
                if suffix == ".zip":
                    extracted = extract_xmls_from_zip(
                        upload.stream,
                        zip_filename=filename,
                        max_entries=MAX_ZIP_ENTRIES,
                        max_xml_bytes=MAX_XML_BYTES,
                        max_total_bytes=MAX_ZIP_TOTAL_BYTES - total_xml_bytes,
                        max_zip_bytes=app.config["MAX_CONTENT_LENGTH"],
                    )
                    issues.extend(extracted.issues)
                    xml_files = extracted.xml_files
                    logs.append(_log_line(
                        f"ZIP processado: {filename} ({len(xml_files)} XML(s) extraídos)."
                    ))
                    if not xml_files and not extracted.issues:
                        issues.append(ParseIssue(filename, "O ZIP não contém arquivos XML."))
                else:
                    xml_files = [(filename, _read_upload(upload, MAX_XML_BYTES, "XML"))]
                for xml_filename, content in xml_files:
                    total_xml_bytes += len(content)
                    if total_xml_bytes > MAX_ZIP_TOTAL_BYTES:
                        raise ValueError("O lote excede o limite total de 100 MB de XMLs descompactados.")
                    try:
                        nfes.append(parser.parse_bytes(content, xml_filename))
                        logs.append(_log_line(f"XML processado: {xml_filename}"))
                    except ValueError as exc:
                        issues.append(ParseIssue(xml_filename, str(exc)))
                        logs.append(_log_line(f"XML rejeitado: {xml_filename}"))
            except (OSError, ValueError) as exc:
                issues.append(ParseIssue(filename, str(exc)))
                logs.append(_log_line(f"Arquivo rejeitado: {filename}"))
                if suffix == ".zip":
                    flash(str(exc), "error")

        comparison, summary = compare_nfes(nfes, catalog)
        logs.append(
            _log_line(
                f"Processamento concluído: {len(nfes)} nota(s), "
                f"{len(issues)} rejeição(ões), {summary.total_ncms} NCM(s) analisado(s)."
            )
        )
        store.replace(
            session["sid"],
            ProcessingState(
                nfes=nfes,
                issues=issues,
                comparison=comparison,
                comparison_summary=summary,
                logs=logs,
                zip_comparison_result=_state(store).zip_comparison_result,
                document_result=_state(store).document_result,
                nfse_state=_state(store).nfse_state,
            ),
        )
        if nfes:
            flash(f"{len(nfes)} nota(s) processada(s) com sucesso.", "success")
            return redirect(url_for("index", tab="resumo"))
        flash("Nenhuma NF-e válida foi processada. Consulte os erros.", "error")
        return redirect(url_for("index", tab="importacao"))

    @app.post("/comparar-zips")
    def compare_zips() -> Any:
        _validate_csrf()
        cliente = request.files.get("zip_cliente")
        portal = request.files.get("zip_portal")
        destination = url_for("index", tab="conciliacao-zips")
        if cliente is None or portal is None or not cliente.filename or not portal.filename:
            flash("Selecione os dois arquivos ZIP: enviado pelo cliente e extraído portal.", "error")
            return redirect(destination)
        if any(Path(_safe_name(upload.filename)).suffix.casefold() != ".zip" for upload in (cliente, portal)):
            flash("Os dois arquivos para conciliação devem ter extensão .zip.", "error")
            return redirect(destination)
        try:
            result = compare_nfe_zips(
                cliente.stream, portal.stream,
                nome_cliente=_safe_name(cliente.filename), nome_portal=_safe_name(portal.filename),
            )
        except (OSError, ValueError) as exc:
            flash(str(exc), "error")
            return redirect(destination)
        state = _state(store)
        state.zip_comparison_result = result
        summary = result.resumo
        state.logs.append(_log_line(
            f"Conciliação ZIP concluída: {summary.total_cliente} nota(s) no cliente, "
            f"{summary.total_portal} no portal, {summary.total_comuns} em comum, "
            f"{len(result.issues_cliente) + len(result.issues_portal)} aviso(s)."
        ))
        flash(f"Conciliação concluída: {summary.total_cliente} notas no cliente, "
              f"{summary.total_portal} no portal, {summary.total_comuns} em comum.", "success")
        return redirect(destination)

    @app.get("/download/conciliacao-zips.xlsx")
    def download_zip_comparison_excel() -> Any:
        return _send_bytes(zip_comparison_excel(_require_zip_comparison(store)),
                           "Conciliacao_ZIPs.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    @app.get("/download/conciliacao-zips.json")
    def download_zip_comparison_json() -> Any:
        return _send_bytes(json_download(zip_comparison_payload(_require_zip_comparison(store))),
                           "Conciliacao_ZIPs.json", "application/json")

    @app.get("/download/conciliacao-zips/<grupo>.csv")
    def download_zip_comparison_csv(grupo: str) -> Any:
        result = _require_zip_comparison(store)
        groups = {"apenas-cliente": result.apenas_cliente, "apenas-portal": result.apenas_portal,
                  "em-ambos": result.em_ambos}
        if grupo == "divergencias":
            content = zip_comparison_divergences_csv(result.divergencias)
        elif grupo in groups:
            content = zip_comparison_csv(groups[grupo])
        else:
            abort(404)
        return _send_bytes(content, f"Conciliacao_{grupo}.csv", "text/csv; charset=utf-8")

    @app.post("/comparar-ncm")
    def compare_current_ncms() -> Any:
        _validate_csrf()
        state = _state(store)
        if not state.nfes:
            flash("Processe os XMLs antes de comparar NCM/ST.", "error")
            return redirect(url_for("index", tab="importacao"))
        try:
            catalog = load_fiscal_catalog(fiscal_path)
            state.comparison, state.comparison_summary = compare_nfes(
                state.nfes, catalog
            )
            state.logs.append(_log_line("NCM/ST recomparado com a base fiscal local."))
        except (OSError, ValueError) as exc:
            flash(str(exc), "error")
            return redirect(url_for("index", tab="comparacao"))
        flash("Comparação NCM/ST atualizada.", "success")
        return redirect(url_for("index", tab="comparacao"))

    @app.post("/base-fiscal/importar")
    def import_fiscal_catalog() -> Any:
        _validate_csrf()
        if request.form.get("confirm_replace") != "yes":
            flash("Confirme a substituição da base fiscal.", "error")
            return redirect(url_for("index", tab="cadastro"))
        upload = request.files.get("catalog_file")
        if upload is None or not upload.filename:
            flash("Selecione uma base fiscal JSON.", "error")
            return redirect(url_for("index", tab="cadastro"))
        try:
            content = _read_upload(upload, MAX_FISCAL_BYTES, "base fiscal")
            count = registration_service.replace(fiscal_path, content)
            state = _state(store)
            if state.nfes:
                catalog = load_fiscal_catalog(fiscal_path)
                state.comparison, state.comparison_summary = compare_nfes(
                    state.nfes, catalog
                )
            state.logs.append(_log_line(f"Base fiscal importada com {count} item(ns)."))
        except (OSError, ValueError) as exc:
            flash(str(exc), "error")
            return redirect(url_for("index", tab="cadastro"))
        flash(f"Base fiscal substituída: {count} item(ns).", "success")
        return redirect(url_for("index", tab="cadastro"))

    @app.post("/base-fiscal/cadastrar")
    def register_fiscal_item() -> Any:
        _validate_csrf()
        item = FiscalRegistration(
            ncm=request.form.get("ncm", ""),
            position=request.form.get("position", ""),
            subposition=request.form.get("subposition", ""),
            subitem=request.form.get("subitem", ""),
            state=request.form.get("state", ""),
            internal_rate=request.form.get("internal_rate", ""),
            reduced_base=request.form.get("reduced_base", ""),
            deferral=request.form.get("deferral", ""),
            fcp=request.form.get("fcp", ""),
            exemption=request.form.get("exemption", ""),
            non_incidence=request.form.get("non_incidence", ""),
            st=request.form.get("st", ""),
            mva=request.form.get("mva", ""),
            cest=request.form.get("cest", ""),
            suspension=request.form.get("suspension", ""),
        )
        try:
            count = registration_service.add(fiscal_path, item)
            state = _state(store)
            if state.nfes:
                catalog = load_fiscal_catalog(fiscal_path)
                state.comparison, state.comparison_summary = compare_nfes(
                    state.nfes, catalog
                )
            state.logs.append(_log_line(f"NCM {item.ncm} cadastrado na base fiscal."))
        except (OSError, ValueError) as exc:
            flash(str(exc), "error")
            return redirect(url_for("index", tab="cadastro"))
        flash(f"NCM cadastrado. A base agora possui {count} item(ns).", "success")
        return redirect(url_for("index", tab="cadastro"))

    @app.post("/comparar-documentos")
    def compare_documents() -> Any:
        _validate_csrf()
        txt_upload = request.files.get("txt_file")
        pdf_upload = request.files.get("pdf_file")
        if (
            txt_upload is None
            or pdf_upload is None
            or not txt_upload.filename
            or not pdf_upload.filename
        ):
            flash("Selecione os arquivos TXT e PDF.", "error")
            return redirect(url_for("index", tab="documentos"))
        if Path(txt_upload.filename).suffix.casefold() != ".txt":
            flash("A lista de produtos deve ser um arquivo .txt.", "error")
            return redirect(url_for("index", tab="documentos"))
        if Path(pdf_upload.filename).suffix.casefold() != ".pdf":
            flash("O relatório deve ser um arquivo .pdf.", "error")
            return redirect(url_for("index", tab="documentos"))

        try:
            result = compare_products_to_pdf(
                _read_upload(txt_upload, MAX_TXT_BYTES, "TXT"),
                _read_upload(pdf_upload, MAX_PDF_BYTES, "PDF"),
                txt_filename=_safe_name(txt_upload.filename),
                pdf_filename=_safe_name(pdf_upload.filename),
            )
            state = _state(store)
            state.document_result = result
            state.logs.append(
                _log_line(
                    "Comparação TXT/PDF concluída: "
                    f"{result['resumo']['total_encontrados']} encontrado(s)."
                )
            )
        except (OSError, RuntimeError, ValueError) as exc:
            flash(str(exc), "error")
            return redirect(url_for("index", tab="documentos"))
        flash("Comparação TXT/PDF concluída.", "success")
        return redirect(url_for("index", tab="documentos"))

    @app.post("/limpar-sessao")
    def clear_session_state() -> Any:
        _validate_csrf()
        store.clear(session["sid"])
        flash("Dados temporários da sessão removidos.", "success")
        return redirect(url_for("index", tab="importacao"))

    @app.get("/download/relatorio.json")
    def download_report_json() -> Any:
        state = _require_nfes(store)
        return _send_bytes(
            json_download(report_payload(state.nfes, state.issues)),
            "Conferencia_Impostos_WEB.json",
            "application/json",
        )

    @app.get("/download/relatorio.xlsx")
    def download_report_excel() -> Any:
        state = _require_nfes(store)
        return _send_bytes(
            excel_download(state.nfes),
            "Conferencia_Impostos_WEB.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    @app.get("/download/comparacao-ncm.json")
    def download_comparison_json() -> Any:
        state = _require_nfes(store)
        return _send_bytes(
            json_download(comparison_payload(state.comparison)),
            "Conferencia_NCM_ST_WEB.json",
            "application/json",
        )

    @app.get("/download/<dataset>.csv")
    def download_csv(dataset: str) -> Any:
        state = _require_nfes(store)
        if dataset == "notas":
            rows, columns = note_rows(state.nfes), NOTE_COLUMNS
        elif dataset == "cfop":
            rows = aggregate_rows(state.nfes, "cfop")
            columns = [("cfop", "CFOP"), *AGGREGATE_VALUE_COLUMNS]
        elif dataset == "cst":
            rows = aggregate_rows(state.nfes, "cst")
            columns = [("cst", "CST/CSOSN"), *AGGREGATE_VALUE_COLUMNS]
        elif dataset == "produtos":
            rows = product_rows(
                state.nfes,
                note_number=request.args.get("nota", ""),
                operacao=request.args.get("operacao", ""),
                cfop=request.args.get("cfop", ""),
                cst=request.args.get("cst", ""),
                status=request.args.get("status", ""),
                query=request.args.get("q", ""),
            )
            columns = PRODUCT_COLUMNS
        elif dataset == "comparacao":
            rows = [
                {
                    **item.to_dict(),
                    "cfops": ", ".join(item.cfops),
                    "ncm_cadastrado": "Sim" if item.ncm_cadastrado else "Não",
                }
                for item in state.comparison
            ]
            columns = COMPARISON_COLUMNS
        else:
            abort(404)
        return _send_bytes(
            csv_download(rows, columns),
            f"{dataset}_WEB.csv",
            "text/csv; charset=utf-8",
        )

    @app.get("/download/comparacao-documentos.json")
    def download_document_json() -> Any:
        result = _require_document_result(store)
        return _send_bytes(
            json_download(result),
            "Comparacao_TXT_PDF_WEB.json",
            "application/json",
        )

    @app.get("/download/comparacao-documentos.txt")
    def download_document_text() -> Any:
        result = _require_document_result(store)
        return _send_bytes(
            text_report(result),
            "Comparacao_TXT_PDF_WEB.txt",
            "text/plain; charset=utf-8",
        )

    @app.errorhandler(400)
    def bad_request(_error: Any) -> tuple[str, int]:
        return render_template(
            "error.html",
            title="Requisição inválida",
            message="A requisição expirou ou não pôde ser validada. Atualize a página e tente novamente.",
        ), 400

    @app.errorhandler(404)
    def not_found(_error: Any) -> tuple[str, int]:
        return render_template(
            "error.html",
            title="Conteúdo não encontrado",
            message="O recurso solicitado não existe ou não está mais disponível.",
        ), 404

    @app.errorhandler(413)
    def too_large(_error: Any) -> tuple[str, int]:
        return render_template(
            "error.html",
            title="Upload muito grande",
            message="A requisição excedeu o limite total de 55 MB.",
        ), 413

    return app


def _state(store: SessionStore) -> ProcessingState:
    return store.get(session["sid"])


def _require_nfes(store: SessionStore) -> ProcessingState:
    state = _state(store)
    if not state.nfes:
        abort(404)
    return state


def _require_document_result(store: SessionStore) -> dict[str, Any]:
    result = _state(store).document_result
    if result is None:
        abort(404)
    return result


def _require_zip_comparison(store: SessionStore) -> ZipComparisonResult:
    result = _state(store).zip_comparison_result
    if result is None:
        abort(404)
    return result


def _validate_csrf() -> None:
    supplied = request.form.get("csrf_token", "")
    expected = session.get("csrf_token", "")
    if not supplied or not expected or not hmac.compare_digest(supplied, expected):
        abort(400)


def _catalog_for_processing(
    upload: FileStorage | None, fiscal_path: Path
) -> dict[str, Any]:
    if upload is not None and upload.filename:
        if Path(upload.filename).suffix.casefold() != ".json":
            raise ValueError("A base fiscal opcional deve ser um arquivo .json.")
        return load_fiscal_catalog_bytes(
            _read_upload(upload, MAX_FISCAL_BYTES, "base fiscal")
        )
    return load_fiscal_catalog(fiscal_path)


def _read_upload(upload: FileStorage, limit: int, label: str) -> bytes:
    content = upload.stream.read(limit + 1)
    if len(content) > limit:
        raise ValueError(f"O arquivo {label} excede o limite de {limit // (1024 * 1024)} MB.")
    if not content:
        raise ValueError(f"O arquivo {label} está vazio.")
    return content


def _safe_name(filename: str) -> str:
    normalized = filename.replace("\\", "/")
    name = normalized.rsplit("/", 1)[-1].strip()
    return "".join(char for char in name if char.isprintable())[:180] or "arquivo"


def _log_line(message: str) -> str:
    return f"[{datetime.now().strftime('%H:%M:%S')}] {message}"


def _send_bytes(content: bytes, filename: str, mimetype: str) -> Any:
    return send_file(
        BytesIO(content),
        mimetype=mimetype,
        as_attachment=True,
        download_name=filename,
        max_age=0,
    )


if __name__ == "__main__":
    host = os.environ.get("NFE_WEB_HOST", "127.0.0.1")
    port = int(os.environ.get("NFE_WEB_PORT", "5000"))
    create_app().run(host=host, port=port, debug=False)
