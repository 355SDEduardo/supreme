"""Role-Based Access Control (RBAC) and Multi-Tenant Isolation."""

from typing import Optional, List
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from .models import User, UserCompanyRole, CompanyTeamAssignment, Company

ROLE_HIERARCHY = {
    "super_admin": 100,
    "supervisor": 80,
    "analyst": 50,
    "bpo_operator": 40,
    "client_admin": 30,
    "client_restricted": 10,
}


def can_user_access_company(db: Session, user: User, target_company_id: str) -> bool:
    """Verifies if user has legitimate access to target_company_id (Strict Cross-Tenant Protection)."""
    # Super admins have full access across the entire organization
    if user.global_role == "super_admin":
        company = db.query(Company).filter(
            Company.id == target_company_id,
            Company.organization_id == user.organization_id
        ).first()
        return company is not None

    # Supervisors have full access within their organization
    if user.global_role == "supervisor":
        company = db.query(Company).filter(
            Company.id == target_company_id,
            Company.organization_id == user.organization_id
        ).first()
        return company is not None

    # Specific company role assigned
    role_assignment = db.query(UserCompanyRole).filter(
        UserCompanyRole.user_id == user.id,
        UserCompanyRole.company_id == target_company_id
    ).first()
    if role_assignment:
        return True

    # Analyst assigned via team assignment
    team_assignment = db.query(CompanyTeamAssignment).filter(
        CompanyTeamAssignment.analyst_user_id == user.id,
        CompanyTeamAssignment.company_id == target_company_id
    ).first()
    if team_assignment:
        return True

    return False


def enforce_company_access(db: Session, user: User, target_company_id: str) -> None:
    """Raises HTTP 403 Forbidden if user lacks access to the company, preventing IDOR leaks."""
    if not can_user_access_company(db, user, target_company_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso negado: você não tem permissão para acessar os dados desta empresa."
        )


def check_role_permission(user_role: str, minimum_required_role: str) -> bool:
    """Checks if user's role meets or exceeds minimum requirement."""
    user_level = ROLE_HIERARCHY.get(user_role, 0)
    required_level = ROLE_HIERARCHY.get(minimum_required_role, 0)
    return user_level >= required_level
