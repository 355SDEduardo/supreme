from __future__ import annotations

import re
from datetime import date

import pymupdf

from .statement_types import ParsedSource, StatementError


def extract_pdf(source: ParsedSource, raw: bytes, start: date, end: date) -> None:
    from .statement_parsers import add_row, digits, is_balance, monetary, normalized, parse_day

    if not raw.startswith(b'%PDF-'):
        raise StatementError('Conteúdo não é um PDF válido.')
    try:
        document = pymupdf.open(stream=raw, filetype='pdf')
    except Exception:
        raise StatementError('Não foi possível ler o PDF.') from None
    with document:
        if document.needs_pass or len(document) > 100:
            raise StatementError('PDF protegido ou com mais de 100 páginas.')
        first = document[0].get_text(sort=True)
        norm = normalized(first)
        sicoob = 'sicoob' in norm
        if sicoob:
            source.bank_code = '756'
            agency = re.search(r'(?:Cooperativa|COOP\.):\s*([\d.-]+)', first, re.I)
        elif 'internet banking empresarial' in norm or 'santander' in norm:
            source.bank_code = '033'
            agency = re.search(r'Ag[eê]ncia:?\s*([\d.-]+)', first, re.I)
        else:
            raise StatementError('Layout PDF não reconhecido. Suportados: Santander e Sicoob das amostras.')
        account = re.search(r'Conta:?\s*([\d.-]+)', first, re.I)
        source.agency = digits(agency[1]) if agency else ''
        source.account = digits(account[1]) if account else ''
        period = re.search(r'Per[ií]odos?:?\s*(\d{2}/\d{2}/\d{4})\s*[-a]\s*(\d{2}/\d{2}/\d{4})', first, re.I)
        if period:
            start, _ = parse_day(period[1], start, end)
            end, _ = parse_day(period[2], start, end)
        date_pattern = r'\d{2}/\d{2}' if sicoob else r'\d{2}/\d{2}/\d{4}'
        amount_pattern = re.compile(r'^(-?)(?:R\$)?(\d[\d.]*,\d{2})([CD*]?)$')
        history_x, document_x = None, None
        for page_no, page in enumerate(document, 1):
            words = page.get_text('words')
            if not words:
                raise StatementError(f'Página {page_no} sem texto; forneça PDF digital. OCR não aplicado.')
            headers = [w for w in words if re.sub(r'[^a-z]', '', normalized(w[4])) == 'data'
                       and w[0] < page.rect.width * .3
                       and any(normalized(v[4]).startswith('hist') and abs(v[1] - w[1]) < 8 for v in words)]
            table_top = headers[0][3] if headers else 0
            header_words = [w for w in words if headers and abs(w[1] - headers[0][1]) < 8]
            for word in header_words:
                text = re.sub(r'[^a-z]', '', normalized(word[4]))
                if text.startswith('hist'):
                    history_x = word[0] - 5
                elif text == 'documento':
                    document_x = word[0] - 5
            dates = sorted([w for w in words if re.fullmatch(date_pattern, w[4])
                            and w[0] < page.rect.width * .25 and w[1] >= table_top
                            and (history_x is None or w[2] <= history_x + 3)], key=lambda w: w[1])
            if not dates:
                # A no-movement document is not a valid source for inventing transactions.
                continue
            money_words = [w for w in words if amount_pattern.fullmatch(w[4])
                           and w[0] > page.rect.width * .45 and (w[1] + w[3]) / 2 >= table_top]
            # Row boundaries in desktop Santander are drawn explicitly, preserving wrapped descriptions.
            separators = set()
            if not sicoob:
                for drawing in page.get_drawings():
                    for item in drawing['items']:
                        if item[0] == 'l' and abs(item[1].y - item[2].y) < 1 and abs(item[1].x - item[2].x) > page.rect.width * .5:
                            separators.add(item[1].y)
            for index, anchor in enumerate(dates):
                center = (anchor[1] + anchor[3]) / 2
                if sicoob:
                    top = anchor[1] - 1
                    bottom = dates[index + 1][1] - 1 if index + 1 < len(dates) else page.rect.height - 20
                else:
                    lower = [y for y in separators if y < center]
                    upper = [y for y in separators if y > center]
                    top = max(lower) if lower else ((dates[index - 1][3] + anchor[1]) / 2 if index else anchor[1] - 10)
                    bottom = min(upper) if upper else ((anchor[3] + dates[index + 1][1]) / 2 if index + 1 < len(dates) else anchor[3] + 10)
                if sicoob:
                    values = [w for w in money_words if abs((w[1] + w[3]) / 2 - center) < 12
                              and index == min(range(len(dates)), key=lambda n: abs((dates[n][1] + dates[n][3]) / 2 - (w[1] + w[3]) / 2))]
                else:
                    values = [w for w in money_words if top <= (w[1] + w[3]) / 2 < bottom]
                if not values:
                    raise StatementError(f'Página {page_no}, movimento {index + 1}: valor não identificado.')
                value = min(values, key=lambda w: w[0])  # Value column, never the following balance column.
                value_match = amount_pattern.fullmatch(value[4])
                left = history_x if history_x is not None else anchor[2] + 2
                right = document_x if document_x and document_x > left else min(w[0] for w in money_words) - 3
                content = [w for w in words if left <= w[0] < right and top <= (w[1] + w[3]) / 2 < bottom]
                content.sort(key=lambda w: (round(w[1] / 3), w[0]))
                description = ' '.join(w[4] for w in content)
                if is_balance(description):
                    source.excluded_balances += 1
                    continue
                # Sicoob prints zero-value balance annotations (SALDO BLOQ...) with '*'.
                if value_match[3] == '*' and 'saldo' in normalized(description):
                    source.excluded_balances += 1
                    continue
                marker = value_match[3]
                if sicoob and marker not in {'C', 'D'}:
                    markers = [w[4] for w in words if w[4] in {'C', 'D'} and w[0] >= value[0]
                               and abs((w[1] + w[3]) / 2 - center) < 12]
                    # Mobile Sicoob prints the C/D marker after the date or near the
                    # right edge, while the amount itself can sit slightly above it.
                    if not markers:
                        markers = [w[4] for w in words if w[4] in {'C', 'D'}
                                   and w[0] > page.rect.width * .7
                                   and abs((w[1] + w[3]) / 2 - center) < 18]
                    if len(markers) != 1:
                        raise StatementError(f'Página {page_no}: indicador C/D ausente ou ambíguo.')
                    marker = markers[0]
                negative = value_match[1] or any(w[4] == '-' and 0 <= value[0] - w[2] < 30
                                                and abs(w[1] - value[1]) < 3 for w in words)
                direction = 'saida' if negative or marker == 'D' else 'entrada'
                day, date_score = parse_day(anchor[4], start, end)
                reference = ''
                if document_x:
                    refs = [w[4] for w in words if w[0] >= document_x and w[2] < value[0]
                            and top <= (w[1] + w[3]) / 2 < bottom and w[4].isdigit()]
                    if len(refs) == 1:
                        reference = refs[0]
                add_row(source, f'página {page_no}, movimento {index + 1}', day, monetary(value_match[2]),
                        direction, description, (date_score, 90, 100 if marker else 90), reference,
                        'document' if reference else 'none')
        if not source.rows:
            raise StatementError('PDF sem movimentações reconhecidas; nenhum lançamento foi presumido.')
