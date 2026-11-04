import json
from pathlib import Path
from tempfile import TemporaryDirectory
import zipfile

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.services.merge_pdf import merge_pdfs, merge_selected_pages
from app.services.number_pdf import add_page_numbers
from app.services.organize_pdf import (
    delete_pages,
    duplicate_page,
    organize_pdf,
    reorder_pages,
    reverse_pdf,
)
from app.services.repair_pdf import repair_pdf
from app.services.rotate_pdf import rotate_pdf
from app.services.split_pdf import (
    extract_page_range,
    split_by_page_count,
    split_by_ranges,
    split_by_size,
    split_every_page,
)
from app.utils.files import generate_safe_filename
from app.utils.page_ranges import parse_page_range_string
from app.validators.pdf_validator import validate_pdf

app = FastAPI(
    title="PDF Tools API",
    description="API para mesclar, dividir, organizar, girar, reparar e numerar arquivos PDF.",
    version="1.0.0",
)

STATIC_DIR = Path(__file__).resolve().parent / "static"
OUTPUT_DIR = Path("outputs")
OUTPUT_DIR.mkdir(exist_ok=True)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = (
        "camera=(), microphone=(), geolocation=(), payment=()"
    )

    if request.url.path == "/" or request.url.path.startswith("/static/"):
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self'; "
            "img-src 'self' data:; "
            "connect-src 'self'; "
            "object-src 'none'; "
            "base-uri 'self'; "
            "form-action 'self'; "
            "frame-ancestors 'none'"
        )

    return response


@app.get("/", include_in_schema=False)
async def frontend() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html", media_type="text/html")


@app.get("/api/status", tags=["Sistema"])
async def status_endpoint():
    return {
        "status": "online",
        "message": "PDF Tools API está pronta para uso.",
        "endpoints": [
            "/pdf/merge",
            "/pdf/split",
            "/pdf/organize",
            "/pdf/rotate",
            "/pdf/repair",
            "/pdf/number",
        ],
    }


@app.post("/pdf/merge")
async def merge_endpoint(
    files: list[UploadFile] = File(...),
):
    if len(files) < 2:
        raise HTTPException(
            status_code=400,
            detail="Envie pelo menos dois arquivos PDF para mesclagem.",
        )

    out_file = OUTPUT_DIR / generate_safe_filename(".pdf")

    with TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        input_files: list[Path] = []

        for seq, uploaded_file in enumerate(files):
            input_path = temp_path / f"{seq:04d}_{uploaded_file.filename}"
            content = await uploaded_file.read()
            input_path.write_bytes(content)

            try:
                validate_pdf(input_path)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc))

            input_files.append(input_path)

        try:
            merge_pdfs(input_files, out_file)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Erro ao mesclar PDFs: {exc}")

    return FileResponse(
        out_file,
        media_type="application/pdf",
        filename="documentos_mesclados.pdf",
    )


@app.post("/pdf/split")
async def split_endpoint(
    file: UploadFile = File(...),
    mode: str = Form("every_page"),  # every_page, range, ranges, count, size
    first_page: int | None = Form(None),
    last_page: int | None = Form(None),
    ranges_str: str | None = Form(None),  # ex: "1-3, 4-7, 8-10"
    pages_per_file: int | None = Form(None),
    target_size_mb: float | None = Form(None),
):
    with TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        input_path = temp_path / file.filename
        content = await file.read()
        input_path.write_bytes(content)

        try:
            validate_pdf(input_path)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

        split_output_dir = temp_path / "split_results"

        try:
            if mode == "every_page":
                generated = split_every_page(input_path, split_output_dir)
            elif mode == "range":
                if first_page is None or last_page is None:
                    raise HTTPException(
                        status_code=400,
                        detail="Para o modo 'range', informe 'first_page' e 'last_page'.",
                    )
                out_single = OUTPUT_DIR / generate_safe_filename(".pdf")
                extract_page_range(input_path, out_single, first_page, last_page)
                return FileResponse(
                    out_single,
                    media_type="application/pdf",
                    filename=f"paginas_{first_page}_a_{last_page}.pdf",
                )
            elif mode == "ranges":
                if not ranges_str:
                    raise HTTPException(
                        status_code=400,
                        detail="Para o modo 'ranges', informe 'ranges_str' (ex: '1-3, 4-7').",
                    )
                parsed_ranges: list[tuple[int, int]] = []
                for item in ranges_str.split(","):
                    item = item.strip()
                    if "-" in item:
                        s, e = item.split("-")
                        parsed_ranges.append((int(s.strip()), int(e.strip())))
                    elif item:
                        p = int(item)
                        parsed_ranges.append((p, p))
                generated = split_by_ranges(input_path, parsed_ranges, split_output_dir)
            elif mode == "count":
                if not pages_per_file or pages_per_file < 1:
                    raise HTTPException(
                        status_code=400,
                        detail="Para o modo 'count', informe um 'pages_per_file' maior que zero.",
                    )
                generated = split_by_page_count(input_path, pages_per_file, split_output_dir)
            elif mode == "size":
                if not target_size_mb or target_size_mb <= 0:
                    raise HTTPException(
                        status_code=400,
                        detail="Para o modo 'size', informe um 'target_size_mb' maior que zero.",
                    )
                generated = split_by_size(input_path, target_size_mb, split_output_dir)
            else:
                raise HTTPException(status_code=400, detail=f"Modo de divisão desconhecido: '{mode}'")

        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Erro ao dividir PDF: {exc}")

        # Se gerou apenas 1 arquivo
        if len(generated) == 1:
            out_single = OUTPUT_DIR / generate_safe_filename(".pdf")
            out_single.write_bytes(generated[0].read_bytes())
            return FileResponse(
                out_single,
                media_type="application/pdf",
                filename=generated[0].name,
            )

        # Se gerou múltiplos arquivos, empacota em ZIP
        zip_path = OUTPUT_DIR / generate_safe_filename(".zip")
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zip_file:
            for g_file in generated:
                zip_file.write(g_file, arcname=g_file.name)

        return FileResponse(
            zip_path,
            media_type="application/zip",
            filename="paginas_divididas.zip",
        )


