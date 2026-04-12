from huey import SqliteHuey

from app.shared.infrastructure.config import settings

huey = SqliteHuey(filename=settings.huey_db_path)

from app.tasks import scheduled  # noqa: E402, F401
from app.tasks import import_export  # noqa: E402, F401
from app.tasks import stats_tasks  # noqa: E402, F401
from app.tasks import seed_tasks  # noqa: E402, F401
