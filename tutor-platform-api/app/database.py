# 過渡用 re-export shim — Phase 9 刪除
from app.shared.infrastructure.database import (  # noqa: F401
    close_pool,
    get_connection,
    get_db,
    init_pool,
    release_connection,
)
