from app.catalog.domain.ports import ISubjectRepository
from app.shared.infrastructure.base_repository import BaseRepository


class PostgresSubjectRepository(BaseRepository, ISubjectRepository):
    def list_subject_ids(self) -> set[int]:
        rows = self.fetch_all("SELECT subject_id FROM subjects")
        return {r["subject_id"] for r in rows}
