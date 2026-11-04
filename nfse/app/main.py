"""
Servidor FastAPI da Aplicação de Extração, Armazenamento e Análise de NFS-e Nacional.
Oferece API REST completa, documentação Swagger (/docs) e entrega do Dashboard Web.
"""

import io
import zipfile
from pathlib import Path
from typing import List, Optional
from datetime import datetime

from fastapi import FastAPI, UploadFile, File, HTTPException, Query, Response
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from app.models import NFSNacionalModel
from app.parser import NFSeNacionalParser
from app.storage import JSONStorage
from app.exporter import NFSeExporter
from app.sample_generator import SAMPLE_FILES
from app.retencoes import build_retention_report, get_retention_amounts

app = FastAPI(
    title="NFS-e Nacional Intelligence Suite",
    description="Sistema corporativo de extração, auditoria fiscal, armazenamento JSON e exportação de NFS-e (Padrão Nacional RFB/SPED).",
    version="1.0.0",
)

# Habilitar CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Inicializar storage
storage = JSONStorage()

# Diretórios estáticos
BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)


@app.get("/api/health")
async def health_check():
    return {
        "status": "online",
        "service": "NFS-e Nacional Intelligence Suite",
        "version": "1.0.0",
        "timestamp": datetime.now().isoformat(),
        "total_notes": len(storage.get_all_notes()),
    }


@app.get("/api/dashboard/stats")
async def get_dashboard_stats():
    """Retorna KPIs contábeis e consolidações analíticas para o dashboard."""
    return storage.get_kpis_and_analytics()


@app.get("/api/retencoes")
async def get_retention_report(
    competencia: Optional[str] = Query(
        None,
        pattern=r"^[0-9]{4}-(0[1-9]|1[0-2])$",
        description="Competência da nota no formato AAAA-MM; omita para consultar todas.",
    ),
):
    """Retenções por tributo e nota, com totais do período selecionado."""
    if competencia and competencia.startswith("0000-"):
        raise HTTPException(status_code=422, detail="O ano da competência deve ser maior que zero.")
    return build_retention_report(storage.get_all_notes(), competencia)


@app.get("/api/notes")
async def list_notes(
    search: Optional[str] = Query(None, description="Busca textual por chave, número, tomador ou descrição"),
    status_conciliacao: Optional[str] = Query(None, description="Filtro por status: CONCILIADO, ALERTA, INCONSISTENTE"),
    retencao: Optional[str] = Query(None, description="Filtro por retenção: com_retencao, sem_retencao"),
    municipio: Optional[str] = Query(None, description="Filtro por município"),
):
    """Lista todas as notas fiscais cadastradas com filtros opcionais."""
    notes = storage.get_all_notes()

    # Aplicação de filtros
    if search:
        s = search.lower().strip()
        filtered = []
        for n in notes:
            haystack = f"{n.chave_nfse} {n.numero_nfse} {n.emitente.razao_social or ''} {n.tomador.razao_social or ''} {n.tomador.cnpj or ''} {n.tomador.cpf or ''} {n.local_prestacao} {n.descricao_servico}".lower()
            if s in haystack:
                filtered.append(n)
        notes = filtered

    if status_conciliacao:
        notes = [n for n in notes if n.auditoria.status_conciliacao.upper() == status_conciliacao.upper()]

    if retencao == "com_retencao":
        notes = [n for n in notes if n.valor_total_retencoes > 0]
    elif retencao == "sem_retencao":
        notes = [n for n in notes if n.valor_total_retencoes == 0]

    if municipio:
        m = municipio.lower()
        notes = [n for n in notes if m in (n.local_prestacao or "").lower() or m in (n.local_incidencia or "").lower()]

    # Retorna resumo de cada nota para a tabela
    return [n.model_dump(mode="json") for n in notes]


@app.get("/api/notes/{chave}")
async def get_note_detail(chave: str):
    """Retorna o JSON completo e estruturado de uma nota fiscal."""
    note = storage.get_note_by_key(chave)
    if not note:
        raise HTTPException(status_code=404, detail="Nota fiscal não encontrada.")
    return note.model_dump(mode="json")


@app.get("/api/notes/{chave}/xml")
async def download_note_xml(chave: str):
    """Permite baixar o arquivo XML original da NFS-e."""
    clean_key = "".join(c for c in chave if c.isalnum() or c in ("-", "_"))
    xml_path = storage.xml_dir / f"{clean_key}.xml"
    if not xml_path.exists():
        raise HTTPException(status_code=404, detail="Arquivo XML original não disponível no servidor.")

    with open(xml_path, "rb") as f:
        xml_data = f.read()

    return Response(
        content=xml_data,
        media_type="application/xml",
        headers={"Content-Disposition": f"attachment; filename={clean_key}.xml"},
    )


