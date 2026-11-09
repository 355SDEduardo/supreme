"""Tenant-scoped APIs for Pluggy Connect and locally stored bank statements."""

from __future__ import annotations

import asyncio
import hmac
import json
import secrets
from datetime import date, datetime, timedelta, timezone
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError
from supreme_common.auth_context import context, require_role

from .database import get_db
from .open_finance_models import OpenFinanceAccount, OpenFinanceConnection, OpenFinanceTransaction
from .open_finance_schemas import Account, CompleteInput, ConnectInput, Connector, Item, Period, Transaction
from .open_finance_schemas import (
    AccountResponse,
    ConnectionResponse,
    ConnectionStatus,
    ConnectTokenResponse,
    RefreshResponse,
    SyncResponse,
    TransactionPage,
)
from .pluggy_client import MAX_TRANSACTIONS, PRODUCTS, PluggyClient, get_pluggy, invalid_response


def permitted(request: Request) -> None:
    roles = ("super_admin", "supervisor", "analyst", "bpo_operator", "client_user", "service")
    require_role(*roles, *(("viewer",) if request.method == "GET" else ()))


router = APIRouter(
    prefix="/bank-accounts/open-finance",
    tags=["Extratos bancários Open Finance"],
    dependencies=[Depends(permitted)],
)


def now() -> datetime:
    return datetime.now(timezone.utc)


def validated[T: BaseModel](model: type[T], data: object) -> T:
    try:
        return model.model_validate(data)
    except ValidationError:
        raise invalid_response() from None


def scoped(db: Session, model: type):
    claims = context()
    return db.query(model).filter(
        model.organization_id == claims["organization_id"],
        model.company_id == claims["company_id"],
    )


def connection(db: Session, connection_id: UUID, *, active: bool = True) -> OpenFinanceConnection:
    row = scoped(db, OpenFinanceConnection).filter(OpenFinanceConnection.id == str(connection_id)).first()
    if not row:
        raise HTTPException(404, "Conexão não encontrada.")
    if active and row.disconnected_at:
        raise HTTPException(410, "Conexão desconectada.")
    return row


def commit(db: Session) -> None:
    try:
        db.commit()
    except (IntegrityError, StaleDataError):
        db.rollback()
        raise HTTPException(
            409, "Conexão modificada por outra operação; consulte o estado e tente novamente."
        ) from None


def supported(connector: Connector, provider: PluggyClient) -> bool:
    return (
        connector.isOpenFinance
        and connector.country == "BR"
        and connector.type in {"PERSONAL_BANK", "BUSINESS_BANK"}
        and (not connector.isSandbox or provider.settings.allow_sandbox)
        and set(PRODUCTS).issubset(connector.products)
    )


async def remote_item(row: OpenFinanceConnection, provider: PluggyClient, item_id: str | None = None) -> Item:
    identifier = item_id or row.item_id
    if not identifier:
        raise HTTPException(409, "Conclua a conexão do banco antes desta operação.")
    item = validated(Item, await provider.request("GET", f"/items/{identifier}"))
    if str(item.id) != identifier:
        raise invalid_response()
    if not item.clientUserId or not hmac.compare_digest(
        item.clientUserId.encode(), row.client_user_id.encode()
    ):
        raise HTTPException(403, "O Item não pertence a esta sessão de conexão.")
    if item.connector.id != row.connector_id or not supported(item.connector, provider):
        raise HTTPException(422, "A conexão deve usar o banco Open Finance selecionado.")
    if not set(item.products).issubset(PRODUCTS):
        raise HTTPException(422, "A conexão deve coletar somente ACCOUNTS e TRANSACTIONS.")
    return item


def summary(row: OpenFinanceConnection) -> dict:
    return {
        "id": row.id,
        "item_id": row.item_id,
        "connector_id": row.connector_id,
        "connector_name": row.connector_name,
        "status": "disconnected" if row.disconnected_at else ("connected" if row.item_id else "pending"),
        "synced_at": row.synced_at,
        "source_updated_at": row.source_updated_at,
        "date_from": row.period_start,
        "date_to": row.period_end,
    }


