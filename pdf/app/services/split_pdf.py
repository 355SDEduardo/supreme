from io import BytesIO
from pathlib import Path
from pypdf import PdfReader, PdfWriter


def split_every_page(
    input_file: str | Path,
    output_directory: str | Path,
) -> list[Path]:
    input_path = Path(input_file)
    output_dir = Path(output_directory)
    output_dir.mkdir(parents=True, exist_ok=True)

    reader = PdfReader(input_path)
    generated_files: list[Path] = []

    for index, page in enumerate(reader.pages, start=1):
        writer = PdfWriter()
        writer.add_page(page)

        output_path = output_dir / f"pagina_{index:04d}.pdf"

        with output_path.open("wb") as output:
            writer.write(output)

        writer.close()
        generated_files.append(output_path)

    return generated_files


def extract_page_range(
    input_file: str | Path,
    output_file: str | Path,
    first_page: int,
    last_page: int,
) -> Path:
    reader = PdfReader(input_file)
    total_pages = len(reader.pages)

    if first_page < 1:
        raise ValueError("A primeira página deve ser maior ou igual a 1.")

    if last_page > total_pages:
        raise ValueError(f"O documento possui somente {total_pages} páginas.")

    if first_page > last_page:
        raise ValueError("A primeira página não pode ser maior que a última.")

    writer = PdfWriter()

    for page_number in range(first_page - 1, last_page):
        writer.add_page(reader.pages[page_number])

    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("wb") as output:
        writer.write(output)

    writer.close()
    return output_path


def split_by_ranges(
    input_file: str | Path,
    ranges: list[tuple[int, int]],
    output_directory: str | Path,
) -> list[Path]:
    reader = PdfReader(input_file)
    total_pages = len(reader.pages)

    output_dir = Path(output_directory)
    output_dir.mkdir(parents=True, exist_ok=True)

    generated: list[Path] = []

    for sequence, (start, end) in enumerate(ranges, start=1):
        if start < 1 or end > total_pages or start > end:
            raise ValueError(
                f"Intervalo inválido: {start}-{end}. O documento tem {total_pages} páginas."
            )

        writer = PdfWriter()

        for index in range(start - 1, end):
            writer.add_page(reader.pages[index])

        output_path = output_dir / f"parte_{sequence:02d}_paginas_{start}_a_{end}.pdf"

        with output_path.open("wb") as output:
            writer.write(output)

        writer.close()
        generated.append(output_path)

    return generated


def split_by_page_count(
    input_file: str | Path,
    pages_per_file: int,
    output_directory: str | Path,
) -> list[Path]:
    if pages_per_file < 1:
        raise ValueError("A quantidade de páginas por arquivo deve ser maior que zero.")

    reader = PdfReader(input_file)
    output_dir = Path(output_directory)
    output_dir.mkdir(parents=True, exist_ok=True)

    generated: list[Path] = []
    total_pages = len(reader.pages)

    for group_start in range(0, total_pages, pages_per_file):
        writer = PdfWriter()
        group_end = min(group_start + pages_per_file, total_pages)

        for index in range(group_start, group_end):
            writer.add_page(reader.pages[index])

        output_path = output_dir / f"paginas_{group_start + 1}_a_{group_end}.pdf"

        with output_path.open("wb") as output:
            writer.write(output)

        writer.close()
        generated.append(output_path)

    return generated


def split_by_size(
    input_file: str | Path,
    target_size_mb: float,
    output_directory: str | Path,
) -> list[Path]:
    if target_size_mb <= 0:
        raise ValueError("O tamanho alvo em MB deve ser maior que zero.")

    target_bytes = target_size_mb * 1024 * 1024
    reader = PdfReader(input_file)
    output_dir = Path(output_directory)
    output_dir.mkdir(parents=True, exist_ok=True)

    generated: list[Path] = []
    total_pages = len(reader.pages)

    current_writer = PdfWriter()
    current_start = 1
    file_sequence = 1

    for index, page in enumerate(reader.pages, start=1):
        current_writer.add_page(page)

        buf = BytesIO()
        current_writer.write(buf)
        size = buf.tell()

        if size > target_bytes and len(current_writer.pages) > 1:
            # Revert last page from this file, write current file, start new
            new_writer = PdfWriter()
            for p in current_writer.pages[:-1]:
                new_writer.add_page(p)

            end_page = index - 1
            output_path = output_dir / f"parte_{file_sequence:02d}_paginas_{current_start}_a_{end_page}.pdf"
            with output_path.open("wb") as out:
                new_writer.write(out)
            new_writer.close()
            generated.append(output_path)

            file_sequence += 1
            current_start = index

            current_writer = PdfWriter()
            current_writer.add_page(page)

    if len(current_writer.pages) > 0:
        end_page = total_pages
        output_path = output_dir / f"parte_{file_sequence:02d}_paginas_{current_start}_a_{end_page}.pdf"
        with output_path.open("wb") as out:
            current_writer.write(out)
        current_writer.close()
        generated.append(output_path)

    return generated