@app.post("/pdf/organize")
async def organize_endpoint(
    files: list[UploadFile] = File(...),
    mode: str = Form("reorder"),  # reorder, delete, duplicate, reverse, custom
    page_order_str: str | None = Form(None),  # ex: "3,1,2,5,4"
    pages_to_delete_str: str | None = Form(None),  # ex: "2,4"
    duplicate_page_num: int | None = Form(None),
    copies: int = Form(1),
    custom_json: str | None = Form(None),  # JSON string para modo customizado
):
    out_file = OUTPUT_DIR / generate_safe_filename(".pdf")

    with TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        input_files_map: dict[str, Path] = {}

        for seq, uploaded_file in enumerate(files):
            key = uploaded_file.filename or f"doc_{seq}"
            file_p = temp_path / f"{seq:04d}_{key}"
            file_p.write_bytes(await uploaded_file.read())
            try:
                validate_pdf(file_p)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc))
            input_files_map[key] = file_p
            input_files_map[f"file_{seq}"] = file_p

        first_file = list(input_files_map.values())[0]

        try:
            if mode == "reorder":
                if not page_order_str:
                    raise HTTPException(status_code=400, detail="Informe 'page_order_str' (ex: '3,1,2').")
                order = [int(p.strip()) for p in page_order_str.split(",") if p.strip()]
                reorder_pages(first_file, out_file, order)

            elif mode == "delete":
                if not pages_to_delete_str:
                    raise HTTPException(status_code=400, detail="Informe 'pages_to_delete_str' (ex: '2,4').")
                to_delete = [int(p.strip()) for p in pages_to_delete_str.split(",") if p.strip()]
                delete_pages(first_file, out_file, to_delete)

            elif mode == "duplicate":
                if not duplicate_page_num:
                    raise HTTPException(status_code=400, detail="Informe 'duplicate_page_num'.")
                duplicate_page(first_file, out_file, duplicate_page_num, copies)

            elif mode == "reverse":
                reverse_pdf(first_file, out_file)

            elif mode == "custom":
                if not custom_json:
                    raise HTTPException(status_code=400, detail="Informe 'custom_json'.")
                page_items = json.loads(custom_json)
                organize_pdf(input_files_map, page_items, out_file)

            else:
                raise HTTPException(status_code=400, detail=f"Modo de organização desconhecido: '{mode}'")

        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Erro ao organizar PDF: {exc}")

    return FileResponse(
        out_file,
        media_type="application/pdf",
        filename="documento_organizado.pdf",
    )


@app.post("/pdf/rotate")
async def rotate_endpoint(
    file: UploadFile = File(...),
    angle: int = Form(...),  # 90, 180, 270, -90, etc.
    pages_str: str | None = Form(None),  # opcional ex: "1,3,5" ou "1-4"
):
    out_file = OUTPUT_DIR / generate_safe_filename(".pdf")

    with TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        input_path = temp_path / file.filename
        content = await file.read()
        input_path.write_bytes(content)

        try:
            validate_pdf(input_path)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

        pages_list = None
        if pages_str:
            try:
                from pypdf import PdfReader
                reader = PdfReader(input_path)
                pages_list = parse_page_range_string(pages_str, len(reader.pages))
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc))

        try:
            rotate_pdf(input_path, out_file, angle, pages_list)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Erro ao girar PDF: {exc}")

    return FileResponse(
        out_file,
        media_type="application/pdf",
        filename="documento_girado.pdf",
    )


@app.post("/pdf/repair")
async def repair_endpoint(
    file: UploadFile = File(...),
    password: str | None = Form(None),
):
    out_file = OUTPUT_DIR / generate_safe_filename(".pdf")

    with TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        input_path = temp_path / file.filename
        content = await file.read()
        input_path.write_bytes(content)

        try:
            repair_pdf(input_path, out_file, password=password)
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail=f"Não foi possível reparar o PDF: {exc}",
            )

    return FileResponse(
        out_file,
        media_type="application/pdf",
        filename="documento_reparado.pdf",
    )


@app.post("/pdf/number")
async def number_endpoint(
    file: UploadFile = File(...),
    position: str = Form("bottom-center"),
    first_number: int = Form(1),
    template: str = Form("Página {current} de {total}"),
    margin: float = Form(24.0),
    font_name: str = Form("Helvetica"),
    font_size: int = Form(10),
):
    out_file = OUTPUT_DIR / generate_safe_filename(".pdf")

    with TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        input_path = temp_path / file.filename
        content = await file.read()
        input_path.write_bytes(content)

        try:
            validate_pdf(input_path)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

        try:
            add_page_numbers(
                input_file=input_path,
                output_file=out_file,
                position=position,
                first_number=first_number,
                template=template,
                margin=margin,
                font_name=font_name,
                font_size=font_size,
            )
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Erro ao numerar PDF: {exc}")

    return FileResponse(
        out_file,
        media_type="application/pdf",
        filename="documento_numerado.pdf",
    )
