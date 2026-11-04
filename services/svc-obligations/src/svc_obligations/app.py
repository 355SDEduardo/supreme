from supreme_common.application import domain_app
from .database import Base
from .router import router
from .integration import integration_router
router.routes[:] = [r for r in router.routes if r.path not in {'/tasks/generate-competence','/tasks/{task_id}/attachments'}]
def create_app(**kwargs):
    return domain_app('svc-obligations', Base, [integration_router, router], **kwargs)
app = create_app()
