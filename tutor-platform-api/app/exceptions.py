# Bug #16: 過渡用 re-export shim
#
# 目前主程式（app/main.py）只認 app.shared.domain.exceptions 中的 DomainException
# 體系；本檔僅保留舊名稱的別名，讓 app/routers/* 下的舊路由模組（已棄用，
# 詳見 app/routers/__init__.py）仍可匯入。原本檔內重複定義的 *_exception_handler
# 函式並未被任何地方註冊，已移除以消除「兩套錯誤處理器」的混淆。

from app.shared.domain.exceptions import (  # noqa: F401
    ConflictError as ConflictException,
    DomainException as AppException,
    NotFoundError as NotFoundException,
    PermissionDeniedError as ForbiddenException,
)
