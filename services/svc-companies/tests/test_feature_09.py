"""Unit and Integration Tests for Feature 09: Gestão Multiempresa."""


import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi import HTTPException

from svc_companies.database import Base
from svc_companies.models import Organization, Company, User, UserCompanyRole, CompanyTeamAssignment
from svc_companies.cnpj_validator import validate_cnpj, validate_cpf, validate_tax_id, clean_tax_id
from svc_companies.rbac import can_user_access_company, enforce_company_access
from svc_companies.service import (
    create_company, get_cockpit_summary, execute_batch_document_requests, switch_company_context
)
from svc_companies.schemas import CompanyCreate, BatchRequestDocumentsInput


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    # Seed organization
    org = Organization(id="org-01", name="Escritório Alpha Contabilidade", tax_id="00000000000191")
    session.add(org)
    session.commit()

    yield session
    session.close()


def test_cnpj_and_cpf_validation():
    """Validates modulo 11 check digits for Brazilian CNPJ and CPF and dummy rejection."""
    # Valid real CNPJ: 11.222.333/0001-81 -> 11222333000181
    # Check: 11222333000181
    assert validate_cnpj("11222333000181") is True
    assert validate_cnpj("11.222.333/0001-81") is True

    # Invalid check digits
    assert validate_cnpj("11222333000182") is False

    # Dummy repeated sequence
    assert validate_cnpj("00000000000000") is False
    assert validate_cnpj("11111111111111") is False

    # Valid CPF: e.g. 52998224725
    assert validate_cpf("52998224725") is True
    assert validate_cpf("52998224720") is False
    assert validate_cpf("00000000000") is False


def test_company_creation_with_cnpj_validation(db_session):
    """Ensures company registration succeeds with valid CNPJ and fails with invalid."""
    valid_data = CompanyCreate(
        organization_id="org-01",
        corporate_name="Empresa Modelo Ltda",
        tax_id="11.222.333/0001-81",
        tax_regime="simples_nacional"
    )
    comp = create_company(db_session, valid_data)
    assert comp.id is not None
    assert comp.tax_id == "11222333000181"

    # Attempt invalid CNPJ
    invalid_data = CompanyCreate(
        organization_id="org-01",
        corporate_name="Empresa Falsa Ltda",
        tax_id="11.222.333/0001-99",  # Invalid DV
        tax_regime="simples_nacional"
    )
    with pytest.raises(HTTPException) as exc:
        create_company(db_session, invalid_data)
    assert exc.value.status_code == 400


def test_cross_tenant_isolation_and_rbac(db_session):
    """Validates that analysts cannot access companies outside their assigned portfolio (IDOR prevention)."""
    # Create two companies
    comp_a = Company(
        id="comp-a", organization_id="org-01", corporate_name="Empresa A",
        tax_id="11222333000181", tax_regime="simples_nacional"
    )
    comp_b = Company(
        id="comp-b", organization_id="org-01", corporate_name="Empresa B",
        tax_id="22333444000199", tax_regime="lucro_presumido"
    )
    db_session.add_all([comp_a, comp_b])

    # Analyst assigned only to Empresa A
    analyst = User(
        id="user-analyst-1", organization_id="org-01", full_name="Analista Junior",
        email="analista@alpha.com", hashed_password="pwd", global_role="analyst"
    )
    db_session.add(analyst)
    db_session.commit()

    assignment = CompanyTeamAssignment(
        company_id="comp-a", analyst_user_id="user-analyst-1", department="fiscal"
    )
    db_session.add(assignment)
    db_session.commit()

    # Analyst can access Company A
    assert can_user_access_company(db_session, analyst, "comp-a") is True

    # Analyst CANNOT access Company B (must be blocked)
    assert can_user_access_company(db_session, analyst, "comp-b") is False
    with pytest.raises(HTTPException) as exc:
        enforce_company_access(db_session, analyst, "comp-b")
    assert exc.value.status_code == 403


def test_cockpit_summary_aggregation(db_session):
    """Tests executive cockpit aggregation across client portfolio."""
    c1 = Company(id="c1", organization_id="org-01", corporate_name="C1", tax_id="111", tax_regime="simples_nacional")
    c2 = Company(id="c2", organization_id="org-01", corporate_name="C2", tax_id="222", tax_regime="lucro_real")
    db_session.add_all([c1, c2])
    db_session.commit()

    summary = get_cockpit_summary(db_session, "org-01")
    assert summary.total_companies >= 2
    assert summary.active_companies >= 2
    assert "simples_nacional" in summary.by_tax_regime


def test_resilient_batch_operations(db_session):
    """Validates partial-failure resilience in batch operations."""
    c_active = Company(id="c-act", organization_id="org-01", corporate_name="Ativa", tax_id="111", status="active")
    c_suspended = Company(id="c-susp", organization_id="org-01", corporate_name="Suspensa", tax_id="222", status="suspended")
    db_session.add_all([c_active, c_suspended])
    db_session.commit()

    batch_input = BatchRequestDocumentsInput(
        organization_id="org-01",
        competence="2026-09"
    )
    result = execute_batch_document_requests(db_session, batch_input)
    assert result.total_requested >= 2
    assert result.success_count >= 1
    assert result.failed_count >= 1
    assert len(result.errors) >= 1
    assert "Suspensa" in result.errors[0]["error"]


def test_switch_company_context(db_session):
    """Validates switching company context and JWT issuance."""
    c1 = Company(id="c-active-switch", organization_id="org-01", corporate_name="Alpha Clientes", tax_id="111")
    admin = User(
        id="user-admin-switch", organization_id="org-01", full_name="Admin",
        email="admin@alpha.com", hashed_password="pwd", global_role="super_admin"
    )
    db_session.add_all([c1, admin])
    db_session.commit()

    res = switch_company_context(db_session, admin, "c-active-switch")
    assert res.active_company_id == "c-active-switch"
    assert res.new_token is not None
    assert len(res.new_token.split(".")) == 3
