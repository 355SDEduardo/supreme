"""Brazilian dynamic tax calendar engine, factoring in business days and holidays."""
from datetime import date, timedelta
from typing import Set, Tuple


def calculate_easter(year: int) -> date:
    """Meeus/Jones/Butcher algorithm for Easter Sunday (Páscoa)."""
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def get_brazilian_national_holidays(year: int) -> Set[date]:
    """Returns set of all Brazilian national fixed and mobile holidays for a given year."""
    holidays = {
        date(year, 1, 1),    # Confraternização Universal
        date(year, 4, 21),   # Tiradentes
        date(year, 5, 1),    # Dia do Trabalho
        date(year, 9, 7),    # Independência do Brasil
        date(year, 10, 12),  # N. Sra. Aparecida
        date(year, 11, 2),   # Finados
        date(year, 11, 15),  # Proclamação da República
        date(year, 11, 20),  # Dia Nacional de Zumbi e da Consciência Negra (Lei 14.759/2023)
        date(year, 12, 25),  # Natal
    }

    # Mobile holidays based on Easter
    easter = calculate_easter(year)
    carnaval_tuesday = easter - timedelta(days=47)
    carnaval_monday = easter - timedelta(days=48)
    good_friday = easter - timedelta(days=2)      # Sexta-feira Santa
    corpus_christi = easter + timedelta(days=60)  # Corpus Christi

    holidays.add(carnaval_monday)
    holidays.add(carnaval_tuesday)
    holidays.add(good_friday)
    holidays.add(corpus_christi)

    return holidays


def is_business_day(d: date) -> bool:
    """Checks if a date is a Monday-Friday and not a national holiday."""
    if d.weekday() >= 5:  # 5 = Saturday, 6 = Sunday
        return False
    holidays = get_brazilian_national_holidays(d.year)
    return d not in holidays


def anticipate_to_business_day(d: date) -> date:
    """If date is non-business day, shift to the immediately preceding business day."""
    current = d
    while not is_business_day(current):
        current -= timedelta(days=1)
    return current


def postpone_to_business_day(d: date) -> date:
    """If date is non-business day, shift to the immediately subsequent business day."""
    current = d
    while not is_business_day(current):
        current += timedelta(days=1)
    return current


def get_subsequent_month(year: int, month: int) -> Tuple[int, int]:
    """Returns (year, month) for M+1."""
    if month == 12:
        return year + 1, 1
    return year, month + 1


def calculate_tax_due_date(competence_str: str, obligation_code: str) -> date:
    """Calculates legal statutory due date for Brazilian tax obligations according to specific federal rules.
    - competence_str: '2026-09'
    - obligation_code: 'DAS', 'PGDAS_D', 'DCTFWEB', 'REINF', 'ESOCIAL', 'FGTS_DIGITAL', etc.
    """
    year, month = map(int, competence_str.split("-"))
    sub_year, sub_month = get_subsequent_month(year, month)

    code = obligation_code.upper()

    if code in ("DAS", "PGDAS", "PGDAS_D", "DEFIS"):
        # Dia 20 do mês subsequente (se dia não útil, prorroga-se para o 1º dia útil seguinte)
        target = date(sub_year, sub_month, 20)
        return postpone_to_business_day(target)

    elif code in ("DCTFWEB", "EFD_REINF", "REINF", "ESOCIAL"):
        # Dia 15 do mês subsequente (se dia não útil, antecipa-se para o dia útil anterior)
        target = date(sub_year, sub_month, 15)
        return anticipate_to_business_day(target)

    elif code in ("FGTS_DIGITAL", "FGTS"):
        # Dia 20 do mês subsequente (se dia não útil, antecipa-se para o dia útil anterior)
        target = date(sub_year, sub_month, 20)
        return anticipate_to_business_day(target)

    else:
        # Default: dia 15 antecipado
        target = date(sub_year, sub_month, 15)
        return anticipate_to_business_day(target)
