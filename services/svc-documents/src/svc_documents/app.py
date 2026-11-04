from supreme_common.application import domain_app
from .database import Base
from .router import router
def create_app(**kwargs):
    return domain_app('svc-documents', Base, [router], **kwargs)
app = create_app()
