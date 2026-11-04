from pathlib import Path
import pymupdf


def reorder_pages(
    input_file: str | Path,
    output_file: str | Path,
    page_order: list[int],
) -> Path:
    source = pymupdf.open(input_file)
    result = pymupdf.open()

    try:
        total_pages = source.page_count

        for page_number in page_order:
            if page_number < 1 or page_number > total_pages:
                raise ValueError(
                    f"Página inválida: {page_number}. O documento possui {total_pages} páginas."
                )

            index = page_number - 1
            result.insert_pdf(
                source,
                from_page=index,
                to_page=index,
            )

        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        result.save(
            output_path,
            garbage=4,
            deflate=True,
        )

        return output_path

    finally:
        result.close()
        source.close()


def delete_pages(
    input_file: str | Path,
    output_file: str | Path,
    pages_to_delete: list[int],
) -> Path:
    document = pymupdf.open(input_file)

    try:
        total_pages = document.page_count
        indexes = sorted(
            {page - 1 for page in pages_to_delete},
            reverse=True,
        )

        for index in indexes:
            if index < 0 or index >= total_pages:
                raise ValueError(f"Página inválida para exclusão: {index + 1}")

            document.delete_page(index)

        if document.page_count == 0:
            raise ValueError("Não é possível excluir todas as páginas do PDF.")

        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        document.save(
            output_path,
            garbage=4,
            deflate=True,
        )

        return output_path

    finally:
        document.close()


def duplicate_page(
    input_file: str | Path,
    output_file: str | Path,
    page_number: int,
    copies: int = 1,
) -> Path:
    if copies < 1:
        raise ValueError("O número de cópias deve ser pelo menos 1.")

    document = pymupdf.open(input_file)

    try:
        index = page_number - 1

        if index < 0 or index >= document.page_count:
            raise ValueError(f"Página inexistente: {page_number}")

        for _ in range(copies):
            document.fullcopy_page(
                index,
                to=index + 1,
            )

        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        document.save(
            output_path,
            garbage=4,
            deflate=True,
        )

        return output_path

    finally:
        document.close()


def reverse_pdf(input_file: str | Path, output_file: str | Path) -> Path:
    source = pymupdf.open(input_file)
    result = pymupdf.open()

    try:
        result.insert_pdf(
            source,
            from_page=source.page_count - 1,
            to_page=0,
        )

        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        result.save(
            output_path,
            garbage=4,
            deflate=True,
        )

        return output_path

    finally:
        result.close()
        source.close()


def organize_pdf(
    input_files: dict[str, str | Path],
    page_items: list[dict],
    output_file: str | Path,
) -> Path:
    """
    `input_files`: dicionário identificador -> caminho_do_arquivo (ex: {"doc1": "path/a.pdf"})
    `page_items`: lista de dicts com keys:
        - "source": id do documento
        - "page": número de página 1-indexed
        - "rotation": rotação em graus (0, 90, 180, 270, etc. opcional)
    """
    opened_docs: dict[str, pymupdf.Document] = {}
    for key, path in input_files.items():
        opened_docs[key] = pymupdf.open(path)

    result = pymupdf.open()

    try:
        for item in page_items:
            source_id = item.get("source")
            page_num = item.get("page")
            rotation = item.get("rotation", 0)

            if source_id not in opened_docs:
                raise ValueError(f"Documento de origem '{source_id}' não fornecido.")

            doc = opened_docs[source_id]
            if page_num < 1 or page_num > doc.page_count:
                raise ValueError(
                    f"Página {page_num} inválida para o documento '{source_id}'."
                )

            index = page_num - 1
            start_index = result.page_count
            result.insert_pdf(doc, from_page=index, to_page=index)

            if rotation:
                new_page = result[start_index]
                new_page.set_rotation((new_page.rotation + rotation) % 360)

        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        result.save(
            output_path,
            garbage=4,
            deflate=True,
        )

        return output_path

    finally:
        result.close()
        for doc in opened_docs.values():
            doc.close()
