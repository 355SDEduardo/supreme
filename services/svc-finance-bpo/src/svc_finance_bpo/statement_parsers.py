"""Deterministic extraction; no model is allowed to infer dates, amounts or direction."""
from __future__ import annotations

import csv
import hashlib
import io
import re
import unicodedata
import zipfile
from datetime import date, datetime
from decimal import Decimal
from pathlib import PurePath

import openpyxl
from pydantic import ValidationError
from supreme_common.monetary import parse_br_number

from .statement_types import Candidate, ParsedSource, StatementError

MAX_ROWS = 5000
MAX_FILE_BYTES = 10 * 1024 * 1024


def normalized(text: object) -> str:
    return ''.join(c for c in unicodedata.normalize('NFKD', str(text or '').lower())
                   if not unicodedata.combining(c)).strip()


def digits(value: object) -> str:
    value = re.sub(r'\D', '', str(value or ''))
    return value.lstrip('0') or ('0' if value else '')


def is_balance(description: str) -> bool:
    return bool(re.match(r'^(?:\d+\s+)?(?:saldo\b|saldos\b|total\b|totais\b)', normalized(description)))


def decode(data: bytes) -> str:
    for encoding in ('utf-8-sig', 'cp1252', 'latin1'):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise StatementError('Codificação de texto não reconhecida.')


def parse_day(value: object, start: date, end: date) -> tuple[date, int]:
    if isinstance(value, datetime):
        return value.date(), 100
    if isinstance(value, date):
        return value, 100
    text = str(value).strip()
    try:
        if re.fullmatch(r'\d{4}-\d{2}-\d{2}', text):
            return date.fromisoformat(text), 98
        if re.fullmatch(r'\d{2}/\d{2}/\d{4}', text):
            return datetime.strptime(text, '%d/%m/%Y').date(), 98
        if re.fullmatch(r'\d{2}/\d{2}', text):
            possible = []
            for year in range(start.year, end.year + 1):
                try:
                    day = datetime.strptime(f'{text}/{year}', '%d/%m/%Y').date()
                except ValueError:
                    continue
                if start <= day <= end:
                    possible.append(day)
            if len(possible) == 1:
                return possible[0], 80
    except ValueError:
        pass
    raise StatementError('Data inválida ou ano ambíguo; confira o período e o documento.')


def monetary(value: object) -> Decimal:
    text = str(value if value is not None else '').strip()
    if not text or text in {'-', '—'}:
        raise StatementError('Valor monetário ausente.')
    try:
        result = parse_br_number(text)
        if result != result.quantize(Decimal('.01')) or abs(result) >= Decimal('10000000000000000'):
            raise ValueError()
        return result
    except (ValueError, ArithmeticError):
        raise StatementError('Valor monetário inválido ou com precisão incompatível.') from None


def add_row(source: ParsedSource, location: str, day: date, amount: Decimal, direction: str,
            description: str, scores: tuple[int, int, int], reference: str = '', reference_kind: str = 'none') -> None:
    description = re.sub(r'\s+', ' ', description).strip()
    if is_balance(description):
        source.excluded_balances += 1
        return
    if len(source.rows) >= MAX_ROWS:
        raise StatementError('Limite de 5.000 transações por arquivo excedido.')
    try:
        source.rows.append(Candidate(
            id=hashlib.sha256(f'{source.id}:{location}'.encode()).hexdigest()[:32],
            source_id=source.id, format=source.format, location=location,
            date=day, amount=abs(amount), type=direction, description=description,
            quality=dict(zip(('date', 'amount', 'type'), scores)), reference=reference[:200],
            reference_kind=reference_kind,
            currency=source.currency,
        ))
    except ValidationError:
        raise StatementError(f'{location}: campos obrigatórios ausentes ou inválidos.') from None


def tag(text: str, name: str) -> str:
    match = re.search(rf'<{name}>\s*([^<\r\n]*)', text, re.I)
    return match[1].strip() if match else ''