async def issue_token(row: OpenFinanceConnection, provider: PluggyClient) -> dict:
    options = {
        "clientUserId": row.client_user_id,
        "products": PRODUCTS,
        # Deduplication is local/tenant-scoped. Global Pluggy deduplication can reuse another tenant's Item.
        "avoidDuplicates": False,
    }
    body: dict = {"options": options}
    if row.item_id:
        body["itemId"] = row.item_id
    data = await provider.request("POST", "/connect_token", json=body)
    token = data.get("accessToken")
    if not isinstance(token, str) or not 1 <= len(token) <= 32768:
        raise invalid_response()
    return {
        "connection_id": row.id,
        "access_token": token,
        "expires_at": row.expires_at,
        "widget_options": {
            "connectorIds": [row.connector_id],
            "selectedConnectorId": row.connector_id,
            "products": PRODUCTS,
            "countries": ["BR"],
            "includeSandbox": provider.settings.allow_sandbox,
            **({"updateItem": row.item_id} if row.item_id else {}),
        },
    }


@router.get("/connectors", response_model=list[Connector])
async def connectors(provider: PluggyClient = Depends(get_pluggy)) -> list[dict]:
    rows = await provider.list_all(
        "/connectors",
        {
            "countries": "BR",
            "types": "PERSONAL_BANK,BUSINESS_BANK",
            "isOpenFinance": "true",
            "sandbox": str(provider.settings.allow_sandbox).lower(),
        },
        limit=2000,
    )
    result = []
    for raw in rows:
        connector = validated(Connector, raw)
        if supported(connector, provider):
            result.append(connector.model_dump())
    return result


@router.post(
    "/connect-token", status_code=201, response_model=ConnectTokenResponse, response_model_exclude_none=True
)
async def connect_token(
    payload: ConnectInput,
    db: Session = Depends(get_db),
    provider: PluggyClient = Depends(get_pluggy),
) -> dict:
    connector = validated(Connector, await provider.request("GET", f"/connectors/{payload.connector_id}"))
    if connector.id != payload.connector_id or not supported(connector, provider):
        raise HTTPException(422, "Selecione um banco brasileiro Open Finance com contas e transações.")
    claims = context()
    row = OpenFinanceConnection(
        id=str(uuid4()),
        organization_id=claims["organization_id"],
        company_id=claims["company_id"],
        user_id=claims["sub"],
        client_user_id=secrets.token_urlsafe(32),
        connector_id=connector.id,
        connector_name=connector.name,
        expires_at=(now() + timedelta(minutes=30)).isoformat(),
    )
    result = await issue_token(row, provider)
    db.add(row)
    commit(db)
    return result


@router.post("/connections/{connection_id}/complete", response_model=ConnectionResponse)
async def complete(
    connection_id: UUID,
    payload: CompleteInput,
    db: Session = Depends(get_db),
    provider: PluggyClient = Depends(get_pluggy),
) -> dict:
    row = connection(db, connection_id)
    if row.user_id != context()["sub"]:
        raise HTTPException(403, "Somente o usuário que iniciou a conexão pode concluí-la.")
    if row.item_id:
        if row.item_id != str(payload.item_id):
            raise HTTPException(409, "A sessão já está vinculada a outro Item.")
        return summary(row)
    if datetime.fromisoformat(row.expires_at) <= now():
        raise HTTPException(410, "Sessão de conexão expirada; inicie uma nova conexão.")
    item = await remote_item(row, provider, str(payload.item_id))
    row.item_id = str(item.id)
    commit(db)
    return summary(row)


@router.get("/connections", response_model=list[ConnectionResponse])
def connections(
    db: Session = Depends(get_db), offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100)
) -> list[dict]:
    rows = scoped(db, OpenFinanceConnection).filter(OpenFinanceConnection.item_id.is_not(None))
    return [summary(row) for row in rows.order_by(OpenFinanceConnection.id).offset(offset).limit(limit)]


@router.get("/connections/{connection_id}", response_model=ConnectionStatus)
async def connection_status(
    connection_id: UUID,
    db: Session = Depends(get_db),
    provider: PluggyClient = Depends(get_pluggy),
) -> dict:
    row = connection(db, connection_id, active=False)
    result = summary(row)
    if row.item_id and not row.disconnected_at:
        item = await remote_item(row, provider)
        result.update(
            provider_status=item.status,
            execution_status=item.executionStatus,
            consent_expires_at=item.consentExpiresAt,
            last_updated_at=item.lastUpdatedAt,
        )
    return result


