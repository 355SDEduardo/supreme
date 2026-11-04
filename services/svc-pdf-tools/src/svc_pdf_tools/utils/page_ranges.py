def parse_page_range_string(range_str: str, total_pages: int) -> list[int]:
    """
    Parses a page range string (e.g. "1-3, 5, 8-10") into a sorted list of 1-based page numbers.
    """
    if not range_str or not range_str.strip():
        return list(range(1, total_pages + 1))

    pages: set[int] = set()
    parts = range_str.split(",")

    for part in parts:
        part = part.strip()
        if not part:
            continue

        if "-" in part:
            subparts = part.split("-")
            if len(subparts) != 2:
                raise ValueError(f"Sintaxe de intervalo inválida: '{part}'")
            try:
                start = int(subparts[0].strip())
                end = int(subparts[1].strip())
            except ValueError as exc:
                raise ValueError(f"Número de página inválido no intervalo '{part}'") from exc

            if start < 1 or end > total_pages or start > end:
                raise ValueError(
                    f"Intervalo de páginas fora dos limites (1-{total_pages}): {start}-{end}"
                )
            pages.update(range(start, end + 1))
        else:
            try:
                page_num = int(part)
            except ValueError as exc:
                raise ValueError(f"Número de página inválido: '{part}'") from exc

            if page_num < 1 or page_num > total_pages:
                raise ValueError(
                    f"Página {page_num} fora do limite do documento (1-{total_pages})."
                )
            pages.add(page_num)

    return sorted(pages)


def validate_ranges(ranges: list[tuple[int, int]], total_pages: int) -> None:
    for start, end in ranges:
        if start < 1 or end > total_pages or start > end:
            raise ValueError(
                f"Intervalo inválido: {start}-{end}. O documento possui {total_pages} páginas."
            )
