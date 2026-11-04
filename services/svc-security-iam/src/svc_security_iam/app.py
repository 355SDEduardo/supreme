from supreme_common.application import domain_app
from .database import Base
from .router import router, cert_router
from .auth import auth_router, mfa_router
router.routes[:] = [route for route in router.routes if '/mfa/' not in route.path]
def create_app(**kwargs):
    return domain_app('svc-security-iam', Base, [auth_router, mfa_router, router, cert_router], **kwargs)
app = create_app()
