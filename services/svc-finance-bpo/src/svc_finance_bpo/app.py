from __future__ import annotations

from supreme_common.application import domain_app
from .database import Base
from .router import router
from .integration import integration_router
from .statement_api import router as statement_router
router.routes[:] = [r for r in router.routes if r.path != '/bills/{bill_id}/dispatch-reminder']
def create_app(**kwargs):
    return domain_app('svc-finance-bpo', Base, [statement_router, integration_router, router], **kwargs)
app = create_app()