@router.post("/connections/{connection_id}/connect-token", response_model=ConnectTokenResponse)
async def reconnect_token(
    connection_id: UUID,
    db: Session = Depends(get_db),
    provider: PluggyClient = Depends(get_pluggy),
) -> dict:
    row = connection(db, connection_id)
    await remote_item(row, provider)
    row.expires_at = (now() + timedelta(minutes=30)).isoformat()
    result = await issue_token(row, provider)
    commit(db)
    return result


@router.post("/connections/{connection_id}/refresh", status_code=202, response_model=RefreshResponse)
async def refresh(
    connection_id: UUID,
    db: Session = Depends(get_db),
    provider: PluggyClient = Depends(get_pluggy),
) -> dict:
    row = connection(db, connection_id)
    await remote_item(row, provider)
    # PATCH starts an asynchronous bank fetch. It does not mean an updated statement is ready.
    item = validated(Item, await provider.request("PATCH", f"/items/{row.item_id}", json={}))
    if str(item.id) != row.item_id:
        raise invalid_response()
    return {"connection_id": row.id, "provider_status": item.status, "execution_status": item.executionStatus}


async def collect(row: OpenFinanceConnection, period: Period, provider: PluggyClient) -> tuple[Item, list]:
    item = await remote_item(row, provider)
    expires = item.consentExpiresAt
    if expires and (expires.tzinfo is None or expires <= now()):
        raise HTTPException(409, "Consentimento expirado; reconecte o banco.")
    if item.status != "UPDATED" or item.executionStatus != "SUCCESS" or item.statusDetail:
        raise HTTPException(
            409, "A sincronização bancária ainda não está completa; consulte o status da conexão."
        )
    if not set(PRODUCTS).issubset(item.products) or item.lastUpdatedAt is None:
        raise invalid_response()
    raw_accounts = await provider.list_all("/accounts", {"itemId": row.item_id, "type": "BANK"}, limit=100)
    collected, ids, transaction_ids = [], set(), set()
    for raw in raw_accounts:
        account = validated(Account, raw)
        if str(account.itemId) != row.item_id or account.type != "BANK" or account.id in ids:
            raise invalid_response()
        ids.add(account.id)
        raw_transactions = await provider.transactions(
            str(account.id),
            period.date_from.isoformat(),
            period.date_to.isoformat(),
        )
        transactions = []
        for raw_transaction in raw_transactions:
            transaction = validated(Transaction, raw_transaction)
            transaction_day = transaction.date.astimezone(timezone.utc).date()
            if (
                transaction.accountId != account.id
                or not period.date_from <= transaction_day <= period.date_to
            ):
                raise invalid_response()
            if transaction.id in transaction_ids:
                raise invalid_response()
            transaction_ids.add(transaction.id)
            if len(transaction_ids) > MAX_TRANSACTIONS:
                raise HTTPException(422, "Extrato excede 20.000 transações; reduza o período.")
            transactions.append(transaction)
        collected.append((account, transactions))
    # Abort if the provider changed while paging; do not publish a mixed snapshot.
    after = await remote_item(row, provider)
    if (
        after.status != item.status
        or after.executionStatus != item.executionStatus
        or after.lastUpdatedAt != item.lastUpdatedAt
        or after.statusDetail
    ):
        raise HTTPException(409, "O banco foi atualizado durante a leitura; sincronize novamente.")
    return item, collected


