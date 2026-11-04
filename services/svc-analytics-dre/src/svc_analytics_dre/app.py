from supreme_common.application import domain_app
from .database import Base
from .router import router
from . import projections
def create_app(**kwargs):
    return domain_app('svc-analytics-dre', Base, [router], **kwargs)
app = create_app()
