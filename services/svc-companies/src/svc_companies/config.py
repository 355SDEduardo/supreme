import os
from types import SimpleNamespace
settings = SimpleNamespace(
    STORAGE_DIR=os.getenv('DOCUMENT_UPLOADS_DIR', './data/storage/uploads'),
    MASTER_ENCRYPTION_KEY=os.getenv('MASTER_ENCRYPTION_KEY', ''),
)
