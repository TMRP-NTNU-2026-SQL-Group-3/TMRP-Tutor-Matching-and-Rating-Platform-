"""Single source of truth for teaching-domain enumerations.

The `exam_type` CHECK constraint in `init_db.py` is generated from this
tuple so the Pydantic validator and the database constraint cannot drift.
"""

# Keep values aligned with the frontend <select> options in
# src/views/tutor/MatchDetailView.vue — the strings are user-facing labels.
EXAM_TYPES: tuple[str, ...] = ("段考", "小考", "模擬考", "其他")
