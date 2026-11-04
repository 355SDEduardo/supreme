from datetime import date, timedelta
from decimal import Decimal
from .projections import BillProjection, AccountProjection
from .dre_engine import calculate_dre_structure
from .cashflow_engine import calculate_daily_cash_flow
from .kpi_engine import calculate_financial_kpis
from .schemas import DreResponse, CashFlowResponse, KpisResponse
from supreme_common.competence import normalize_competencia

ZERO = Decimal('0')

def period(competence):
    start = date.fromisoformat(normalize_competencia(competence) + '-01')
    end = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
    return start, end

def figures(db, company_id, competence):
    start, end = period(competence)
    bills = db.query(BillProjection).filter(BillProjection.company_id == company_id,
        BillProjection.issue_date >= start, BillProjection.issue_date < end,
        BillProjection.status.notin_(['canceled','rejected','draft'])).all()
    def amount(category):
        return sum((b.amount for b in bills if b.category == category), ZERO)
    revenue = sum((b.amount for b in bills if b.type == 'receivable' and b.category != 'financial_revenue'), ZERO)
    opex = sum((b.amount for b in bills if b.type == 'payable' and b.category not in {'sales_deductions','cogs','financial_expense'}), ZERO)
    return calculate_dre_structure(revenue, amount('sales_deductions'), amount('cogs'), opex,
                                  amount('financial_revenue'), amount('financial_expense'))

def get_company_dre(db, company_id, competence):
    data = figures(db, company_id, competence)
    return DreResponse(company_id=company_id, competence=competence,
        **{key: data[key] for key in DreResponse.model_fields if key not in {'company_id','competence'}})

def get_company_cash_flow(db, company_id, days_forward=30):
    today = date.today()
    balances = db.query(AccountProjection).filter(AccountProjection.company_id == company_id).all()
    initial = sum((a.balance for a in balances), ZERO)
    bills = db.query(BillProjection).filter(BillProjection.company_id == company_id,
        BillProjection.status.in_(['approved','scheduled','pending_approval'])).all()
    entries = []
    for index in range(days_forward):
        when = today + timedelta(days=index)
        due = [b for b in bills if max(b.due_date, today) == when]
        entries.append({'date': when, 'inflows_realized': ZERO, 'outflows_realized': ZERO,
            'inflows_projected': sum((b.amount for b in due if b.type == 'receivable'), ZERO),
            'outflows_projected': sum((b.amount for b in due if b.type == 'payable'), ZERO)})
    data = calculate_daily_cash_flow(initial, entries)
    return CashFlowResponse(company_id=company_id, **data)

def get_company_kpis(db, company_id, competence):
    data = figures(db, company_id, competence)
    bills = db.query(BillProjection).filter(BillProjection.company_id == company_id,
        BillProjection.status.in_(['approved','scheduled','pending_approval'])).all()
    receivables = sum((b.amount for b in bills if b.type == 'receivable'), ZERO)
    payables = sum((b.amount for b in bills if b.type == 'payable'), ZERO)
    cash = sum((a.balance for a in db.query(AccountProjection).filter(AccountProjection.company_id == company_id)), ZERO)
    ratios = calculate_financial_kpis(receivables, data['gross_revenue'], payables,
        sum((b.amount for b in bills if b.type == 'payable'), ZERO), ZERO,
        Decimal(str(data['gross_margin_pct'])), cash + receivables, payables, Decimal(str(data['net_income'])))
    return KpisResponse(company_id=company_id, competence=competence, **ratios)
