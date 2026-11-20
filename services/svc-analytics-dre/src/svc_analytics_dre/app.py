from supreme_common.application import domain_app
from .database import Base
from .router import router
from . import models, projections
def create_app(**kwargs):
    # The imports register the ORM tables before the remote schema check.
    assert models.ChartOfAccounts.__tablename__ and projections is not None
    return domain_app('svc-analytics-dre', Base, [router], **kwargs)
app = create_app()
