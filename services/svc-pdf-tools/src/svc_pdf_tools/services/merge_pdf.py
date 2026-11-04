from pathlib import Path
from pypdf import PdfReader, PdfWriter


def merge_pdfs(
    input_files: list[str | Path],
    output_file: str | Path,
    passwords: dict[str, str] | None = None,
) -> Path:
    if len(input_files) < 2:
        raise ValueError("Informe pelo menos dois arquivos PDF para mesclar.")

    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    passwords = passwords or {}
    writer = PdfWriter()

    try:
        for file_path in input_files:
            path = Path(file_path)

            if not path.exists():
                raise FileNotFoundError(f"Arquivo não encontrado: {path}")

            if path.suffix.lower() != ".pdf":
                raise ValueError(f"O arquivo não é PDF: {path.name}")

            reader = PdfReader(path)

            if reader.is_encrypted:
                file_pwd = passwords.get(str(path)) or passwords.get(path.name)
                if file_pwd:
                    decrypted = reader.decrypt(file_pwd)
                    if decrypted == 0:
                        raise ValueError(f"Senha incorreta para o arquivo: {path.name}")
                else:
                    raise ValueError(f"O arquivo {path.name} está protegido por senha.")

            writer.append(reader)

        with output_path.open("wb") as output:
            writer.write(output)

    finally:
        writer.close()

    return output_path


def merge_selected_pages(
    selections: list[tuple[str | Path, list[int]]],
    output_file: str | Path,
) -> Path:
    """
    `selections`: Lista de tuplas (caminho_do_arquivo, lista_de_indices_de_paginas_0_indexed).
    """
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    writer = PdfWriter()

    try:
        for filename, pages in selections:
            path = Path(filename)
            if not path.exists():
                raise FileNotFoundError(f"Arquivo não encontrado: {path}")

            writer.append(path, pages=pages)

        with output_path.open("wb") as output:
            writer.write(output)
    finally:
        writer.close()

    return output_path