@app.post("/api/upload")
async def upload_xml_files(files: List[UploadFile] = File(...)):
    """
    Recebe arquivos XML individuais ou pacotes ZIP contendo múltiplos XMLs.
    Executa o parser, audita as notas e persiste os arquivos .json.
    """
    success_count = 0
    errors = []
    processed_notes = []

    for file in files:
        filename = file.filename or "upload.xml"
        content = await file.read()

        if filename.lower().endswith(".zip"):
            # Trata arquivo ZIP contendo múltiplos XMLs
            try:
                with zipfile.ZipFile(io.BytesIO(content)) as zf:
                    for zip_info in zf.infolist():
                        if zip_info.filename.lower().endswith(".xml") and not zip_info.filename.startswith("__MACOSX"):
                            xml_bytes = zf.read(zip_info.filename)
                            try:
                                note = NFSeNacionalParser.parse(xml_bytes, filename=zip_info.filename)
                                storage.save_note(note, xml_bytes=xml_bytes)
                                success_count += 1
                                processed_notes.append(note.chave_nfse)
                            except Exception as e:
                                errors.append(f"{zip_info.filename}: {str(e)}")
            except Exception as e:
                errors.append(f"{filename} (ZIP corrompido): {str(e)}")
        else:
            # Arquivo XML isolado
            try:
                note = NFSeNacionalParser.parse(content, filename=filename)
                storage.save_note(note, xml_bytes=content)
                success_count += 1
                processed_notes.append(note.chave_nfse)
            except Exception as e:
                errors.append(f"{filename}: {str(e)}")

    return {
        "success": True,
        "processed_count": success_count,
        "error_count": len(errors),
        "errors": errors[:20],
        "processed_keys": processed_notes,
    }


@app.post("/api/load-samples")
async def load_sample_data():
    """Carrega as 4 notas fiscais de amostra oficiais documentadas nas instruções."""
    count = 0
    for filename, xml_text in SAMPLE_FILES.items():
        xml_bytes = xml_text.strip().encode("utf-8")
        note = NFSeNacionalParser.parse(xml_bytes, filename=filename)
        storage.save_note(note, xml_bytes=xml_bytes)
        count += 1

    return {
        "success": True,
        "message": f"{count} notas de exemplo carregadas e salvas em .json com sucesso!",
        "stats": storage.get_kpis_and_analytics(),
    }


@app.delete("/api/notes/{chave}")
async def delete_single_note(chave: str):
    """Remove uma nota fiscal da base e apaga seus arquivos .json e .xml."""
    success = storage.delete_note(chave)
    if not success:
        raise HTTPException(status_code=404, detail="Nota não encontrada.")
    return {"success": True, "message": "Nota removida com sucesso."}


@app.delete("/api/notes")
async def clear_database():
    """Limpa todas as notas fiscais cadastradas."""
    storage.clear_all()
    return {"success": True, "message": "Base de dados e arquivos JSON limpos com sucesso."}


@app.get("/api/export/excel")
async def export_to_excel():
    """Gera e faz download da planilha Excel com 4 abas e formatação profissional."""
    notes = storage.get_all_notes()
    if not notes:
        raise HTTPException(status_code=400, detail="Não há notas fiscais cadastradas para exportação.")

    excel_bytes = NFSeExporter.generate_excel(notes)
    filename = f"Relatorio_NFSe_Nacional_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"

    return StreamingResponse(
        io.BytesIO(excel_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@app.get("/api/export/csv")
async def export_to_csv():
    """Gera e faz download do arquivo CSV consolidado formatado para Excel PT-BR."""
    notes = storage.get_all_notes()
    if not notes:
        raise HTTPException(status_code=400, detail="Não há notas fiscais cadastradas para exportação.")

    csv_bytes = NFSeExporter.generate_csv(notes)
    filename = f"Extrato_NFSe_Nacional_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

    return Response(
        content=csv_bytes,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@app.get("/api/export/json")
async def export_consolidated_json():
    """Exporta arquivo JSON consolidado de todas as notas."""
    notes = storage.get_all_notes()
    notes_json = [
        {
            **n.model_dump(mode="json"),
            "retencoes": {field: float(amount) for field, amount in get_retention_amounts(n).items()},
        }
        for n in notes
    ]
    data = {
        "metadata": {
            "gerado_em": datetime.now().isoformat(),
            "padrao": "NFS-e Nacional RFB/SPED v1.01",
            "total_notas": len(notes),
        },
        "notas": notes_json,
    }
    filename = f"Consolidado_NFSe_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    return JSONResponse(
        content=data,
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# Montagem dos arquivos estáticos para o Dashboard Web
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/", response_class=HTMLResponse)
async def serve_dashboard():
    index_path = STATIC_DIR / "index.html"
    if index_path.exists():
        with open(index_path, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>Dashboard em inicialização...</h1>"
