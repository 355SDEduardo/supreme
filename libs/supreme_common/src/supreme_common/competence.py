from datetime import date, datetime
import re

def normalize_competencia(value) -> str:
    if isinstance(value, (datetime, date)):
        return value.strftime('%Y-%m')
    text = str(value).strip()
    if re.fullmatch(r'\d{2}/\d{4}', text):
        month, year = text.split('/')
    elif re.fullmatch(r'\d{2}-\d{4}', text):
        month, year = text.split('-')
    elif re.fullmatch(r'\d{4}/\d{2}', text):
        year, month = text.split('/')
    elif re.fullmatch(r'\d{2}/\d{2}/\d{4}', text):
        day, month, year = text.split('/')
        date(int(year),int(month),int(day))
    elif re.match(r'^\d{4}-\d{2}(?:$|[T -]|-\d{2})', text):
        year, month = text[:7].split('-')
    else:
        raise ValueError('Competência deve estar em YYYY-MM ou MM/YYYY.')
    return date(int(year), int(month), 1).strftime('%Y-%m')

def format_competencia_display(value) -> str:
    year, month = normalize_competencia(value).split('-')
    return f'{month}/{year}'
