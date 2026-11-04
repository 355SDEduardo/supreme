from __future__ import annotations

from io import BytesIO
from typing import Any

try:
    import pymupdf as fitz
except ImportError:  # pragma: no cover - fallback depends on the environment
    try:
        import fitz  # type: ignore[no-redef]
    except ImportError:
        fitz = None  # type: ignore[assignment]

try:
    import pypdf
except ImportError:  # pragma: no cover - reported at runtime
    pypdf = None


MAX_PDF_PAGES = 300
MAX_PRODUCTS = 10_000


def read_product_list(content: bytes) -> list[str]:
    text: str | None = None
    for encoding in ("utf-8-sig", "latin-1", "cp1252"):
        try:
            text = content.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        raise ValueError("Não foi possível ler o TXT nas codificações suportadas.")

    products = [
        line.strip()
        for line in text.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    if not products:
        raise ValueError("O TXT não contém produtos para comparar.")
    if len(products) > MAX_PRODUCTS:
        raise ValueError(f"O TXT excede o limite de {MAX_PRODUCTS} produtos.")
    return products


def extract_pdf_pages(content: bytes) -> list[tuple[int, str]]:
    pymupdf_error: Exception | None = None
    if fitz is not None:
        try:
            with fitz.open(stream=content, filetype="pdf") as document:
                if document.page_count > MAX_PDF_PAGES:
                    raise ValueError(
                        f"O PDF excede o limite de {MAX_PDF_PAGES} páginas."
                    )
                return [
                    (index + 1, page.get_text("text") or "")
                    for index, page in enumerate(document)
                ]
        except ValueError:
            raise
        except Exception as exc:  # fallback is intentional
            pymupdf_error = exc

    if pypdf is not None:
        try:
            reader = pypdf.PdfReader(BytesIO(content))
            if len(reader.pages) > MAX_PDF_PAGES:
                raise ValueError(
                    f"O PDF excede o limite de {MAX_PDF_PAGES} páginas."
                )
            return [
                (index + 1, page.extract_text() or "")
                for index, page in enumerate(reader.pages)
            ]
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError("Não foi possível extrair texto do PDF informado.") from exc

    if pymupdf_error is not None:
        raise ValueError("Não foi possível extrair texto do PDF informado.") from pymupdf_error
    raise RuntimeError("Nenhuma biblioteca de leitura de PDF está instalada.")


def compare_products_to_pdf(
    txt_content: bytes,
    pdf_content: bytes,
    *,
    txt_filename: str,
    pdf_filename: str,
) -> dict[str, Any]:
    products = read_product_list(txt_content)
    pages = extract_pdf_pages(pdf_content)
    searchable_pages = [
        (number, text, text.casefold(), text.splitlines())
        for number, text in pages
    ]

    found: list[dict[str, Any]] = []
    missing: list[dict[str, str]] = []
    for product in products:
        needle = product.casefold()
        match: dict[str, Any] | None = None
        for page_number, _text, folded, lines in searchable_pages:
            if needle not in folded:
                continue
            excerpt = next(
                (line.strip() for line in lines if needle in line.casefold()),
                "",
            )
            match = {
                "produto": product,
                "pagina": page_number,
                "trecho_pdf": excerpt,
            }
            break
        if match is None:
            missing.append({"produto": product})
        else:
            found.append(match)

    return {
        "encontrados": found,
        "nao_encontrados": missing,
        "resumo": {
            "total_txt": len(products),
            "total_encontrados": len(found),
            "total_nao_encontrados": len(missing),
            "arquivo_txt": txt_filename,
            "arquivo_pdf": pdf_filename,
        },
    }


def text_report(result: dict[str, Any]) -> bytes:
    summary = result["resumo"]
    lines = [
        "RELATÓRIO DE CONFERÊNCIA DE PRODUTOS: TXT vs PDF",
        "=" * 62,
        f"Arquivo TXT: {summary['arquivo_txt']}",
        f"Arquivo PDF: {summary['arquivo_pdf']}",
        f"Total de produtos: {summary['total_txt']}",
        f"Encontrados: {summary['total_encontrados']}",
        f"Não encontrados: {summary['total_nao_encontrados']}",
        "",
        "PRODUTOS ENCONTRADOS",
    ]
    lines.extend(
        f"- {item['produto']} | página {item['pagina']} | {item['trecho_pdf']}"
        for item in result["encontrados"]
    )
    lines.extend(["", "PRODUTOS NÃO ENCONTRADOS"])
    lines.extend(f"- {item['produto']}" for item in result["nao_encontrados"])
    return ("\n".join(lines) + "\n").encode("utf-8")
