from pathlib import Path
from pypdf import PdfReader, PdfWriter

VALID_ROTATIONS = {90, 180, 270, -90, -180, -270, 0, 360}


def rotate_pdf(
    input_file: str | Path,
    output_file: str | Path,
    angle: int,
    pages: list[int] | None = None,
) -> Path:
    if angle not in VALID_ROTATIONS:
        raise ValueError(
            "O ângulo de rotação deve ser 90, 180, 270, -90, -180 ou -270."
        )

    reader = PdfReader(input_file)
    writer = PdfWriter()

    selected_indexes = None
    if pages is not None:
        selected_indexes = {page - 1 for page in pages}

    for index, page in enumerate(reader.pages):
        if selected_indexes is None or index in selected_indexes:
            page.rotate(angle)

        writer.add_page(page)

    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("wb") as output:
        writer.write(output)

    writer.close()
    return output_path
