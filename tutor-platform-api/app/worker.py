from huey import SqliteHuey

from app.shared.infrastructure.config import settings
from app.shared.infrastructure.huey_json_serializer import JSONSerializer

# JSONSerializer is passed explicitly so task payloads written to the huey
# SQLite backend are plain JSON. This prevents pickle-based deserialization
# attacks on any reader of the raw payload bytes (e.g. the admin task status
# endpoint).
huey = SqliteHuey(filename=settings.huey_db_path, serializer=JSONSerializer())


@huey.on_startup()
def _init_worker_db_pool():
    """Open the psycopg2 connection pool inside each Huey consumer worker.

    The consumer (`huey_consumer app.worker.huey`) runs as its own process,
    separate from the FastAPI app, so the lifespan hook in app.main that calls
    init_pool() never executes here. Without this, every task that calls
    get_connection() fails with "Database pool not initialized" and Huey
    retries it indefinitely. init_pool() is idempotent, so running it once per
    worker thread is safe.
    """
    from app.shared.infrastructure.database import init_pool
    init_pool()


@huey.on_shutdown()
def _close_worker_db_pool():
    """Release pooled connections when the consumer stops."""
    from app.shared.infrastructure.database import close_pool
    close_pool()


from app.tasks import scheduled  # noqa: E402, F401
from app.tasks import import_export  # noqa: E402, F401
from app.tasks import stats_tasks  # noqa: E402, F401
from app.tasks import seed_tasks  # noqa: E402, F401
