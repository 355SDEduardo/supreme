from io import BytesIO
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas


def create_number_overlay(
    width: float,
    height: float,
    text: str,
    position: str = "bottom-center",
    margin: float = 24,
    font_name: str = "Helvetica",
    font_size: int = 10,
) -> BytesIO:
    buffer = BytesIO()
    pdf_canvas = canvas.Canvas(
        buffer,
        pagesize=(width, height),
    )

    pdf_canvas.setFont(font_name, font_size)

    if position == "bottom-left":
        x = margin
        y = margin
        pdf_canvas.drawString(x, y, text)

    elif position == "bottom-center":
        x = width / 2
        y = margin
        pdf_canvas.drawCentredString(x, y, text)

    elif position == "bottom-right":
        x = width - margin
        y = margin
        pdf_canvas.drawRightString(x, y, text)

    elif position == "top-left":
        x = margin
        y = height - margin
        pdf_canvas.drawString(x, y, text)

    elif position == "top-center":
        x = width / 2
        y = height - margin
        pdf_canvas.drawCentredString(x, y, text)

    elif position == "top-right":
        x = width - margin
        y = height - margin
        pdf_canvas.drawRightString(x, y, text)

    else:
        raise ValueError(f"Posição de numeração inválida: {position}")

    pdf_canvas.save()
    buffer.seek(0)

    return buffer


def add_page_numbers(
    input_file: str | Path,
    output_file: str | Path,
    position: str = "bottom-center",
    first_number: int = 1,
    template: str = "Página {current} de {total}",
    margin: float = 24,
    font_name: str = "Helvetica",
    font_size: int = 10,
) -> Path:
    reader = PdfReader(input_file)
    writer = PdfWriter()

    total_pages = len(reader.pages)

    for index, page in enumerate(reader.pages):
        current_number = first_number + index

        text = template.format(
            current=current_number,
            total=first_number + total_pages - 1,
            document_total=total_pages,
        )

        width = float(page.mediabox.width)
        height = float(page.mediabox.height)

        overlay_buffer = create_number_overlay(
            width=width,
            height=height,
            text=text,
            position=position,
            margin=margin,
            font_name=font_name,
            font_size=font_size,
        )

        overlay_reader = PdfReader(overlay_buffer)
        overlay_page = overlay_reader.pages[0]

        writer.add_page(page)
        writer.pages[index].merge_page(overlay_page)


    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("wb") as output:
        writer.write(output)

    writer.close()
    return output_path
