import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from svc_security_iam.database import Base
from svc_security_iam import models
@pytest.fixture
def database_engine():
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()
@pytest.fixture
def db_session(database_engine):
    with Session(database_engine) as session:
        yield session
