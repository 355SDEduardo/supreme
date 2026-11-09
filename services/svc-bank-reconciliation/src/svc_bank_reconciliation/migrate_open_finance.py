"""Add Open Finance and encrypted configuration tables to the service's private database."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from sqlalchemy import Engine, create_engine, inspect
from sqlalchemy.exc import SQLAlchemyError

from .database import Base
from .open_finance_models import OpenFinanceAccount, OpenFinanceConnection, OpenFinanceTransaction
from .pluggy_configuration_store import PluggyConfiguration

TABLES = [
    model.__table__
    for model in (
        OpenFinanceConnection,
        OpenFinanceAccount,
        OpenFinanceTransaction,
        PluggyConfiguration,
    )
]


def missing_tables(engine: Engine) -> list[str]:
    present = set(inspect(engine).get_table_names())
    return [table.name for table in TABLES if table.name not in present]


def upgrade(engine: Engine) -> list[str]:
    missing = missing_tables(engine)
    Base.metadata.create_all(engine, tables=TABLES, checkfirst=True)
    return missing


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Verifica as tabelas sem alterar o banco.")
    args = parser.parse_args()
    path = Path(os.getenv("DB_ROOT_DIR", "./data/db")) / "svc-bank-reconciliation.db"
    url = os.getenv("DATABASE_URL")
    if not url:
        if not path.is_file():
            parser.error("Banco local não encontrado; inicialize o serviço ou configure DATABASE_URL.")
        url = f"sqlite:///{path.resolve().as_posix()}"
    engine = create_engine(url)
    try:
        if args.check:
            missing = missing_tables(engine)
            print("Tabelas ausentes: " + ", ".join(missing) if missing else "Migração Open Finance aplicada.")
            if missing:
                raise SystemExit(1)
        else:
            created = upgrade(engine)
            print("Tabelas criadas: " + ", ".join(created) if created else "Migração já aplicada.")
    except SQLAlchemyError:
        # Database URLs can contain credentials; do not print the underlying exception.
        raise SystemExit("Falha na migração; verifique acesso e configuração do banco do serviço.") from None
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
