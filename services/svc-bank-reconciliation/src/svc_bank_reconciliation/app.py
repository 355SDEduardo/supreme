from __future__ import annotations

from supreme_common.application import domain_app
from .database import Base
from .router import router
from .integration import integration_router
from .open_finance import router as open_finance_router
from .pluggy_configuration import router as pluggy_configuration_router
router.routes[:] = [r for r in router.routes if r.path not in {'/reconciliations/suggest','/reconciliations/confirm'}]
def create_app(**kwargs):
    return domain_app('svc-bank-reconciliation', Base, [pluggy_configuration_router, open_finance_router, integration_router, router], **kwargs)
app = create_app()
