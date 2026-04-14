from huey import SqliteHuey

from app.shared.infrastructure.config import settings
from app.shared.infrastructure.huey_json_serializer import JSONSerializer

# JSONSerializer is passed explicitly so task payloads written to the huey
# SQLite backend are plain JSON. This prevents pickle-based deserialization
# attacks on any reader of the raw payload bytes (e.g. the admin task status
# endpoint).
huey = SqliteHuey(filename=settings.huey_db_path, serializer=JSONSerializer())

from app.tasks import scheduled  # noqa: E402, F401
from app.tasks import import_export  # noqa: E402, F401
from app.tasks import stats_tasks  # noqa: E402, F401
from app.tasks import seed_tasks  # noqa: E402, F401
