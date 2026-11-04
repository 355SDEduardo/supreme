"""Shared test resources; never connect integration tests to the local database."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from portalcontabilidades.app import create_app
from portalcontabilidades.core.database import Base, get_db


@pytest.fixture
def database_engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def db_session(database_engine):
    with Session(database_engine) as session:
        yield session


@pytest.fixture
def client(database_engine, db_session):
    application = create_app(database_engine=database_engine)

    def override_get_db():
        yield db_session

    application.dependency_overrides[get_db] = override_get_db
    with TestClient(application) as test_client:
        yield test_client