def parse_ofx(source: ParsedSource, raw: bytes) -> None:
    text = decode(raw)
    if '<!DOCTYPE' in text.upper() or '<!ENTITY' in text.upper():
        raise StatementError('Declarações externas não são permitidas em OFX.')
    accounts = re.findall(r'<BANKACCTFROM>(.*?)</BANKACCTFROM>', text, re.I | re.S)
    if len(accounts) != 1:
        raise StatementError('O OFX deve conter exatamente uma conta bancária.')
    account = accounts[0]
    source.bank_code = digits(tag(account, 'BANKID')).zfill(3)
    source.agency, source.account = digits(tag(account, 'BRANCHID')), digits(tag(account, 'ACCTID'))
    if source.bank_code == '033' and not source.agency:
        combined = re.sub(r'\D', '', tag(account, 'ACCTID'))
        if len(combined) == 13:
            source.agency, source.account = digits(combined[:4]), digits(combined[4:])
    currency = tag(text, 'CURDEF')
    if currency and currency not in {'BRL', 'BRC'}:
        raise StatementError('O processamento financeiro aceita apenas extratos em BRL.')
    source.currency = currency or 'BRL'
    records = re.findall(r'<STMTTRN>(.*?)</STMTTRN>', text, re.I | re.S)
    if not records or len(records) != len(re.findall(r'<STMTTRN>', text, re.I)):
        raise StatementError('OFX sem movimentações ou com registros incompletos.')
    for index, record in enumerate(records, 1):
        try:
            day = datetime.strptime(tag(record, 'DTPOSTED')[:8], '%Y%m%d').date()
        except ValueError:
            raise StatementError(f'OFX registro {index}: data inválida.') from None
        amount = monetary(tag(record, 'TRNAMT'))
        kind = tag(record, 'TRNTYPE').upper()
        direction = 'saida' if amount < 0 else 'entrada'
        if kind in {'DEBIT', 'CREDIT'}:
            direction = 'saida' if kind == 'DEBIT' else 'entrada'
            if (direction == 'saida' and amount > 0) or (direction == 'entrada' and amount < 0):
                raise StatementError(f'OFX registro {index}: tipo e sinal do valor divergem.')
        elif amount == 0:
            raise StatementError(f'OFX registro {index}: tipo indefinido para valor zero.')
        description = ' '.join(dict.fromkeys(t for t in (tag(record, 'MEMO'), tag(record, 'NAME')) if t))
        reference = tag(record, 'FITID')
        add_row(source, f'registro {index}', day, amount, direction, description,
                (100, 100 if source.currency == 'BRL' else 0, 100 if kind in {'DEBIT', 'CREDIT'} else 95), reference,
                'fitid' if reference else 'none')


ALIASES = {
    'data': 'date', 'date': 'date', 'data lancamento': 'date',
    'descricao': 'description', 'historico': 'description', 'description': 'description',
    'valor': 'amount', 'valor (r$)': 'amount', 'amount': 'amount',
    'tipo': 'type', 'type': 'type', 'natureza': 'type',
    'conta_debito': 'debit_account', 'conta_credito': 'credit_account',
    'documento': 'reference', 'fitid': 'fitid', 'credito': 'credit', 'debito': 'debit',
}


def table(source: ParsedSource, rows: list[list], start: date, end: date, *, sheet: str = '') -> None:
    header = None
    for number, values in enumerate(rows, 1):
        if number > 15000 or len(values) > 100:
            raise StatementError('Planilha excede o limite de linhas ou colunas.')
        values = list(values)
        if not any(v is not None and str(v).strip() for v in values):
            continue
        names = [normalized(v) for v in values]
        if 'agencia' in names and 'conta' in names:
            try:
                source.agency = digits(values[names.index('agencia') + 1])
                source.account = digits(values[names.index('conta') + 1])
            except IndexError:
                raise StatementError('Metadados de agência/conta incompletos.') from None
            continue
        mapped = {ALIASES[n]: i for i, n in enumerate(names) if n in ALIASES}
        if {'date', 'description'} <= mapped.keys() and ('amount' in mapped or {'debit', 'credit'} <= mapped.keys()):
            header = mapped
            continue
        if header is None:
            if number > 30:
                raise StatementError('Cabeçalho Data/Descrição/Valor não encontrado nas primeiras 30 linhas.')
            continue
        def cell(key: str):
            index = header.get(key)
            return values[index] if index is not None and index < len(values) else None
        description = str(cell('description') or '').strip()
        if is_balance(description):
            source.excluded_balances += 1
            continue
        location = f'{sheet + " " if sheet else ""}linha {number}'
        try:
            day, date_score = parse_day(cell('date'), start, end)
            # Formula results are not accepted as extracted bank facts.
            if any(isinstance(cell(k), str) and cell(k).startswith('=') for k in header):
                raise StatementError('Células com fórmulas não são aceitas.')
            kind = normalized(cell('type'))
            kinds = {'entrada': 'entrada', 'credito': 'entrada', 'credit': 'entrada', 'c': 'entrada',
                     'saida': 'saida', 'debito': 'saida', 'debit': 'saida', 'd': 'saida'}
            direction = kinds.get(kind)
            if kind and not direction:
                raise StatementError('Tipo de movimentação desconhecido.')
            if 'debit_account' in header and 'credit_account' in header:
                debit, credit = normalized(cell('debit_account')), normalized(cell('credit_account'))
                mapped_kind = 'entrada' if (debit, credit) == ('banco', 'receita') else (
                    'saida' if (debit, credit) == ('despesa', 'banco') else None)
                if mapped_kind is None or (direction and direction != mapped_kind):
                    raise StatementError('Contas de débito/crédito não definem uma direção inequívoca.')
                direction = mapped_kind
            if 'amount' in header:
                amount = monetary(cell('amount'))
            else:
                debit = monetary(cell('debit')) if cell('debit') not in (None, '') else Decimal(0)
                credit = monetary(cell('credit')) if cell('credit') not in (None, '') else Decimal(0)
                if debit < 0 or credit < 0 or bool(debit) == bool(credit):
                    raise StatementError('Preencha apenas uma coluna de crédito ou débito com valor positivo.')
                amount = credit if credit else -debit
                direction = 'entrada' if credit else 'saida'
            if direction == 'entrada' and amount < 0:
                raise StatementError('Tipo de entrada incompatível com valor negativo.')
            type_score = 100 if direction else 95
            if amount == 0 and direction is None:
                raise StatementError('Valor zero exige indicação explícita de entrada/saída.')
            direction = direction or ('saida' if amount < 0 else 'entrada')
            reference = str(cell('fitid') or cell('reference') or '').strip()
            add_row(source, location, day, amount, direction, description,
                    (date_score, 98 if source.format == 'xlsx' else 95, type_score), reference,
                    'fitid' if cell('fitid') else ('document' if reference else 'none'))
        except StatementError as exc:
            raise StatementError(f'{location}: {exc}') from None
    if header is None:
        raise StatementError('Cabeçalho da tabela não reconhecido.')


