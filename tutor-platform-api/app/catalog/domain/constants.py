"""Catalog bounded-context domain constants.

Values here are business rules that belong to the catalog domain, not infra
knobs. Infrastructure-level tunables (pool sizes, upload caps, rate limits,
JWT expiry) live in `app.shared.infrastructure.config.Settings`.
"""

# Default cap on concurrently active students a tutor can accept when the
# tutor has not explicitly set their own `max_students`.
DEFAULT_MAX_STUDENTS_PER_TUTOR: int = 5
