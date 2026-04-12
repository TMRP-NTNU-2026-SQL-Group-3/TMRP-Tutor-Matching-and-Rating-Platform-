"""
⚠️ DEPRECATED：本套件為 DDD 重構前的舊路由實作，已不被 app/main.py 載入。

新的 router 位置：
  app/identity/api/router.py        （原 routers/auth.py）
  app/catalog/api/tutor_router.py   （原 routers/tutors.py）
  app/catalog/api/student_router.py （原 routers/students.py）
  app/catalog/api/subject_router.py （原 routers/subjects.py）
  app/matching/api/router.py        （原 routers/matches.py）
  app/teaching/api/session_router.py（原 routers/sessions.py）
  app/teaching/api/exam_router.py   （原 routers/exams.py）
  app/review/api/router.py          （原 routers/reviews.py）
  app/messaging/api/router.py       （原 routers/messages.py）
  app/analytics/api/router.py       （原 routers/stats.py）
  app/admin/api/router.py           （原 routers/admin.py）
  app/shared/api/health_router.py   （原 routers/health.py）

⚠️ 修改本目錄的程式碼【不會生效】，請改修對應的 BC 路由。
   tests/ 仍 patch 此處模組做為單元測試的隔離點，
   完整移除前需先遷移測試（見 docs/ddd-migration-spec.md）。

Bug #15 (systematic-bug-audit.md): 死碼仍保留是為了讓既有測試套件可運行；
未來於測試遷移完成後移除整個套件。
"""
import warnings

warnings.warn(
    "app.routers is deprecated and not wired into app/main.py. "
    "Edit the corresponding app/<bc>/api/*_router.py instead.",
    DeprecationWarning,
    stacklevel=2,
)