@router.post("/connections/{connection_id}/sync", response_model=SyncResponse)
async def sync(
    connection_id: UUID,
    payload: Period,
    db: Session = Depends(get_db),
    provider: PluggyClient = Depends(get_pluggy),
) -> dict:
    row = connection(db, connection_id)
    try:
        async with asyncio.timeout(80):
            item, collected = await collect(row, payload, provider)
    except TimeoutError:
        raise HTTPException(
            504, "Tempo limite da sincronização; reduza o período e tente novamente."
        ) from None
    row.synced_at = now().isoformat()
    row.source_updated_at = item.lastUpdatedAt.isoformat()
    row.period_start, row.period_end = payload.date_from, payload.date_to
    try:
        db.flush()  # Version check before replacing any account/transaction rows.
        previous_accounts = (
            scoped(db, OpenFinanceAccount).filter(OpenFinanceAccount.connection_id == row.id).all()
        )
        previous_ids = [a.id for a in previous_accounts]
        if previous_ids:
            for transaction in (
                scoped(db, OpenFinanceTransaction)
                .filter(OpenFinanceTransaction.account_id.in_(previous_ids))
                .all()
            ):
                db.delete(transaction)
        db.flush()
        for account in previous_accounts:
            db.delete(account)
        db.flush()
        claims = context()
        tenant = {"organization_id": claims["organization_id"], "company_id": claims["company_id"]}
        total = 0
        for account, transactions in collected:
            db.add(
                OpenFinanceAccount(
                    id=str(account.id),
                    connection_id=row.id,
                    name=account.name,
                    number=account.number,
                    balance=str(account.balance),
                    currency_code=account.currencyCode,
                    **tenant,
                )
            )
            db.flush()
            for transaction in transactions:
                db.add(
                    OpenFinanceTransaction(
                        id=str(transaction.id),
                        account_id=str(account.id),
                        transaction_date=transaction.date.astimezone(timezone.utc).date(),
                        data=transaction.model_dump_json(),
                        **tenant,
                    )
                )
            total += len(transactions)
        commit(db)
    except (IntegrityError, StaleDataError):
        db.rollback()
        raise HTTPException(409, "Conflito ao armazenar o extrato; sincronize novamente.") from None
    return {**summary(row), "accounts": len(collected), "transactions": total}


@router.get("/connections/{connection_id}/accounts", response_model=list[AccountResponse])
def accounts(connection_id: UUID, db: Session = Depends(get_db)) -> list[dict]:
    row = connection(db, connection_id)
    if not row.synced_at:
        raise HTTPException(409, "Sincronize a conexão para consultar as contas e extratos locais.")
    return [
        {
            "id": a.id,
            "connection_id": row.id,
            "name": a.name,
            "number": a.number,
            "balance": a.balance,
            "currency_code": a.currency_code,
            "synced_at": row.synced_at,
            "date_from": row.period_start,
            "date_to": row.period_end,
        }
        for a in scoped(db, OpenFinanceAccount)
        .filter(OpenFinanceAccount.connection_id == row.id)
        .order_by(OpenFinanceAccount.id)
    ]


@router.get("/accounts/{account_id}/transactions", response_model=TransactionPage)
def transactions(
    account_id: UUID,
    date_from: date,
    date_to: date,
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> dict:
    try:
        period = Period(date_from=date_from, date_to=date_to)
    except ValidationError:
        raise HTTPException(422, "Período inválido; informe até 366 dias em ordem cronológica.") from None
    account = scoped(db, OpenFinanceAccount).filter(OpenFinanceAccount.id == str(account_id)).first()
    if not account:
        raise HTTPException(404, "Conta não encontrada.")
    row = connection(db, UUID(account.connection_id))
    if not row.synced_at or period.date_from < row.period_start or period.date_to > row.period_end:
        raise HTTPException(409, "Período fora do extrato local; sincronize o período solicitado.")
    query = scoped(db, OpenFinanceTransaction).filter(
        OpenFinanceTransaction.account_id == account.id,
        OpenFinanceTransaction.transaction_date >= period.date_from,
        OpenFinanceTransaction.transaction_date <= period.date_to,
    )
    total = query.count()
    rows = (
        query.order_by(OpenFinanceTransaction.transaction_date, OpenFinanceTransaction.id)
        .offset(offset)
        .limit(limit)
    )
    return {
        "account_id": account.id,
        "date_from": period.date_from,
        "date_to": period.date_to,
        "synced_at": row.synced_at,
        "source_updated_at": row.source_updated_at,
        "total": total,
        "offset": offset,
        "limit": limit,
        "results": [json.loads(t.data) for t in rows],
    }


@router.delete("/connections/{connection_id}", status_code=204)
async def disconnect(
    connection_id: UUID,
    db: Session = Depends(get_db),
    provider: PluggyClient = Depends(get_pluggy),
) -> Response:
    row = connection(db, connection_id, active=False)
    if row.disconnected_at:
        return Response(status_code=204)
    if row.item_id:
        try:
            await remote_item(row, provider)
            data = await provider.request("DELETE", f"/items/{row.item_id}")
            if data.get("count") != 1:
                raise invalid_response()
        except HTTPException as exc:
            if exc.status_code != 404:
                raise
    row.disconnected_at = now().isoformat()
    commit(db)
    return Response(status_code=204)
