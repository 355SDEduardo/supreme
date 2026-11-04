from sqlalchemy.orm import declarative_base
from supreme_common.database import request_db
Base = declarative_base()
def get_db():
    yield from request_db()
