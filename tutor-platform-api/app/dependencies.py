# 過渡用 re-export shim — Phase 9 刪除
from app.identity.api.dependencies import (  # noqa: F401
    get_current_user,
    get_db,
    is_admin,
    require_role,
)
