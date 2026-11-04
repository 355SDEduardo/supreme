from supreme_common.application import domain_app
from .database import Base
from .router import router
from .integration import integration_router, company_access
from fastapi import Depends
router.routes[:] = [r for r in router.routes if r.path not in {'/auth/switch-company-context','/companies/batch/request-documents','/cockpit/companies/summary','/companies/{company_id}/assign-analyst'}]
def create_app(**kwargs):
    app = domain_app('svc-companies', Base, [integration_router, router], **kwargs)
    return app
app = create_app()