def parse_xlsx(source: ParsedSource, raw: bytes, start: date, end: date) -> None:
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            infos = archive.infolist()
            if len(infos) > 2000 or sum(i.file_size for i in infos) > 50 * 1024 * 1024:
                raise StatementError('XLSX excede o limite de conteúdo descompactado.')
            if any('vbaProject' in i.filename or '/externalLinks/' in i.filename for i in infos):
                raise StatementError('Macros e vínculos externos não são aceitos.')
        book = openpyxl.load_workbook(io.BytesIO(raw), read_only=True, data_only=False, keep_links=False)
        try:
            populated = [s for s in book if s.max_row and s.max_row > 1]
            if len(populated) != 1:
                raise StatementError('Envie uma planilha com uma única aba de movimentações.')
            sheet = populated[0]
            if sheet.max_row > 15000 or sheet.max_column > 100:
                raise StatementError('Planilha excede o limite de linhas ou colunas.')
            table(source, sheet.iter_rows(values_only=True), start, end, sheet=sheet.title)
        finally:
            book.close()
    except StatementError:
        raise
    except Exception:
        raise StatementError('XLSX inválido, protegido ou incompatível.') from None


def parse_pdf(source: ParsedSource, raw: bytes, start: date, end: date) -> None:
    from .statement_pdf import extract_pdf
    extract_pdf(source, raw, start, end)


def parse_statement(filename: str, raw: bytes, start: date, end: date) -> ParsedSource:
    if not 0 <= (end - start).days <= 365:
        raise StatementError('Período deve conter até 366 dias em ordem cronológica.')
    extension = PurePath(filename).suffix.lower().lstrip('.')
    if extension not in {'pdf', 'csv', 'xlsx', 'ofx'}:
        raise StatementError('Formato não aceito; envie PDF, CSV, XLSX ou OFX.')
    if not raw or len(raw) > MAX_FILE_BYTES:
        raise StatementError('Arquivo vazio ou maior que 10 MiB.')
    digest = hashlib.sha256(raw).hexdigest()
    source = ParsedSource(id=digest[:32], sha256=digest, format=extension,
                          filename=filename.replace('\\', '/').rsplit('/', 1)[-1][:200])
    if extension == 'ofx':
        parse_ofx(source, raw)
    elif extension == 'pdf':
        parse_pdf(source, raw, start, end)
    elif extension == 'xlsx':
        parse_xlsx(source, raw, start, end)
    else:
        text = decode(raw)
        delimiter = ';' if text.splitlines()[0].count(';') > text.splitlines()[0].count(',') else ','
        try:
            table(source, csv.reader(io.StringIO(text, newline=''), delimiter=delimiter, strict=True), start, end)
        except csv.Error:
            raise StatementError('Estrutura CSV inválida.') from None
    if not source.rows:
        raise StatementError('Nenhuma transação válida encontrada no arquivo.')
    if any(not start <= row.date <= end for row in source.rows):
        raise StatementError('Há transações fora do período informado; ajuste o período ou o arquivo.')
    return source
