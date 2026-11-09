from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StrictBool, model_validator

Money = Annotated[Decimal, Field(allow_inf_nan=False, max_digits=28, decimal_places=8)]
Currency = Annotated[str, Field(pattern=r"^[A-Z]{3}$")]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ConnectInput(Input):
    connector_id: int = Field(gt=0, strict=True)


class CompleteInput(Input):
    item_id: UUID


class Period(Input):
    date_from: date
    date_to: date

    @model_validator(mode="after")
    def valid_period(self) -> Period:
        if not 0 <= (self.date_to - self.date_from).days <= 365:
            raise ValueError("O período deve ser ordenado e conter no máximo 366 dias.")
        return self


class Connector(BaseModel):
    id: int = Field(gt=0)
    name: str = Field(min_length=1, max_length=200)
    country: str
    type: str
    isOpenFinance: StrictBool
    isSandbox: StrictBool
    products: list[str]


class Item(BaseModel):
    id: UUID
    clientUserId: str | None = None
    connector: Connector
    status: str = Field(max_length=100)
    executionStatus: str = Field(max_length=100)
    products: list[str]
    lastUpdatedAt: AwareDatetime | None = None
    consentExpiresAt: AwareDatetime | None = None
    statusDetail: dict | None = None


class Account(BaseModel):
    id: UUID
    itemId: UUID
    type: str
    name: str = Field(min_length=1, max_length=200)
    number: str = Field(max_length=200)
    balance: Money
    currencyCode: Currency


class Transaction(BaseModel):
    id: UUID
    accountId: UUID
    date: datetime
    description: str = Field(max_length=10000)
    amount: Money
    currencyCode: Currency
    status: Literal["PENDING", "POSTED"]
    type: Literal["DEBIT", "CREDIT"]
    providerId: str | None = Field(default=None, max_length=500)
    balance: Money | None = None

    @model_validator(mode="after")
    def valid_bank_transaction(self) -> Transaction:
        if self.date.tzinfo is None:
            raise ValueError("Data da transação deve conter fuso horário.")
        if (self.type == "DEBIT" and self.amount > 0) or (self.type == "CREDIT" and self.amount < 0):
            raise ValueError("Sinal do valor incompatível com o tipo da transação bancária.")
        return self


class ConnectionResponse(BaseModel):
    id: UUID
    item_id: UUID | None
    connector_id: int
    connector_name: str
    status: Literal["pending", "connected", "disconnected"]
    synced_at: datetime | None
    source_updated_at: datetime | None
    date_from: date | None
    date_to: date | None


class ConnectionStatus(ConnectionResponse):
    provider_status: str | None = None
    execution_status: str | None = None
    consent_expires_at: datetime | None = None
    last_updated_at: datetime | None = None


class WidgetOptions(BaseModel):
    connectorIds: list[int]
    selectedConnectorId: int
    products: list[Literal["ACCOUNTS", "TRANSACTIONS"]]
    countries: list[Literal["BR"]]
    includeSandbox: bool
    updateItem: UUID | None = None


class ConnectTokenResponse(BaseModel):
    connection_id: UUID
    access_token: str
    expires_at: datetime
    widget_options: WidgetOptions


class RefreshResponse(BaseModel):
    connection_id: UUID
    provider_status: str
    execution_status: str


class SyncResponse(ConnectionResponse):
    accounts: int
    transactions: int


class AccountResponse(BaseModel):
    id: UUID
    connection_id: UUID
    name: str
    number: str
    balance: Money
    currency_code: Currency
    synced_at: datetime
    date_from: date
    date_to: date


class TransactionPage(BaseModel):
    account_id: UUID
    date_from: date
    date_to: date
    synced_at: datetime
    source_updated_at: datetime
    total: int
    offset: int
    limit: int
    results: list[Transaction]
