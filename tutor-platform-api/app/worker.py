from huey import SqliteHuey

huey = SqliteHuey(filename="data/huey.db")

from app.tasks import scheduled  # noqa: E402, F401
from app.tasks import import_export  # noqa: E402, F401
from app.tasks import stats_tasks  # noqa: E402, F401
from app.tasks import seed_tasks  # noqa: E402, F401
